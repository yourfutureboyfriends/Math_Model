"""
One rate service for the platform: the 13-week Treasury bill (^IRX, Yahoo), the reference rate for
excess returns (Sharpe, Sortino) and the default remuneration of idle cash in backtests and paper books.

Conventions (one set, used everywhere):
  quote      ^IRX is a discount yield in percent; it is used directly as an annual simple rate (the
             difference from the bond-equivalent yield is a few bp at these maturities)
  daily      annual / 252 per *trading day* — a return series earns one accrual per observed session
  accrue()   the same convention between two dates: the sum of the daily rates of the sessions after
             `from_date` up to and including `to_date`
  as-of      a date takes the latest observation on or before it — never a later one; dates before the
             series starts have no rate (0, and `known()` is False) rather than a borrowed future value
Remuneration is a choice: positive broker cash need not earn the full bill rate (see cash_spread in the
Code Lab cost schema and the paper traders' settings).

Other account currencies (`ccy=`): the currency's own short rate, same conventions —
  * OECD 3-month interbank rates (FRED IR3TIB01xxM156N): monthly averages, usable from the 15th of the
    following month (the month must be over and published — never earlier);
  * EUR / GBP after the OECD series ends: the ECB's €STR / the Bank of England's SONIA (daily, usable the next day);
  * INR, BRL, TRY: the central bank's discount rate (FRED INTDSRxxM193N), where no interbank series is free;
  * HKD, SAR, QAR, AED, BHD, OMR (pegged to the dollar): the US T-bill rate, labelled as a proxy;
  * anything else: unknown — cash earns 0 and `known(ccy)` is False, shown with the result.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)
_cache: dict = {}
TTL = 6 * 3600
DISK = Path(__file__).resolve().parent.parent.parent / "data" / "processed" / "quant" / "rates"
DISK_TTL = 86400

# currency → FRED series, spliced in order (a later series only extends past the earlier one's last observation)
_OECD = lambda c: (f"IR3TIB01{c}M156N", "monthly", "OECD 3-month interbank rate")
CASH_RATES: Dict[str, List[Tuple[str, str, str]]] = {
    "EUR": [_OECD("EZ"), ("ECBESTRVOLWGTTRMDMNRT", "daily", "ECB euro short-term rate (€STR)")],
    "GBP": [_OECD("GB"), ("IUDSOIA", "daily", "Bank of England SONIA")],
    **{ccy: [_OECD(c)] for ccy, c in {
        "JPY": "JP", "CAD": "CA", "AUD": "AU", "CHF": "CH", "SEK": "SE", "NOK": "NO", "DKK": "DK",
        "NZD": "NZ", "KRW": "KR", "CNY": "CN", "ZAR": "ZA", "MXN": "MX", "PLN": "PL", "CZK": "CZ", "HUF": "HU",
        "ILS": "IL", "IDR": "ID", "CLP": "CL", "ISK": "IS"}.items()},
    **{ccy: [(f"INTDSR{c}M193N", "monthly", "central-bank discount rate")] for ccy, c in
       {"INR": "IN", "BRL": "BR", "TRY": "TR"}.items()},
}
USD_PEGS = {"HKD", "SAR", "QAR", "AED", "BHD", "OMR"}
STALE_DAYS = 120          # a rate older than this is still used (as-of) but reported as stale


def _irx() -> Optional[pd.Series]:
    hit = _cache.get("irx")
    if hit and time.time() - hit[0] < TTL:
        return hit[1]
    s = None
    try:
        from api.quant import data as qdata
        got, _ = qdata.load(["^IRX"])
        df = got.get("^IRX")
        if df is not None and len(df) > 100:
            s = df["Close"].astype(float)
            s.index = pd.DatetimeIndex(s.index).tz_localize(None).normalize()
            s = s[(s >= 0) & (s <= 25)]                       # percent; anything else is bad data
    except Exception:                                         # noqa: BLE001 — no network: rate 0
        s = None
    _cache["irx"] = (time.time(), s)
    return s


def _fred(series_id: str) -> Optional[pd.Series]:
    """Observations of a FRED series (percent), cached on disk for a day; a stale copy beats nothing."""
    f = DISK / f"{series_id}.json"
    raw = None
    try:
        if time.time() - f.stat().st_mtime < DISK_TTL:
            raw = json.loads(f.read_text())
    except (OSError, ValueError):
        pass
    if raw is None:
        try:
            import requests
            from api.config import FRED_API_KEY
            if not FRED_API_KEY:
                raise RuntimeError("no FRED key")
            r = requests.get("https://api.stlouisfed.org/fred/series/observations", timeout=30,
                             params={"series_id": series_id, "api_key": FRED_API_KEY, "file_type": "json"})
            r.raise_for_status()
            raw = [(o["date"], o["value"]) for o in r.json().get("observations", [])]
            DISK.mkdir(parents=True, exist_ok=True)
            tmp = f.with_suffix(".tmp")
            tmp.write_text(json.dumps(raw))
            tmp.replace(f)
        except Exception as e:                                # noqa: BLE001 — offline / refused: stale cache or nothing
            logger.warning("[rates] %s unavailable: %s", series_id, str(e)[:120])
            try:
                raw = json.loads(f.read_text())
            except (OSError, ValueError):
                return None
    vals = {d: float(v) for d, v in raw if v not in (".", "", None)}
    if not vals:
        return None
    ser = pd.Series(vals, dtype=float)
    ser.index = pd.DatetimeIndex(pd.to_datetime(ser.index))
    return ser.sort_index()[lambda x: x.abs() < 100]


def _usable_from(ser: pd.Series, freq: str) -> pd.Series:
    """Re-index observations by the first date they could be known: a monthly average from the 15th of the next
    month, a daily fixing from the next day."""
    out = ser.copy()
    out.index = (ser.index + pd.offsets.MonthBegin(1) + pd.Timedelta(days=14)) if freq == "monthly" \
        else ser.index + pd.Timedelta(days=1)
    return out[~out.index.duplicated(keep="last")]


def _ccy_series(ccy: str) -> Tuple[Optional[pd.Series], Dict[str, Any]]:
    """(annual % rate indexed by the date it was known, description) for an account currency."""
    ccy = (ccy or "USD").upper()
    hit = _cache.get(("ccy", ccy))
    if hit and time.time() - hit[0] < TTL:
        return hit[1], hit[2]
    if ccy == "USD" or ccy in USD_PEGS:
        s = _irx()
        info = {"currency": ccy, "source": "US 13-week T-bill (^IRX)",
                "kind": "own" if ccy == "USD" else "proxy",
                "note": None if ccy == "USD" else f"{ccy} is pegged to the dollar: the US T-bill rate is used as its cash rate"}
    elif ccy in CASH_RATES:
        parts, used = [], []
        for sid, freq, label in CASH_RATES[ccy]:
            ser = _fred(sid)
            if ser is None or ser.empty:
                continue
            ser = _usable_from(ser, freq)
            if parts:
                ser = ser[ser.index > parts[-1].index[-1]]
            if len(ser):
                parts.append(ser)
                used.append(f"{label} (FRED {sid})")
        s = pd.concat(parts).sort_index() if parts else None
        info = {"currency": ccy, "source": " then ".join(used) or None, "kind": "own" if parts else None,
                "note": None if parts else f"No free {ccy} short-rate history could be loaded"}
    else:
        s = None
        info = {"currency": ccy, "source": None, "kind": None,
                "note": f"No free {ccy} short-rate series: cash earns 0 and Sharpe is on raw returns"}
    if s is not None and not s.empty:
        info["first"], info["last_known"] = str(s.index[0].date()), str(s.index[-1].date())
    _cache[("ccy", ccy)] = (time.time(), s, info)
    return s, info


def describe(ccy: str = "USD") -> Dict[str, Any]:
    """Where an account currency's cash rate comes from (shown with results)."""
    s, info = _ccy_series(ccy)
    out = dict(info)
    out["known"] = s is not None and not s.empty
    if out["known"] and (pd.Timestamp.today() - s.index[-1]).days > STALE_DAYS:
        out["stale_since"] = str(s.index[-1].date())
    return out


