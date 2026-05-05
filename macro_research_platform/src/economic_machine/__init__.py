"""
Economic Machine Module

Implements Bridgewater-style causal graph and transmission channels
for understanding how macroeconomic forces propagate through the system.
"""

from .causal_graph import CausalGraph, MacroNode, CausalEdge
from .transmission_channels import (
    TransmissionChannel,
    TransmissionChannelAnalyzer,
    calculate_rates_channel_impact,
    calculate_credit_channel_impact,
    calculate_earnings_channel_impact,
)
from .policy_reaction_function import (
    PolicyReactionFunction,
    PolicyReactionParameters,
    PolicyRegime,
    estimate_optimal_policy_rate,
    assess_policy_restrictiveness,
)
from .debt_cycle_tracker import (
    DebtCycleTracker,
    DebtCycleState,
    LeveragingMetrics,
    calculate_private_sector_balance,
    assess_credit_availability,
)

__all__ = [
    "CausalGraph",
    "MacroNode",
    "CausalEdge",
    "TransmissionChannel",
    "TransmissionChannelAnalyzer",
    "calculate_rates_channel_impact",
    "calculate_credit_channel_impact",
    "calculate_earnings_channel_impact",
    "PolicyReactionFunction",
    "PolicyReactionParameters",
    "PolicyRegime",
    "estimate_optimal_policy_rate",
    "assess_policy_restrictiveness",
    "DebtCycleTracker",
    "DebtCycleState",
    "LeveragingMetrics",
    "calculate_private_sector_balance",
    "assess_credit_availability",
]
