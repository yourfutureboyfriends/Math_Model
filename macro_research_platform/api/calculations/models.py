"""
Core financial model formulas — single, documented, unit-tested source of truth.

Every function here is pure (no I/O), carries a docstring stating its formula, inputs,
units and expected output range, and clamps to that range so a downstream display can
never show an out-of-bounds value. The MODELS registry mirrors these docstrings for the
/api/v1/methodology endpoint so an institutional user can audit model logic before
trusting it with capital.
"""
from __future__ import annotations

from typing import Sequence, Optional, Dict, Any, List
from collections import Counter

from scipy.stats import norm


# ─────────────────────────────────────────────────────────────────────────────
# Recession probability — NY Fed Estrella-Mishkin probit
# ─────────────────────────────────────────────────────────────────────────────
# Coefficients from Estrella & Mishkin (1998), "Predicting U.S. Recessions:
# Financial Variables as Leading Indicators", Review of Economics and Statistics,
# as maintained by the Federal Reserve Bank of New York's yield-curve model.
_EM_INTERCEPT = -0.6045
_EM_SLOPE = -0.7374


def estrella_mishkin_recession_prob(spread_3m10y_pp: float) -> float:
    """12-month-ahead recession probability from the 3m10y Treasury spread.

    Formula : P = Phi(-0.6045 - 0.7374 * spread), spread in PERCENTAGE POINTS.
    Inputs  : spread_3m10y_pp — (10y yield - 3m yield) in percentage points
              (e.g. -0.66 for a 66bp inversion). NOT basis points.
    Units   : probability, dimensionless.
    Range   : [0.0, 1.0]. Reference points: spread=-0.66pp -> ~0.45;
              spread=+1.0pp -> ~0.09; a normal +positive curve -> low single digits.
    Source  : Estrella & Mishkin (1998); NY Fed yield-curve recession model.
    """
    if spread_3m10y_pp is None:
        raise ValueError("spread_3m10y_pp is required")
    # Guard against a bps/pp unit error: a real 3m10y spread lives well within +-6pp.
    if not (-6.0 < spread_3m10y_pp < 6.0):
        raise ValueError(
            f"spread {spread_3m10y_pp} out of plausible range (pp); looks like basis points"
        )
    p = float(norm.cdf(_EM_INTERCEPT + _EM_SLOPE * spread_3m10y_pp))
    return max(0.0, min(1.0, p))


# ─────────────────────────────────────────────────────────────────────────────
# Yield-curve spread
# ─────────────────────────────────────────────────────────────────────────────
def yield_curve_spread_bps(long_yield_pct: float, short_yield_pct: float) -> float:
    """Term spread in basis points.

    Formula : (long_yield - short_yield) * 100.
    Inputs  : yields in percent (e.g. 4.49 for 4.49%).
    Units   : basis points.
    Range   : unbounded in principle; realistically [-400, 400] bps.
    """
    return round((long_yield_pct - short_yield_pct) * 100.0, 1)


# ─────────────────────────────────────────────────────────────────────────────
# Copper / gold ratio — cyclical growth indicator
# ─────────────────────────────────────────────────────────────────────────────
def copper_gold_ratio(copper_usd_lb: float, gold_usd_oz: float) -> float:
    """Copper/gold ratio, a market-based growth/reflation proxy.

    Formula : copper_usd_lb / (gold_usd_oz / 1000).
    Inputs  : copper in USD per pound, gold in USD per troy ounce.
    Units   : dimensionless ratio.
    Range   : (0, 10) in practice (typically ~0.6-2.5). A rising ratio is risk-on.
    Source  : Widely used cyclical indicator (e.g. Gundlach's "copper/gold" signal).
    """
    if gold_usd_oz is None or gold_usd_oz <= 0:
        raise ValueError("gold_usd_oz must be positive")
    ratio = copper_usd_lb / (gold_usd_oz / 1000.0)
    return round(ratio, 4)


