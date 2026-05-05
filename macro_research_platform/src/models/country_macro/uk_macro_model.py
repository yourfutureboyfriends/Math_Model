"""
UK Macro Model

United Kingdom macroeconomic model.
"""

import logging
from datetime import datetime
from typing import Dict, Tuple

import pandas as pd

from .base_country_model import BaseCountryMacroModel

logger = logging.getLogger(__name__)


class UKMacroModel(BaseCountryMacroModel):
    """UK macroeconomic model using ONS and BoE data."""

    UK_REGIMES = {
        "goldilocks": "Goldilocks",
        "reflation": "Reflation",
        "slowdown": "Slowdown",
        "stagflation": "Stagflation",
        "policy_support": "Policy Support",
        "mixed": "Mixed / Transition",
    }

    def __init__(self):
        super().__init__(
            country_code="UK",
            country_name="United Kingdom",
            region="Europe",
            currency="GBP",
            data_sources=["ONS", "Bank of England"],
        )
        self.inflation_target = 2.0

    def load_data(self, as_of_date=None, use_live=False) -> bool:
        self.macro_data = self.get_sample_data()
        return True

    def calculate_regime(self) -> Tuple[str, float]:
        gdp = self.macro_data.get("gdp_growth", pd.Series([0.5])).iloc[-1]
        inflation = self.macro_data.get("cpi", pd.Series([3.2])).iloc[-1]

        if gdp < 0.5 and inflation > 2.5:
            regime = "stagflation"
            conf = 0.7
        elif gdp < 0.5:
            regime = "slowdown"
            conf = 0.7
        elif gdp > 1.5 and inflation < 2.5:
            regime = "goldilocks"
            conf = 0.75
        else:
            regime = "mixed"
            conf = 0.5

        return self.UK_REGIMES[regime], conf

    def calculate_growth_momentum(self) -> Tuple[float, str]:
        gdp = self.macro_data.get("gdp_growth", pd.Series([0.5]))
        if len(gdp) >= 2:
            mom = gdp.iloc[-1] - gdp.iloc[-2]
            trend = "accelerating" if mom > 0.2 else "decelerating" if mom < -0.2 else "stable"
            return gdp.iloc[-1] - 1.0, trend
        return 0.0, "stable"

    def calculate_inflation_pressure(self) -> Tuple[float, str]:
        cpi = self.macro_data.get("cpi", pd.Series([3.2]))
        if len(cpi) >= 2:
            mom = cpi.iloc[-1] - cpi.iloc[-2]
            trend = "rising" if mom > 0.1 else "falling" if mom < -0.1 else "stable"
            return cpi.iloc[-1] - self.inflation_target, trend
        return 0.0, "stable"

    def calculate_policy_stance(self) -> Tuple[str, float]:
        rate = self.macro_data.get("policy_rate", pd.Series([5.25])).iloc[-1]
        return "tight", rate - 3.0

    def calculate_financial_conditions(self) -> float:
        return 0.45

    def calculate_credit_stress(self) -> float:
        return 0.35

    def calculate_recession_risk(self) -> Tuple[float, float]:
        return 0.3, 0.25

    def calculate_currency_pressure(self) -> Tuple[float, str]:
        return 0.0, "stable"

    def get_sample_data(self) -> Dict[str, pd.Series]:
        dates = pd.date_range(end=datetime.now(), periods=24, freq="ME")
        return {
            "gdp_growth": pd.Series([1.5, 1.3, 1.1, 0.9, 0.7, 0.5, 0.3, 0.2, 0.3, 0.4, 0.5, 0.6,
                                    0.7, 0.8, 0.9, 1.0, 1.1, 1.0, 0.9, 0.8, 0.7, 0.6, 0.5], index=dates),
            "cpi": pd.Series([9.0, 7.0, 5.5, 4.0, 3.0, 2.5, 2.3, 2.2, 2.8, 3.2, 3.5, 3.8,
                            4.0, 3.8, 3.5, 3.2, 3.0, 2.8, 2.6, 2.4, 2.3, 2.2, 2.1], index=dates),
            "policy_rate": pd.Series([3.0, 3.5, 4.0, 4.5, 5.0, 5.25, 5.5, 5.25, 5.0, 4.75, 4.5, 4.25,
                                    4.0, 3.75, 3.5, 3.25, 3.0, 2.75, 2.5, 2.25, 2.0, 1.75, 1.5], index=dates),
        }
