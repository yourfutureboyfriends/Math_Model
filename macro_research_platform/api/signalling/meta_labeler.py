"""
Meta-Labeling: Secondary Conviction Filter
============================================
Academic basis: Lopez de Prado (2018) — Advances in Financial
Machine Learning, Chapter 3.

The meta-labeling framework separates two questions:
  Q1 (Primary model): WHICH DIRECTION to trade? (LONG vs SHORT)
       → Already answered by the 7-layer trade engine.
  Q2 (Meta model):    WHETHER to act on this specific instance?
       → This is what the meta-labeler answers.

By separating these questions, we achieve:
  1. Higher precision: filter out cases where the primary signal
     is correct on direction but incorrect on timing/strength.
  2. Regime filtering: avoid acting on signals that historically
     underperform in the current regime.
  3. Crowding filter: avoid acting when the factor is crowded.
  4. Vol environment: avoid acting on signals that work in
     low-vol regimes during high-vol environments.

This is a RULES-BASED meta-labeler (not a trained ML model,
since we cannot train on sufficient samples here). In production,
you would train a GBM on historical signal outcomes.
"""

import numpy as np
import pandas as pd
from typing import Optional

logger = __import__("logging").getLogger(__name__)

# ── META-LABELER FILTER WEIGHTS ─────────────────────────────
META_FILTER_WEIGHTS = {
    "regime_consistency":  0.30,
    "signal_strength":     0.25,
    "crowding_safety":     0.20,
    "vol_environment":     0.15,
    "signal_health":       0.10,
}

META_SCORE_THRESHOLD = 0.40
FULL_SIZE_THRESHOLD = 0.65

# Signal-vol compatibility matrix (layer, vol_regime) -> score
COMPATIBILITY_MATRIX = {
    ("momentum", "high"):   0.25,
    ("momentum", "normal"): 0.80,
    ("momentum", "low"):    0.90,
    ("value", "high"):      0.55,
    ("value", "normal"):    0.85,
    ("value", "low"):       0.70,
    ("quality", "high"):    0.90,
    ("quality", "normal"):  0.80,
    ("quality", "low"):     0.65,
    ("carry", "high"):      0.20,
    ("carry", "normal"):    0.75,
    ("carry", "low"):       0.85,
    ("bab", "high"):        0.85,
    ("bab", "normal"):      0.70,
    ("bab", "low"):         0.50,
    ("trend", "high"):      0.60,
    ("trend", "normal"):    0.80,
    ("trend", "low"):       0.75,
    ("regime", "high"):     0.70,
    ("regime", "normal"):   0.85,
    ("regime", "low"):      0.80,
}


