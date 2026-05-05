"""
Dollar Signals

Signals related to the US dollar, dollar cycles, and dollar impact.

Research backing:
- Rey - Dilemma not Trilemma
- Eichengreen - Exorbitant Privilege
- BIS - Dollar funding and global liquidity
"""

import logging
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from .signal_base import Signal, SignalDirection, SignalOutput, SignalConfidence

logger = logging.getLogger(__name__)


class DollarCycleSignal(Signal):
    """
    Dollar cycle signal based on economic divergences.

    Research: Rey - The US dollar drives the global financial cycle

    US growth outperformance = stronger dollar
    """

    def __init__(self):
        super().__init__(
            name="dollar_cycle",
            description="Dollar cycle based on growth differentials",
            asset_universe=["dollar", "fx", "em"],
            frequency="monthly",
        )
        self.parameters = {
            "growth_weight": 0.5,
            "rate_weight": 0.3,
            "sentiment_weight": 0.2,
        }

    def calculate(self, data: Dict[str, float]) -> SignalOutput:
        """
        Calculate dollar cycle signal.

        Args:
            data: Dict with us_growth, row_growth, fed_rate, dm_rates

        Returns:
            SignalOutput with dollar outlook
        """
        weights = self.parameters
        score = 0.0
        total_weight = 0.0

        # Growth differential (US vs rest of world)
        if 'us_growth' in data and 'row_growth' in data:
            growth_diff = data['us_growth'] - data['row_growth']
            score += np.sign(growth_diff) * min(1.0, abs(growth_diff) / 2) * weights['growth_weight']
            total_weight += weights['growth_weight']

        # Rate differential
        if 'fed_rate' in data and 'dm_rates' in data:
            rate_diff = data['fed_rate'] - data['dm_rates']
            score += np.sign(rate_diff) * min(1.0, abs(rate_diff) / 2) * weights['rate_weight']
            total_weight += weights['rate_weight']

        # Positioning/sentiment
        if 'dxy_sentiment' in data:
            sentiment = data['dxy_sentiment']  # -1 to 1
            score += sentiment * weights['sentiment_weight']
            total_weight += weights['sentiment_weight']

        if total_weight == 0:
            return self._neutral_output()

        # Normalize
        score = score / total_weight

        if score > 0.3:
            direction = SignalDirection.LONG  # Dollar strength
            strength = min(1.0, score)
            confidence = SignalConfidence.HIGH if abs(score) > 0.5 else SignalConfidence.MEDIUM
            rationale = f"Dollar strengthening conditions (score: {score:.2f})"
        elif score < -0.3:
            direction = SignalDirection.SHORT  # Dollar weakness
            strength = min(1.0, abs(score))
            confidence = SignalConfidence.HIGH if abs(score) > 0.5 else SignalConfidence.MEDIUM
            rationale = f"Dollar weakening conditions (score: {score:.2f})"
        else:
            direction = SignalDirection.NEUTRAL
            strength = 0.5
            confidence = SignalConfidence.LOW
            rationale = f"Neutral dollar conditions (score: {score:.2f})"

        return SignalOutput(
            timestamp=pd.Timestamp.now(),
            direction=direction,
            strength=strength,
            confidence=confidence,
            expected_return=self._estimate_return(direction),
            rationale=rationale,
            metadata={
                "cycle_score": score,
                "components": list(data.keys()),
            },
        )

    def _estimate_return(self, direction: SignalDirection) -> float:
        returns = {
            SignalDirection.LONG: 0.04,   # Dollar appreciation
            SignalDirection.SHORT: -0.04,  # Dollar depreciation
            SignalDirection.NEUTRAL: 0.0,
        }
        return returns.get(direction, 0.0)

    def _neutral_output(self) -> SignalOutput:
        return SignalOutput(
            timestamp=pd.Timestamp.now(),
            direction=SignalDirection.NEUTRAL,
            strength=0.0,
            confidence=SignalConfidence.VERY_LOW,
            rationale="Insufficient data for dollar cycle signal",
        )


