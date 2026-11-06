"""
Extended factors for the ML engine's section experts: free FRED series that the core inputs and the FRED-MD-style
panel do not cover, many with shorter histories (VIX from 1990, high-yield spreads from 1996, breakevens from 2003).
The panel needs series complete back to the 1970s; the section experts do not — a section joins the walk-forward from
the year its data exist, and is marked missing before that.

Each value is the one known at the month: data through the previous month (a one-month publication lag, applied to
every series, including market ones, to stay conservative). Weekly and daily series are monthly averages. Series are
latest revised data, as with the panel. ICE BofA corporate spreads are not used: FRED serves only their last three
years, too short to learn from; credit uses Moody's spreads from the panel, the excess bond premium and the NFCI.

id → (section, transformation, label). Transformations: lvl level · d3 3-month change · d12 12-month change ·
yoy 12-month % change · g6 6-month log growth (%).
"""
from __future__ import annotations

import logging
from typing import Dict

import numpy as np

logger = logging.getLogger(__name__)

SERIES: Dict[str, tuple] = {
    # financial conditions and stress
    "NFCI": ("fin_conditions", "lvl", "Chicago Fed financial conditions (NFCI)"),
    "NFCIRISK": ("fin_conditions", "lvl", "NFCI: risk"), "NFCICREDIT": ("credit", "lvl", "NFCI: credit"),
    "NFCILEVERAGE": ("fin_conditions", "lvl", "NFCI: leverage"), "STLFSI4": ("fin_conditions", "lvl", "St. Louis Fed financial stress"),
    "VIXCLS": ("fin_conditions", "lvl", "VIX"),
    # credit
    # (ICE BofA high-yield / BBB spreads are left out: FRED now serves only their last three years)
    "DRTSCILM": ("credit", "lvl", "Banks tightening C&I standards (SLOOS)"),
    # rates and curve
    "THREEFYTP10": ("rates_curve", "lvl", "10-year term premium (Kim–Wright)"), "T10YIE": ("inflation", "lvl", "10-year breakeven inflation"),
    "T5YIFR": ("inflation", "lvl", "5y5y forward inflation"), "DFII10": ("rates_curve", "lvl", "10-year real yield (TIPS)"),
    "MORTGAGE30US": ("housing", "d12", "30-year mortgage rate, 12-month change"),
    # labour
    "SAHMREALTIME": ("labour", "lvl", "Sahm rule (real time)"), "TEMPHELPS": ("labour", "g6", "Temporary help jobs, 6-month growth"),
    "JTSJOL": ("labour", "g6", "Job openings, 6-month growth"), "CCSA": ("labour", "g6", "Continuing claims, 6-month growth"),
    "U6RATE": ("labour", "d12", "U-6 underemployment, 12-month change"),
    # activity and surveys
    "CFNAI": ("activity", "lvl", "Chicago Fed National Activity Index"), "CFNAIMA3": ("activity", "lvl", "CFNAI, 3-month average"),
    "GACDFSA066MSFRBPHI": ("activity", "lvl", "Philadelphia Fed: current activity"),
    "GAFDFSA066MSFRBPHI": ("activity", "lvl", "Philadelphia Fed: future activity"),
    # housing
    "CSUSHPINSA": ("housing", "yoy", "Case-Shiller home prices, y/y"),
    # money and liquidity
    "WALCL": ("money", "g6", "Fed balance sheet, 6-month growth"),
    # markets and global
    "PCOPPUSDM": ("markets", "g6", "Copper price, 6-month growth"), "PALLFNFINDEXM": ("markets", "g6", "Global commodity prices, 6-month growth"),
    "DTWEXBGS": ("markets", "g6", "Broad trade-weighted dollar, 6-month growth"), "DCOILBRENTEU": ("markets", "g6", "Brent oil, 6-month growth"),
}
LABEL_OF = {f"x_{k}": v[2] for k, v in SERIES.items()}
SECTION_OF = {f"x_{k}": v[0] for k, v in SERIES.items()}


def _apply(s, how: str):
    if how == "lvl":
        return s
    if how == "d3":
        return s.diff(3)
    if how == "d12":
        return s.diff(12)
    if how == "yoy":
        return (s / s.shift(12) - 1) * 100
    if how == "g6":
        return np.log(s.where(s > 0)).diff(6) * 100
    raise ValueError(how)


def _build() -> Dict[str, Dict[str, float]]:
    import pandas as pd
    from api.models_ml.recession_ensemble import _fred
    f = _fred()
    cache: Dict[str, object] = {}
    out: Dict[str, Dict[str, float]] = {}
    for key, (_, how, _) in SERIES.items():
        sid = key.split("_")[0]
        try:
            if sid not in cache:
                s = f.get_series(sid).dropna()
                s.index = pd.to_datetime(s.index)
                cache[sid] = s.resample("MS").mean().ffill(limit=2)          # quarterly / sparse series hold for a quarter
            v = _apply(cache[sid], how).shift(1).dropna()                        # known the month after
            out[f"x_{key}"] = {d.strftime("%Y-%m"): round(float(x), 5) for d, x in v.items() if np.isfinite(x)}
        except Exception as e:                                                  # noqa: BLE001 — a missing series is skipped
            logger.warning("[ml.extended] %s unavailable: %s", sid, e)
    return out


def load() -> Dict[str, Dict[str, float]]:
    """{x_<series>: {month: value}} for every extended series available (cached daily)."""
    from api import research_indicators as ri
    got, _ = ri._cached("ml_extended", _build)
    return got or {}
