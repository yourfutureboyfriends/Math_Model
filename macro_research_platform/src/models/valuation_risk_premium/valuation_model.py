"""
Valuation & Risk Premium Model

Estimates fair value and risk premia across asset classes.
Provides context for signal strength - a strong signal in an expensive
market has different implications than the same signal in a cheap market.

Key metrics:
- Equity ERP (Earnings Yield - Real Yield)
- Credit risk premia (Spreads vs historical)
- Term premium estimates
- Cross-asset relative value

Based on:
- Campbell & Cochrane (1999) - Consumption-based asset pricing
- Fama & French (2002) - Equity premium
- Cochrane & Piazzesi (2005) - Bond risk premia
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from enum import Enum

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class ValuationLevel(Enum):
    VERY_CHEAP = "very_cheap"
    CHEAP = "cheap"
    FAIR = "fair"
    EXPENSIVE = "expensive"
    VERY_EXPENSIVE = "very_expensive"


@dataclass
class AssetValuation:
    """Valuation metrics for a single asset."""
    asset: str
    current_value: float
    percentile_5y: float  # 0-100
    percentile_10y: float
    z_score: float
    level: ValuationLevel
    risk_premium: Optional[float]
    risk_premium_percentile: Optional[float]


@dataclass
class ValuationResult:
    """Complete valuation assessment."""
    equity_erp: Optional[float]  # Equity risk premium
    equity_valuation: Optional[AssetValuation]
    credit_premium: Optional[float]
    credit_valuation: Optional[AssetValuation]
    term_premium_estimate: Optional[float]
    cross_asset_assessment: Dict[str, AssetValuation]
    overall_risk_premium: float  # Composite
    regime_context: str  # How valuation affects regime interpretation


class ValuationRiskPremiumModel:
    """
    Valuation and Risk Premium Model

    Calculates risk premia and valuations to contextualize macro signals.
    """

    # Historical percentiles for assessment
    PERCENTILE_THRESHOLDS = {
        "very_cheap": 10,
        "cheap": 25,
        "fair_low": 40,
        "fair_high": 60,
        "expensive": 75,
        "very_expensive": 90,
    }

    def __init__(self):
        self.lookback_5y = 60  # months
        self.lookback_10y = 120  # months

    def _calculate_percentile(self, current: float, history: pd.Series) -> float:
        """Calculate percentile of current value in historical distribution."""
        if len(history) == 0:
            return 50.0

        # Remove NaN
        clean = history.dropna()
        if len(clean) == 0:
            return 50.0

        # Calculate percentile (0-100)
        percentile = (clean < current).mean() * 100

        return np.clip(percentile, 0, 100)

    def _calculate_z_score(self, current: float, history: pd.Series) -> float:
        """Calculate z-score of current value."""
        clean = history.dropna()
        if len(clean) < 12:
            return 0.0

        mean = clean.mean()
        std = clean.std()

        if std == 0:
            return 0.0

        return (current - mean) / std

    def _classify_level(self, percentile: float, higher_is_cheaper: bool = True) -> ValuationLevel:
        """Classify valuation level from percentile."""
        th = self.PERCENTILE_THRESHOLDS

        # For metrics where higher = cheaper (like earnings yield)
        if higher_is_cheaper:
            if percentile < th["very_cheap"]:
                return ValuationLevel.VERY_EXPENSIVE
            elif percentile < th["cheap"]:
                return ValuationLevel.EXPENSIVE
            elif percentile < th["fair_low"]:
                return ValuationLevel.FAIR
            elif percentile < th["fair_high"]:
                return ValuationLevel.FAIR
            elif percentile < th["expensive"]:
                return ValuationLevel.CHEAP
            else:
                return ValuationLevel.VERY_CHEAP
        else:
            # For metrics where higher = more expensive (like P/E)
            if percentile < th["very_cheap"]:
                return ValuationLevel.VERY_CHEAP
            elif percentile < th["cheap"]:
                return ValuationLevel.CHEAP
            elif percentile < th["fair_low"]:
                return ValuationLevel.FAIR
            elif percentile < th["fair_high"]:
                return ValuationLevel.FAIR
            elif percentile < th["expensive"]:
                return ValuationLevel.EXPENSIVE
            else:
                return ValuationLevel.VERY_EXPENSIVE

    def _calculate_equity_erp(
        self,
        earnings_yield: float,
        real_yield: float,
        equity_risk_premium_history: Optional[pd.Series] = None,
    ) -> Tuple[float, Optional[float]]:
        """
        Calculate equity risk premium.

        ERP = Earnings Yield - Real Treasury Yield
        """
        erp = earnings_yield - real_yield

        percentile = None
        if equity_risk_premium_history is not None:
            percentile = self._calculate_percentile(erp, equity_risk_premium_history)

        return erp, percentile

    def assess_equity_valuation(
        self,
        df: pd.DataFrame,
        pe_ratio_col: Optional[str] = None,
        earnings_yield_col: Optional[str] = None,
    ) -> Optional[AssetValuation]:
        """
        Assess equity market valuation.

        Uses earnings yield (inverse of P/E) or direct ERP calculation.
        """
        # Try to find appropriate column
        if pe_ratio_col is None:
            candidates = [c for c in df.columns if "pe" in c.lower() or "earnings" in c.lower()]
            if candidates:
                pe_ratio_col = candidates[0]

        if earnings_yield_col is None:
            candidates = [c for c in df.columns if "yield" in c.lower() and "earnings" in c.lower()]
            if candidates:
                earnings_yield_col = candidates[0]

        if pe_ratio_col not in df.columns and earnings_yield_col not in df.columns:
            logger.debug("No equity valuation data available")
            return None

        # Calculate earnings yield
        if earnings_yield_col and earnings_yield_col in df.columns:
            earnings_yield = df[earnings_yield_col].iloc[-1]
            earnings_yield_history = df[earnings_yield_col]
        elif pe_ratio_col and pe_ratio_col in df.columns:
            pe = df[pe_ratio_col].iloc[-1]
            earnings_yield = 1.0 / pe if pe > 0 else 0.0
            earnings_yield_history = 1.0 / df[pe_ratio_col].replace(0, np.nan)
        else:
            return None

        if pd.isna(earnings_yield):
            return None

        # Calculate percentiles
        p5y = self._calculate_percentile(earnings_yield, earnings_yield_history.iloc[-self.lookback_5y:])
        p10y = self._calculate_percentile(earnings_yield, earnings_yield_history.iloc[-self.lookback_10y:])
        z = self._calculate_z_score(earnings_yield, earnings_yield_history.iloc[-self.lookback_10y:])

        level = self._classify_level(p10y, higher_is_cheaper=True)

        return AssetValuation(
            asset="Equity (Earnings Yield)",
            current_value=earnings_yield,
            percentile_5y=p5y,
            percentile_10y=p10y,
            z_score=z,
            level=level,
            risk_premium=None,  # Will calculate separately
            risk_premium_percentile=None,
        )

    def assess_credit_valuation(
        self,
        df: pd.DataFrame,
        spread_col: Optional[str] = None,
    ) -> Optional[AssetValuation]:
        """Assess credit market valuation via spreads."""
        if spread_col is None:
            candidates = [c for c in df.columns if "spread" in c.lower() or "credit" in c.lower()]
            if candidates:
                spread_col = candidates[0]

        if spread_col not in df.columns:
            return None

        current_spread = df[spread_col].iloc[-1]
        if pd.isna(current_spread):
            return None

        spread_history = df[spread_col]

        p5y = self._calculate_percentile(current_spread, spread_history.iloc[-self.lookback_5y:])
        p10y = self._calculate_percentile(current_spread, spread_history.iloc[-self.lookback_10y:])
        z = self._calculate_z_score(current_spread, spread_history.iloc[-self.lookback_10y:])

        level = self._classify_level(p10y, higher_is_cheaper=True)  # Higher spread = cheaper (more risk premium)

        return AssetValuation(
            asset="Credit (HY Spread)",
            current_value=current_spread,
            percentile_5y=p5y,
            percentile_10y=p10y,
            z_score=z,
            level=level,
            risk_premium=current_spread / 100.0,  # Convert bps to decimal
            risk_premium_percentile=p10y,
        )

    def assess_rates_valuation(
        self,
        df: pd.DataFrame,
        yield_col: Optional[str] = None,
    ) -> Optional[AssetValuation]:
        """Assess bond market valuation via yields."""
        if yield_col is None:
            candidates = [c for c in df.columns if "yield" in c.lower() and "10" in c]
            if candidates:
                yield_col = candidates[0]

        if yield_col not in df.columns:
            return None

        current_yield = df[yield_col].iloc[-1]
        if pd.isna(current_yield):
            return None

        yield_history = df[yield_col]

        p5y = self._calculate_percentile(current_yield, yield_history.iloc[-self.lookback_5y:])
        p10y = self._calculate_percentile(current_yield, yield_history.iloc[-self.lookback_10y:])
        z = self._calculate_z_score(current_yield, yield_history.iloc[-self.lookback_10y:])

        # For yields, higher = cheaper (more return potential)
        level = self._classify_level(p10y, higher_is_cheaper=True)

        return AssetValuation(
            asset="Rates (10Y Yield)",
            current_value=current_yield,
            percentile_5y=p5y,
            percentile_10y=p10y,
            z_score=z,
            level=level,
            risk_premium=None,
            risk_premium_percentile=None,
        )

    def calculate_full_assessment(self, df: pd.DataFrame) -> ValuationResult:
        """
        Calculate complete valuation assessment.

        Args:
            df: DataFrame with relevant columns (pe_ratio, earnings_yield, credit_spread, etc.)

        Returns:
            ValuationResult with all assessments
        """
        cross_asset = {}

        # Equity assessment
        equity = self.assess_equity_valuation(df)
        if equity:
            cross_asset["equity"] = equity

        # Credit assessment
        credit = self.assess_credit_valuation(df)
        if credit:
            cross_asset["credit"] = credit

        # Rates assessment
        rates = self.assess_rates_valuation(df)
        if rates:
            cross_asset["rates"] = rates

        # Calculate ERP if possible
        erp = None
        erp_percentile = None

        if equity and rates:
            # Rough ERP = Earnings Yield - Real Yield estimate
            # Assuming 2% inflation expectation
            real_yield = rates.current_value - 2.0
            erp = equity.current_value - real_yield

            # Estimate percentile
            if equity.percentile_10y and rates.percentile_10y:
                # Simplified: average of components
                erp_percentile = (equity.percentile_10y + (100 - rates.percentile_10y)) / 2

        # Calculate composite risk premium
        premiums = []
        if equity:
            premiums.append(equity.percentile_10y)
        if credit and credit.risk_premium_percentile:
            premiums.append(credit.risk_premium_percentile)

        overall_rp = sum(premiums) / len(premiums) if premiums else 50.0

        # Generate regime context
        regime_context = self._generate_regime_context(equity, credit, rates, erp)

        return ValuationResult(
            equity_erp=erp,
            equity_valuation=equity,
            credit_premium=credit.risk_premium if credit else None,
            credit_valuation=credit,
            term_premium_estimate=None,  # Would need more sophisticated calculation
            cross_asset_assessment=cross_asset,
            overall_risk_premium=overall_rp,
            regime_context=regime_context,
        )

    def _generate_regime_context(
        self,
        equity: Optional[AssetValuation],
        credit: Optional[AssetValuation],
        rates: Optional[AssetValuation],
        erp: Optional[float],
    ) -> str:
        """Generate context for how valuation affects regime interpretation."""
        contexts = []

        if equity:
            if equity.level in [ValuationLevel.VERY_EXPENSIVE, ValuationLevel.EXPENSIVE]:
                contexts.append(
                    "Equity market appears expensive. Even in Goldilocks, expected returns "
                    "may be limited. Tighten position sizing."
                )
            elif equity.level in [ValuationLevel.VERY_CHEAP, ValuationLevel.CHEAP]:
                contexts.append(
                    "Equity market appears cheap. Attractive entry point if macro improves."
                )

        if credit:
            if credit.level in [ValuationLevel.VERY_CHEAP, ValuationLevel.CHEAP]:
                contexts.append(
                    f"Credit spreads at {credit.percentile_10y:.0f}th percentile - "
                    "compensating well for risk, but watch for stress escalation."
                )
            elif credit.level in [ValuationLevel.VERY_EXPENSIVE, ValuationLevel.EXPENSIVE]:
                contexts.append(
                    "Credit spreads tight - minimal risk premium. Vulnerable to shocks."
                )

        if not contexts:
            return "Valuation appears roughly fair. Macro signal dominates."

        return " ".join(contexts)

    def get_valuation_summary(self, result: ValuationResult) -> str:
        """Get plain-English valuation summary."""
        lines = ["## Valuation Assessment", ""]

        if result.equity_valuation:
            ev = result.equity_valuation
            lines.append(
                f"**Equities:** {ev.level.value.replace('_', ' ').title()} "
                f"({ev.percentile_10y:.0f}th percentile vs 10Y history)"
            )
            if result.equity_erp:
                lines.append(f"  Equity Risk Premium: {result.equity_erp:.1f}%")

        if result.credit_valuation:
            cv = result.credit_valuation
            lines.append(
                f"**Credit:** {cv.level.value.replace('_', ' ').title()} "
                f"({cv.percentile_10y:.0f}th percentile vs 10Y history)"
            )

        if result.rates_valuation:
            rv = result.rates_valuation
            lines.append(
                f"**Rates:** {rv.level.value.replace('_', ' ').title()} "
                f"({rv.percentile_10y:.0f}th percentile vs 10Y history)"
            )

        lines.append("")
        lines.append(f"**Implication:** {result.regime_context}")

        return "\n".join(lines)


def calculate_valuation_assessment(df: pd.DataFrame) -> ValuationResult:
    """Convenience function for valuation assessment."""
    model = ValuationRiskPremiumModel()
    return model.calculate_full_assessment(df)