def compute_meta_score(
    rec: dict,
    crowding_result: dict,
    ic_result: dict,
    vix: float,
    vix_percentile: float,
    modal_regime: str,
) -> dict:
    """
    Compute meta-label for a single recommendation.
    Each filter scores 0.0 to 1.0.
    Final meta_score = weighted sum of filter scores.
    """
    ticker = rec.get("ticker", "")
    direction = rec.get("direction", "LONG")
    abs_score = rec.get("abs_score", 0.0)

    top_drivers = rec.get("top_drivers", [])
    top_driver = top_drivers[0].get("layer", "") if top_drivers else ""

    filter_scores = {}
    filters_triggered = []

    # ── FILTER 1: Regime Consistency ─────────────────────
    regime_consistent = rec.get("regime_valid", False)
    if regime_consistent:
        filter_scores["regime_consistency"] = 1.0
    else:
        filter_scores["regime_consistency"] = 0.25
        filters_triggered.append(
            f"Regime inconsistent ({modal_regime} favors "
            f"{'LONG' if direction == 'SHORT' else 'SHORT'} for {ticker})"
        )

    # ── FILTER 2: Signal Strength ─────────────────────────
    z_min, z_max = 0.5, 2.5
    z_score_frac = float(np.clip((abs_score - z_min) / (z_max - z_min), 0.0, 1.0))
    filter_scores["signal_strength"] = round(z_score_frac, 3)
    if z_score_frac < 0.3:
        filters_triggered.append(f"Weak signal Z={abs_score:.2f} (below 1.0σ)")

    # ── FILTER 3: Crowding Safety ─────────────────────────
    crowding_level = "low"
    if top_driver:
        fc = crowding_result.get("factor_crowding", {})
        if top_driver in fc:
            crowding_level = fc[top_driver].get("level", "low")
            corr_dir = fc[top_driver].get("direction", "stable")

            # Active unwind: hardest block
            if corr_dir == "falling" and crowding_level in ("high", "extreme"):
                filter_scores["crowding_safety"] = 0.0
                filters_triggered.append(
                    f"⚠️ UNWIND SIGNAL in {top_driver}: correlation falling + crowding {crowding_level}"
                )
            elif crowding_level == "extreme":
                filter_scores["crowding_safety"] = 0.10
                filters_triggered.append(f"Extreme crowding in {top_driver} factor")
            elif crowding_level == "high":
                filter_scores["crowding_safety"] = 0.35
                filters_triggered.append(f"High crowding in {top_driver} factor")
            elif crowding_level == "medium":
                filter_scores["crowding_safety"] = 0.65
                filters_triggered.append(f"Moderate crowding in {top_driver} factor")
            else:
                filter_scores["crowding_safety"] = 1.0
        else:
            filter_scores["crowding_safety"] = 0.75
    else:
        filter_scores["crowding_safety"] = 0.75

    # ── FILTER 4: Vol Environment ─────────────────────────
    vol_regime = (
        "high" if vix > 25 or vix_percentile > 0.75
        else "low" if vix < 15 or vix_percentile < 0.25
        else "normal"
    )

    compat_key = (top_driver, vol_regime)
    compat_score = COMPATIBILITY_MATRIX.get(compat_key, 0.70)
    filter_scores["vol_environment"] = compat_score

    if compat_score < 0.40:
        filters_triggered.append(
            f"{top_driver} signal historically weak in {vol_regime}-vol regime (VIX={vix:.1f}, P{vix_percentile*100:.0f})"
        )

    # ── FILTER 5: Signal Health (IC) ─────────────────────
    if top_driver:
        layer_ic = ic_result.get("layer_ic", {})
        if top_driver in layer_ic:
            ic_health = layer_ic[top_driver].get("health", "ACCEPTABLE")
            ic_mult = layer_ic[top_driver].get("weight_mult", 0.75)
            filter_scores["signal_health"] = ic_mult
            if ic_health in ("DECAYED", "MARGINAL"):
                filters_triggered.append(
                    f"{top_driver} IC decayed (rolling IC = {layer_ic[top_driver].get('rolling_ic', 0):.3f})"
                )
        else:
            filter_scores["signal_health"] = 0.75
    else:
        filter_scores["crowding_safety"] = 0.75

    # ── COMPUTE FINAL META SCORE ─────────────────────────
    meta_score = sum(
        filter_scores.get(f, 0.5) * w
        for f, w in META_FILTER_WEIGHTS.items()
    )
    meta_score = round(float(np.clip(meta_score, 0.0, 1.0)), 3)

    # ── DECISION ─────────────────────────────────────────
    act = meta_score >= META_SCORE_THRESHOLD

    # Size fraction: linearly scale from threshold to 1.0
    if meta_score < META_SCORE_THRESHOLD:
        size_fraction = 0.0
    elif meta_score >= FULL_SIZE_THRESHOLD:
        size_fraction = 1.0
    else:
        size_fraction = round(
            (meta_score - META_SCORE_THRESHOLD) / (FULL_SIZE_THRESHOLD - META_SCORE_THRESHOLD), 2
        )

    # Also apply portfolio crowding multiplier
    size_fraction *= crowding_result.get("size_multiplier", 1.0)
    size_fraction = round(float(np.clip(size_fraction, 0.0, 1.0)), 3)

    # ── HUMAN-READABLE REASONING ─────────────────────────
    if not act:
        action_text = "SKIP — meta-labeler filtered this trade"
    elif size_fraction >= 0.80:
        action_text = "FULL SIZE — high meta-conviction"
    elif size_fraction >= 0.50:
        action_text = "HALF SIZE — moderate meta-conviction"
    else:
        action_text = "QUARTER SIZE — low meta-conviction, marginal inclusion"

    reasoning = (
        f"Meta score {meta_score:.2f} → {action_text}. "
        + (f"Filters: {'; '.join(filters_triggered)}." if filters_triggered else "All filters passed.")
    )

    return {
        "act": act,
        "meta_score": meta_score,
        "size_fraction": size_fraction,
        "filters_triggered": filters_triggered,
        "filter_scores": filter_scores,
        "crowding_level": crowding_level,
        "vol_regime": vol_regime,
        "reasoning": reasoning,
        "action_text": action_text,
    }


def apply_meta_labels(
    recommendations: list[dict],
    crowding_result: dict,
    ic_result: dict,
    vix: float,
    vix_pct: float,
    modal_regime: str,
) -> list[dict]:
    """
    Apply meta-labeling to all recommendations.
    Adds a 'meta' key to each rec dict and filters out trades with act=False.
    Returns only actionable recommendations, sorted by meta_score * abs_score.
    """
    for rec in recommendations:
        meta = compute_meta_score(
            rec, crowding_result, ic_result,
            vix, vix_pct, modal_regime
        )
        rec["meta"] = meta
        # Scale position size by meta size_fraction
        if "position_size_pct" in rec:
            rec["position_size_pct"] = round(
                rec["position_size_pct"] * meta["size_fraction"], 1
            )
        if "kelly_fraction" in rec:
            rec["kelly_fraction"] = round(
                rec["kelly_fraction"] * meta["size_fraction"], 3
            )

    # Filter to only actionable trades
    actionable = [r for r in recommendations if r["meta"]["act"]]

    # Re-sort by composite: meta_score * abs_score
    actionable.sort(key=lambda x: x["meta"]["meta_score"] * x["abs_score"], reverse=True)

    return actionable
