"""
Policy Signals

Signals related to monetary policy, fiscal policy, and central bank actions.

Research backing:
- Kuttner - Monetary Policy Surprises
- D'Amico, King - Flow and Stock Effects of LSAPs
- Bernanke, Blinder - The Federal Funds Rate and Channels of Monetary Transmission
"""

import logging
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from .signal_base import Signal, SignalDirection, SignalOutput, SignalConfidence

logger = logging.getLogger(__name__)


class FedPolicySurpriseSignal(Signal):
    """
    Federal Reserve policy surprise signal.

    Research: Kuttner - Monetary Policy Surprises

    Unexpected policy moves create asset price reactions.
    """

    def __init__(self):
        super().__init__(
            name="fed_policy_surprise",
            description="Fed policy surprise signal",
            asset_universe=["rates", "equities", "fx", "credit"],
            frequency="daily",
        )
        self.parameters = {
            "surprise_threshold": 5,  # bps for target rate
            "forward_threshold": 10,  # bps for forward guidance
        }

    def calculate(self, fed_action: float, market_expectation: float, asset_class: str = "rates") -> SignalOutput:
        """
        Calculate policy surprise signal.

        Args:
            fed_action: Actual Fed action (rate change in bps)
            market_expectation: Expected action (bps)
            asset_class: Asset class for signal

        Returns:
            SignalOutput with surprise assessment
        """
        surprise = fed_action - market_expectation
        threshold = self.parameters["surprise_threshold"]

        # Map surprise to asset direction
        asset_directions = {
            "rates": -1,      # Hawkish = rates up = bond prices down
            "equities": -1,   # Hawkish = equities down
            "fx": 1,          # Hawkish = dollar up
            "credit": -1,     # Hawkish = credit spreads widen
        }

        direction_mult = asset_directions.get(asset_class, -1)

        if abs(surprise) > threshold:
            direction = SignalDirection.LONG if surprise * direction_mult > 0 else SignalDirection.SHORT
            strength = min(1.0, abs(surprise) / 25)
            confidence = SignalConfidence.HIGH if abs(surprise) > threshold * 2 else SignalConfidence.MEDIUM

            surprise_type = "hawkish" if surprise > 0 else "dovish"
            rationale = f"Fed {surprise_type} surprise ({surprise:+.0f}bps) vs expectation"
        else:
            direction = SignalDirection.NEUTRAL
            strength = 0.0
            confidence = SignalConfidence.LOW
            rationale = f"Fed action in line with expectations ({surprise:+.0f}bps)"

        return SignalOutput(
            timestamp=pd.Timestamp.now(),
            direction=direction,
            strength=strength,
            confidence=confidence,
            expected_return=self._estimate_return(direction, abs(surprise)),
            rationale=rationale,
            metadata={
                "surprise": surprise,
                "fed_action": fed_action,
                "expectation": market_expectation,
                "asset_class": asset_class,
            },
        )

    def _estimate_return(self, direction: SignalDirection, surprise: float) -> float:
        # Returns proportional to surprise
        if direction == SignalDirection.LONG:
            return 0.001 * surprise  # 0.1% per 10bp surprise
        elif direction == SignalDirection.SHORT:
            return -0.001 * surprise
        return 0.0


class PolicyStanceSignal(Signal):
    """
    Central bank policy stance signal.

    Evaluates whether policy is accommodative, neutral, or restrictive.
    """

    def __init__(self):
        super().__init__(
            name="policy_stance",
            description="Central bank policy stance signal",
            asset_universe=["rates", "equities", "credit", "fx"],
            frequency="monthly",
        )
        self.parameters = {
            "neutral_rate": 2.5,  # Estimate of R-star
            "tolerance": 0.5,     # Range around neutral
        }

    def calculate(self, policy_rate: float, neutral_rate: Optional[float] = None) -> SignalOutput:
        """
        Calculate policy stance.

        Args:
            policy_rate: Current policy rate (%)
            neutral_rate: Estimated neutral rate (uses default if None)

        Returns:
            SignalOutput with policy stance
        """
        neutral = neutral_rate if neutral_rate else self.parameters["neutral_rate"]
        tolerance = self.parameters["tolerance"]

        gap = policy_rate - neutral

        if gap < -tolerance:
            # Accommodative
            direction = SignalDirection.LONG  # Supportive for risk assets
            strength = min(1.0, abs(gap) / 2)
            confidence = SignalConfidence.MEDIUM
            rationale = f"Accommodative policy: {policy_rate:.1f}% vs neutral {neutral:.1f}%"
        elif gap > tolerance:
            # Restrictive
            direction = SignalDirection.SHORT  # Restrictive for risk assets
            strength = min(1.0, gap / 2)
            confidence = SignalConfidence.MEDIUM
            rationale = f"Restrictive policy: {policy_rate:.1f}% vs neutral {neutral:.1f}%"
        else:
            # Neutral
            direction = SignalDirection.NEUTRAL
            strength = 0.5
            confidence = SignalConfidence.MEDIUM
            rationale = f"Neutral policy stance: {policy_rate:.1f}%"

        return SignalOutput(
            timestamp=pd.Timestamp.now(),
            direction=direction,
            strength=strength,
            confidence=confidence,
            expected_return=self._estimate_return(direction, abs(gap)),
            rationale=rationale,
            metadata={
                "policy_rate": policy_rate,
                "neutral_rate": neutral,
                "gap": gap,
            },
        )

    def _estimate_return(self, direction: SignalDirection, gap: float) -> float:
        if direction == SignalDirection.LONG:
            return 0.04 * min(1.0, gap / 2)  # Returns from easy policy
        elif direction == SignalDirection.SHORT:
            return -0.03 * min(1.0, gap / 2)  # Drag from tight policy
        return 0.0


