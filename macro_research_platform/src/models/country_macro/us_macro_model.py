"""
US Macro Model

United States macroeconomic model using FRED, BEA, and BLS data.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .base_country_model import BaseCountryMacroModel, CountryMacroOutput

logger = logging.getLogger(__name__)


class USMacroModel(BaseCountryMacroModel):
    """
    US macroeconomic model.

    Data sources:
    - FRED (Federal Reserve Economic Data)
    - ALFRED (Archival FRED for vintage data)
    - BEA (Bureau of Economic Analysis)
    - BLS (Bureau of Labor Statistics)
    """

    # US-specific regime labels
    US_REGIMES = {
        "goldilocks": "Goldilocks (growth up, inflation stable)",
        "reflation": "Reflation (growth up, inflation up)",
        "inflation_pressure": "Inflation Pressure / Late-Cycle",
        "slowdown": "Slowdown (growth down, inflation down)",
        "stagflation": "Stagflation (growth down, inflation up)",
        "policy_support": "Policy Support / Weak Demand",
        "mixed": "Mixed / Transition",
    }

    def __init__(self):
        super().__init__(
            country_code="US",
            country_name="United States",
            region="North America",
            currency="USD",
            data_sources=["FRED", "ALFRED", "BEA", "BLS"],
        )

        # US-specific parameters
        self.inflation_target = 2.0
        self.neutral_rate_estimate = 2.5
        self.nairu = 4.0

        # Key FRED series
        self.series_ids = {
            "gdp": "GDPC1",
            "gdp_growth": "A191RL1A225NBEA",
            "unemployment": "UNRATE",
            "payrolls": "PAYEMS",
            "cpi": "CPIAUCSL",
            "core_cpi": "CPILFESL",
            "pce": "PCEPI",
            "core_pce": "PCEPILFE",
            "fedfunds": "FEDFUNDS",
            "teny_yield": "DGS10",
            "twoy_yield": "DGS2",
            "credit_spread": "BAA10Y",
            "dollar_index": "DTWEXBGS",
            "vix": "VIXCLS",
        }

    def load_data(
        self,
        as_of_date: Optional[datetime] = None,
        use_live: bool = False,
    ) -> bool:
        """Load US macro data."""
        # For now, use sample data
        self.macro_data = self.get_sample_data()
        return True

    def calculate_regime(self) -> Tuple[str, float]:
        """Determine US macro regime."""
        # Get latest values
        gdp_growth = self.macro_data.get("gdp_growth", pd.Series([2.0])).iloc[-1]
        inflation = self.macro_data.get("core_pce", pd.Series([2.5])).iloc[-1]

        # Calculate deviations
        growth_dev = gdp_growth - self.growth_trend_estimate
        inflation_dev = inflation - self.inflation_target

        # Classify regime
        if growth_dev > 0.5 and abs(inflation_dev) < 0.5:
            regime = "goldilocks"
            confidence = 0.8
        elif growth_dev > 0.5 and inflation_dev > 0.5:
            regime = "reflation"
            confidence = 0.75
        elif growth_dev < -0.5 and inflation_dev > 0.5:
            regime = "stagflation"
            confidence = 0.7
        elif growth_dev < -0.5 and inflation_dev < 0.5:
            regime = "slowdown"
            confidence = 0.75
        elif inflation_dev > 1.0 and growth_dev > 0:
            regime = "inflation_pressure"
            confidence = 0.8
        elif growth_dev < -1.0:
            regime = "policy_support"
            confidence = 0.6
        else:
            regime = "mixed"
            confidence = 0.5

        return self.US_REGIMES.get(regime, regime), confidence

    def calculate_growth_momentum(self) -> Tuple[float, str]:
        """Calculate US growth momentum."""
        gdp = self.macro_data.get("gdp_growth", pd.Series([2.0]))
        if len(gdp) >= 2:
            mom = gdp.iloc[-1] - gdp.iloc[-2]
            trend = "accelerating" if mom > 0.3 else "decelerating" if mom < -0.3 else "stable"
            return gdp.iloc[-1] - self.growth_trend_estimate, trend
        return 0.0, "stable"

    def calculate_inflation_pressure(self) -> Tuple[float, str]:
        """Calculate US inflation pressure."""
        pce = self.macro_data.get("core_pce", pd.Series([2.5]))
        if len(pce) >= 2:
            mom = pce.iloc[-1] - pce.iloc[-2]
            trend = "rising" if mom > 0.1 else "falling" if mom < -0.1 else "stable"
            return pce.iloc[-1] - self.inflation_target, trend
        return 0.0, "stable"

    def calculate_policy_stance(self) -> Tuple[str, float]:
        """Calculate US policy stance."""
        fedfunds = self.macro_data.get("fedfunds", pd.Series([5.25])).iloc[-1]
        inflation = self.macro_data.get("core_pce", pd.Series([2.5])).iloc[-1]

        # Taylor rule implied rate
        taylor_rate = self.neutral_rate_estimate + 1.5 * (inflation - self.inflation_target)
        policy_gap = fedfunds - taylor_rate

        if policy_gap > 1.5:
            stance = "tight"
        elif policy_gap > 0.5:
            stance = "neutral-tight"
        elif policy_gap < -1.5:
            stance = "loose"
        elif policy_gap < -0.5:
            stance = "neutral-loose"
        else:
            stance = "neutral"

        return stance, policy_gap

    def calculate_financial_conditions(self) -> float:
        """Calculate US financial conditions."""
        credit_spread = self.macro_data.get("credit_spread", pd.Series([2.0])).iloc[-1]
        vix = self.macro_data.get("vix", pd.Series([20])).iloc[-1]

        # Simple FCI
        fci = (credit_spread / 100) * 0.5 + (vix / 100) * 0.5
        return fci

    def calculate_credit_stress(self) -> float:
        """Calculate US credit stress."""
        credit_spread = self.macro_data.get("credit_spread", pd.Series([2.0])).iloc[-1]
        # Normalize to 0-1
        stress = min(1.0, max(0.0, (credit_spread - 1.5) / 4.0))
        return stress

    def calculate_recession_risk(self) -> Tuple[float, float]:
        """Calculate US recession risk."""
        unemployment = self.macro_data.get("unemployment", pd.Series([4.0]))
        if len(unemployment) >= 13:
            # Sahm rule
            current = unemployment.iloc[-1]
            min_12m = unemployment.iloc[-13:-1].min()
            sahm = current - min_12m

            if sahm > 0.5:
                return 0.8, 0.7
            elif sahm > 0.3:
                return 0.5, 0.4

        return 0.15, 0.2

    def calculate_currency_pressure(self) -> Tuple[float, str]:
        """Calculate USD pressure."""
        dollar = self.macro_data.get("dollar_index", pd.Series([100]))
        if len(dollar) >= 2:
            change = dollar.iloc[-1] - dollar.iloc[-2]
            trend = "appreciating" if change > 1 else "depreciating" if change < -1 else "stable"
            return change, trend
        return 0.0, "stable"

    def get_sample_data(self) -> Dict[str, pd.Series]:
        """Generate sample US data."""
        dates = pd.date_range(end=datetime.now(), periods=24, freq="ME")

        return {
            "gdp_growth": pd.Series([2.1, 2.3, 2.5, 2.4, 2.2, 2.1, 1.9, 1.8, 1.9, 2.0, 2.1, 2.2,
                                    2.3, 2.4, 2.5, 2.3, 2.1, 1.9, 1.8, 1.9, 2.0, 2.1, 2.2],
                                   index=dates, name="gdp_growth"),
            "core_pce": pd.Series([2.1, 2.2, 2.3, 2.5, 2.7, 2.9, 3.1, 3.2, 3.1, 3.0, 2.9, 2.8,
                                   2.7, 2.6, 2.5, 2.6, 2.7, 2.8, 2.9, 2.9, 2.8, 2.7, 2.6],
                                  index=dates, name="core_pce"),
            "fedfunds": pd.Series([0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0,
                                   5.25, 5.5, 5.5, 5.5, 5.25, 5.0, 4.75, 4.5, 4.25, 4.0, 3.75],
                                  index=dates, name="fedfunds"),
            "unemployment": pd.Series([3.5, 3.6, 3.7, 3.8, 3.9, 4.0, 4.1, 4.2, 4.3, 4.4, 4.3, 4.2,
                                     4.1, 4.0, 3.9, 3.8, 3.9, 4.0, 4.1, 4.2, 4.3, 4.4, 4.5],
                                    index=dates, name="unemployment"),
            "credit_spread": pd.Series([1.5, 1.6, 1.7, 1.8, 1.9, 2.0, 2.1, 2.2, 2.3, 2.4, 2.3, 2.2,
                                        2.1, 2.0, 1.9, 1.8, 1.9, 2.0, 2.1, 2.2, 2.3, 2.4, 2.5],
                                       index=dates, name="credit_spread"),
            "vix": pd.Series([18, 19, 20, 22, 24, 26, 28, 25, 22, 20, 19, 18,
                              17, 16, 17, 18, 19, 20, 21, 22, 21, 20, 19],
                             index=dates, name="vix"),
            "dollar_index": pd.Series([96, 97, 98, 100, 102, 104, 106, 105, 104, 103, 102, 101,
                                      100, 101, 102, 103, 104, 105, 106, 107, 106, 105, 104],
                                     index=dates, name="dollar_index"),
        }
