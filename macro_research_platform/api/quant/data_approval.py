"""
G1 data-approval report: the evidence a reviewer needs to approve (or reject) a model's data, computed from the data
itself. It prepares the G1 sign-off; it does not give it — two people still sign at G1.

For each series the model uses:
  coverage      first / last date, sessions, sessions missing against the exchange's reference calendar
                (SPY for US listings and indices, CSPX.L for London), longest gap
  integrity     non-positive or missing closes, stale runs (same close 3+ sessions), outsized one-day moves, bars on
                days the exchange was shut (e.g. VIX's holiday prints)
  point-in-time adjusted closes are back-adjusted for dividends and splits — right for returns, not an as-of price; a
                market close is never revised, unlike an economic release
  timing        when each close is known, and whether the strategy only trades after it (next-bar execution)
  survivorship  instrument-level (index / ETF): none, as long as the instruments existed over the test period; the
                inception date is checked against the backtest start
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pandas as pd

KNOWN_AT = {"^VIX": "16:15 New York (CBOE settles VIX after the cash close)", "^GSPC": "16:00 New York",
            ".L": "16:35 London (closing auction)", "": "16:00 New York (exchange close)"}
JUMP = {"^VIX": 1.0, "^GSPC": 0.15}                                  # |daily return| that is flagged for a look


def _closes(symbol: str) -> pd.Series:
    from api.marketdata.core import yahoo_download
    df = yahoo_download(symbol, period="max", interval="1d", auto_adjust=True)
    if df is None or len(df) == 0:
        return pd.Series(dtype=float)
    c = df["Close"]
    if isinstance(c, pd.DataFrame):
        c = c.iloc[:, 0]
    c.index = pd.to_datetime(c.index).tz_localize(None).normalize()
    return c.astype(float)


def _known_at(sym: str) -> str:
    if sym in KNOWN_AT:
        return KNOWN_AT[sym]
    return KNOWN_AT[".L"] if sym.endswith(".L") else KNOWN_AT[""]


def series_report(sym: str, close: pd.Series, ref: Optional[pd.Series], start: Optional[str],
                  implementation: bool = False) -> Dict[str, Any]:
    out: Dict[str, Any] = {"symbol": sym, "known_at": _known_at(sym), "role": "implementation" if implementation else "backtest"}
    raw = close
    close = close.dropna()
    if close.empty:
        return {**out, "status": "fail", "issues": ["no data returned"]}
    out.update({"first": close.index[0].date().isoformat(), "last": close.index[-1].date().isoformat(), "sessions": int(len(close)),
                "missing_values": int(raw.isna().sum())})
    issues: List[str] = []
    warns: List[str] = []
    if start and close.index[0] > pd.Timestamp(start):
        if implementation:
            warns.append(f"traded instrument starts {out['first']}: before then the record is the backtest's proxy, not this fund")
        else:
            issues.append(f"history starts {out['first']}, after the backtest start {start} — the test cannot use it before then")
    nonpos = int((close <= 0).sum())
    if nonpos:
        issues.append(f"{nonpos} non-positive closes")
    # stale runs: same close three or more sessions running
    same = close.diff().eq(0)
    runs, best, cur = 0, 0, 0
    for v in same.values:
        cur = cur + 1 if v else 0
        if cur == 2:
            runs += 1
        best = max(best, cur + 1 if cur else 0)
    out["stale_runs"] = runs
    if runs:
        warns.append(f"{runs} stale runs (same close 3+ sessions; longest {best})")
    r = close.pct_change().dropna()
    lim = JUMP.get(sym, 0.25)
    big = r[r.abs() > lim]
    out["large_moves"] = [{"date": d.date().isoformat(), "return_pct": round(v * 100, 1)} for d, v in big.items()][:10]
    if len(big):
        warns.append(f"{len(big)} one-day moves beyond ±{lim:.0%} — check each against news (crashes are real; splits are not)")
    if ref is not None and not ref.empty:
        lo, hi = max(close.index[0], ref.index[0]), min(close.index[-1], ref.index[-1])
        cal = ref.index[(ref.index >= lo) & (ref.index <= hi)]
        have = close.index[(close.index >= lo) & (close.index <= hi)]
        missing = cal.difference(have)
        extra = have.difference(cal)
        out["missing_sessions"] = int(len(missing))
        out["coverage_pct"] = round(100 * (1 - len(missing) / max(1, len(cal))), 2)
        out["off_calendar_bars"] = [d.date().isoformat() for d in extra[-10:]]
        out["off_calendar_count"] = int(len(extra))
        gap, longest = 0, 0
        ms = set(missing)
        for d in cal:
            gap = gap + 1 if d in ms else 0
            longest = max(longest, gap)
        out["longest_gap_sessions"] = longest
        if out["coverage_pct"] < 99:
            issues.append(f"coverage {out['coverage_pct']}% of exchange sessions (longest gap {longest})")
        elif len(missing):
            warns.append(f"{len(missing)} sessions missing (longest gap {longest}); forward-filled in the backtest")
        if len(extra):
            warns.append(f"{len(extra)} bars on days the reference exchange was shut — dropped when aligned to the trading calendar")
    out["issues"], out["warnings"] = issues, warns
    out["status"] = "fail" if issues else "warn" if warns else "pass"
    return out


def g1_report(symbols: List[str], start: Optional[str] = None, implementation: Optional[List[str]] = None) -> Dict[str, Any]:
    """`symbols` the backtest uses; `implementation` the instruments the fund would actually trade (UCITS equivalents)."""
    impl = [x for x in (implementation or []) if x not in symbols]
    symbols = list(symbols) + impl
    ref_us, ref_ln = _closes("SPY"), None
    if any(x.endswith(".L") for x in symbols):
        ref_ln = _closes("CSPX.L")
    rows = []
    for s in symbols:
        try:
            c = _closes(s)
        except Exception as e:                                                   # noqa: BLE001 — reported, not raised
            rows.append({"symbol": s, "status": "fail", "issues": [f"download failed: {type(e).__name__}"], "warnings": []})
            continue
        ref = ref_ln if s.endswith(".L") else ref_us
        if s in ("SPY", "CSPX.L"):
            ref = None                                                            # the reference itself
        rows.append(series_report(s, c, ref, start, implementation=s in impl))
    usable_from = max((r["first"] for r in rows if r.get("first") and r.get("role") != "implementation"), default=None)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "symbols": symbols, "implementation": impl,
        "backtest_start": start,
        "series": rows, "common_history_from": usable_from,
        "overall": "fail" if any(r["status"] == "fail" for r in rows) else "warn" if any(r["status"] == "warn" for r in rows) else "pass",
        "evidence": {
            "Point-in-time integrity": "Market closes are final when printed and never revised. Prices are total-return "
                                       "(dividend- and split-adjusted) series, back-adjusted when a dividend is paid: right for "
                                       "returns, but the level on a past date is not the price quoted that day. No economic "
                                       "releases (which are revised) are used.",
            "Coverage": "Per series above: sessions present against the exchange calendar, longest gap, and the common "
                        f"history from {usable_from or '—'} — the earliest date every series exists.",
            "Survivorship": "Instrument-level model (an index and ETFs): no stock-selection survivorship. Each instrument's "
                            "first date is checked against the backtest start; an instrument launched later cannot be "
                            "traded before it existed.",
            "Publication-timing audit": "Each close is known only after the time shown per series. The Quant Lab trades at "
                                        "the next bar's open by default, and series are aligned to the trading calendar with "
                                        "forward-fill only (no back-fill), so no signal uses a price before it was printed.",
        },
        "note": "Prepared evidence for the G1 data approval. The research lead and an independent reviewer still read it and "
                "sign off in Fund Governance; this report does not approve anything.",
    }
