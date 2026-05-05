"""
Global Liquidity Signals

Signals related to global liquidity, dollar funding, and the global financial cycle.

Research backing:
- Rey - Dilemma not Trilemma: The Global Financial Cycle
- Miranda-Agrippino and Rey - U.S. Monetary Policy and the Global Financial Cycle
- Du, Tepper, Verdelhan - Deviations from Covered Interest Rate Parity
"""

import logging
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from .signal_base import Signal, SignalDirection, SignalOutput, SignalConfidence

logger = logging.getLogger(__name__)


class GlobalLiquidityPressureSignal(Signal):
    """
    Global liquidity pressure signal.

    Research: Rey - Dilemma not Trilemma

    US monetary policy transmits globally through capital flows.
    Tightening US policy creates global liquidity pressure.
    """

    def __init__(self):
        super().__init__(
            name="global_liquidity_pressure",
            description="Global liquidity pressure signal",
            asset_universe=["em_equities", "em_credit", "commodities", "fx"],
            frequency="monthly",
        )
        self.parameters = {
            "fed_policy_rate_weight": 0.4,
            "dollar_index_weight": 0.3,
            "cross_currency_basis_weight": 0.3,
        }

    def calculate(self, data: Dict[str, pd.Series]) -> SignalOutput:
        """
        Calculate global liquidity pressure.

        Args:
            data: Dict with fed_rate, dollar_index, cross_currency_basis

        Returns:
            SignalOutput with liquidity assessment
        """
        weights = self.parameters

        pressure_score = 0.0
        total_weight = 0.0

        # Fed policy rate (higher = tighter)
        if 'fed_rate' in data and len(data['fed_rate']) > 0:
            fed_rate = data['fed_rate'].iloc[-1]
            # Normalize to 0-1 scale (assuming 0-6% range)
            fed_pressure = min(1.0, max(0.0, fed_rate / 6.0))
            pressure_score += fed_pressure * weights["fed_policy_rate_weight"]
            total_weight += weights["fed_policy_rate_weight"]

        # Dollar index (higher = tighter for EM)
        if 'dollar_index' in data and len(data['dollar_index']) > 0:
            dxy = data['dollar_index'].iloc[-1]
            # Normalize to 0-1 scale (assuming 90-110 range)
            dxy_pressure = min(1.0, max(0.0, (dxy - 90) / 20))
            pressure_score += dxy_pressure * weights["dollar_index_weight"]
            total_weight += weights["dollar_index_weight"]

        # Cross-currency basis (more negative = tighter)
        if 'cross_currency_basis' in data and len(data['cross_currency_basis']) > 0:
            basis = data['cross_currency_basis'].iloc[-1]
            # Normalize (assuming -50 to 0 bps range)
            basis_pressure = min(1.0, max(0.0, abs(basis) / 50))
            pressure_score += basis_pressure * weights["cross_currency_basis_weight"]
            total_weight += weights["cross_currency_basis_weight"]

        if total_weight == 0:
            return self._neutral_output()

        # Normalize
        pressure_score = pressure_score / total_weight

        # Determine signal (tight liquidity = defensive for EM/risk)
        if pressure_score > 0.6:
            direction = SignalDirection.SHORT  # Risk-off
            strength = min(1.0, pressure_score)
            rationale = f"High global liquidity pressure ({pressure_score:.2f}) - EM vulnerability"
        elif pressure_score < 0.4:
            direction = SignalDirection.LONG  # Risk-on
            strength = min(1.0, 1.0 - pressure_score)
            rationale = f"Easy global liquidity conditions ({pressure_score:.2f}) - supportive for EM"
        else:
            direction = SignalDirection.NEUTRAL
            strength = 0.5
            rationale = f"Neutral global liquidity conditions ({pressure_score:.2f})"

        return SignalOutput(
            timestamp=pd.Timestamp.now(),
            direction=direction,
            strength=strength,
            confidence=SignalConfidence.MEDIUM if total_weight > 0.5 else SignalConfidence.LOW,
            expected_return=self._estimate_return(direction),
            rationale=rationale,
            metadata={
                "pressure_score": pressure_score,
                "components_used": list(data.keys()),
            },
        )

    def _estimate_return(self, direction: SignalDirection) -> float:
        returns = {
            SignalDirection.LONG: 0.06,   # EM outperformance
            SignalDirection.SHORT: -0.08,  # EM underperformance
            SignalDirection.NEUTRAL: 0.0,
        }
        return returns.get(direction, 0.0)

    def _neutral_output(self) -> SignalOutput:
        return SignalOutput(
            timestamp=pd.Timestamp.now(),
            direction=SignalDirection.NEUTRAL,
            strength=0.0,
            confidence=SignalConfidence.VERY_LOW,
            rationale="Insufficient data for global liquidity signal",
        )


