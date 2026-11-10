"""
Sector scoring and OW/N/UW signals — single source of truth: config/sector_rules.yaml.

`src.models.portfolio_construction.portfolio_constructor` and `src.reporting.memo_generator`
import this module (it was missing, so both failed on import / KeyError'd on
SECTOR_CONFIG[...]["description"]).

Score for each sector:
    score = regime_fit + 0.5 * Σ_f sensitivity_f · signal_f
where regime_fit is the sector's configured score for the current regime (0 if the regime
isn't configured) and signal_f ∈ {growth, inflation, liquidity, risk} are the macro factor
signals (roughly in [-1, 1]). Scores are clamped to [-3, 3].
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

import pandas as pd
import yaml

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "sector_rules.yaml"
_FACTOR_WEIGHT = 0.5

with open(_CONFIG_PATH, "r") as _f:
    _RULES = yaml.safe_load(_f)


def _describe(cfg: dict) -> str:
    ch = cfg.get("characteristics", {})
    parts = []
    if "cyclical_beta" in ch:
        parts.append(f"Cyclical beta {ch['cyclical_beta']}")
    if "rate_sensitivity" in ch:
        parts.append(f"{ch['rate_sensitivity']} rate sensitivity")
    if "earnings_volatility" in ch:
        parts.append(f"{ch['earnings_volatility']} earnings volatility")
    return ("; ".join(parts) or cfg.get("name", "")) + "."


SECTOR_CONFIG: Dict[str, dict] = {
    name: {**cfg, "description": _describe(cfg)}
    for name, cfg in (_RULES.get("sectors") or {}).items()
}

_th = _RULES.get("signal_thresholds") or {}
SIGNAL_THRESHOLDS: Dict[str, float] = {
    "overweight": float(_th.get("overweight", 0.15)),
    "underweight": float(_th.get("underweight", -0.15)),
}


def compute_sector_scores(
    regime: str,
    growth_score: float,
    liquidity_score: float,
    risk_score: float,
    inflation_score: float = 0.0,
) -> Dict[str, float]:
    """Score every configured sector for a regime and set of macro factor signals."""
    signals = {"growth": growth_score, "inflation": inflation_score,
               "liquidity": liquidity_score, "risk": risk_score}
    out: Dict[str, float] = {}
    for sector, cfg in SECTOR_CONFIG.items():
        regime_fit = float(((cfg.get("regime_performance") or {}).get(regime) or {}).get("score", 0.0))
        sens = cfg.get("factor_sensitivities") or {}
        factor = sum(float(sens.get(f, 0.0)) * float(v) for f, v in signals.items() if v is not None)
        out[sector] = round(max(-3.0, min(3.0, regime_fit + _FACTOR_WEIGHT * factor)), 4)
    return out


def get_sector_signals(sector_scores: Dict[str, float]) -> Dict[str, str]:
    """Overweight if score >= OW threshold, Underweight if <= UW threshold, else Neutral."""
    ow, uw = SIGNAL_THRESHOLDS["overweight"], SIGNAL_THRESHOLDS["underweight"]
    return {s: ("Overweight" if v >= ow else "Underweight" if v <= uw else "Neutral")
            for s, v in sector_scores.items()}


def get_sector_table(sector_scores: Dict[str, float], signals: Dict[str, str],
                     regime: Optional[str] = None) -> pd.DataFrame:
    """One row per sector (Sector, Signal, Score, Rationale), sorted by score descending.
    Rationale is the configured regime rationale when `regime` is given, else the sector
    description."""
    rows = []
    for sector, score in sector_scores.items():
        cfg = SECTOR_CONFIG.get(sector, {})
        rationale = ((cfg.get("regime_performance") or {}).get(regime) or {}).get("rationale") \
            if regime else None
        rows.append({"Sector": sector, "Signal": signals.get(sector, "Neutral"),
                     "Score": score, "Rationale": rationale or cfg.get("description", "")})
    return pd.DataFrame(rows, columns=["Sector", "Signal", "Score", "Rationale"]) \
        .sort_values("Score", ascending=False).reset_index(drop=True)