class DollarSafeHavenSignal(Signal):
    """
    Dollar safe haven demand signal.

    Dollar strengthens during risk-off periods.
    """

    def __init__(self):
        super().__init__(
            name="dollar_safe_haven",
            description="Safe haven demand for dollar",
            asset_universe=["dollar", "fx"],
            frequency="daily",
        )
        self.parameters = {
            "vix_threshold": 25,
            "hy_spread_threshold": 400,
        }

    def calculate(self, vix: float, hy_spread: float) -> SignalOutput:
        """
        Calculate safe haven signal.

        Args:
            vix: VIX level
            hy_spread: High yield spread (bps)

        Returns:
            SignalOutput with safe haven assessment
        """
        risk_off_score = 0.0

        if vix > self.parameters["vix_threshold"]:
            risk_off_score += min(1.0, (vix - 20) / 30)

        if hy_spread > self.parameters["hy_spread_threshold"]:
            risk_off_score += min(1.0, (hy_spread - 300) / 400)

        risk_off_score = min(1.0, risk_off_score / 2)

        if risk_off_score > 0.5:
            direction = SignalDirection.LONG  # Dollar demand
            strength = risk_off_score
            confidence = SignalConfidence.HIGH
            rationale = f"Risk-off environment (VIX {vix:.1f}, HY {hy_spread:.0f}bps) - dollar demand"
        elif risk_off_score > 0.2:
            direction = SignalDirection.LONG
            strength = risk_off_score
            confidence = SignalConfidence.MEDIUM
            rationale = f"Elevated risk (VIX {vix:.1f}, HY {hy_spread:.0f}bps)"
        else:
            direction = SignalDirection.NEUTRAL
            strength = 0.5
            confidence = SignalConfidence.MEDIUM
            rationale = f"Normal risk environment (VIX {vix:.1f}, HY {hy_spread:.0f}bps)"

        return SignalOutput(
            timestamp=pd.Timestamp.now(),
            direction=direction,
            strength=strength,
            confidence=confidence,
            expected_return=self._estimate_return(direction, risk_off_score),
            rationale=rationale,
            metadata={
                "risk_off_score": risk_off_score,
                "vix": vix,
                "hy_spread": hy_spread,
            },
        )

    def _estimate_return(self, direction: SignalDirection, risk_off_score: float) -> float:
        if direction == SignalDirection.LONG:
            return 0.03 * risk_off_score
        return 0.0


class DollarCarrySignal(Signal):
    """
    Dollar carry signal from rate differentials.

    Higher US rates = dollar carry trade.
    """

    def __init__(self):
        super().__init__(
            name="dollar_carry",
            description="Dollar carry from interest rate differentials",
            asset_universe=["dollar", "fx"],
            frequency="monthly",
        )
        self.parameters = {
            "min_rate_diff": 1.0,  # %
        }

    def calculate(self, us_rate: float, dm_rates: Dict[str, float]) -> SignalOutput:
        """
        Calculate dollar carry signal.

        Args:
            us_rate: US policy rate (%)
            dm_rates: Dict of country to policy rate

        Returns:
            SignalOutput with carry assessment
        """
        if not dm_rates:
            return self._neutral_output()

        avg_dm_rate = np.mean(list(dm_rates.values()))
        rate_diff = us_rate - avg_dm_rate
        min_diff = self.parameters["min_rate_diff"]

        if rate_diff > min_diff:
            direction = SignalDirection.LONG
            strength = min(1.0, rate_diff / 3)
            confidence = SignalConfidence.MEDIUM
            rationale = f"US rates {us_rate:.1f}% vs DM avg {avg_dm_rate:.1f}% - carry support"
        elif rate_diff < -min_diff:
            direction = SignalDirection.SHORT
            strength = min(1.0, abs(rate_diff) / 3)
            confidence = SignalConfidence.MEDIUM
            rationale = f"US rates below DM - negative carry"
        else:
            direction = SignalDirection.NEUTRAL
            strength = 0.5
            confidence = SignalConfidence.LOW
            rationale = f"Rate differentials neutral: {rate_diff:.1f}%"

        return SignalOutput(
            timestamp=pd.Timestamp.now(),
            direction=direction,
            strength=strength,
            confidence=confidence,
            expected_return=self._estimate_return(direction, rate_diff),
            rationale=rationale,
            metadata={
                "rate_diff": rate_diff,
                "us_rate": us_rate,
                "dm_avg": avg_dm_rate,
            },
        )

    def _estimate_return(self, direction: SignalDirection, rate_diff: float) -> float:
        if direction == SignalDirection.LONG:
            return 0.02 * rate_diff / 100
        elif direction == SignalDirection.SHORT:
            return -0.02 * rate_diff / 100
        return 0.0

    def _neutral_output(self) -> SignalOutput:
        return SignalOutput(
            timestamp=pd.Timestamp.now(),
            direction=SignalDirection.NEUTRAL,
            strength=0.0,
            confidence=SignalConfidence.VERY_LOW,
            rationale="Insufficient rate data",
        )


