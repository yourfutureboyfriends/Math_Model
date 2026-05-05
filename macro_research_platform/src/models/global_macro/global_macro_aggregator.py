"""
Global Macro Aggregator

Combines country-specific macro models into a global macro view.

Key principle: Do not simply average. Use configurable weights
and handle divergences intelligently.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import yaml

from ..country_macro.base_country_model import CountryMacroOutput

logger = logging.getLogger(__name__)


@dataclass
class GlobalMacroView:
    """Global macro view output."""

    # Global aggregates
    global_growth_momentum: float
    global_inflation_pressure: float
    global_liquidity_impulse: float
    dollar_liquidity_pressure: float
    global_risk_appetite: float
    global_recession_risk: float
    global_recession_probability_12m: float
    global_policy_stance: str
    global_policy_gap: float
    global_financial_conditions: float

    # Global regime
    global_regime: str
    global_regime_confidence: float
    regime_description: str

    # Regional divergence
    regional_divergence: float  # 0 = all aligned, 1 = complete divergence
    growth_dispersion: float
    inflation_dispersion: float

    # Country contributions
    country_outputs: Dict[str, CountryMacroOutput] = field(default_factory=dict)

    # Cross-asset implications
    cross_asset_signals: Dict[str, Dict] = field(default_factory=dict)

    # Narrative
    narrative: str = ""
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            "global_growth_momentum": self.global_growth_momentum,
            "global_inflation_pressure": self.global_inflation_pressure,
            "global_liquidity_impulse": self.global_liquidity_impulse,
            "dollar_liquidity_pressure": self.dollar_liquidity_pressure,
            "global_risk_appetite": self.global_risk_appetite,
            "global_recession_risk": self.global_recession_risk,
            "global_recession_probability_12m": self.global_recession_probability_12m,
            "global_policy_stance": self.global_policy_stance,
            "global_policy_gap": self.global_policy_gap,
            "global_financial_conditions": self.global_financial_conditions,
            "global_regime": self.global_regime,
            "global_regime_confidence": self.global_regime_confidence,
            "regime_description": self.regime_description,
            "regional_divergence": self.regional_divergence,
            "growth_dispersion": self.growth_dispersion,
            "inflation_dispersion": self.inflation_dispersion,
            "narrative": self.narrative,
            "timestamp": self.timestamp.isoformat(),
        }


class GlobalMacroAggregator:
    """
    Aggregate country macro outputs into a global macro view.

    Uses configurable weights and handles regional divergences.
    """

    def __init__(
        self,
        weights_config_path: Optional[Path] = None,
        weight_scheme: str = "default",
    ):
        """
        Initialize aggregator.

        Args:
            weights_config_path: Path to weights YAML file
            weight_scheme: Which weighting scheme to use
        """
        self.weights = self._load_weights(weights_config_path, weight_scheme)
        self.country_outputs: Dict[str, CountryMacroOutput] = {}

        # Thresholds
        self.recession_warning_threshold = 0.30
        self.recession_high_threshold = 0.50

    def _load_weights(
        self,
        config_path: Optional[Path],
        scheme: str,
    ) -> Dict[str, float]:
        """Load weights from config file."""
        default_weights = {
            "US": 0.40,
            "EuroArea": 0.20,
            "China": 0.20,
            "Japan": 0.10,
            "UK": 0.05,
            "EmergingMarkets": 0.05,
        }

        if config_path is None:
            config_path = Path(__file__).parent.parent.parent.parent / "config" / "global_macro_weights.yaml"

        if not config_path.exists():
            logger.warning(f"Weights config not found: {config_path}, using defaults")
            return default_weights

        try:
            with open(config_path) as f:
                config = yaml.safe_load(f)

            if scheme == "default":
                return config.get("country_weights", default_weights)
            elif scheme == "market_cap":
                return config.get("weight_schemes", {}).get("market_cap", default_weights)
            elif scheme == "gdp":
                return config.get("weight_schemes", {}).get("gdp", default_weights)
            elif scheme == "equal":
                return config.get("weight_schemes", {}).get("equal", default_weights)
            else:
                return default_weights

        except Exception as e:
            logger.error(f"Error loading weights: {e}, using defaults")
            return default_weights

    def add_country_output(self, output: CountryMacroOutput) -> None:
        """Add a country's macro output."""
        # Map country names to weight keys
        weight_key = self._get_weight_key(output.country)
        self.country_outputs[weight_key] = output

    def _get_weight_key(self, country_name: str) -> str:
        """Map country name to weight key."""
        mapping = {
            "United States": "US",
            "US": "US",
            "Euro Area": "EuroArea",
            "EuroArea": "EuroArea",
            "China": "China",
            "Japan": "Japan",
            "United Kingdom": "UK",
            "UK": "UK",
            "Emerging Markets": "EmergingMarkets",
            "EM": "EmergingMarkets",
        }
        return mapping.get(country_name, country_name)

    def aggregate(self) -> GlobalMacroView:
        """
        Aggregate all country outputs into global view.

        Returns:
            GlobalMacroView with aggregated metrics
        """
        if not self.country_outputs:
            raise ValueError("No country outputs to aggregate")

        # Calculate weighted aggregates
        global_growth = self._weighted_average(
            [o.growth_momentum for o in self.country_outputs.values()],
            [self.weights.get(k, 0) for k in self.country_outputs.keys()],
        )

        global_inflation = self._weighted_average(
            [o.inflation_pressure for o in self.country_outputs.values()],
            [self.weights.get(k, 0) for k in self.country_outputs.keys()],
        )

        global_rec_risk = self._weighted_average(
            [o.recession_risk for o in self.country_outputs.values()],
            [self.weights.get(k, 0) for k in self.country_outputs.keys()],
        )

        global_rec_prob_12m = self._weighted_average(
            [o.recession_probability_12m for o in self.country_outputs.values()],
            [self.weights.get(k, 0) for k in self.country_outputs.keys()],
        )

        global_policy_gap = self._weighted_average(
            [o.policy_gap for o in self.country_outputs.values()],
            [self.weights.get(k, 0) for k in self.country_outputs.keys()],
        )

        global_fin_cond = self._weighted_average(
            [o.financial_conditions for o in self.country_outputs.values()],
            [self.weights.get(k, 0) for k in self.country_outputs.keys()],
        )

        global_credit_stress = self._weighted_average(
            [o.credit_stress for o in self.country_outputs.values()],
            [self.weights.get(k, 0) for k in self.country_outputs.keys()],
        )

        # Liquidity impulse (inverted financial conditions)
        global_liquidity = -global_fin_cond

        # Dollar liquidity pressure
        us_data = self.country_outputs.get("US")
        if us_data:
            dollar_pressure = us_data.currency_pressure
        else:
            dollar_pressure = 0.0

        # Risk appetite (inverted from recession risk, adjusted for credit)
        global_risk_app = 1.0 - (global_rec_risk * 0.5 + global_credit_stress * 0.5)

        # Policy stance
        global_policy_stance = self._classify_policy_stance(global_policy_gap)

        # Calculate divergence metrics
        growth_dispersion = self._calculate_dispersion(
            [o.growth_momentum for o in self.country_outputs.values()]
        )
        inflation_dispersion = self._calculate_dispersion(
            [o.inflation_pressure for o in self.country_outputs.values()]
        )
        regional_divergence = (growth_dispersion + inflation_dispersion) / 2

        # Determine global regime
        global_regime, regime_conf = self._determine_global_regime(
            global_growth, global_inflation, regional_divergence
        )

        # Generate narrative
        narrative = self._generate_narrative(
            global_regime, global_growth, global_inflation, regional_divergence
        )

        # Generate cross-asset signals
        cross_asset = self._generate_cross_asset_signals()

        return GlobalMacroView(
            global_growth_momentum=round(global_growth, 2),
            global_inflation_pressure=round(global_inflation, 2),
            global_liquidity_impulse=round(global_liquidity, 2),
            dollar_liquidity_pressure=round(dollar_pressure, 2),
            global_risk_appetite=round(global_risk_app, 2),
            global_recession_risk=round(global_rec_risk, 2),
            global_recession_probability_12m=round(global_rec_prob_12m, 2),
            global_policy_stance=global_policy_stance,
            global_policy_gap=round(global_policy_gap, 2),
            global_financial_conditions=round(global_fin_cond, 2),
            global_regime=global_regime,
            global_regime_confidence=round(regime_conf, 2),
            regime_description=self._describe_regime(global_regime),
            regional_divergence=round(regional_divergence, 2),
            growth_dispersion=round(growth_dispersion, 2),
            inflation_dispersion=round(inflation_dispersion, 2),
            country_outputs=self.country_outputs.copy(),
            cross_asset_signals=cross_asset,
            narrative=narrative,
        )

    def _weighted_average(self, values: List[float], weights: List[float]) -> float:
        """Calculate weighted average."""
        total_weight = sum(weights)
        if total_weight == 0:
            return sum(values) / len(values) if values else 0.0

        weighted_sum = sum(v * w for v, w in zip(values, weights))
        return weighted_sum / total_weight

    def _calculate_dispersion(self, values: List[float]) -> float:
        """Calculate dispersion (standard deviation normalized)."""
        if len(values) < 2:
            return 0.0

        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        std = variance ** 0.5

        # Normalize to 0-1
        return min(1.0, std / 2.0)

    def _classify_policy_stance(self, policy_gap: float) -> str:
        """Classify global policy stance."""
        if policy_gap > 1.5:
            return "tight"
        elif policy_gap > 0.5:
            return "neutral-tight"
        elif policy_gap < -1.5:
            return "loose"
        elif policy_gap < -0.5:
            return "neutral-loose"
        return "neutral"

    def _determine_global_regime(
        self,
        growth: float,
        inflation: float,
        divergence: float,
    ) -> Tuple[str, float]:
        """Determine global macro regime."""
        # High divergence = mixed regime
        if divergence > 0.4:
            return "regional_divergence", 0.7

        # Standard regime classification
        if growth > 0.5 and abs(inflation) < 0.5:
            return "goldilocks", 0.75
        elif growth > 0.5 and inflation > 0.5:
            return "reflation", 0.70
        elif growth < -0.5 and inflation > 0.5:
            return "stagflation", 0.65
        elif growth < -0.5 and inflation < 0.5:
            return "slowdown", 0.70
        elif inflation > 1.0:
            return "inflation_pressure", 0.75
        else:
            return "mixed", 0.50

    def _describe_regime(self, regime: str) -> str:
        """Get regime description."""
        descriptions = {
            "goldilocks": "Global Goldilocks: Growth above trend, inflation contained",
            "reflation": "Global Reflation: Growth and inflation both rising",
            "slowdown": "Global Slowdown: Growth and inflation both declining",
            "stagflation": "Global Stagflation: Weak growth with elevated inflation",
            "inflation_pressure": "Global Inflation Pressure: Late-cycle dynamics",
            "regional_divergence": "Regional Divergence: Economies out of sync",
            "mixed": "Mixed Signals: Unclear global direction",
        }
        return descriptions.get(regime, "Unknown regime")

    def _generate_narrative(
        self,
        regime: str,
        growth: float,
        inflation: float,
        divergence: float,
    ) -> str:
        """Generate narrative summary."""
        # Get country details
        us = self.country_outputs.get("US")
        euro = self.country_outputs.get("EuroArea")
        china = self.country_outputs.get("China")
        japan = self.country_outputs.get("Japan")

        parts = []

        # Opening based on regime
        if regime == "regional_divergence":
            parts.append(
                "Global macro conditions remain divergent rather than cleanly synchronised. "
            )

            if us:
                parts.append(f"The US shows {us.current_regime.lower()}, ")
            if euro:
                parts.append(f"Europe is closer to {euro.current_regime.lower()}, ")
            if china:
                parts.append(f"China remains {china.current_regime.lower()}, ")
            if japan:
                parts.append(f"and Japan is {japan.current_regime.lower()}. ")

            parts.append(
                "This argues for selective regional allocation rather than a single global risk-on or risk-off stance."
            )
        else:
            parts.append(f"Global macro conditions are in a {regime.replace('_', ' ')} regime. ")

            if growth > 0:
                parts.append(f"Global growth momentum is positive at {growth:.1f}%. ")
            else:
                parts.append(f"Global growth momentum is negative at {growth:.1f}%. ")

            if abs(inflation) > 0.5:
                parts.append(f"Inflation pressure is {'elevated' if inflation > 0 else 'subdued'}. ")

        return "".join(parts)

    def _generate_cross_asset_signals(self) -> Dict[str, Dict]:
        """Generate cross-asset signals based on global view."""
        signals = {}

        # Equities
        us = self.country_outputs.get("US")
        euro = self.country_outputs.get("EuroArea")
        china = self.country_outputs.get("China")
        japan = self.country_outputs.get("Japan")

        equity_bias = "neutral"
        equity_conf = 0.5

        if us and us.growth_momentum > 0 and us.inflation_pressure < 1.0:
            equity_bias = "overweight"
            equity_conf = 0.7
        elif us and us.recession_risk > 0.3:
            equity_bias = "underweight"
            equity_conf = 0.65

        signals["equities"] = {
            "signal": equity_bias,
            "confidence": equity_conf,
            "rationale": "US growth momentum and recession risk primary drivers",
        }

        # Rates
        rates_bias = "neutral"
        if us and us.policy_gap > 1.0:
            rates_bias = "bullish"  # High rates will eventually fall
        elif us and us.policy_gap < -0.5:
            rates_bias = "bearish"

        signals["rates"] = {
            "signal": rates_bias,
            "confidence": 0.6,
            "rationale": "Policy stance and inflation trajectory",
        }

        # FX
        fx_bias = "neutral"
        if us and us.currency_trend == "appreciating":
            fx_bias = "dollar_bullish"
        elif us and us.currency_trend == "depreciating":
            fx_bias = "dollar_bearish"

        signals["fx"] = {
            "signal": fx_bias,
            "confidence": 0.55,
            "rationale": "US policy divergence and growth differentials",
        }

        # Commodities
        comm_bias = "neutral"
        if china and china.growth_momentum > 0.5:
            comm_bias = "bullish"
        elif global_recession_risk := (
            sum(o.recession_risk for o in self.country_outputs.values()) / len(self.country_outputs)
            if self.country_outputs else 0
        ) > 0.3:
            comm_bias = "bearish"

        signals["commodities"] = {
            "signal": comm_bias,
            "confidence": 0.55,
            "rationale": "China demand and global recession risk",
        }

        return signals

    def get_world_macro_map(self, is_sample_data: bool = True) -> pd.DataFrame:
        """
        Generate World Macro Map table.

        Args:
            is_sample_data: Whether this is sample/placeholder data

        Returns:
            DataFrame with countries/regions as rows
        """
        rows = []

        # Determine data status
        data_status = "Sample" if is_sample_data else "Placeholder"

        # Add global row
        if self.country_outputs:
            view = self.aggregate()
            rows.append({
                "Region": "Global",
                "Regime": view.global_regime.replace("_", " ").title(),
                "Growth": f"{view.global_growth_momentum:+.1f}",
                "Inflation": f"{view.global_inflation_pressure:+.1f}",
                "Policy": view.global_policy_stance.title(),
                "FX Pressure": "N/A",
                "Recession Risk": f"{view.global_recession_probability_12m:.0%}",
                "Confidence": f"{view.global_regime_confidence:.0%}",
                "Data Status": data_status,
            })

        # Add countries
        for key, output in sorted(self.country_outputs.items()):
            rows.append({
                "Region": output.country,
                "Regime": output.current_regime,
                "Growth": f"{output.growth_momentum:+.1f}",
                "Inflation": f"{output.inflation_pressure:+.1f}",
                "Policy": output.policy_stance.title(),
                "FX Pressure": f"{output.currency_pressure:+.1f}",
                "Recession Risk": f"{output.recession_probability_12m:.0%}",
                "Confidence": f"{output.confidence_level:.0%}",
                "Data Status": data_status,
            })

        return pd.DataFrame(rows)
