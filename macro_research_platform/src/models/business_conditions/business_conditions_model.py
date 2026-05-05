"""
Business Conditions Nowcast Model

Implements diffusion index approach inspired by Stock and Watson (2002),
Aruoba-Diebold-Scotti (2009), and Giannone-Reichlin-Small (2008).

Estimates real-time growth momentum before GDP confirms it using:
- Labour market indicators
- Production indicators
- Consumption indicators
- Financial confirmation signals

Output:
- Business conditions score (-3 to +3)
- Growth momentum direction
- Top positive drivers
- Top negative drivers
- Confidence level based on data coverage
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class BusinessConditionsResult:
    """Output from business conditions nowcast."""
    score: float  # -3 to +3
    direction: str  # improving/stable/deteriorating
    labour_score: float
    production_score: float
    consumption_score: float
    financial_score: float
    top_positive: List[str]
    top_negative: List[str]
    confidence: str  # high/moderate/low
    latest_data_date: Optional[datetime]
    coverage_pct: float


class BusinessConditionsModel:
    """
    Real-time business conditions nowcast using diffusion index.

    Financial context:
      GDP is released quarterly with a lag. Business conditions change
      in real time. A nowcast model bridges this gap by combining:
      1. Labour market data (monthly, timely)
      2. Production data (monthly, leading)
      3. Consumption proxies (monthly)
      4. Financial confirmation (daily, market-implied)

    Methodology follows Stock-Watson diffusion indexes and
    Giannone-Reichlin-Small nowcasting framework.
    """

    # Default weights based on research literature
    DEFAULT_WEIGHTS = {
        "labour": 0.30,
        "production": 0.25,
        "consumption": 0.20,
        "income": 0.10,
        "financial": 0.15,
    }

    def __init__(self, weights: Optional[Dict[str, float]] = None):
        self.weights = weights or self.DEFAULT_WEIGHTS
        self._validate_weights()

    def _validate_weights(self):
        """Ensure weights sum to 1.0."""
        total = sum(self.weights.values())
        if abs(total - 1.0) > 0.01:
            logger.warning(f"Weights sum to {total:.2f}, normalizing")
            factor = 1.0 / total
            for k in self.weights:
                self.weights[k] *= factor

    def nowcast(self, df: pd.DataFrame) -> BusinessConditionsResult:
        """
        Generate business conditions nowcast from DataFrame.

        Args:
            df: DataFrame with transformed macro indicators (z-scores)

        Returns:
            BusinessConditionsResult with score and components
        """
        # Calculate component scores
        labour = self._calc_labour_score(df)
        production = self._calc_production_score(df)
        consumption = self._calc_consumption_score(df)
        income = self._calc_income_score(df)
        financial = self._calc_financial_score(df)

        # Weighted composite
        score = (
            self.weights["labour"] * labour +
            self.weights["production"] * production +
            self.weights["consumption"] * consumption +
            self.weights["income"] * income +
            self.weights["financial"] * financial
        )

        # Direction based on 3-month change
        direction = self._calc_direction(df, score)

        # Drivers
        top_positive, top_negative = self._identify_drivers(df)

        # Confidence
        confidence, coverage = self._calc_confidence(df)

        # Latest date
        latest_date = df.index.max() if not df.empty else None

        return BusinessConditionsResult(
            score=score,
            direction=direction,
            labour_score=labour,
            production_score=production,
            consumption_score=consumption,
            financial_score=financial,
            top_positive=top_positive,
            top_negative=top_negative,
            confidence=confidence,
            latest_data_date=latest_date,
            coverage_pct=coverage,
        )

    def _calc_labour_score(self, df: pd.DataFrame) -> float:
        """Calculate labour market component."""
        indicators = []

        # Unemployment (inverted - higher = worse)
        if "us_unemployment_rate_zscore" in df.columns:
            indicators.append(-df["us_unemployment_rate_zscore"].iloc[-1])

        # Check if we have any valid indicators
        if not indicators:
            return 0.0

        return np.nanmean(indicators)

    def _calc_production_score(self, df: pd.DataFrame) -> float:
        """Calculate production component."""
        indicators = []

        if "us_industrial_production_zscore" in df.columns:
            indicators.append(df["us_industrial_production_zscore"].iloc[-1])

        if not indicators:
            return 0.0

        return np.nanmean(indicators)

    def _calc_consumption_score(self, df: pd.DataFrame) -> float:
        """Calculate consumption component."""
        indicators = []

        if "us_retail_sales_zscore" in df.columns:
            indicators.append(df["us_retail_sales_zscore"].iloc[-1])

        if not indicators:
            return 0.0

        return np.nanmean(indicators)

    def _calc_income_score(self, df: pd.DataFrame) -> float:
        """Calculate income component."""
        # Placeholder - would need wage/personal income data
        return 0.0

    def _calc_financial_score(self, df: pd.DataFrame) -> float:
        """Calculate financial confirmation component."""
        indicators = []

        # Yield curve (steeper = better)
        if "us_10y_yield_zscore" in df.columns and "us_2y_yield_zscore" in df.columns:
            curve = df["us_10y_yield"].iloc[-1] - df["us_2y_yield"].iloc[-1]
            # Normalize roughly
            indicators.append(curve * 0.5)

        # Credit spreads (lower = better, inverted)
        if "baa_credit_spread_zscore" in df.columns:
            indicators.append(-df["baa_credit_spread_zscore"].iloc[-1])

        # Equity momentum
        if "sp500_zscore" in df.columns:
            indicators.append(df["sp500_zscore"].iloc[-1])

        if not indicators:
            return 0.0

        return np.nanmean(indicators)

    def _calc_direction(self, df: pd.DataFrame, current_score: float) -> str:
        """Calculate direction based on recent trend."""
        if len(df) < 4:
            return "insufficient_data"

        # Calculate historical composite to get trend
        recent = self._calc_historical_score(df.iloc[-4:])
        past = self._calc_historical_score(df.iloc[-8:-4])

        delta = recent - past

        if delta > 0.2:
            return "improving"
        elif delta < -0.2:
            return "deteriorating"
        else:
            return "stable"

    def _calc_historical_score(self, df_window: pd.DataFrame) -> float:
        """Calculate average score over a window."""
        scores = []

        for idx in range(len(df_window)):
            row = df_window.iloc[idx]
            s = 0
            n = 0

            if "us_unemployment_rate_zscore" in df_window.columns:
                s += -row["us_unemployment_rate_zscore"]
                n += 1
            if "us_industrial_production_zscore" in df_window.columns:
                s += row["us_industrial_production_zscore"]
                n += 1
            if "us_retail_sales_zscore" in df_window.columns:
                s += row["us_retail_sales_zscore"]
                n += 1

            if n > 0:
                scores.append(s / n)

        return np.nanmean(scores) if scores else 0.0

    def _identify_drivers(self, df: pd.DataFrame) -> Tuple[List[str], List[str]]:
        """Identify top positive and negative drivers."""
        drivers = []

        indicator_map = {
            "us_unemployment_rate_zscore": ("Unemployment", -1),  # inverted
            "us_industrial_production_zscore": ("Industrial Production", 1),
            "us_retail_sales_zscore": ("Retail Sales", 1),
            "us_cpi_zscore": ("CPI", 0),  # neutral for growth
            "us_10y_yield_zscore": ("10Y Yield", 0),
            "baa_credit_spread_zscore": ("Credit Spreads", -1),  # inverted
            "sp500_zscore": ("Equity Market", 1),
        }

        for col, (name, direction) in indicator_map.items():
            if col in df.columns:
                val = df[col].iloc[-1]
                if not np.isnan(val):
                    drivers.append((name, val * direction))

        # Sort by absolute impact
        drivers.sort(key=lambda x: x[1], reverse=True)

        top_positive = [d[0] for d in drivers if d[1] > 0.3][:3]
        top_negative = [d[0] for d in drivers if d[1] < -0.3][:3]

        return top_positive, top_negative

    def _calc_confidence(self, df: pd.DataFrame) -> Tuple[str, float]:
        """Calculate confidence based on data coverage."""
        required = [
            "us_unemployment_rate_zscore",
            "us_industrial_production_zscore",
            "us_retail_sales_zscore",
        ]

        available = sum(1 for r in required if r in df.columns)
        coverage = available / len(required)

        if coverage >= 0.9:
            return "high", coverage * 100
        elif coverage >= 0.6:
            return "moderate", coverage * 100
        else:
            return "low", coverage * 100


def get_business_conditions_summary(result: BusinessConditionsResult) -> str:
    """Generate human-readable summary."""
    if result.confidence == "low":
        return f"Business conditions: Insufficient data (coverage: {result.coverage_pct:.0f}%)"

    direction_desc = {
        "improving": "improving momentum",
        "stable": "stable momentum",
        "deteriorating": "weakening momentum",
        "insufficient_data": "unclear trend",
    }

    summary = f"Business conditions: {direction_desc.get(result.direction, result.direction)}"
    summary += f" (score: {result.score:.2f}, confidence: {result.confidence})"

    if result.top_positive:
        summary += f" | Positive: {', '.join(result.top_positive)}"
    if result.top_negative:
        summary += f" | Negative: {', '.join(result.top_negative)}"

    return summary
