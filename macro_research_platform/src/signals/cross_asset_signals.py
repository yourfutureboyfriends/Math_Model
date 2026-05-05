"""
Cross-Asset Signals

Signals that exploit relationships between asset classes.

Key relationships:
- Rates → FX (interest rate differentials)
- Commodities → Inflation expectations
- Credit → Equity risk premium
- Dollar → Emerging markets
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from .signal_base import CrossAssetSignal, SignalConfidence, SignalDirection, SignalOutput

logger = logging.getLogger(__name__)


class RatesFXSignal(CrossAssetSignal):
    """
    Signal based on rate differentials and FX.

    Currencies with higher real rates tend to appreciate.
    Carry trades work when volatility is low.
    """

    def __init__(self, primary_ccy: str, secondary_ccy: str):
        super().__init__(
            name=f"rates_fx_{primary_ccy}_{secondary_ccy}",
            description=f"Trade {primary_ccy}/{secondary_ccy} based on rate differentials",
            primary_asset=primary_ccy,
            secondary_asset=secondary_ccy,
            relationship_type="lead_lag",
            frequency="daily",
        )
        self.threshold = 1.0  # Percentage point differential

    def calculate(
        self,
        data: Dict[str, pd.DataFrame],
        as_of_date: Optional[datetime] = None,
    ) -> SignalOutput:
        """Generate signal based on rate differential."""
        primary_rates = data.get(f"rates_{self.primary_asset}", pd.Series())
        secondary_rates = data.get(f"rates_{self.secondary_asset}", pd.Series())

        if len(primary_rates) < 30 or len(secondary_rates) < 30:
            return SignalOutput(
                timestamp=as_of_date or datetime.now(),
                direction=SignalDirection.NEUTRAL,
                strength=0.0,
                confidence=SignalConfidence.LOW,
                rationale="Insufficient rate data",
            )

        # Calculate rate differential
        diff = primary_rates.iloc[-1] - secondary_rates.iloc[-1]
        diff_ma = (primary_rates - secondary_rates).rolling(30).mean().iloc[-1]

        # Rate of change in differential
        diff_change = diff - (primary_rates.iloc[-30] - secondary_rates.iloc[-30])

        if diff > diff_ma + self.threshold and diff_change > 0:
            # Widening differential favors primary currency
            direction = SignalDirection.LONG
            strength = min(1.0, abs(diff - diff_ma) / self.threshold)
            rationale = f"Rate differential widening: {diff:.2f}% vs {diff_ma:.2f}% MA"
        elif diff < diff_ma - self.threshold and diff_change < 0:
            # Narrowing differential favors secondary currency
            direction = SignalDirection.SHORT
            strength = min(1.0, abs(diff - diff_ma) / self.threshold)
            rationale = f"Rate differential narrowing: {diff:.2f}% vs {diff_ma:.2f}% MA"
        else:
            direction = SignalDirection.NEUTRAL
            strength = 0.3
            rationale = f"Rate differential stable: {diff:.2f}%"

        return SignalOutput(
            timestamp=as_of_date or datetime.now(),
            direction=direction,
            strength=strength,
            confidence=SignalConfidence.MEDIUM,
            rationale=rationale,
            metadata={
                "rate_differential": diff,
                "differential_ma": diff_ma,
                "differential_change": diff_change,
            },
        )


class CommodityInflationSignal(CrossAssetSignal):
    """
    Signal based on commodity prices leading inflation.

    Commodity prices lead CPI by several months.
    Useful for positioning in inflation-linked bonds.
    """

    def __init__(self):
        super().__init__(
            name="commodity_inflation_lead",
            description="Trade TIPS based on commodity momentum",
            primary_asset="commodities",
            secondary_asset="tips",
            relationship_type="lead_lag",
            frequency="weekly",
        )
        self.lead_lag_months = 3

    def calculate(
        self,
        data: Dict[str, pd.DataFrame],
        as_of_date: Optional[datetime] = None,
    ) -> SignalOutput:
        """Generate signal based on commodity momentum."""
        commodities = data.get("commodities", pd.Series())
        breakeven = data.get("breakeven_inflation", pd.Series())

        if len(commodities) < 6:
            return SignalOutput(
                timestamp=as_of_date or datetime.now(),
                direction=SignalDirection.NEUTRAL,
                strength=0.0,
                confidence=SignalConfidence.LOW,
                rationale="Insufficient commodity data",
            )

        # Commodity momentum
        commodity_mom = commodities.iloc[-1] / commodities.iloc[-6] - 1

        # Current inflation expectations
        current_be = breakeven.iloc[-1] if len(breakeven) > 0 else 2.0

        # Expected inflation change from commodities
        expected_inflation_change = commodity_mom * 0.3  # Rough coefficient

        if commodity_mom > 0.1 and expected_inflation_change > current_be * 0.1:
            # Strong commodity momentum suggests inflation pickup
            direction = SignalDirection.LONG  # Long TIPS
            strength = min(1.0, commodity_mom / 0.2)
            rationale = f"Commodity momentum {commodity_mom:.1%} suggests inflation rising"
        elif commodity_mom < -0.1:
            # Commodity weakness suggests disinflation
            direction = SignalDirection.SHORT  # Short TIPS
            strength = min(1.0, abs(commodity_mom) / 0.2)
            rationale = f"Commodity momentum {commodity_mom:.1%} suggests disinflation"
        else:
            direction = SignalDirection.NEUTRAL
            strength = 0.2
            rationale = f"Commodity momentum {commodity_mom:.1%} neutral"

        return SignalOutput(
            timestamp=as_of_date or datetime.now(),
            direction=direction,
            strength=strength,
            confidence=SignalConfidence.MEDIUM,
            rationale=rationale,
            metadata={
                "commodity_momentum": commodity_mom,
                "expected_inflation_change": expected_inflation_change,
                "current_breakeven": current_be,
            },
        )


class CreditEquitySignal(CrossAssetSignal):
    """
    Signal based on credit spreads as equity risk indicator.

    Credit leads equities at turning points.
    Widening credit spreads warn of equity weakness.
    """

    def __init__(self):
        super().__init__(
            name="credit_equity_lead",
            description="Use credit spreads to time equity exposure",
            primary_asset="credit_spreads",
            secondary_asset="equities",
            relationship_type="lead_lag",
            frequency="daily",
        )

    def calculate(
        self,
        data: Dict[str, pd.DataFrame],
        as_of_date: Optional[datetime] = None,
    ) -> SignalOutput:
        """Generate signal based on credit spread momentum."""
        spreads = data.get("credit_spreads", pd.Series())

        if len(spreads) < 30:
            return SignalOutput(
                timestamp=as_of_date or datetime.now(),
                direction=SignalDirection.NEUTRAL,
                strength=0.0,
                confidence=SignalConfidence.LOW,
                rationale="Insufficient credit data",
            )

        # Spread momentum
        current_spread = spreads.iloc[-1]
        spread_ma = spreads.rolling(30).mean().iloc[-1]
        spread_z = (current_spread - spreads.mean()) / spreads.std() if spreads.std() > 0 else 0

        # Rate of change
        spread_change = current_spread - spreads.iloc[-20]

        if spread_change > 50 and current_spread > spread_ma:
            # Rapid spread widening - risk off
            direction = SignalDirection.SHORT  # Short equities
            strength = min(1.0, abs(spread_change) / 100)
            rationale = f"Credit spreads widening {spread_change:.0f}bps, equity risk rising"
        elif spread_change < -20 and current_spread < spread_ma:
            # Spread tightening - risk on
            direction = SignalDirection.LONG  # Long equities
            strength = min(1.0, abs(spread_change) / 50)
            rationale = f"Credit spreads tightening {abs(spread_change):.0f}bps, risk appetite improving"
        else:
            direction = SignalDirection.NEUTRAL
            strength = 0.3
            rationale = f"Credit spreads stable at {current_spread:.0f}bps"

        return SignalOutput(
            timestamp=as_of_date or datetime.now(),
            direction=direction,
            strength=strength,
            confidence=SignalConfidence.HIGH if abs(spread_change) > 50 else SignalConfidence.MEDIUM,
            rationale=rationale,
            metadata={
                "credit_spread": current_spread,
                "spread_ma": spread_ma,
                "spread_change": spread_change,
                "spread_zscore": spread_z,
            },
        )


class DollarEMSignal(CrossAssetSignal):
    """
    Signal based on USD strength and EM assets.

    Strong USD is typically bad for EM:
    - Tighter financial conditions
    - Capital outflows
    - Dollar debt servicing harder
    """

    def __init__(self):
        super().__init__(
            name="dollar_em",
            description="Trade EM assets based on dollar momentum",
            primary_asset="dollar_index",
            secondary_asset="emerging_markets",
            relationship_type="correlation",
            frequency="daily",
        )

    def calculate(
        self,
        data: Dict[str, pd.DataFrame],
        as_of_date: Optional[datetime] = None,
    ) -> SignalOutput:
        """Generate signal based on dollar trend."""
        dollar = data.get("dollar_index", pd.Series())

        if len(dollar) < 60:
            return SignalOutput(
                timestamp=as_of_date or datetime.now(),
                direction=SignalDirection.NEUTRAL,
                strength=0.0,
                confidence=SignalConfidence.LOW,
                rationale="Insufficient dollar data",
            )

        # Dollar trend
        current = dollar.iloc[-1]
        ma20 = dollar.rolling(20).mean().iloc[-1]
        ma60 = dollar.rolling(60).mean().iloc[-1]

        # Trend strength
        dollar_z = (current - dollar.mean()) / dollar.std() if dollar.std() > 0 else 0

        if current > ma20 > ma60 and dollar_z > 1.0:
            # Strong dollar uptrend - negative for EM
            direction = SignalDirection.SHORT  # Short EM
            strength = min(1.0, dollar_z / 2)
            rationale = f"Strong dollar trend: {current:.2f} above {ma20:.2f} and {ma60:.2f}"
        elif current < ma20 < ma60 and dollar_z < -1.0:
            # Dollar downtrend - positive for EM
            direction = SignalDirection.LONG  # Long EM
            strength = min(1.0, abs(dollar_z) / 2)
            rationale = f"Weak dollar trend: {current:.2f} below {ma20:.2f} and {ma60:.2f}"
        else:
            direction = SignalDirection.NEUTRAL
            strength = 0.3
            rationale = f"Dollar in consolidation: {current:.2f}"

        return SignalOutput(
            timestamp=as_of_date or datetime.now(),
            direction=direction,
            strength=strength,
            confidence=SignalConfidence.MEDIUM,
            rationale=rationale,
            metadata={
                "dollar_index": current,
                "dollar_ma20": ma20,
                "dollar_ma60": ma60,
                "dollar_zscore": dollar_z,
            },
        )


class RealRatesGoldSignal(CrossAssetSignal):
    """
    Signal based on real rates and gold.

    Gold is inversely related to real rates:
    - No yield, so opportunity cost is real rate
    - Also a safe haven when real rates very low
    """

    def __init__(self):
        super().__init__(
            name="real_rates_gold",
            description="Trade gold based on real rate environment",
            primary_asset="real_rates",
            secondary_asset="gold",
            relationship_type="correlation",
            frequency="daily",
        )

    def calculate(
        self,
        data: Dict[str, pd.DataFrame],
        as_of_date: Optional[datetime] = None,
    ) -> SignalOutput:
        """Generate signal based on real rate level and trend."""
        real_rates = data.get("real_rates", pd.Series())

        if len(real_rates) < 30:
            return SignalOutput(
                timestamp=as_of_date or datetime.now(),
                direction=SignalDirection.NEUTRAL,
                strength=0.0,
                confidence=SignalConfidence.LOW,
                rationale="Insufficient real rate data",
            )

        current_rr = real_rates.iloc[-1]
        rr_trend = real_rates.iloc[-1] - real_rates.iloc[-20]

        # Historical context
        rr_percentile = (real_rates < current_rr).mean()

        if current_rr < 0 and rr_trend < 0:
            # Negative and falling real rates - very bullish gold
            direction = SignalDirection.LONG
            strength = min(1.0, abs(current_rr) / 2)
            rationale = f"Negative real rates {current_rr:.2f}% and falling - gold positive"
        elif current_rr > 2 and rr_trend > 0:
            # Rising positive real rates - bearish gold
            direction = SignalDirection.SHORT
            strength = min(1.0, (current_rr - 1) / 2)
            rationale = f"Rising real rates {current_rr:.2f}% - gold negative"
        elif rr_trend < -0.5:
            # Sharp real rate decline - gold positive
            direction = SignalDirection.LONG
            strength = min(1.0, abs(rr_trend) / 1.0)
            rationale = f"Real rates falling {abs(rr_trend):.2f}% - gold positive"
        else:
            direction = SignalDirection.NEUTRAL
            strength = 0.3
            rationale = f"Real rates {current_rr:.2f}% at {rr_percentile:.0%} percentile"

        return SignalOutput(
            timestamp=as_of_date or datetime.now(),
            direction=direction,
            strength=strength,
            confidence=SignalConfidence.MEDIUM,
            rationale=rationale,
            metadata={
                "real_rate": current_rr,
                "real_rate_trend": rr_trend,
                "real_rate_percentile": rr_percentile,
            },
        )