class QuantitativeTighteningSignal(Signal):
    """
    Quantitative tightening/balance sheet signal.

    Research: D'Amico, King - Flow and Stock Effects

    QT creates upward pressure on rates, particularly term premium.
    """

    def __init__(self):
        super().__init__(
            name="qt_signal",
            description="Quantitative tightening signal",
            asset_universe=["rates", "equities", "credit"],
            frequency="monthly",
        )
        self.parameters = {
            "qt_threshold": 50,  # bns per month
            "qe_threshold": -50,
        }

    def calculate(self, balance_sheet_change: float, balance_sheet_level: float) -> SignalOutput:
        """
        Calculate QT signal.

        Args:
            balance_sheet_change: Monthly change in balance sheet (bns USD)
            balance_sheet_level: Current balance sheet size (trns USD)

        Returns:
            SignalOutput with QT assessment
        """
        # Normalize by level
        if balance_sheet_level > 0:
            pct_change = (balance_sheet_change / (balance_sheet_level * 1000)) * 100
        else:
            pct_change = 0

        qt_threshold = self.parameters["qt_threshold"]
        qe_threshold = self.parameters["qe_threshold"]

        if balance_sheet_change < qe_threshold:
            # Active QT
            direction = SignalDirection.SHORT  # Tightening
            strength = min(1.0, abs(balance_sheet_change) / 100)
            confidence = SignalConfidence.HIGH
            rationale = f"QT active: ${abs(balance_sheet_change):.0f}bn monthly reduction"
        elif balance_sheet_change > abs(qe_threshold):
            # Active QE
            direction = SignalDirection.LONG  # Easing
            strength = min(1.0, balance_sheet_change / 100)
            confidence = SignalConfidence.HIGH
            rationale = f"QE active: ${balance_sheet_change:.0f}bn monthly addition"
        else:
            # Passive runoff or neutral
            direction = SignalDirection.NEUTRAL
            strength = 0.5
            confidence = SignalConfidence.MEDIUM
            rationale = f"Balance sheet stable: ${balance_sheet_change:+.0f}bn change"

        return SignalOutput(
            timestamp=pd.Timestamp.now(),
            direction=direction,
            strength=strength,
            confidence=confidence,
            expected_return=self._estimate_return(direction, abs(pct_change)),
            rationale=rationale,
            metadata={
                "balance_sheet_change": balance_sheet_change,
                "balance_sheet_level": balance_sheet_level,
                "pct_change": pct_change,
            },
        )

    def _estimate_return(self, direction: SignalDirection, pct_change: float) -> float:
        # QT creates drag on asset prices
        if direction == SignalDirection.SHORT:
            return -0.02 * pct_change  # Drag from tightening
        elif direction == SignalDirection.LONG:
            return 0.015 * pct_change  # Boost from QE
        return 0.0


