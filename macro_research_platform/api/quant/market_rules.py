"""
Market microstructure and tax rules by listing country, for the Code Lab engine:

  board lots   the smallest tradable quantity. Most markets trade single shares (odd lots); Japan (100 since
               2018), China A-shares (100 on purchases), Taiwan (1,000 — odd lots trade separately and thinly),
               Thailand, Malaysia, Indonesia, Singapore, Brazil and the Philippines trade in round lots, and Hong
               Kong's board lot is set per stock — read from HKEX's published list of securities (cached weekly;
               today's lots, which rarely change).
  tick sizes   the minimum price increment, from each exchange's tick table, in the quote unit (pence, cents,
               agorot for GBp / ZAc / ILA). Half a tick is the narrowest possible half-spread, so it floors the
               spread model. EU/UK venues use the MiFID II regime (tick depends on liquidity band and price);
               a typical liquid-band tick of roughly 2–5 bp of price is used there.
  withholding  tax withheld at source on dividends paid to a foreign portfolio investor (statutory
               non-resident rates for individuals, 2025), optionally capped at a treaty rate (cost
               `wht_treaty_cap`, default 15% — the usual treaty rate for portfolio dividends). Listings in the
               account currency are treated as domestic (nothing withheld); domestic income tax is not modelled.

All approximate and dated — shown with every result. Rules change; exemptions (Australian franked dividends,
UK REITs, reclaim procedures) are not modelled.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Callable, Dict, Optional, Sequence

import numpy as np

logger = logging.getLogger(__name__)
CACHE = Path(__file__).resolve().parent.parent.parent / "data" / "processed" / "quant" / "market_rules"
HKEX_URL = "https://www.hkex.com.hk/eng/services/trading/securities/securitieslists/ListOfSecurities.xlsx"
TTL = 7 * 86400

# ── Board lots ───────────────────────────────────────────────────────────────
LOTS: Dict[str, int] = {"JP": 100, "CN": 100, "TW": 1000, "TH": 100, "MY": 100, "ID": 100, "SG": 100, "BR": 100,
                        "HK": 1000}              # HK: per stock from HKEX; 1,000 only if a stock is missing there


def _ph_lot(price: float) -> int:
    """Philippine Stock Exchange board lots by price band."""
    for upto, lot in ((0.0099, 1_000_000), (0.495, 10_000), (4.99, 1000), (49.95, 100), (999.5, 10)):
        if price <= upto:
            return lot
    return 5


def hk_lots() -> Dict[str, int]:
    """{'0700.HK': 100, …} from HKEX's list of securities (equities), cached weekly; stale copy if offline."""
    f = CACHE / "hkex_board_lots.json"
    try:
        if time.time() - f.stat().st_mtime < TTL:
            return json.loads(f.read_text())
    except (OSError, ValueError):
        pass
    try:
        import io
        import pandas as pd
        import requests
        r = requests.get(HKEX_URL, timeout=60, headers={"User-Agent": "Mozilla/5.0 (macro research terminal)"})
        r.raise_for_status()
        df = pd.read_excel(io.BytesIO(r.content), header=2)
        df = df[df["Category"].astype(str).str.strip() == "Equity"]
        lots = {}
        for code, lot in zip(df["Stock Code"], df["Board Lot"]):
            try:
                lots[f"{int(code):04d}.HK"] = int(str(lot).replace(",", ""))
            except (TypeError, ValueError):
                continue
        if lots:
            CACHE.mkdir(parents=True, exist_ok=True)
            tmp = f.with_suffix(".tmp")
            tmp.write_text(json.dumps(lots))
            tmp.replace(f)
            return lots
    except Exception as e:                                       # noqa: BLE001 — stale beats nothing
        logger.warning("[market_rules] HKEX board lots unavailable: %s", str(e)[:120])
    try:
        return json.loads(f.read_text())
    except (OSError, ValueError):
        return {}


def lot_size(symbol: str, country: str, hk: Optional[Dict[str, int]] = None) -> int:
    if country == "HK":
        return int((hk if hk is not None else hk_lots()).get(symbol.upper(), LOTS["HK"]))
    return LOTS.get(country, 1)


_PH_BANDS = (np.array([0.0099, 0.495, 4.99, 49.95, 999.5]), np.array([1_000_000, 10_000, 1000, 100, 10, 5], float))


def lot_frame_value(country: str, lot: int, price):
    """Shares per lot at each price (only the Philippines varies lots with price). Vectorised."""
    p = np.asarray(price, float)
    if country == "PH":
        ups, lots = _PH_BANDS
        out = lots[np.searchsorted(ups, p, side="left")]
        return np.where(np.isfinite(p), out, np.nan)
    return np.full(p.shape, float(lot))


# ── Tick sizes (quote units) ────────────────────────────────────────────────
class _bands:
    """A tick table: tick for prices below each threshold. Callable on a scalar or a whole array (vectorised)."""

    def __init__(self, table: Sequence[tuple]):
        self.ups = np.array([u for u, _ in table], float)
        self.ticks = np.array([t for _, t in table], float)

    def __call__(self, p):
        i = np.searchsorted(self.ups, np.asarray(p, float), side="right")
        return self.ticks[np.minimum(i, len(self.ticks) - 1)]


def _mifid(p):
    """Typical liquid-band MiFID II tick: a 1-2-5 step of about 2–5 bp of price (scalar or array)."""
    raw = np.asarray(p, float) * 0.0002
    e = 10.0 ** np.floor(np.log10(np.where(raw > 0, raw, 1e-4)))
    m = np.where(raw <= e, 1.0, np.where(raw <= 2 * e, 2.0, np.where(raw <= 5 * e, 5.0, 10.0)))
    return m * e


