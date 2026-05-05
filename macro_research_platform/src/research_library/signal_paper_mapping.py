"""
Signal to Paper Mapping

Maps each signal to its supporting research papers.
Used to validate signals with research backing.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .research_library import PAPER_REGISTRY, get_paper


@dataclass
class SignalPaperMapping:
    """Mapping of a signal to its research support."""
    signal_name: str
    paper_ids: List[str]
    primary_paper: str
    confidence_weight: float  # How much research supports this signal


# Signal to papers mapping
SIGNAL_TO_PAPERS: Dict[str, SignalPaperMapping] = {
    # Macro breadth signals
    "macro_breadth_score": SignalPaperMapping(
        signal_name="macro_breadth_score",
        paper_ids=["fred_md", "sw_pca"],
        primary_paper="fred_md",
        confidence_weight=0.8,
    ),

    "growth_diffusion_index": SignalPaperMapping(
        signal_name="growth_diffusion_index",
        paper_ids=["fred_md", "sw_diffusion"],
        primary_paper="sw_diffusion",
        confidence_weight=0.75,
    ),

    "inflation_diffusion_index": SignalPaperMapping(
        signal_name="inflation_diffusion_index",
        paper_ids=["fred_md"],
        primary_paper="fred_md",
        confidence_weight=0.75,
    ),

    "business_conditions_diffusion_index": SignalPaperMapping(
        signal_name="business_conditions_diffusion_index",
        paper_ids=["sw_diffusion", "ads_index", "grs_nowcast"],
        primary_paper="ads_index",
        confidence_weight=0.85,
    ),

    # Global liquidity signals
    "global_liquidity_pressure": SignalPaperMapping(
        signal_name="global_liquidity_pressure",
        paper_ids=["rey_dilemma", "mar_us_global"],
        primary_paper="rey_dilemma",
        confidence_weight=0.8,
    ),

    "global_risk_cycle": SignalPaperMapping(
        signal_name="global_risk_cycle",
        paper_ids=["rey_dilemma"],
        primary_paper="rey_dilemma",
        confidence_weight=0.7,
    ),

    "us_policy_global_transmission_signal": SignalPaperMapping(
        signal_name="us_policy_global_transmission_signal",
        paper_ids=["mar_us_global"],
        primary_paper="mar_us_global",
        confidence_weight=0.75,
    ),

    "dollar_funding_stress": SignalPaperMapping(
        signal_name="dollar_funding_stress",
        paper_ids=["dtv_cip"],
        primary_paper="dtv_cip",
        confidence_weight=0.85,
    ),

    # Uncertainty signals
    "global_uncertainty_risk": SignalPaperMapping(
        signal_name="global_uncertainty_risk",
        paper_ids=["abf_wui"],
        primary_paper="abf_wui",
        confidence_weight=0.7,
    ),

    "policy_uncertainty_risk": SignalPaperMapping(
        signal_name="policy_uncertainty_risk",
        paper_ids=["bbd_epu"],
        primary_paper="bbd_epu",
        confidence_weight=0.75,
    ),

    # Recession and business cycle signals
    "recession_probability_combined": SignalPaperMapping(
        signal_name="recession_probability_combined",
        paper_ids=["em_recession", "eh_term_structure", "bdx_financial_cycle"],
        primary_paper="em_recession",
        confidence_weight=0.85,
    ),

    "credit_stress_signal": SignalPaperMapping(
        signal_name="credit_stress_signal",
        paper_ids=["gz_credit_spreads", "lsz_credit_sentiment"],
        primary_paper="gz_credit_spreads",
        confidence_weight=0.8,
    ),

    "credit_impulse_signal": SignalPaperMapping(
        signal_name="credit_impulse_signal",
        paper_ids=["gz_credit_spreads", "lsz_credit_sentiment"],
        primary_paper="lsz_credit_sentiment",
        confidence_weight=0.75,
    ),

    "yield_curve_recession_signal": SignalPaperMapping(
        signal_name="yield_curve_recession_signal",
        paper_ids=["eh_term_structure", "em_recession"],
        primary_paper="eh_term_structure",
        confidence_weight=0.8,
    ),

    "growth_at_risk": SignalPaperMapping(
        signal_name="growth_at_risk",
        paper_ids=["abg_vulnerable"],
        primary_paper="abg_vulnerable",
        confidence_weight=0.75,
    ),

    # Regime signals
    "regime_probability": SignalPaperMapping(
        signal_name="regime_probability",
        paper_ids=["hamilton_regime", "at_regime_changes"],
        primary_paper="hamilton_regime",
        confidence_weight=0.8,
    ),

    "regime_transition_risk": SignalPaperMapping(
        signal_name="regime_transition_risk",
        paper_ids=["at_regime_changes"],
        primary_paper="at_regime_changes",
        confidence_weight=0.7,
    ),

    "environment_balance_score": SignalPaperMapping(
        signal_name="environment_balance_score",
        paper_ids=["bridgewater_all_weather"],
        primary_paper="bridgewater_all_weather",
        confidence_weight=0.7,
    ),

    # Cross-asset factor signals
    "cross_asset_momentum_confirmation": SignalPaperMapping(
        signal_name="cross_asset_momentum_confirmation",
        paper_ids=["mop_tsmom", "hop_trend"],
        primary_paper="mop_tsmom",
        confidence_weight=0.85,
    ),

    "trend_following_overlay": SignalPaperMapping(
        signal_name="trend_following_overlay",
        paper_ids=["hop_trend"],
        primary_paper="hop_trend",
        confidence_weight=0.75,
    ),

    "cross_asset_value_score": SignalPaperMapping(
        signal_name="cross_asset_value_score",
        paper_ids=["amp_valmom"],
        primary_paper="amp_valmom",
        confidence_weight=0.75,
    ),

    "cross_asset_momentum_score": SignalPaperMapping(
        signal_name="cross_asset_momentum_score",
        paper_ids=["amp_valmom", "mop_tsmom"],
        primary_paper="amp_valmom",
        confidence_weight=0.8,
    ),

    "carry_score": SignalPaperMapping(
        signal_name="carry_score",
        paper_ids=["kmp_carry"],
        primary_paper="kmp_carry",
        confidence_weight=0.75,
    ),

    "bond_risk_premium": SignalPaperMapping(
        signal_name="bond_risk_premium",
        paper_ids=["cp_bond_rp"],
        primary_paper="cp_bond_rp",
        confidence_weight=0.7,
    ),

    "yield_spread_signal": SignalPaperMapping(
        signal_name="yield_spread_signal",
        paper_ids=["cs_yield_spreads"],
        primary_paper="cs_yield_spreads",
        confidence_weight=0.7,
    ),

    # Portfolio construction signals
    "black_litterman_weights": SignalPaperMapping(
        signal_name="black_litterman_weights",
        paper_ids=["bl_optimization"],
        primary_paper="bl_optimization",
        confidence_weight=0.8,
    ),

    "volatility_managed_position": SignalPaperMapping(
        signal_name="volatility_managed_position",
        paper_ids=["mm_vol_manage"],
        primary_paper="mm_vol_manage",
        confidence_weight=0.75,
    ),

    "risk_managed_momentum": SignalPaperMapping(
        signal_name="risk_managed_momentum",
        paper_ids=["bs_momentum_risk"],
        primary_paper="bs_momentum_risk",
        confidence_weight=0.75,
    ),

    "beta_arbitrage": SignalPaperMapping(
        signal_name="beta_arbitrage",
        paper_ids=["fp_bab", "afp_risk_parity"],
        primary_paper="fp_bab",
        confidence_weight=0.7,
    ),

    "risk_parity_allocation": SignalPaperMapping(
        signal_name="risk_parity_allocation",
        paper_ids=["afp_risk_parity", "bridgewater_all_weather"],
        primary_paper="afp_risk_parity",
        confidence_weight=0.8,
    ),

    "mean_variance_optimal": SignalPaperMapping(
        signal_name="mean_variance_optimal",
        paper_ids=["markowitz_portfolio"],
        primary_paper="markowitz_portfolio",
        confidence_weight=0.7,
    ),
}


def get_papers_for_signal(signal_name: str) -> List[str]:
    """Get paper IDs for a signal."""
    mapping = SIGNAL_TO_PAPERS.get(signal_name)
    return mapping.paper_ids if mapping else []


def get_research_support_for_signal(signal_name: str) -> Optional[SignalPaperMapping]:
    """Get full research support for a signal."""
    return SIGNAL_TO_PAPERS.get(signal_name)


def get_signal_research_confidence(signal_name: str) -> float:
    """Get research confidence weight for a signal."""
    mapping = SIGNAL_TO_PAPERS.get(signal_name)
    return mapping.confidence_weight if mapping else 0.5


def get_signals_without_research() -> List[str]:
    """Get signals that don't have research backing."""
    # This would require knowing all signals in the system
    return []


def get_all_research_backed_signals() -> List[str]:
    """Get all signals with research backing."""
    return list(SIGNAL_TO_PAPERS.keys())


def export_research_mapping_table(output_path: str) -> str:
    """Export signal-to-paper mapping as CSV."""
    import csv

    with open(output_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            'signal_name',
            'paper_ids',
            'primary_paper',
            'confidence_weight',
            'num_supporting_papers'
        ])

        for signal_name, mapping in SIGNAL_TO_PAPERS.items():
            writer.writerow([
                signal_name,
                '|'.join(mapping.paper_ids),
                mapping.primary_paper,
                mapping.confidence_weight,
                len(mapping.paper_ids)
            ])

    return output_path
