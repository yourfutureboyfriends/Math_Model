"""
Single authoritative regime classification.
Computed ONCE per dashboard refresh. All sections use this object.
It is frozen (immutable) so no section can accidentally mutate it.
"""
import time, logging
from dataclasses import dataclass
from typing import Literal, Optional, Callable

logger = logging.getLogger(__name__)

RegimeType = Literal["Goldilocks", "Reflation", "Stagflation", "Slowdown"]

@dataclass(frozen=True)
class RegimeContext:
    regime: RegimeType
    confidence: float
    growth_zscore: float
    inflation_zscore: float
    liquidity_zscore: float
    duration_months: int
    timestamp: float

    # Convenience properties used by downstream sections
    @property
    def is_inflationary(self) -> bool:
        return self.inflation_zscore > 0.3

    @property
    def is_above_trend_growth(self) -> bool:
        return self.growth_zscore > 0.0

    @property
    def scenario_labels(self) -> list[dict]:
        """Regime-appropriate scenario names and base probabilities."""
        scenarios = {
            "Goldilocks":  [
                {"label": "Soft Landing",       "prob": 0.50, "return": 12.0},
                {"label": "Mild Slowdown",       "prob": 0.30, "return": 3.0},
                {"label": "Unexpected Shock",    "prob": 0.20, "return": -15.0},
            ],
            "Reflation": [
                {"label": "Continued Expansion", "prob": 0.45, "return": 10.0},
                {"label": "Inflation Spike",     "prob": 0.35, "return": 1.0},
                {"label": "Stagflationary Turn", "prob": 0.20, "return": -10.0},
            ],
            "Stagflation": [
                {"label": "Soft Landing",        "prob": 0.25, "return": 8.0},
                {"label": "Persistent Stagflation","prob": 0.50, "return": 1.0},
                {"label": "Stagflationary Recession","prob": 0.25,"return": -18.0},
            ],
            "Slowdown": [
                {"label": "Soft Landing",        "prob": 0.40, "return": 6.0},
                {"label": "Mild Recession",      "prob": 0.40, "return": -8.0},
                {"label": "Hard Landing",        "prob": 0.20, "return": -25.0},
            ],
        }
        return scenarios.get(self.regime, [])

    @property
    def business_layer_tags(self) -> dict:
        """Regime-appropriate supporting/opposing tags for Business Layer."""
        tags = {
            "Goldilocks":  {
                "supporting": ["growth_momentum", "easing_inflation", "credit_expanding"],
                "opposing":   ["late_cycle_risk", "valuation_stretched"],
            },
            "Reflation": {
                "supporting": ["growth_momentum", "commodity_tailwind", "earnings_upgrades"],  # FIXED: was growth_positive
                "opposing":   ["inflation_risk", "rate_sensitivity", "margin_compression"],
            },
            "Stagflation": {
                "supporting": ["inflation_hedge", "real_asset_outperformance"],
                "opposing":   ["growth_headwinds", "elevated_recession_risk", "margin_pressure"],
            },
            "Slowdown": {
                "supporting": ["defensive_quality", "bond_duration", "low_vol"],
                "opposing":   ["credit_stress", "earnings_revision_risk", "cyclical_weakness"],
            },
        }
        return tags.get(self.regime, {"supporting": [], "opposing": []})

    @property
    def sector_playbook(self) -> dict:
        """Returns regime-appropriate sector tilts. One source of truth."""
        playbooks = {
            "Goldilocks": {
                "overweight":  ["XLK", "XLY", "XLF", "XLRE"],
                "underweight": ["XLE", "XLB", "XLU"],
                "rationale": "High-growth cyclicals and rate-sensitive sectors outperform",
            },
            "Reflation": {
                "overweight":  ["XLE", "XLB", "XLF", "XLI"],
                "underweight": ["XLK", "XLU", "XLP"],
                "rationale": "Inflation beneficiaries and cyclicals; avoid long duration",
            },
            "Stagflation": {
                "overweight":  ["XLE", "XLB", "XLP", "XLV"],
                "underweight": ["XLK", "XLY", "XLF"],
                "rationale": "Real assets and defensives; avoid growth and financials",
            },
            "Slowdown": {
                "overweight":  ["XLV", "XLU", "XLP", "TLT"],
                "underweight": ["XLE", "XLB", "XLY"],
                "rationale": "Defensives and duration; avoid cyclicals",
            },
        }
        return playbooks.get(self.regime, {})


def build_regime_context(
    growth_val: float,
    inflation_val: float,
    liquidity_zscore: float = 0.0,
    confidence: float = 0.8,
    duration_fn: Optional[Callable[[], int]] = None,      # optional callable() -> int for duration
) -> RegimeContext:
    """
    THE ONLY place where regime is classified.
    Called once at the top of compute_full_dashboard().
    Result passed as argument to every downstream function.
    """
    # Historical norms (US long-run)
    GROWTH_MEAN,    GROWTH_STD    = 2.2, 2.0
    INFLATION_MEAN, INFLATION_STD = 2.5, 1.5

    g_z = (growth_val    - GROWTH_MEAN)    / GROWTH_STD
    i_z = (inflation_val - INFLATION_MEAN) / INFLATION_STD

    # Bridgewater 2×2 matrix
    above_trend  = g_z >  0.0
    above_target = i_z >  0.3    # >3.0% inflation = above-target

    regime: RegimeType = (
        "Goldilocks"  if     above_trend and not above_target else
        "Reflation"   if     above_trend and     above_target else
        "Stagflation" if not above_trend and     above_target else
        "Slowdown"
    )

    duration = duration_fn() if duration_fn else 0

    logger.info(
        f"[REGIME] g={growth_val:.1f}% (z={g_z:.2f}) "
        f"i={inflation_val:.1f}% (z={i_z:.2f}) "
        f"→ {regime} (conf={confidence:.0%})"
    )

    return RegimeContext(
        regime=regime,
        confidence=confidence,
        growth_zscore=round(g_z, 2),
        inflation_zscore=round(i_z, 2),
        liquidity_zscore=round(liquidity_zscore, 2),
        duration_months=duration,
        timestamp=time.time(),
    )
