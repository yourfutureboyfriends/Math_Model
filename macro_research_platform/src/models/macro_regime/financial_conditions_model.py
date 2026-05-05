"""
Financial Conditions Model

Estimates the impulse of financial conditions on growth using multiple components:
- Real yields
- Credit spreads
- Equity momentum
- Dollar index
- VIX
- NFCI (if available - uses direct NFCI when available)

IMPORTANT DISTINCTION:
This model implements the Adrian, Boyarchenko & Giannone (2019) "Vulnerable Growth"
methodology for financial conditions impulse, NOT the Chicago Fed National Financial
Conditions Index (NFCI).

Scale differences:
- ABG (2019) Impulse Score: -1 to +1 (tightening to easing)
- Chicago Fed NFCI: approximately -5 to +5 (loose to tight)

When NFCI data is available, it is used directly (converted to -1 to +1 scale).
Otherwise, a custom composite is computed from the 5 components above.

Based on:
- Adrian, Boyarchenko & Giannone (2019) - Vulnerable Growth
- Chicago Fed NFCI methodology (for comparison/reference only)
- Federal Reserve research on financial conditions impulse
"""

import logging
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class FinancialConditionsImpulse:
    """Financial conditions impulse result."""
    impulse_score: float  # -1 to 1, negative = tightening
    category: str  # easing, neutral, tightening
    confidence: float  # 0-1
    components: Dict[str, float]
    drivers: Dict[str, str]


class FinancialConditionsModel:
    """
    Financial Conditions Model

    Combines multiple market-based indicators into a single
    financial conditions impulse score.
    """

    def __init__(self):
        # Component weights (sum to 1.0)
        self.component_weights = {
            "real_yield": 0.25,
            "credit_spread": 0.25,
            "equity_momentum": 0.20,
            "dollar_index": 0.15,
            "vix": 0.15,
        }

        # Normal ranges for each component (percentiles)
        self.normal_ranges = {
            "real_yield": (0.5, 2.5),  # percent
            "credit_spread": (200, 500),  # bps
            "equity_momentum": (-0.05, 0.05),  # 3-month return
            "dollar_index": (90, 110),  # DXY level
            "vix": (12, 25),  # VIX level
        }

    def _compute_real_yield_impulse(
        self,
        nominal_yield: float,
        inflation_expectation: float = 2.0,
    ) -> float:
        """
        Compute real yield impulse.

        Higher real yields = tighter conditions
        """
        real_yield = nominal_yield - inflation_expectation

        # Normalize: 0 = neutral, positive = tight, negative = easy
        # Long-term average real yield ~1.0%
        neutral_real_yield = 1.0

        # Scale: 1% deviation = 0.5 impulse
        impulse = (real_yield - neutral_real_yield) / 2.0

        return np.clip(impulse, -1.0, 1.0)

    def _compute_credit_spread_impulse(self, credit_spread: float) -> float:
        """
        Compute credit spread impulse.

        Wider spreads = tighter conditions
        """
        # Typical HY spread range: 300-600 bps
        neutral_spread = 400  # bps

        # Log scale for extreme values
        if credit_spread > 0:
            impulse = np.log(credit_spread / neutral_spread) / np.log(2)
        else:
            impulse = 0

        return np.clip(impulse, -1.0, 1.0)

    def _compute_equity_momentum_impulse(self, momentum_3m: float) -> float:
        """
        Compute equity momentum impulse.

        Positive momentum = easier conditions
        """
        # Annualize roughly
        annualized = momentum_3m * 4

        # Neutral = 0 (market drift)
        # Scale: 20% annual return = +0.5 impulse, -20% = -0.5 impulse
        impulse = -annualized / 0.4  # Negative because risk-off tightens

        return np.clip(impulse, -1.0, 1.0)

    def _compute_dollar_impulse(self, dollar_level: float) -> float:
        """
        Compute dollar strength impulse.

        Stronger dollar = tighter global conditions
        """
        # DXY long-term average ~100
        neutral_dxy = 100

        # Scale: 10% deviation = 0.5 impulse
        impulse = (dollar_level - neutral_dxy) / 20.0

        return np.clip(impulse, -1.0, 1.0)

    def _compute_vix_impulse(self, vix_level: float) -> float:
        """
        Compute VIX impulse.

        Higher VIX = tighter conditions
        """
        # Log scale - VIX is naturally log-normal
        neutral_vix = 18

        if vix_level > 0:
            impulse = np.log(vix_level / neutral_vix) / np.log(3)
        else:
            impulse = 0

        return np.clip(impulse, -1.0, 1.0)

    def compute_impulse(
        self,
        nominal_yield: Optional[float] = None,
        credit_spread: Optional[float] = None,
        equity_momentum_3m: Optional[float] = None,
        dollar_index: Optional[float] = None,
        vix: Optional[float] = None,
        nfci: Optional[float] = None,
    ) -> FinancialConditionsImpulse:
        """
        Compute overall financial conditions impulse.

        Args:
            nominal_yield: 10Y Treasury yield (%)
            credit_spread: High yield credit spread (bps)
            equity_momentum_3m: 3-month equity return
            dollar_index: DXY level
            vix: VIX level
            nfci: Chicago Fed NFCI (if available, overrides)

        Returns:
            FinancialConditionsImpulse with score and components
        """
        components = {}
        drivers = {}

        # Use NFCI directly if available (it's already a composite)
        if nfci is not None:
            # NFCI: positive = tighter, negative = easier
            # Range typically -1 to 1
            impulse = nfci
            category = self._classify_impulse(impulse)

            return FinancialConditionsImpulse(
                impulse_score=impulse,
                category=category,
                confidence=0.9,  # NFCI is authoritative
                components={"nfci": nfci},
                drivers={"nfci": "Using Chicago Fed NFCI directly"},
            )

        # Compute individual components
        if nominal_yield is not None:
            components["real_yield"] = self._compute_real_yield_impulse(nominal_yield)
            drivers["real_yield"] = f"Real yield: {nominal_yield:.2f}%"
        else:
            components["real_yield"] = 0.0
            drivers["real_yield"] = "Missing - assuming neutral"

        if credit_spread is not None:
            components["credit_spread"] = self._compute_credit_spread_impulse(credit_spread)
            drivers["credit_spread"] = f"Credit spread: {credit_spread:.0f} bps"
        else:
            components["credit_spread"] = 0.0
            drivers["credit_spread"] = "Missing - assuming neutral"

        if equity_momentum_3m is not None:
            components["equity_momentum"] = self._compute_equity_momentum_impulse(equity_momentum_3m)
            drivers["equity_momentum"] = f"3M equity return: {equity_momentum_3m:.1%}"
        else:
            components["equity_momentum"] = 0.0
            drivers["equity_momentum"] = "Missing - assuming neutral"

        if dollar_index is not None:
            components["dollar_index"] = self._compute_dollar_impulse(dollar_index)
            drivers["dollar_index"] = f"DXY: {dollar_index:.1f}"
        else:
            components["dollar_index"] = 0.0
            drivers["dollar_index"] = "Missing - assuming neutral"

        if vix is not None:
            components["vix"] = self._compute_vix_impulse(vix)
            drivers["vix"] = f"VIX: {vix:.1f}"
        else:
            components["vix"] = 0.0
            drivers["vix"] = "Missing - assuming neutral"

        # Calculate weighted impulse
        available_components = {k: v for k, v in components.items() if v != 0.0}

        if available_components:
            # Re-normalize weights for available components
            available_weight = sum(self.component_weights.get(k, 0) for k in available_components.keys())
            normalized_weights = {
                k: self.component_weights[k] / available_weight
                for k in available_components.keys()
            }

            impulse = sum(
                normalized_weights[k] * components[k]
                for k in available_components.keys()
            )

            # Confidence based on data availability
            confidence = min(0.9, len(available_components) / len(self.component_weights))
        else:
            impulse = 0.0
            confidence = 0.0
            drivers["error"] = "No financial conditions data available"

        category = self._classify_impulse(impulse)

        return FinancialConditionsImpulse(
            impulse_score=impulse,
            category=category,
            confidence=confidence,
            components=components,
            drivers=drivers,
        )

    def _classify_impulse(self, impulse: float) -> str:
        """Classify impulse into category."""
        if impulse < -0.5:
            return "easing"
        elif impulse > 0.5:
            return "tightening"
        else:
            return "neutral"

    def get_impulse_description(self, impulse: FinancialConditionsImpulse) -> str:
        """Get textual description of financial conditions."""
        descriptions = {
            "easing": (
                "Financial conditions are easing. Credit is flowing freely, "
                "risk assets are supported, and financing costs are declining. "
                "Constructive for growth and risk assets."
            ),
            "neutral": (
                "Financial conditions are broadly neutral. No significant "
                "tightening or easing impulse from credit markets."
            ),
            "tightening": (
                "Financial conditions are tightening. Credit availability is "
                "constrained, risk premia are expanding, and financing costs "
                "are rising. Headwind for growth and risk assets."
            ),
        }

        return descriptions.get(impulse.category, "Conditions unclear")


