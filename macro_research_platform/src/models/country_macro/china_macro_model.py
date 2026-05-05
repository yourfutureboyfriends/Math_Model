"""
China Macro Model

China macroeconomic model with unique regime labels.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import pandas as pd

from .base_country_model import BaseCountryMacroModel

logger = logging.getLogger(__name__)


class ChinaMacroModel(BaseCountryMacroModel):
    """
    China macroeconomic model.

    China-specific regimes:
    - Policy Support / Weak Demand
    - Deflationary Pressure
    - Credit Stress / Property Drag
    - Reflation
    - Mixed / Transition
    """

    CHINA_REGIMES = {
        "policy_support": "Policy Support / Weak Demand",
        "deflationary": "Deflationary Pressure",
        "credit_stress": "Credit Stress / Property Drag",
        "reflation": "Reflation",
        "mixed": "Mixed / Transition",
    }

    def __init__(self):
        super().__init__(
            country_code="CN",
            country_name="China",
            region="Asia",
            currency="CNY",
            data_sources=["OECD", "World Bank", "IMF", "PMI"],
        )
        self.inflation_target = 3.0

    def load_data(self, as_of_date=None, use_live=False):
        """Load China macro data."""
        self.macro_data = self.get_sample_data()
        return True

    def calculate_regime(self) -> Tuple[str, float]:
        """Determine China regime."""
        # Simplified logic
        gdp = self.macro_data.get("gdp_growth", pd.Series([4.5])).iloc[-1]
        inflation = self.macro_data.get("cpi", pd.Series([0.2])).iloc[-1]
        credit = self.macro_data.get("credit_growth", pd.Series([9.0])).iloc[-1]

        if gdp < 4.0 and inflation < 0.5 and credit < 10:
            regime = "deflationary"
            conf = 0.75
        elif gdp < 4.5 and credit < 10:
            regime = "policy_support"
            conf = 0.7
        elif credit > 12:
            regime = "credit_stress"
            conf = 0.65
        elif gdp > 5.0 and inflation > 1.5:
            regime = "reflation"
            conf = 0.75
        else:
            regime = "mixed"
            conf = 0.5

        return self.CHINA_REGIMES[regime], conf

    def calculate_growth_momentum(self) -> Tuple[float, str]:
        gdp = self.macro_data.get("gdp_growth", pd.Series([4.5]))
        if len(gdp) >= 2:
            mom = gdp.iloc[-1] - gdp.iloc[-2]
            trend = "accelerating" if mom > 0.3 else "decelerating" if mom < -0.3 else "stable"
            return gdp.iloc[-1] - 5.0, trend
        return 0.0, "stable"

    def calculate_inflation_pressure(self) -> Tuple[float, str]:
        cpi = self.macro_data.get("cpi", pd.Series([0.2]))
        if len(cpi) >= 2:
            mom = cpi.iloc[-1] - cpi.iloc[-2]
            trend = "rising" if mom > 0.1 else "falling" if mom < -0.1 else "stable"
            return cpi.iloc[-1] - self.inflation_target, trend
        return 0.0, "stable"

    def calculate_policy_stance(self) -> Tuple[str, float]:
        return "loose", -1.5  # China typically accommodative

    def calculate_financial_conditions(self) -> float:
        return 0.3

    def calculate_credit_stress(self) -> float:
        credit = self.macro_data.get("credit_growth", pd.Series([9.0])).iloc[-1]
        if credit < 8:
            return 0.7
        elif credit < 10:
            return 0.5
        return 0.3

    def calculate_recession_risk(self) -> Tuple[float, float]:
        gdp = self.macro_data.get("gdp_growth", pd.Series([4.5])).iloc[-1]
        if gdp < 3.0:
            return 0.4, 0.35
        return 0.2, 0.15

    def calculate_currency_pressure(self) -> Tuple[float, str]:
        return 0.2, "stable"

    def get_sample_data(self) -> Dict[str, pd.Series]:
        from datetime import datetime
        dates = pd.date_range(end=datetime.now(), periods=24, freq="ME")
        return {
            "gdp_growth": pd.Series([5.5, 5.3, 5.1, 4.9, 4.7, 4.5, 4.3, 4.2, 4.1, 4.0, 3.9, 3.8,
                                    3.9, 4.0, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9], index=dates),
            "cpi": pd.Series([0.1, -0.1, -0.2, 0.0, 0.2, 0.3, 0.4, 0.5, 0.4, 0.3, 0.2, 0.1,
                            0.0, -0.1, -0.2, 0.1, 0.3, 0.5, 0.6, 0.5, 0.4, 0.3, 0.2], index=dates),
            "credit_growth": pd.Series([10.5, 10.2, 9.8, 9.5, 9.2, 9.0, 8.8, 8.5, 8.3, 8.0, 7.8, 7.5,
                                       7.8, 8.0, 8.2, 8.5, 8.8, 9.0, 9.2, 9.5, 9.8, 10.0, 10.2], index=dates),
        }