class DollarFundingStressSignal(Signal):
    """
    Dollar funding stress signal based on CIP deviations.

    Research: Du, Tepper, Verdelhan - Deviations from CIP

    CIP deviations measure dollar funding stress in global markets.
    High stress = flight to dollar, EM stress.
    """

    def __init__(self):
        super().__init__(
            name="dollar_funding_stress",
            description="Dollar funding stress from CIP deviations",
            asset_universe=["em_fx", "em_credit", "dollar"],
            frequency="daily",
        )
        self.parameters = {
            "cip_threshold": 20,  # bps
            "stress_threshold": 40,  # bps
        }

    def calculate(self, cip_basis: pd.Series) -> SignalOutput:
        """
        Calculate dollar funding stress.

        Args:
            cip_basis: Series of cross-currency basis (negative = stress)

        Returns:
            SignalOutput with stress assessment
        """
        if len(cip_basis) == 0:
            return self._neutral_output()

        current_basis = cip_basis.iloc[-1]
        abs_basis = abs(current_basis)

        threshold = self.parameters["cip_threshold"]
        stress_threshold = self.parameters["stress_threshold"]

        if abs_basis > stress_threshold:
            direction = SignalDirection.LONG  # Dollar strength
            strength = min(1.0, abs_basis / 100)
            confidence = SignalConfidence.HIGH
            rationale = f"Severe dollar funding stress: {current_basis:.0f}bps"
        elif abs_basis > threshold:
            direction = SignalDirection.LONG
            strength = min(1.0, abs_basis / stress_threshold)
            confidence = SignalConfidence.MEDIUM
            rationale = f"Elevated dollar funding stress: {current_basis:.0f}bps"
        else:
            direction = SignalDirection.NEUTRAL
            strength = 0.5
            confidence = SignalConfidence.MEDIUM
            rationale = f"Normal dollar funding conditions: {current_basis:.0f}bps"

        return SignalOutput(
            timestamp=cip_basis.index[-1] if len(cip_basis.index) > 0 else pd.Timestamp.now(),
            direction=direction,
            strength=strength,
            confidence=confidence,
            expected_return=self._estimate_return(direction),
            rationale=rationale,
            metadata={
                "basis": current_basis,
                "abs_basis": abs_basis,
            },
        )

    def _estimate_return(self, direction: SignalDirection) -> float:
        returns = {
            SignalDirection.LONG: 0.04,   # Dollar strength
            SignalDirection.SHORT: -0.03,  # Dollar weakness
            SignalDirection.NEUTRAL: 0.0,
        }
        return returns.get(direction, 0.0)

    def _neutral_output(self) -> SignalOutput:
        return SignalOutput(
            timestamp=pd.Timestamp.now(),
            direction=SignalDirection.NEUTRAL,
            strength=0.0,
            confidence=SignalConfidence.VERY_LOW,
            rationale="Insufficient data for dollar funding stress signal",
        )