INF = float("inf")
TICKS: Dict[str, Callable[[float], float]] = {
    "US": _bands([(1.0, 0.0001), (INF, 0.01)]),
    "CA": _bands([(0.5, 0.005), (INF, 0.01)]),
    "MX": _bands([(INF, 0.01)]), "BR": _bands([(INF, 0.01)]), "CL": _bands([(INF, 0.01)]), "AR": _bands([(INF, 0.05)]),
    "JP": _bands([(3000, 1), (5000, 5), (30000, 10), (50000, 50), (300000, 100), (500000, 500), (3e6, 1000),
                  (5e6, 5000), (3e7, 10000), (5e7, 50000), (INF, 100000)]),
    "HK": _bands([(0.25, 0.001), (0.5, 0.005), (10, 0.01), (20, 0.02), (100, 0.05), (200, 0.1), (500, 0.2),
                  (1000, 0.5), (2000, 1), (5000, 2), (INF, 5)]),
    "CN": _bands([(INF, 0.01)]),
    "TW": _bands([(10, 0.01), (50, 0.05), (100, 0.1), (500, 0.5), (1000, 1), (INF, 5)]),
    "KR": _bands([(2000, 1), (5000, 5), (20000, 10), (50000, 50), (200000, 100), (500000, 500), (INF, 1000)]),
    "IN": _bands([(INF, 0.05)]),
    "TH": _bands([(2, 0.01), (5, 0.02), (10, 0.05), (25, 0.1), (100, 0.25), (200, 0.5), (400, 1), (INF, 2)]),
    "MY": _bands([(1, 0.005), (10, 0.01), (100, 0.02), (INF, 0.1)]),
    "ID": _bands([(200, 1), (500, 2), (2000, 5), (5000, 10), (INF, 25)]),
    "SG": _bands([(0.2, 0.001), (1, 0.005), (INF, 0.01)]),
    "PH": _bands([(0.01, 0.0001), (0.05, 0.001), (0.25, 0.001), (0.5, 0.005), (5, 0.01), (10, 0.01), (20, 0.02),
                  (50, 0.05), (100, 0.05), (200, 0.1), (500, 0.2), (1000, 0.5), (2000, 1), (INF, 5)]),
    "AU": _bands([(0.1, 0.001), (2, 0.005), (INF, 0.01)]),
    "NZ": _bands([(0.2, 0.001), (INF, 0.01)]),
    "ZA": _bands([(INF, 1.0)]),                                     # cents
    "SA": _bands([(10, 0.01), (25, 0.02), (50, 0.05), (100, 0.1), (INF, 0.2)]),
    "QA": _bands([(INF, 0.001)]),
    "TR": _bands([(20, 0.01), (50, 0.02), (100, 0.05), (250, 0.1), (500, 0.25), (1000, 0.5), (2500, 1), (INF, 2.5)]),
}


def half_tick_bps(country: str, quote_price: np.ndarray) -> np.ndarray:
    """Half the minimum price increment, in bp of price, for prices in the listing's quote unit."""
    f = TICKS.get(country, _mifid)
    p = np.asarray(quote_price, float)
    out = np.full(p.shape, np.nan)
    ok = np.isfinite(p) & (p > 0)
    if ok.any():
        out[ok] = 0.5 * np.asarray(f(p[ok]), float) / p[ok] * 1e4
    return out


# ── Dividend withholding tax (non-resident portfolio investor, statutory, 2025) ──
WHT: Dict[str, float] = {
    "US": 0.30, "CA": 0.25, "MX": 0.10, "BR": 0.00, "CL": 0.35, "AR": 0.07,
    "GB": 0.00, "IE": 0.25, "FR": 0.128, "DE": 0.26375, "NL": 0.15, "BE": 0.30, "CH": 0.35, "IT": 0.26, "ES": 0.19,
    "SE": 0.30, "NO": 0.25, "DK": 0.27, "FI": 0.35, "AT": 0.275, "PT": 0.25, "PL": 0.19, "CZ": 0.15, "HU": 0.00,
    "GR": 0.05, "IS": 0.22, "EE": 0.00, "LT": 0.15, "RO": 0.10,
    "JP": 0.15315, "CN": 0.10, "HK": 0.00, "TW": 0.21, "KR": 0.22, "IN": 0.20, "AU": 0.30, "NZ": 0.15, "SG": 0.00,
    "MY": 0.00, "TH": 0.10, "ID": 0.20, "PH": 0.25,
    "IL": 0.25, "SA": 0.05, "QA": 0.00, "TR": 0.15, "ZA": 0.20,
}


def wht_rate(country: str, listing_currency: str, account_currency: str, treaty_cap: float = 0.15) -> float:
    """Tax withheld on a dividend: 0 for listings in the account currency (domestic), else the statutory rate
    capped at the treaty rate."""
    if listing_currency == account_currency:
        return 0.0
    return float(min(WHT.get(country, 0.15), max(treaty_cap, 0.0)))


def describe() -> Dict[str, str]:
    return {"board_lots": "per market (JP 100, CN 100, TW 1,000, TH/MY/ID/SG/BR 100, PH by price band); Hong Kong per "
                          "stock from HKEX's list of securities; elsewhere single shares",
            "ticks": "exchange tick tables (JP, HK, CN, TW, KR, IN, ASEAN, AU, Americas, SA, TR); MiFID II liquid band "
                     "approximated elsewhere",
            "withholding": "statutory non-resident dividend withholding by listing country, capped at the treaty rate; "
                           "listings in the account currency treated as domestic"}