def known(ccy: str = "USD") -> bool:
    """Whether the reference rate is available at all (UI flags results computed without it)."""
    s = _irx() if (ccy or "USD").upper() == "USD" else _ccy_series(ccy)[0]
    return s is not None and not s.empty


def daily(index: Sequence, ccy: str = "USD") -> pd.Series:
    """Daily reference rate (decimal per trading day) for each date, as of that date; 0 where unknown.
    `ccy`: the account currency's own short rate (see module docstring)."""
    idx = pd.DatetimeIndex(pd.to_datetime(list(index))).normalize()
    s = _irx() if (ccy or "USD").upper() == "USD" else _ccy_series(ccy)[0]
    if s is None or s.empty:
        return pd.Series(0.0, index=idx)
    asof = s.reindex(s.index.union(idx)).ffill().reindex(idx)        # latest observation on or before each date
    return (asof / 100 / 252).fillna(0.0)


def annual(start: str, end: str, ccy: str = "USD") -> float:
    """Average annual reference rate (decimal) over [start, end], from observations in that interval; if
    none, the latest observation on or before `start`; never a later one."""
    s = _irx() if (ccy or "USD").upper() == "USD" else _ccy_series(ccy)[0]
    if s is None or s.empty:
        return 0.0
    w = s[(s.index >= pd.Timestamp(start)) & (s.index <= pd.Timestamp(end))]
    if len(w):
        return float(w.mean() / 100)
    before = s[s.index <= pd.Timestamp(start)]
    return float(before.iloc[-1] / 100) if len(before) else 0.0


def accrue(cash: float, from_date: str, to_date: str, borrow_spread: float = 0.01, cash_spread: float = 0.0,
           ccy: str = "USD") -> float:
    """Interest on a balance held from `from_date` to `to_date`: one daily accrual per trading session after
    from_date up to and including to_date (same convention as `daily`). Positive cash earns the rate less
    `cash_spread`; a negative balance (margin) pays the rate plus `borrow_spread`."""
    if not cash or to_date <= from_date:
        return 0.0
    days = pd.bdate_range(pd.Timestamp(from_date) + pd.Timedelta(days=1), pd.Timestamp(to_date))
    if not len(days):
        return 0.0
    r = daily(days, ccy)
    adj = (-cash_spread if cash > 0 else borrow_spread) / 252
    return float(cash * (r + adj).sum())


def excess(r: np.ndarray, dates: Optional[Sequence[str]], ccy: str = "USD") -> np.ndarray:
    """Returns minus the reference rate for the same days (unchanged if no dates)."""
    r = np.asarray(r, float)
    if dates is None or len(dates) == 0 or len(dates) != len(r):
        return r
    return r - daily(dates, ccy).to_numpy()