class DollarTechnicalSignal(Signal):
    """
    Dollar technical signal based on DXY trends.
    """

    def __init__(self, lookback_months: int = 6):
        super().__init__(
            name="dollar_technical",
            description="Dollar technical trend signal",
            asset_universe=["dollar"],
            frequency="weekly",
        )
        self.parameters = {
            "lookback_months": lookback_months,
            "ma_short": 20,
            "ma_long": 50,
        }

    def calculate(self, dxy_series: pd.Series) -> SignalOutput:
        """
        Calculate dollar technical signal.

        Args:
            dxy_series: Dollar index series

        Returns:
            SignalOutput with technical assessment
        """
        if len(dxy_series) < self.parameters["ma_long"]:
            return self._neutral_output()

        current = dxy_series.iloc[-1]
        ma_short = dxy_series.iloc[-self.parameters["ma_short"]:].mean()
        ma_long = dxy_series.iloc[-self.parameters["ma_long"]:].mean()

        # Trend strength
        trend = (current / ma_long - 1) * 100

        if current > ma_short > ma_long and trend > 2:
            direction = SignalDirection.LONG
            strength = min(1.0, trend / 5)
            confidence = SignalConfidence.MEDIUM
            rationale = f"Dollar uptrend: {trend:.1f}% above long-term MA"
        elif current < ma_short < ma_long and trend < -2:
            direction = SignalDirection.SHORT
            strength = min(1.0, abs(trend) / 5)
            confidence = SignalConfidence.MEDIUM
            rationale = f"Dollar downtrend: {trend:.1f}% below long-term MA"
        else:
            direction = SignalDirection.NEUTRAL
            strength = 0.5
            confidence = SignalConfidence.LOW
            rationale = f"Dollar trend unclear: {trend:.1f}% from MA"

        return SignalOutput(
            timestamp=dxy_series.index[-1] if len(dxy_series.index) > 0 else pd.Timestamp.now(),
            direction=direction,
            strength=strength,
            confidence=confidence,
            expected_return=self._estimate_return(direction, abs(trend)),
            rationale=rationale,
            metadata={
                "current": current,
                "ma_short": ma_short,
                "ma_long": ma_long,
                "trend_pct": trend,
            },
        )

    def _estimate_return(self, direction: SignalDirection, trend: float) -> float:
        if direction == SignalDirection.LONG:
            return 0.03 * min(1.0, trend / 5)
        elif direction == SignalDirection.SHORT:
            return -0.03 * min(1.0, trend / 5)
        return 0.0

    def _neutral_output(self) -> SignalOutput:
        return SignalOutput(
            timestamp=pd.Timestamp.now(),
            direction=SignalDirection.NEUTRAL,
            strength=0.0,
            confidence=SignalConfidence.VERY_LOW,
            rationale="Insufficient DXY data",
        )


class DollarEMStressSignal(Signal):
    """
    Dollar stress signal for emerging markets.

    Strong dollar creates EM stress.
    """

    def __init__(self):
        super().__init__(
            name="dollar_em_stress",
            description="Dollar strength impact on EM",
            asset_universe=["em_fx", "em_credit", "dollar"],
            frequency="weekly",
        )
        self.parameters = {
            "dxy_threshold": 100,
            "em_debt_threshold": 60,  # % of GDP
        }

    def calculate(self, dxy: float, em_debt_gdp: Dict[str, float]) -> SignalOutput:
        """
        Calculate dollar EM stress signal.

        Args:
            dxy: Dollar index level
            em_debt_gdp: Dict of country to debt/GDP

        Returns:
            SignalOutput with EM stress assessment
        """
        threshold = self.parameters["dxy_threshold"]

        if dxy > threshold * 1.1:
            # Strong dollar - EM stress
            vulnerable_countries = sum(1 for debt in em_debt_gdp.values() if debt > self.parameters["em_debt_threshold"])
            total_countries = len(em_debt_gdp)

            if vulnerable_countries > total_countries / 2:
                direction = SignalDirection.SHORT  # EM underperformance
                strength = min(1.0, (dxy - threshold) / 20)
                confidence = SignalConfidence.HIGH
                rationale = f"Strong dollar ({dxy:.0f}) + high EM leverage - stress risk"
            else:
                direction = SignalDirection.NEUTRAL
                strength = 0.6
                confidence = SignalConfidence.MEDIUM
                rationale = f"Strong dollar but EM debt manageable"
        elif dxy < threshold * 0.9:
            direction = SignalDirection.LONG  # EM relief rally
            strength = min(1.0, (threshold - dxy) / 20)
            confidence = SignalConfidence.MEDIUM
            rationale = f"Weak dollar ({dxy:.0f}) - EM relief"
        else:
            direction = SignalDirection.NEUTRAL
            strength = 0.5
            confidence = SignalConfidence.MEDIUM
            rationale = f"Dollar neutral ({dxy:.0f}) - limited EM stress"

        return SignalOutput(
            timestamp=pd.Timestamp.now(),
            direction=direction,
            strength=strength,
            confidence=confidence,
            expected_return=self._estimate_return(direction),
            rationale=rationale,
            metadata={
                "dxy": dxy,
                "vulnerable_em": sum(1 for d in em_debt_gdp.values() if d > self.parameters["em_debt_threshold"]),
            },
        )

    def _estimate_return(self, direction: SignalDirection) -> float:
        returns = {
            SignalDirection.LONG: 0.05,   # EM outperformance
            SignalDirection.SHORT: -0.08,  # EM underperformance
            SignalDirection.NEUTRAL: 0.0,
        }
        return returns.get(direction, 0.0)