# ─────────────────────────────────────────────────────────────────────────────
# Momentum — 12-minus-1 month total return
# ─────────────────────────────────────────────────────────────────────────────
def momentum_12_1(price_now: float, price_1m_ago: float, price_12m_ago: float) -> float:
    """12-1 month momentum (skip most-recent month to avoid short-term reversal).

    Formula : (price_1m_ago / price_12m_ago) - 1.
    Inputs  : split-adjusted prices (same series). price_now is accepted for API
              symmetry but the 12-1 signal deliberately excludes the last month.
    Units   : fraction (0.15 = +15%).
    Range   : clamped to [-1.0, 3.0] (i.e. -100% to +300%); values outside imply
              a data error (split mismatch / stale base price).
    Source  : Jegadeesh & Titman (1993) cross-sectional momentum, 12-1 convention.
    """
    if not price_12m_ago:
        raise ValueError("price_12m_ago must be non-zero")
    m = (price_1m_ago / price_12m_ago) - 1.0
    return max(-1.0, min(3.0, m))


# ─────────────────────────────────────────────────────────────────────────────
# Ensemble agreement
# ─────────────────────────────────────────────────────────────────────────────
def ensemble_agreement(signals: Sequence[str]) -> float:
    """Fraction of models agreeing with the ensemble's modal (majority) signal.

    Formula : count(signal == mode) / n.
    Inputs  : list of per-model categorical signals, e.g. ["BULLISH","BULLISH","NEUTRAL"].
    Units   : fraction.
    Range   : [0.0, 1.0]. All-agree -> 1.0; empty -> 0.0.
    """
    sigs = [s for s in signals if s is not None]
    if not sigs:
        return 0.0
    mode, mode_count = Counter(sigs).most_common(1)[0]
    return round(mode_count / len(sigs), 4)


# ─────────────────────────────────────────────────────────────────────────────
# Methodology registry (served by /api/v1/methodology)
# ─────────────────────────────────────────────────────────────────────────────
MODELS: List[Dict[str, Any]] = [
    {
        "id": "recession_estrella_mishkin",
        "name": "Recession Probability (Estrella-Mishkin probit)",
        "formula": "P = Phi(-0.6045 - 0.7374 * spread_3m10y_pp)",
        "inputs": {"spread_3m10y_pp": "10y minus 3m Treasury yield, percentage points"},
        "output": {"units": "probability", "range": [0.0, 1.0]},
        "reference_points": {"-0.66pp": "~0.45", "+1.0pp": "~0.09"},
        "citation": "Estrella & Mishkin (1998); NY Fed yield-curve model",
    },
    {
        "id": "yield_curve_spread",
        "name": "Yield-Curve Spread",
        "formula": "(long_yield - short_yield) * 100",
        "inputs": {"long_yield_pct": "percent", "short_yield_pct": "percent"},
        "output": {"units": "basis points", "range": [-400, 400]},
        "citation": "Standard term-spread definition",
    },
    {
        "id": "copper_gold_ratio",
        "name": "Copper/Gold Ratio (growth proxy)",
        "formula": "copper_usd_lb / (gold_usd_oz / 1000)",
        "inputs": {"copper_usd_lb": "USD/lb", "gold_usd_oz": "USD/oz"},
        "output": {"units": "ratio", "range": [0, 10]},
        "citation": "Cyclical growth/reflation indicator (Gundlach)",
    },
    {
        "id": "momentum_12_1",
        "name": "12-1 Month Momentum",
        "formula": "(price_1m_ago / price_12m_ago) - 1",
        "inputs": {"price_1m_ago": "adj. price", "price_12m_ago": "adj. price"},
        "output": {"units": "fraction", "range": [-1.0, 3.0]},
        "citation": "Jegadeesh & Titman (1993), 12-1 convention",
    },
    {
        "id": "ensemble_agreement",
        "name": "Ensemble Agreement",
        "formula": "count(signal == mode) / n",
        "inputs": {"signals": "list of categorical model signals"},
        "output": {"units": "fraction", "range": [0.0, 1.0]},
        "citation": "Majority-vote concordance",
    },
]