class GlobalRiskCycleSignal(Signal):
    """
    Global risk cycle signal based on risk appetite indicators.

    Research: Miranda-Agrippino and Rey - US Monetary Policy and Global Financial Cycle

    Composite of risk appetite measures indicating global risk-on/risk-off.
    """

    def __init__(self):
        super().__init__(
            name="global_risk_cycle",
            description="Global risk cycle/risk appetite signal",
            asset_universe=["equities", "credit", "em", "commodities"],
            frequency="weekly",
        )
        self.parameters = {
            "vix_weight": 0.25,
            "credit_spread_weight": 0.25,
            "em_spread_weight": 0.25,
            "commodity_weight": 0.25,
        }

    def calculate(self, data: Dict[str, pd.Series]) -> SignalOutput:
        """
        Calculate global risk cycle.

        Args:
            data: Dict with vix, credit_spreads, em_spreads, commodities

        Returns:
            SignalOutput with risk cycle assessment
        """
        weights = self.parameters
        risk_score = 0.0
        total_weight = 0.0

        # VIX (inverse - lower = more risk-on)
        if 'vix' in data and len(data['vix']) > 0:
            vix = data['vix'].iloc[-1]
            vix_z = self._zscore(data['vix'])
            # Higher VIX = lower risk score
            vix_contrib = 0.5 - vix_z / 4  # Normalize
            risk_score += vix_contrib * weights["vix_weight"]
            total_weight += weights["vix_weight"]

        # Credit spreads (inverse)
        if 'credit_spread' in data and len(data['credit_spread']) > 0:
            spread_z = self._zscore(data['credit_spread'])
            spread_contrib = 0.5 - spread_z / 4
            risk_score += spread_contrib * weights["credit_spread_weight"]
            total_weight += weights["credit_spread_weight"]

        # EM spreads (inverse)
        if 'em_spread' in data and len(data['em_spread']) > 0:
            em_z = self._zscore(data['em_spread'])
            em_contrib = 0.5 - em_z / 4
            risk_score += em_contrib * weights["em_spread_weight"]
            total_weight += weights["em_spread_weight"]

        # Commodities (direct - higher = more risk-on)
        if 'commodity_index' in data and len(data['commodity_index']) > 0:
            comm_z = self._zscore(data['commodity_index'])
            comm_contrib = 0.5 + comm_z / 4
            risk_score += comm_contrib * weights["commodity_weight"]
            total_weight += weights["commodity_weight"]

        if total_weight == 0:
            return self._neutral_output()

        risk_score = risk_score / total_weight

        # Determine signal
        if risk_score > 0.6:
            direction = SignalDirection.LONG  # Risk-on
            strength = min(1.0, (risk_score - 0.5) * 2)
            rationale = f"Global risk-on conditions ({risk_score:.2f})"
        elif risk_score < 0.4:
            direction = SignalDirection.SHORT  # Risk-off
            strength = min(1.0, (0.5 - risk_score) * 2)
            rationale = f"Global risk-off conditions ({risk_score:.2f})"
        else:
            direction = SignalDirection.NEUTRAL
            strength = 0.5
            rationale = f"Neutral global risk conditions ({risk_score:.2f})"

        return SignalOutput(
            timestamp=pd.Timestamp.now(),
            direction=direction,
            strength=strength,
            confidence=SignalConfidence.MEDIUM if total_weight > 0.5 else SignalConfidence.LOW,
            expected_return=self._estimate_return(direction),
            rationale=rationale,
            metadata={
                "risk_score": risk_score,
                "components_used": list(data.keys()),
            },
        )

    def _zscore(self, series: pd.Series) -> float:
        """Calculate z-score."""
        if len(series) < 24:
            return 0.0
        recent = series.iloc[-24:]
        if recent.std() == 0:
            return 0.0
        return (series.iloc[-1] - recent.mean()) / recent.std()

    def _estimate_return(self, direction: SignalDirection) -> float:
        returns = {
            SignalDirection.LONG: 0.07,   # Risk assets outperform
            SignalDirection.SHORT: -0.10,  # Risk assets underperform
            SignalDirection.NEUTRAL: 0.0,
        }
        return returns.get(direction, 0.0)

    def _neutral_output(self) -> SignalOutput:
        return SignalOutput(
            timestamp=pd.Timestamp.now(),
            direction=SignalDirection.NEUTRAL,
            strength=0.0,
            confidence=SignalConfidence.VERY_LOW,
            rationale="Insufficient data for global risk cycle signal",
        )