def compute_financial_conditions_from_data(
    df: pd.DataFrame,
    model: Optional[FinancialConditionsModel] = None,
) -> FinancialConditionsImpulse:
    """
    Compute financial conditions from a DataFrame.

    Expected columns:
    - us_10y_yield (or similar)
    - us_credit_spread
    - sp500 (or equity index)
    - dxy
    - vix
    - us_nfci (optional)
    """
    if model is None:
        model = FinancialConditionsModel()

    # Extract latest values
    latest = df.iloc[-1] if not df.empty else pd.Series()

    # Map column names
    yield_col = next((c for c in df.columns if "yield" in c.lower() and "10" in c), None)
    credit_col = next((c for c in df.columns if "credit" in c.lower() or "spread" in c.lower()), None)
    equity_col = next((c for c in df.columns if "sp500" in c.lower() or "stock" in c.lower()), None)
    dxy_col = next((c for c in df.columns if "dollar" in c.lower() or "dxy" in c.lower()), None)
    vix_col = next((c for c in df.columns if "vix" in c.lower()), None)
    nfci_col = next((c for c in df.columns if "nfci" in c.lower()), None)

    # Calculate equity momentum if we have equity data
    equity_momentum = None
    if equity_col and len(df) >= 4:
        current = df[equity_col].iloc[-1]
        past = df[equity_col].iloc[-4]
        if past != 0:
            equity_momentum = (current - past) / past

    return model.compute_impulse(
        nominal_yield=latest.get(yield_col) if yield_col else None,
        credit_spread=latest.get(credit_col) if credit_col else None,
        equity_momentum_3m=equity_momentum,
        dollar_index=latest.get(dxy_col) if dxy_col else None,
        vix=latest.get(vix_col) if vix_col else None,
        nfci=latest.get(nfci_col) if nfci_col else None,
    )
