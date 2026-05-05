"""
RESEARCH-2: Tariff Shock Risk Module (SSRN 5206224, 2025)

Academic basis: Tariff shocks compress regime transition lag from ~6 months
to ~6 weeks by transmitting through inflation expectations before official
macro data confirms. Directly relevant to Trump tariff environment.

Reference: SSRN 5206224 (2025)
"""

from typing import Dict, Optional
from dataclasses import dataclass


@dataclass
class TariffRiskResult:
    """Result from tariff risk monitoring."""
    tariff_rate: float
    tariff_elevated: bool
    stagflation_risk_mult: float
    transition_speed: str
    risk_level: str
    adjusted_stag_prob: Optional[float]
    note: str
    confidence: float


class TariffRiskMonitor:
    """
    Monitor tariff shock risk and its impact on regime transitions.

    Per SSRN 5206224 (2025): Tariff shocks compress regime transition
    lag from ~6 months to ~6 weeks via inflation expectations channel.
    """

    TARIFF_THRESHOLD = 15.0   # effective avg tariff rate %
    INFL_EXP_THRESHOLD = 2.5  # 5Y breakeven threshold
    ISM_CONTRACTION = 50.0  # ISM manufacturing threshold

    def compute(
        self,
        current_tariff_rate: float,
        infl_exp_5y: float,
        ism_mfg: float,
        current_regime: str,
        base_stagflation_prob: Optional[float] = None
    ) -> TariffRiskResult:
        """
        Compute tariff risk metrics.

        Args:
            current_tariff_rate: Current effective tariff rate (%)
            infl_exp_5y: 5Y breakeven inflation expectation
            ism_mfg: ISM manufacturing index
            current_regime: Current macro regime
            base_stagflation_prob: Base stagflation probability (optional)

        Returns:
            TariffRiskResult with risk assessment
        """
        tariff_elevated = current_tariff_rate > self.TARIFF_THRESHOLD
        infl_rising = infl_exp_5y > self.INFL_EXP_THRESHOLD
        mfg_contracting = ism_mfg < self.ISM_CONTRACTION

        # Stagflation multiplier per SSRN 2025
        stag_mult = 1.0
        if tariff_elevated and infl_rising:
            stag_mult *= 1.8
        if mfg_contracting:
            stag_mult *= 1.3

        # Regime transition speed
        speed = "FAST" if tariff_elevated else "NORMAL"

        # Risk level determination
        if stag_mult > 2.0:
            risk_level = "HIGH"
        elif stag_mult > 1.5:
            risk_level = "ELEVATED"
        else:
            risk_level = "NORMAL"

        # Adjusted stagflation probability
        adjusted_stag_prob = None
        if base_stagflation_prob is not None:
            adjusted_stag_prob = min(0.95, base_stagflation_prob * stag_mult)

        # Generate note
        if tariff_elevated:
            note = (
                "Tariff shock active — regime transitions compress from "
                "~6 months to ~6 weeks via inflation expectations channel. "
                f"Stagflation probability multiplier: {stag_mult:.1f}x"
            )
        else:
            note = "Tariff risk within normal range."

        # Confidence based on data availability
        confidence = 0.7 if tariff_elevated else 0.5

        return TariffRiskResult(
            tariff_rate=round(current_tariff_rate, 2),
            tariff_elevated=tariff_elevated,
            stagflation_risk_mult=round(stag_mult, 2),
            transition_speed=speed,
            risk_level=risk_level,
            adjusted_stag_prob=round(adjusted_stag_prob, 3) if adjusted_stag_prob else None,
            note=note,
            confidence=confidence
        )

    def to_dict(self, result: TariffRiskResult) -> Dict:
        """Convert result to dictionary for JSON serialization."""
        return {
            "tariff_rate": result.tariff_rate,
            "tariff_elevated": result.tariff_elevated,
            "stagflation_risk_mult": result.stagflation_risk_mult,
            "transition_speed": result.transition_speed,
            "risk_level": result.risk_level,
            "adjusted_stag_prob": result.adjusted_stag_prob,
            "note": result.note,
            "confidence": result.confidence,
        }


def compute_tariff_risk(
    current_tariff_rate: float = 12.5,
    infl_exp_5y: float = 2.3,
    ism_mfg: float = 49.0,
    current_regime: str = "Goldilocks",
    base_stagflation_prob: Optional[float] = None
) -> Dict:
    """
    Convenience function to compute tariff risk.

    Args:
        current_tariff_rate: Current tariff rate (default 12.5% for Trump tariffs)
        infl_exp_5y: 5Y breakeven (default 2.3%)
        ism_mfg: ISM manufacturing (default 49.0)
        current_regime: Current regime
        base_stagflation_prob: Base stagflation probability

    Returns:
        Dictionary with tariff risk data
    """
    monitor = TariffRiskMonitor()
    result = monitor.compute(
        current_tariff_rate=current_tariff_rate,
        infl_exp_5y=infl_exp_5y,
        ism_mfg=ism_mfg,
        current_regime=current_regime,
        base_stagflation_prob=base_stagflation_prob
    )
    return monitor.to_dict(result)


def apply_tariff_adjustment(
    regime_transitions: Dict,
    tariff_risk: Dict
) -> Dict:
    """
    Apply tariff risk adjustment to regime transition probabilities.

    Args:
        regime_transitions: Original transition probabilities
        tariff_risk: Tariff risk assessment

    Returns:
        Adjusted regime transitions
    """
    if not tariff_risk.get("tariff_elevated"):
        return regime_transitions

    adjusted = regime_transitions.copy()
    mult = tariff_risk.get("stagflation_risk_mult", 1.0)

    # Increase probability of stagflation transitions
    for transition in adjusted.get("transitions", []):
        if transition.get("toRegime") == "Stagflation":
            orig_prob = transition.get("probability", 0.1)
            transition["probability"] = min(0.95, orig_prob * mult)
            transition["tariff_adjusted"] = True

    # Compress transition timeline
    if tariff_risk.get("transition_speed") == "FAST":
        adjusted["transition_speed"] = "FAST"
        adjusted["expected_weeks"] = 6  # vs 24 normal

    return adjusted
