"""
Emerging Markets Macro Model

Aggregate model for Emerging Markets with special regime labels.
"""

import logging
from datetime import datetime
from typing import Dict, Tuple

import pandas as pd

from .base_country_model import BaseCountryMacroModel

logger = logging.getLogger(__name__)


class EmergingMarketsModel(BaseCountryMacroModel):
    """
    Emerging Markets macroeconomic model.

    EM-specific regimes:
    - Dollar Pressure
    - Commodity Support
    - External Financing Stress
    - Carry Support
    - Policy Support / Weak Demand
    - Mixed
    """

    EM_REGIMES = {
        "dollar_pressure": "Dollar Pressure",
        "commodity_support": "Commodity Support",
        "external_financing_stress": "External Financing Stress",
        "carry_support": "Carry Support",
        "policy_support": "Policy Support / Weak Demand",
        "mixed": "Mixed / Transition",
    }

    def __init__(self):
        super().__init__(
            country_code="EM",
            country_name="Emerging Markets",
            region="Emerging",
            currency="EM_FX",
            data_sources=["IMF", "World Bank", "OECD"],
        )
        self.inflation_target = 4.0  # EM typically higher

    def load_data(self, as_of_date=None, use_live=False) -> bool:
        self.macro_data = self.get_sample_data()
        return True

    def calculate_regime(self) -> Tuple[str, float]:
        """Determine EM regime based on external factors."""
        dollar = self.macro_data.get("dollar_index", pd.Series([100])).iloc[-1]
        commodity = self.macro_data.get("commodity_index", pd.Series([100])).iloc[-1]
        gdp = self.macro_data.get("gdp_growth", pd.Series([3.5])).iloc[-1]

        if dollar > 105:
            regime = "dollar_pressure"
            conf = 0.75
        elif commodity > 110 and dollar < 100:
            regime = "commodity_support"
            conf = 0.7
        elif gdp < 3.0:
            regime = "policy_support"
            conf = 0.65
        else:
            regime = "mixed"
            conf = 0.5

        return self.EM_REGIMES[regime], conf

    def calculate_growth_momentum(self) -> Tuple[float, str]:
        gdp = self.macro_data.get("gdp_growth", pd.Series([3.5]))
        if len(gdp) >= 2:
            mom = gdp.iloc[-1] - gdp.iloc[-2]
            trend = "accelerating" if mom > 0.3 else "decelerating" if mom < -0.3 else "stable"
            return gdp.iloc[-1] - 4.0, trend
        return 0.0, "stable"

    def calculate_inflation_pressure(self) -> Tuple[float, str]:
        cpi = self.macro_data.get("cpi", pd.Series([4.5]))
        if len(cpi) >= 2:
            mom = cpi.iloc[-1] - cpi.iloc[-2]
            trend = "rising" if mom > 0.15 else "falling" if mom < -0.15 else "stable"
            return cpi.iloc[-1] - self.inflation_target, trend
        return 0.0, "stable"

    def calculate_policy_stance(self) -> Tuple[str, float]:
        return "neutral", 0.0

    def calculate_financial_conditions(self) -> float:
        dollar = self.macro_data.get("dollar_index", pd.Series([100])).iloc[-1]
        # Higher dollar = tighter EM financial conditions
        return max(0, (dollar - 95) / 20)

    def calculate_credit_stress(self) -> float:
        return 0.4

    def calculate_recession_risk(self) -> Tuple[float, float]:
        gdp = self.macro_data.get("gdp_growth", pd.Series([3.5])).iloc[-1]
        if gdp < 2.5:
            return 0.35, 0.3
        return 0.2, 0.18

    def calculate_currency_pressure(self) -> Tuple[float, str]:
        dollar = self.macro_data.get("dollar_index", pd.Series([100]))
        if len(dollar) >= 2:
            change = dollar.iloc[-1] - dollar.iloc[-2]
            if change > 1:
                return 0.5, "depreciating"
            elif change < -1:
                return -0.3, "appreciating"
        return 0.0, "stable"

    def get_sample_data(self) -> Dict[str, pd.Series]:
        dates = pd.date_range(end=datetime.now(), periods=24, freq="ME")
        return {
            "gdp_growth": pd.Series([5.0, 4.8, 4.5, 4.2, 4.0, 3.8, 3.6, 3.5, 3.4, 3.3, 3.5, 3.8,
                                    4.0, 4.2, 4.0, 3.8, 3.6, 3.4, 3.2, 3.3, 3.5, 3.8, 4.0], index=dates),
            "cpi": pd.Series([6.0, 5.5, 5.0, 4.5, 4.2, 4.0, 3.8, 3.6, 3.5, 3.8, 4.2, 4.5,
                            4.8, 5.0, 4.8, 4.5, 4.2, 4.0, 3.8, 3.6, 3.5, 3.4, 3.5], index=dates),
            "dollar_index": pd.Series([96, 97, 98, 100, 102, 104, 106, 105, 104, 103, 102, 101,
                                      100, 101, 102, 103, 104, 105, 106, 107, 106, 105, 104], index=dates),
            "commodity_index": pd.Series([100, 102, 105, 108, 110, 112, 115, 118, 120, 118, 116, 114,
                                         112, 110, 108, 106, 104, 102, 100, 98, 96, 98, 100], index=dates),
        }
