"""
Signals Module

Systematic trading signals based on macroeconomic relationships.
"""

from .signal_base import (
    Signal,
    MacroSignal,
    TechnicalSignal,
    CrossAssetSignal,
    CompositeSignal,
    SignalDirection,
    SignalConfidence,
    SignalOutput,
    SignalPerformance,
)
from .signal_registry import SignalRegistry, get_default_registry
from .regime_signals import (
    GrowthInflationRegimeSignal,
    BusinessCyclePhaseSignal,
    PolicyStanceSignal,
)
from .macro_rate_signals import (
    InflationExpectationsSignal,
    YieldCurveSteepenerSignal,
    CreditCycleSignal,
    TermPremiumSignal,
)
from .cross_asset_signals import (
    RatesFXSignal,
    CommodityInflationSignal,
    CreditEquitySignal,
    DollarEMSignal,
    RealRatesGoldSignal,
)
from .growth_signals import (
    GrowthDiffusionSignal,
    GDPNowcastSignal,
    BusinessConditionsSignal,
)
from .inflation_signals import (
    InflationDiffusionSignal,
    InflationExpectationsSignal as InflationExpectationsDiffSignal,
    InflationMomentumSignal,
)
from .credit_signals import (
    CreditStressSignal,
    CreditImpulseSignal,
    CreditSpreadMomentumSignal,
)
from .global_liquidity_signals import (
    GlobalLiquidityPressureSignal,
    DollarFundingStressSignal,
    GlobalRiskCycleSignal,
)
from .uncertainty_signals import (
    PolicyUncertaintySignal,
    GlobalUncertaintySignal,
    VolatilityUncertaintySignal,
)
from .momentum_signals import (
    TimeSeriesMomentumSignal,
    CrossAssetMomentumSignal,
    TrendFollowingSignal,
    MomentumReversalSignal,
)
from .valuation_signals import (
    CAPESignal,
    YieldGapSignal,
    ValueSpreadSignal,
    CreditYieldSignal,
    AssetClassValuationSignal,
)
from .carry_signals import (
    TermPremiumCarrySignal,
    CreditCarrySignal,
    FXCarrySignal,
    CarryTradeRiskSignal,
    RollDownCarrySignal,
)
from .commodity_signals import (
    CommodityCurveSignal,
    InventoryPressureSignal,
    CommodityMomentumSignal,
    DollarCommoditySignal,
)
from .dollar_signals import (
    DollarCycleSignal,
    DollarSafeHavenSignal,
    DollarCarrySignal,
    DollarTechnicalSignal,
    DollarEMStressSignal,
)
from .policy_signals import (
    FedPolicySurpriseSignal,
    PolicyStanceSignal as CBPolicyStanceSignal,
    QuantitativeTighteningSignal,
    FiscalImpulseSignal,
    ForwardGuidanceSignal,
)

__all__ = [
    "Signal",
    "MacroSignal",
    "TechnicalSignal",
    "CrossAssetSignal",
    "CompositeSignal",
    "SignalDirection",
    "SignalConfidence",
    "SignalOutput",
    "SignalPerformance",
    "SignalRegistry",
    "get_default_registry",
    "GrowthInflationRegimeSignal",
    "BusinessCyclePhaseSignal",
    "PolicyStanceSignal",
    "InflationExpectationsSignal",
    "YieldCurveSteepenerSignal",
    "CreditCycleSignal",
    "TermPremiumSignal",
    "RatesFXSignal",
    "CommodityInflationSignal",
    "CreditEquitySignal",
    "DollarEMSignal",
    "RealRatesGoldSignal",
    # Growth signals
    "GrowthDiffusionSignal",
    "GDPNowcastSignal",
    "BusinessConditionsSignal",
    # Inflation signals
    "InflationDiffusionSignal",
    "InflationExpectationsDiffSignal",
    "InflationMomentumSignal",
    # Credit signals
    "CreditStressSignal",
    "CreditImpulseSignal",
    "CreditSpreadMomentumSignal",
    # Global liquidity signals
    "GlobalLiquidityPressureSignal",
    "DollarFundingStressSignal",
    "GlobalRiskCycleSignal",
    # Uncertainty signals
    "PolicyUncertaintySignal",
    "GlobalUncertaintySignal",
    "VolatilityUncertaintySignal",
    # Momentum signals
    "TimeSeriesMomentumSignal",
    "CrossAssetMomentumSignal",
    "TrendFollowingSignal",
    "MomentumReversalSignal",
    # Valuation signals
    "CAPESignal",
    "YieldGapSignal",
    "ValueSpreadSignal",
    "CreditYieldSignal",
    "AssetClassValuationSignal",
    # Carry signals
    "TermPremiumCarrySignal",
    "CreditCarrySignal",
    "FXCarrySignal",
    "CarryTradeRiskSignal",
    "RollDownCarrySignal",
    # Commodity signals
    "CommodityCurveSignal",
    "InventoryPressureSignal",
    "CommodityMomentumSignal",
    "DollarCommoditySignal",
    # Dollar signals
    "DollarCycleSignal",
    "DollarSafeHavenSignal",
    "DollarCarrySignal",
    "DollarTechnicalSignal",
    "DollarEMStressSignal",
    # Policy signals
    "FedPolicySurpriseSignal",
    "CBPolicyStanceSignal",
    "QuantitativeTighteningSignal",
    "FiscalImpulseSignal",
    "ForwardGuidanceSignal",
]
