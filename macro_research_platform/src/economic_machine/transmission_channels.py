"""
Transmission Channels

Models how macroeconomic forces transmit to asset prices.

Inspired by systematic macro frameworks that trace:
1. Policy changes → interest rates → discount rates → valuations
2. Growth changes → earnings → corporate profitability → equity prices
3. Credit conditions → funding costs → economic activity → asset prices
4. Risk appetite → risk premia → required returns → asset allocation
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .causal_graph import CausalGraph

logger = logging.getLogger(__name__)


@dataclass
class TransmissionChannel:
    """
    A specific transmission channel from macro to assets.

    Example: "rates channel" - how interest rates affect equity valuations
    """
    name: str
    description: str
    input_nodes: List[str]  # Macro nodes that feed this channel
    output_assets: List[str]  # Asset classes affected
    transmission_function: str  # How to calculate the signal
    current_state: str = "neutral"  # active, dormant, neutral
    signal_strength: float = 0.0
    explanation: str = ""


class TransmissionChannelAnalyzer:
    """
    Analyze which transmission channels are currently active.

    Helps answer: "What is driving markets right now?"
    """

    CHANNELS = {
        "rates": TransmissionChannel(
            name="Rates Channel",
            description="Interest rates affect discount rates and long-duration assets",
            input_nodes=["policy_rates", "real_rates", "yield_curve"],
            output_assets=["equities", "rates_market", "credit", "housing"],
            transmission_function="discount_rate_effect",
        ),
        "credit": TransmissionChannel(
            name="Credit Channel",
            description="Credit conditions affect funding availability and economic activity",
            input_nodes=["credit_spreads", "credit_growth", "financial_conditions"],
            output_assets=["equities", "credit", "business_investment", "housing"],
            transmission_function="credit_supply_effect",
        ),
        "earnings": TransmissionChannel(
            name="Earnings Channel",
            description="Economic growth drives corporate profitability",
            input_nodes=["growth", "consumption", "production", "margins"],
            output_assets=["equities", "earnings"],
            transmission_function="earnings_growth_effect",
        ),
        "margin": TransmissionChannel(
            name="Margin Channel",
            description="Cost pressures and pricing power affect profitability",
            input_nodes=["wage_inflation", "core_inflation", "commodities"],
            output_assets=["equities", "margins"],
            transmission_function="cost_pressure_effect",
        ),
        "currency": TransmissionChannel(
            name="Currency Channel",
            description="Exchange rates affect international competitiveness and inflation",
            input_nodes=["dollar", "policy_rates", "real_rates"],
            output_assets=["equities", "earnings", "commodities"],
            transmission_function="exchange_rate_effect",
        ),
        "commodity": TransmissionChannel(
            name="Commodity Channel",
            description="Commodity prices affect costs, inflation, and sectors",
            input_nodes=["oil", "commodities"],
            output_assets=["equities", "headline_inflation", "margins"],
            transmission_function="input_cost_effect",
        ),
        "liquidity": TransmissionChannel(
            name="Liquidity Channel",
            description="Money market conditions affect risk-taking and asset prices",
            input_nodes=["liquidity", "credit_growth", "policy_rates"],
            output_assets=["equities", "risk_appetite", "credit"],
            transmission_function="liquidity_effect",
        ),
        "risk_appetite": TransmissionChannel(
            name="Risk Appetite Channel",
            description="Sentiment drives risk premia and asset allocation",
            input_nodes=["risk_appetite", "consumer_confidence", "business_confidence"],
            output_assets=["equities", "credit", "valuations"],
            transmission_function="risk_premium_effect",
        ),
        "policy_reaction": TransmissionChannel(
            name="Policy Reaction Channel",
            description="Central bank response to economic conditions",
            input_nodes=["policy_rates", "headline_inflation", "growth", "employment"],
            output_assets=["all_assets"],
            transmission_function="policy_expectation_effect",
        ),
    }

    def __init__(self, causal_graph: CausalGraph):
        self.cg = causal_graph
        self.channels = self.CHANNELS.copy()
        self.channel_signals: Dict[str, float] = {}

    def analyze_channel(
        self,
        channel_name: str,
        node_states: Dict[str, Dict],
    ) -> TransmissionChannel:
        """
        Analyze a specific transmission channel.

        Returns channel with current state and explanation.
        """
        if channel_name not in self.channels:
            raise ValueError(f"Unknown channel: {channel_name}")

        channel = self.channels[channel_name]

        # Get states of input nodes
        input_states = []
        for node in channel.input_nodes:
            state = node_states.get(node)
            if state:
                input_states.append({
                    "node": node,
                    "direction": state.get("direction", "stable"),
                    "zscore": state.get("zscore", 0),
                })

        if not input_states:
            channel.current_state = "dormant"
            channel.signal_strength = 0.0
            channel.explanation = "Insufficient data on input variables"
            return channel

        # Calculate channel signal
        avg_zscore = np.mean([s["zscore"] for s in input_states])

        # Determine if channel is active
        if abs(avg_zscore) > 0.5:
            channel.current_state = "active"
            channel.signal_strength = abs(avg_zscore)
        else:
            channel.current_state = "neutral"
            channel.signal_strength = abs(avg_zscore)

        # Generate explanation
        active_inputs = [s for s in input_states if abs(s["zscore"]) > 0.5]
        if active_inputs:
            direction = "tightening/contractionary" if avg_zscore < 0 else "easing/expansionary"
            channel.explanation = (
                f"Channel is {direction} due to: "
                + ", ".join([f"{s['node']} ({s['direction']})" for s in active_inputs])
            )
        else:
            channel.explanation = "Channel inputs near neutral levels"

        self.channel_signals[channel_name] = channel.signal_strength

        return channel

    def analyze_all_channels(
        self,
        node_states: Dict[str, Dict],
    ) -> Dict[str, TransmissionChannel]:
        """Analyze all transmission channels."""
        results = {}
        for name in self.channels:
            results[name] = self.analyze_channel(name, node_states)
        return results

    def get_active_channels(self, min_strength: float = 0.5) -> List[TransmissionChannel]:
        """Get channels that are currently active."""
        return [
            ch for ch in self.channels.values()
            if ch.current_state == "active" and ch.signal_strength >= min_strength
        ]

    def get_asset_impacts(
        self,
        asset_class: str,
        node_states: Dict[str, Dict],
    ) -> List[Tuple[str, float, str]]:
        """
        Get transmission channels affecting a specific asset class.

        Returns list of (channel_name, impact_score, explanation).
        """
        impacts = []

        for name, channel in self.channels.items():
            if asset_class not in channel.output_assets and "all_assets" not in channel.output_assets:
                continue

            # Analyze channel
            analyzed = self.analyze_channel(name, node_states)

            if analyzed.current_state == "active":
                impacts.append((
                    name,
                    analyzed.signal_strength,
                    analyzed.explanation,
                ))

        return sorted(impacts, key=lambda x: x[1], reverse=True)

    def generate_transmission_report(
        self,
        node_states: Dict[str, Dict],
    ) -> Dict:
        """
        Generate comprehensive transmission channel report.
        """
        self.analyze_all_channels(node_states)

        active = self.get_active_channels()

        report = {
            "summary": {
                "total_channels": len(self.channels),
                "active_channels": len(active),
                "primary_driver": active[0].name if active else "None",
            },
            "active_channels": [
                {
                    "name": ch.name,
                    "signal_strength": round(ch.signal_strength, 2),
                    "explanation": ch.explanation,
                    "affected_assets": ch.output_assets,
                }
                for ch in active
            ],
            "dormant_channels": [
                ch.name for ch in self.channels.values()
                if ch.current_state == "dormant"
            ],
            "asset_impacts": {},
        }

        # Get impacts by asset class
        for asset in ["equities", "credit", "rates_market", "housing"]:
            impacts = self.get_asset_impacts(asset, node_states)
            report["asset_impacts"][asset] = [
                {"channel": ch, "strength": round(strength, 2), "explanation": exp}
                for ch, strength, exp in impacts[:3]  # Top 3
            ]

        return report


def calculate_rates_channel_impact(
    policy_rate_change: float,
    duration_years: float = 7.0,
) -> float:
    """
    Estimate valuation impact of rate changes.

    Simplified duration-based impact:
    ΔValue ≈ -Duration × ΔRate

    Args:
        policy_rate_change: Change in policy rate (decimal, e.g., 0.0025 for 25bps)
        duration_years: Effective duration of asset

    Returns:
        Estimated percent change in value
    """
    # Duration approximation: 7 years for equities (long-duration cash flows)
    # Slope of 1:1 between policy rates and long rates (simplified)
    rate_change_pct = policy_rate_change * 100  # Convert to percentage points

    # Impact = -Duration × ΔRate
    impact = -duration_years * rate_change_pct

    return impact / 100  # Return as decimal


def calculate_credit_channel_impact(
    spread_change_bps: float,
    leverage: float = 1.5,
) -> float:
    """
    Estimate equity impact of credit spread changes.

    Args:
        spread_change_bps: Change in credit spreads (bps)
        leverage: Corporate leverage ratio

    Returns:
        Estimated percent impact on corporate values
    """
    # Rough approximation: 100bps spread widening = -10% equity impact
    # Adjusted by leverage
    base_sensitivity = 0.10 / 100  # 10% per 100bps

    impact = -spread_change_bps * base_sensitivity * leverage

    return impact


def calculate_earnings_channel_impact(
    gdp_growth_change: float,
    operating_leverage: float = 1.5,
) -> float:
    """
    Estimate earnings impact of GDP growth changes.

    Args:
        gdp_growth_change: Change in GDP growth rate (decimal)
        operating_leverage: Corporate operating leverage

    Returns:
        Estimated earnings growth impact
    """
    # Earnings typically move 1.5-2x GDP growth due to operating leverage
    return gdp_growth_change * operating_leverage
