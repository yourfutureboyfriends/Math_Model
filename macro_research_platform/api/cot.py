"""
CFTC Commitments of Traders — non-commercial (speculative) positioning, legacy futures-only
report (publicreporting.cftc.gov dataset 6dca-aqww).

Contracts are selected by CFTC contract-market code. Matching by name (LIKE '%GOLD%') mixed
different markets — micro contracts, other exchanges — so the "latest" and "prior" rows
could come from different contracts: gold showed net SHORT 619 when speculators were net
long ~219,000, and week-on-week changes were differences between unrelated markets.

Extremes use the standard COT index: where the current net position sits within its own
3-year (156-week) range, 0-100. >= 90 = crowded long, <= 10 = crowded short. (A fixed
±200,000-contract threshold was applied to every market regardless of size.)
"""
from __future__ import annotations

from typing import Dict, List, Optional

DATASET = "https://publicreporting.cftc.gov/resource/6dca-aqww.json"
CONTRACTS = [
    ("E-mini S&P 500", "13874A", "Equity"),
    ("10-Year T-Note", "043602", "Rates"),
    ("Euro FX", "099741", "FX"),
    ("Gold (COMEX)", "088691", "Commodities"),
    ("WTI Crude (NYMEX)", "067651", "Commodities"),
]
LOOKBACK_WEEKS = 156
EXTREME_HIGH, EXTREME_LOW = 90.0, 10.0


def cot_index(net_history: List[float]) -> Optional[float]:
    """Current net (last element) as a 0-100 percentile of its range over the history."""
    if len(net_history) < 20:
        return None
    lo, hi = min(net_history), max(net_history)
    if hi == lo:
        return 50.0
    return round((net_history[-1] - lo) / (hi - lo) * 100, 1)


def summarize(name: str, code: str, asset_class: str, rows: List[Dict]) -> Optional[Dict]:
    """rows: newest first, as returned by the CFTC API."""
    rows = [r for r in rows if r.get("cftc_contract_market_code") == code]
    if not rows:
        return None
    def _net(r):
        return int(r["noncomm_positions_long_all"]) - int(r["noncomm_positions_short_all"])
    latest = rows[0]
    longs, shorts = int(latest["noncomm_positions_long_all"]), int(latest["noncomm_positions_short_all"])
    oi = int(latest.get("open_interest_all") or 0)
    net = longs - shorts
    history = [_net(r) for r in reversed(rows[:LOOKBACK_WEEKS])]
    idx = cot_index(history)
    return {
        "name": name, "code": code, "asset_class": asset_class,
        "market": latest.get("market_and_exchange_names"),
        "report_date": latest.get("report_date_as_yyyy_mm_dd", "")[:10],
        "speculator_longs": longs, "speculator_shorts": shorts, "net_position": net,
        "net_change": net - _net(rows[1]) if len(rows) > 1 else None,
        "open_interest": oi,
        "net_speculative_pct": round(net / oi * 100, 1) if oi else None,
        "cot_index": idx, "weeks_of_history": len(history),
        "positioning": "NET_LONG" if net > 0 else "NET_SHORT",
        "extreme_long": idx is not None and idx >= EXTREME_HIGH,
        "extreme_short": idx is not None and idx <= EXTREME_LOW,
        "extreme": idx is not None and (idx >= EXTREME_HIGH or idx <= EXTREME_LOW),
    }


def fetch_cot() -> Dict:
    import requests
    from concurrent.futures import ThreadPoolExecutor

    def _one(spec):
        name, code, ac = spec
        r = requests.get(DATASET, params={"cftc_contract_market_code": code, "$limit": LOOKBACK_WEEKS,
                                          "$order": "report_date_as_yyyy_mm_dd DESC"}, timeout=20)
        r.raise_for_status()
        return summarize(name, code, ac, r.json())

    with ThreadPoolExecutor(max_workers=len(CONTRACTS)) as pool:
        results = [x for x in pool.map(_one, CONTRACTS) if x]
    return {
        "report_date": max((c["report_date"] for c in results), default=None),
        "contracts": results,
        "extreme_positions": sum(1 for c in results if c["extreme"]),
        "methodology": ("Non-commercial positions, CFTC legacy futures-only report. COT index = current "
                        f"net position as a percentile of its {LOOKBACK_WEEKS}-week range; >= {EXTREME_HIGH:.0f} "
                        f"crowded long, <= {EXTREME_LOW:.0f} crowded short."),
        "source": "CFTC Public Reporting (dataset 6dca-aqww)",
    }
