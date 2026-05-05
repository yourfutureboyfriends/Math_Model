"""
Euro Area Macro Model

Euro Area macroeconomic model using ECB and Eurostat data.
"""

import logging
from datetime import datetime
from typing import Dict, Tuple

import pandas as pd

from .base_country_model import BaseCountryMacroModel

logger = logging.getLogger(__name__)


class EuroAreaMacroModel(BaseCountryMacroModel):
    """
    Euro Area macroeconomic model.

    Data sources:
    - ECB Data Portal
    - Eurostat
    - OECD
    """

    EURO_REGIMES = {
        "goldilocks": "Goldilocks (growth up, inflation stable)",
        "reflation": "Reflation (growth up, inflation up)",
        "slowdown": "Slowdown (growth down, inflation down)",
        "stagflation": "Stagflation (growth down, inflation up)",
        "policy_support": "Policy Support / Weak Demand",
        "mixed": "Mixed / Transition",
    }

    def __init__(self):
        super().__init__(
            country_code="EA",
            country_name="Euro Area",
            region="Europe",
            currency="EUR",
            data_sources=["ECB", "Eurostat", "OECD"],
        )
        self.inflation_target = 2.0
        self.neutral_rate_estimate = 2.0

    def load_data(self, as_of_date=None, use_live=False) -> bool:
        """Load Euro Area macro data."""
        self.macro_data = self.get_sample_data()
        return True

    def calculate_regime(self) -> Tuple[str, float]:
        """Determine Euro Area regime."""
        gdp = self.macro_data.get("gdp_growth", pd.Series([1.0])).iloc[-1]
        inflation = self.macro_data.get("cpi", pd.Series([2.4])).iloc[-1]

        growth_dev = gdp - 1.5  # Euro area trend lower
        inflation_dev = inflation - self.inflation_target

        if growth_dev < -0.5 and inflation_dev < 0:
            regime = "slowdown"
            conf = 0.75
        elif growth_dev < 0 and inflation_dev > 0.5:
            regime = "stagflation"
            conf = 0.7
        elif growth_dev > 0.5 and abs(inflation_dev) < 0.5:
            regime = "goldilocks"
            conf = 0.8
        elif growth_dev < -1.0:
            regime = "policy_support"
            conf = 0.7
        else:
            regime = "mixed"
            conf = 0.5

        return self.EURO_REGIMES[regime], conf

    def calculate_growth_momentum(self) -> Tuple[float, str]:
        gdp = self.macro_data.get("gdp_growth", pd.Series([1.0]))
        if len(gdp) >= 2:
            mom = gdp.iloc[-1] - gdp.iloc[-2]
            trend = "accelerating" if mom > 0.2 else "decelerating" if mom < -0.2 else "stable"
            return gdp.iloc[-1] - 1.5, trend
        return 0.0, "stable"

    def calculate_inflation_pressure(self) -> Tuple[float, str]:
        cpi = self.macro_data.get("cpi", pd.Series([2.4]))
        if len(cpi) >= 2:
            mom = cpi.iloc[-1] - cpi.iloc[-2]
            trend = "rising" if mom > 0.1 else "falling" if mom < -0.1 else "stable"
            return cpi.iloc[-1] - self.inflation_target, trend
        return 0.0, "stable"

    def calculate_policy_stance(self) -> Tuple[str, float]:
        rate = self.macro_data.get("policy_rate", pd.Series([4.0])).iloc[-1]
        taylor = self.neutral_rate_estimate + 1.5 * (self.macro_data.get("cpi", pd.Series([2.4])).iloc[-1] - self.inflation_target)
        gap = rate - taylor

        if gap > 1.0:
            stance = "tight"
        elif gap < -0.5:
            stance = "loose"
        else:
            stance = "neutral"
        return stance, gap

    def calculate_financial_conditions(self) -> float:
        return 0.4

    def calculate_credit_stress(self) -> float:
        return 0.25

    def calculate_recession_risk(self) -> Tuple[float, float]:
        gdp = self.macro_data.get("gdp_growth", pd.Series([1.0])).iloc[-1]
        if gdp < 0.5:
            return 0.4, 0.35
        return 0.2, 0.2

    def calculate_currency_pressure(self) -> Tuple[float, str]:
        return -0.1, "stable"

    def get_sample_data(self) -> Dict[str, pd.Series]:
        dates = pd.date_range(end=datetime.now(), periods=24, freq="ME")
        return {
            "gdp_growth": pd.Series([1.5, 1.4, 1.3, 1.2, 1.1, 1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4,
                                    0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5], index=dates),
            "cpi": pd.Series([2.1, 2.3, 2.5, 2.7, 2.6, 2.5, 2.4, 2.3, 2.2, 2.1, 2.0, 1.9,
                            2.0, 2.1, 2.2, 2.3, 2.4, 2.5, 2.4, 2.3, 2.2, 2.1, 2.2], index=dates),
            "policy_rate": pd.Series([2.0, 2.25, 2.5, 3.0, 3.5, 4.0, 4.25, 4.5, 4.5, 4.25, 4.0, 3.75,
                                   3.5, 3.25, 3.0, 2.75, 2.5, 2.25, 2.0, 1.75, 1.5, 1.25, 1.0], index=dates),
        }