class FiscalImpulseSignal(Signal):
    """
    Fiscal policy impulse signal.

    Changes in fiscal stance affect aggregate demand.
    """

    def __init__(self):
        super().__init__(
            name="fiscal_impulse",
            description="Fiscal policy impulse signal",
            asset_universe=["equities", "rates", "cyclicals"],
            frequency="quarterly",
        )
        self.parameters = {
            "deficit_threshold": 3.0,  # % of GDP
            "change_threshold": 1.0,   # % of GDP change
        }

    def calculate(self, deficit_pct: float, lagged_deficit_pct: float, debt_pct: float) -> SignalOutput:
        """
        Calculate fiscal impulse signal.

        Args:
            deficit_pct: Current deficit as % of GDP
            lagged_deficit_pct: Prior period deficit %
            debt_pct: Debt to GDP ratio

        Returns:
            SignalOutput with fiscal assessment
        """
        deficit_change = deficit_pct - lagged_deficit_pct
        threshold = self.parameters["change_threshold"]

        # Check sustainability
        sustainable = debt_pct < 100  # Rough threshold

        if deficit_change > threshold and sustainable:
            # Expansionary
            direction = SignalDirection.LONG
            strength = min(1.0, deficit_change / 3)
            confidence = SignalConfidence.MEDIUM
            rationale = f"Fiscal expansion: deficit {deficit_pct:.1f}% vs {lagged_deficit_pct:.1f}% GDP"
        elif deficit_change < -threshold:
            # Contractionary
            direction = SignalDirection.SHORT
            strength = min(1.0, abs(deficit_change) / 3)
            confidence = SignalConfidence.MEDIUM
            rationale = f"Fiscal contraction: deficit {deficit_pct:.1f}% vs {lagged_deficit_pct:.1f}% GDP"
        else:
            direction = SignalDirection.NEUTRAL
            strength = 0.5
            confidence = SignalConfidence.LOW
            rationale = f"Stable fiscal stance: {deficit_pct:.1f}% deficit"

        return SignalOutput(
            timestamp=pd.Timestamp.now(),
            direction=direction,
            strength=strength,
            confidence=confidence,
            expected_return=self._estimate_return(direction, deficit_pct),
            rationale=rationale,
            metadata={
                "deficit_pct": deficit_pct,
                "deficit_change": deficit_change,
                "debt_pct": debt_pct,
            },
        )

    def _estimate_return(self, direction: SignalDirection, deficit: float) -> float:
        if direction == SignalDirection.LONG:
            return 0.03 * min(1.0, deficit / 5)
        elif direction == SignalDirection.SHORT:
            return -0.02 * min(1.0, abs(deficit) / 5)
        return 0.0


class ForwardGuidanceSignal(Signal):
    """
    Central bank forward guidance signal.

    Dot plot vs market pricing creates signal.
    """

    def __init__(self):
        super().__init__(
            name="forward_guidance",
            description="Forward guidance signal",
            asset_universe=["rates", "equities"],
            frequency="quarterly",
        )
        self.parameters = {
            "gap_threshold": 0.5,  # % difference
        }

    def calculate(self, cb_projection: float, market_pricing: float, time_horizon: str = "1y") -> SignalOutput:
        """
        Calculate forward guidance signal.

        Args:
            cb_projection: Central bank projection (%)
            market_pricing: Market implied rate (%)
            time_horizon: Time horizon for projection

        Returns:
            SignalOutput with guidance assessment
        """
        gap = cb_projection - market_pricing
        threshold = self.parameters["gap_threshold"]

        if gap > threshold:
            # CB more hawkish than market
            direction = SignalDirection.SHORT  # Rates repricing higher
            strength = min(1.0, gap / 1.5)
            confidence = SignalConfidence.MEDIUM
            rationale = f"CB projects {cb_projection:.1f}% vs market {market_pricing:.1f}% - hawkish gap"
        elif gap < -threshold:
            # CB more dovish than market
            direction = SignalDirection.LONG  # Rates repricing lower
            strength = min(1.0, abs(gap) / 1.5)
            confidence = SignalConfidence.MEDIUM
            rationale = f"CB projects {cb_projection:.1f}% vs market {market_pricing:.1f}% - dovish gap"
        else:
            direction = SignalDirection.NEUTRAL
            strength = 0.0
            confidence = SignalConfidence.LOW
            rationale = f"CB aligned with market: {cb_projection:.1f}% vs {market_pricing:.1f}%"

        return SignalOutput(
            timestamp=pd.Timestamp.now(),
            direction=direction,
            strength=strength,
            confidence=confidence,
            expected_return=self._estimate_return(direction, abs(gap)),
            rationale=rationale,
            metadata={
                "cb_projection": cb_projection,
                "market_pricing": market_pricing,
                "gap": gap,
                "horizon": time_horizon,
            },
        )

    def _estimate_return(self, direction: SignalDirection, gap: float) -> float:
        # Returns from market repricing to CB view
        if direction == SignalDirection.LONG:
            return 0.02 * min(1.0, gap / 1)
        elif direction == SignalDirection.SHORT:
            return -0.02 * min(1.0, gap / 1)
        return 0.0
