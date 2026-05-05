"""
Japan Macro Model

Japan macroeconomic model with unique regime labels.
"""

import logging
from datetime import datetime
from typing import Dict, Tuple

import pandas as pd

from .base_country_model import BaseCountryMacroModel

logger = logging.getLogger(__name__)


class JapanMacroModel(BaseCountryMacroModel):
    """
    Japan macroeconomic model.

    Japan-specific regimes:
    - Reflation / Policy Normalisation
    - Weak Yen Inflation Pressure
    - Yield Curve Normalisation
    - Policy Support / Weak Demand
    - Mixed
    """

    JAPAN_REGIMES = {
        "reflation": "Reflation / Policy Normalisation",
        "weak_yen": "Weak Yen Inflation Pressure",
        "yc_normalisation": "Yield Curve Normalisation",
        "policy_support": "Policy Support / Weak Demand",
        "mixed": "Mixed / Transition",
    }

    def __init__(self):
        super().__init__(
            country_code="JP",
            country_name="Japan",
            region="Asia",
            currency="JPY",
            data_sources=["OECD", "IMF", "World Bank", "BoJ"],
        )
        self.inflation_target = 2.0

    def load_data(self, as_of_date=None, use_live=False) -> bool:
        self.macro_data = self.get_sample_data()
        return True

    def calculate_regime(self) -> Tuple[str, float]:
        inflation = self.macro_data.get("cpi", pd.Series([2.2])).iloc[-1]
        gdp = self.macro_data.get("gdp_growth", pd.Series([0.8])).iloc[-1]

        if inflation > 2.0 and gdp > 0.5:
            regime = "reflation"
            conf = 0.75
        elif inflation > 2.5:
            regime = "weak_yen"
            conf = 0.7
        elif gdp < 0.3 and inflation < 1.5:
            regime = "policy_support"
            conf = 0.65
        else:
            regime = "mixed"
            conf = 0.5

        return self.JAPAN_REGIMES[regime], conf

    def calculate_growth_momentum(self) -> Tuple[float, str]:
        gdp = self.macro_data.get("gdp_growth", pd.Series([0.8]))
        if len(gdp) >= 2:
            mom = gdp.iloc[-1] - gdp.iloc[-2]
            trend = "accelerating" if mom > 0.2 else "decelerating" if mom < -0.2 else "stable"
            return gdp.iloc[-1] - 1.0, trend
        return 0.0, "stable"

    def calculate_inflation_pressure(self) -> Tuple[float, str]:
        cpi = self.macro_data.get("cpi", pd.Series([2.2]))
        if len(cpi) >= 2:
            mom = cpi.iloc[-1] - cpi.iloc[-2]
            trend = "rising" if mom > 0.05 else "falling" if mom < -0.05 else "stable"
            return cpi.iloc[-1] - self.inflation_target, trend
        return 0.0, "stable"

    def calculate_policy_stance(self) -> Tuple[str, float]:
        return "loose", -1.0

    def calculate_financial_conditions(self) -> float:
        return 0.2

    def calculate_credit_stress(self) -> float:
        return 0.15

    def calculate_recession_risk(self) -> Tuple[float, float]:
        return 0.15, 0.12

    def calculate_currency_pressure(self) -> Tuple[float, str]:
        return -0.5, "depreciating"

    def get_sample_data(self) -> Dict[str, pd.Series]:
        dates = pd.date_range(end=datetime.now(), periods=24, freq="ME")
        return {
            "gdp_growth": pd.Series([1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1,
                                    1.2, 1.1, 1.0, 0.9, 0.8, 0.7, 0.8, 0.9, 1.0, 1.1, 1.0], index=dates),
            "cpi": pd.Series([0.5, 0.8, 1.0, 1.3, 1.6, 1.9, 2.2, 2.5, 2.4, 2.3, 2.2, 2.1,
                            2.0, 2.1, 2.2, 2.3, 2.4, 2.3, 2.2, 2.1, 2.0, 1.9, 2.0], index=dates),
        }
