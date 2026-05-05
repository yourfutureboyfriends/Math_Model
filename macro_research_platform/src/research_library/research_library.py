"""
Research Library - Paper to Signal Mapping

Maps 35 research papers to specific signals and implementation files.
Organized by category:
A. Macro data and nowcasting
B. Global liquidity and world macro
C. Business cycle, recession, and credit
D. Macro regimes and asset allocation
E. Cross-asset momentum, value, carry
F. Portfolio construction
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional


class ResearchCategory(Enum):
    """Research paper categories."""
    MACRO_DATA_NOWCASTING = "A. Macro Data and Nowcasting"
    GLOBAL_LIQUIDITY = "B. Global Liquidity and World Macro"
    BUSINESS_CYCLE_CREDIT = "C. Business Cycle, Recession, and Credit"
    MACRO_REGIMES = "D. Macro Regimes and Asset Allocation"
    CROSS_ASSET_FACTORS = "E. Cross-Asset Momentum, Value, Carry"
    PORTFOLIO_CONSTRUCTION = "F. Portfolio Construction and Risk Management"


@dataclass
class ResearchPaper:
    """
    Research paper with full business mapping.

    Every paper must map to specific implementation, not just theory.
    """
    # Identification
    id: str
    title: str
    authors: str
    year: int
    category: ResearchCategory

    # Business mapping
    model_area: str
    business_use: str
    main_idea: str

    # Implementation mapping
    variables_added: List[str]
    implementation_file: str
    signal_created: str
    output_affected: str

    # Status
    implementation_status: str = "not_implemented"  # not_implemented, partial, complete
    limitation: str = ""

    # Additional metadata
    doi: str = ""
    url: str = ""
    notes: str = ""


# =============================================================================
# A. MACRO DATA AND NOWCASTING
# =============================================================================

PAPER_REGISTRY: Dict[str, ResearchPaper] = {
    # A1. McCracken and Ng - FRED-MD
    "fred_md": ResearchPaper(
        id="fred_md",
        title="FRED-MD: A Monthly Database for Macroeconomic Research",
        authors="McCracken and Ng",
        year=2016,
        category=ResearchCategory.MACRO_DATA_NOWCASTING,
        model_area="Data backbone",
        business_use="Create broad macro data backbone instead of hand-picked indicators",
        main_idea="Use 100+ macro series covering output, labor, prices, financial markets",
        variables_added=["macro_breadth_score", "growth_diffusion_index", "inflation_diffusion_index"],
        implementation_file="src/data/fred_md_loader.py",
        signal_created="macro_breadth_score",
        output_affected="Nowcast and growth/inflation signals",
        limitation="Requires FRED API access and data maintenance",
    ),

    # A2. McCracken and Ng - FRED-QD
    "fred_qd": ResearchPaper(
        id="fred_qd",
        title="FRED-QD: A Quarterly Database for Macroeconomic Research",
        authors="McCracken and Ng",
        year=2020,
        category=ResearchCategory.MACRO_DATA_NOWCASTING,
        model_area="Data backbone - quarterly",
        business_use="Add longer-horizon quarterly data for structural analysis",
        main_idea="Quarterly aggregates for GDP, productivity, profits",
        variables_added=["quarterly_growth_proxy", "productivity_trend", "profit_cycle"],
        implementation_file="src/data/fred_qd_loader.py",
        signal_created="quarterly_macro_cycle",
        output_affected="Business cycle phase and long-term trends",
        limitation="Lower frequency, more lag",
    ),

    # A3. Stock and Watson - Diffusion Indexes
    "sw_diffusion": ResearchPaper(
        id="sw_diffusion",
        title="Macroeconomic Forecasting Using Diffusion Indexes",
        authors="Stock and Watson",
        year=2002,
        category=ResearchCategory.MACRO_DATA_NOWCASTING,
        model_area="Nowcasting",
        business_use="Compress many indicators into common macro factors",
        main_idea="Use PCA to extract common factors from many macro series",
        variables_added=["diffusion_factor_1", "diffusion_factor_2", "diffusion_factor_3"],
        implementation_file="src/nowcasting/diffusion_index_model.py",
        signal_created="business_conditions_diffusion_index",
        output_affected="Business conditions nowcast",
        limitation="PCA may miss nonlinear relationships",
    ),

    # A4. Aruoba, Diebold, Scotti - Real-Time Business Conditions
    "ads_index": ResearchPaper(
        id="ads_index",
        title="Real-Time Measurement of Business Conditions",
        authors="Aruoba, Diebold, and Scotti",
        year=2009,
        category=ResearchCategory.MACRO_DATA_NOWCASTING,
        model_area="Business conditions index",
        business_use="Build real-time business conditions index from mixed-frequency data",
        main_idea="Dynamic factor model using mixed-frequency macro data",
        variables_added=["ads_business_conditions_index"],
        implementation_file="src/nowcasting/ads_index.py",
        signal_created="real_time_business_conditions",
        output_affected="Daily/weekly business conditions update",
        limitation="Requires high-frequency data feeds",
    ),

    # A5. Giannone, Reichlin, Small - Nowcasting GDP
    "grs_nowcast": ResearchPaper(
        id="grs_nowcast",
        title="Nowcasting GDP and Inflation",
        authors="Giannone, Reichlin, and Small",
        year=2008,
        category=ResearchCategory.MACRO_DATA_NOWCASTING,
        model_area="GDP nowcasting",
        business_use="Build nowcast engine for growth before official releases",
        main_idea="Use bridge equations with monthly indicators to nowcast quarterly GDP",
        variables_added=["gdp_nowcast", "nowcast_error", "nowcast_confidence"],
        implementation_file="src/nowcasting/bridge_model.py",
        signal_created="gdp_nowcast",
        output_affected="Growth expectations and nowcast confidence",
        limitation="Dependent on timely monthly data",
    ),

    # A6. Bok et al - Macroeconomic Nowcasting with Big Data
    "bok_big_data": ResearchPaper(
        id="bok_big_data",
        title="Macroeconomic Nowcasting and Forecasting with Big Data",
        authors="Bok, Caratelli, Giannone, Sbordone, Tambalotti",
        year=2018,
        category=ResearchCategory.MACRO_DATA_NOWCASTING,
        model_area="Nowcasting with big data",
        business_use="Use broader data sources for professional macro engine",
        main_idea="Incorporate Google Trends, sentiment, high-frequency data",
        variables_added=["big_data_factor", "sentiment_adjustment"],
        implementation_file="src/nowcasting/big_data_nowcast.py",
        signal_created="big_data_macro_signal",
        output_affected="Real-time macro assessment",
        limitation="Data quality varies; sentiment can be noisy",
    ),

    # A7. Stock and Watson - Principal Components
    "sw_pca": ResearchPaper(
        id="sw_pca",
        title="Forecasting Using Principal Components from a Large Number of Predictors",
        authors="Stock and Watson",
        year=2002,
        category=ResearchCategory.MACRO_DATA_NOWCASTING,
        model_area="Dimension reduction",
        business_use="Handle many macro predictors efficiently",
        main_idea="PCA extracts factors that predict better than individual series",
        variables_added=["principal_component_factors"],
        implementation_file="src/features/pca_factors.py",
        signal_created="pca_macro_factor",
        output_affected="All macro models",
        limitation="Linear only; assumes stable relationships",
    ),
}

# =============================================================================
# B. GLOBAL LIQUIDITY AND WORLD MACRO
# =============================================================================

PAPER_REGISTRY.update({
    # B8. Rey - Dilemma not Trilemma
    "rey_dilemma": ResearchPaper(
        id="rey_dilemma",
        title="Dilemma not Trilemma: The Global Financial Cycle and Monetary Policy Independence",
        authors="Helene Rey",
        year=2013,
        category=ResearchCategory.GLOBAL_LIQUIDITY,
        model_area="Global financial cycle",
        business_use="Add global financial cycle and dollar liquidity logic",
        main_idea="US monetary policy transmits globally through capital flows, not just exchange rates",
        variables_added=["global_liquidity_pressure", "global_risk_cycle", "dollar_spillover_index"],
        implementation_file="src/global_macro/global_liquidity_model.py",
        signal_created="global_liquidity_pressure",
        output_affected="Global risk appetite and EM positioning",
        limitation="Difficult to measure global liquidity in real-time",
    ),

    # B9. Miranda-Agrippino and Rey - US Policy and Global Cycle
    "mar_us_global": ResearchPaper(
        id="mar_us_global",
        title="U.S. Monetary Policy and the Global Financial Cycle",
        authors="Miranda-Agrippino and Rey",
        year=2020,
        category=ResearchCategory.GLOBAL_LIQUIDITY,
        model_area="US policy transmission",
        business_use="Model how US monetary policy transmits into global risky assets",
        main_idea="US monetary policy shocks explain significant global asset price variance",
        variables_added=["us_policy_global_impact", "fed_shock_global_transmission"],
        implementation_file="src/global_macro/us_policy_transmission.py",
        signal_created="us_policy_global_transmission_signal",
        output_affected="Global equity and credit positioning",
        limitation="Requires identifying policy shocks vs endogenous responses",
    ),

    # B10. Du, Tepper, Verdelhan - CIP Deviations
    "dtv_cip": ResearchPaper(
        id="dtv_cip",
        title="Deviations from Covered Interest Rate Parity",
        authors="Du, Tepper, and Verdelhan",
        year=2018,
        category=ResearchCategory.GLOBAL_LIQUIDITY,
        model_area="Dollar funding stress",
        business_use="Add dollar funding stress and cross-currency basis logic",
        main_idea="CIP deviations measure dollar funding pressure in global markets",
        variables_added=["cip_deviation", "dollar_funding_basis", "fx_swap_stress"],
        implementation_file="src/signals/dollar_funding_signals.py",
        signal_created="dollar_funding_stress",
        output_affected="FX positioning and EM vulnerability assessment",
        limitation="Requires high-frequency FX swap data",
    ),

    # B11. Ahir, Bloom, Furceri - World Uncertainty Index
    "abf_wui": ResearchPaper(
        id="abf_wui",
        title="World Uncertainty Index",
        authors="Ahir, Bloom, and Furceri",
        year=2022,
        category=ResearchCategory.GLOBAL_LIQUIDITY,
        model_area="Global uncertainty",
        business_use="Add global uncertainty as macro risk overlay",
        main_idea="Text-based uncertainty index from Economist Intelligence Unit",
        variables_added=["world_uncertainty_index", "country_uncertainty_premium"],
        implementation_file="src/signals/uncertainty_signals.py",
        signal_created="global_uncertainty_risk",
        output_affected="Risk-off positioning and flight-to-quality",
        limitation="Text-based; may lag real-time sentiment",
    ),

    # B12. Baker, Bloom, Davis - Economic Policy Uncertainty
    "bbd_epu": ResearchPaper(
        id="bbd_epu",
        title="Measuring Economic Policy Uncertainty",
        authors="Baker, Bloom, and Davis",
        year=2016,
        category=ResearchCategory.GLOBAL_LIQUIDITY,
        model_area="Policy uncertainty",
        business_use="Add policy uncertainty to recession and risk appetite models",
        main_idea="Newspaper-based policy uncertainty index predicts investment and employment",
        variables_added=["policy_uncertainty_index", "epu_risk_premium"],
        implementation_file="src/signals/uncertainty_signals.py",
        signal_created="policy_uncertainty_risk",
        output_affected="Recession probability and risk appetite",
        limitation="US-focused; may not capture all policy risks",
    ),
})

# =============================================================================
# C. BUSINESS CYCLE, RECESSION, AND CREDIT
# =============================================================================

PAPER_REGISTRY.update({
    # C13. Estrella and Mishkin - Predicting US Recessions
    "em_recession": ResearchPaper(
        id="em_recession",
        title="Predicting U.S. Recessions: Financial Variables as Leading Indicators",
        authors="Estrella and Mishkin",
        year=1998,
        category=ResearchCategory.BUSINESS_CYCLE_CREDIT,
        model_area="Recession prediction",
        business_use="Improve recession risk model with financial variables",
        main_idea="Yield curve slope + stock prices + leading indicators predict recessions",
        variables_added=["rec_prob_yield_curve", "rec_prob_financial", "rec_prob_combined"],
        implementation_file="src/models/recession_risk/recession_model.py",
        signal_created="recession_probability_combined",
        output_affected="Recession risk and defensive positioning",
        limitation="Historical patterns may not repeat; low recession frequency",
    ),

    # C14. Estrella and Hardouvelis - Term Structure
    "eh_term_structure": ResearchPaper(
        id="eh_term_structure",
        title="The Term Structure as a Predictor of Real Economic Activity",
        authors="Estrella and Hardouvelis",
        year=1991,
        category=ResearchCategory.BUSINESS_CYCLE_CREDIT,
        model_area="Yield curve signal",
        business_use="Use yield curve as growth and recession signal",
        main_idea="Inverted yield curve predicts future economic slowdown",
        variables_added=["yield_curve_slope", "term_spread_growth_signal"],
        implementation_file="src/signals/growth_signals.py",
        signal_created="yield_curve_recession_signal",
        output_affected="Duration positioning and recession probability",
        limitation="Can give false signals in low-rate environments",
    ),

    # C15. Borio, Drehmann, Xia - Financial Cycle vs Term Spread
    "bdx_financial_cycle": ResearchPaper(
        id="bdx_financial_cycle",
        title="Predicting Recessions: Financial Cycle Versus Term Spread",
        authors="Borio, Drehmann, and Xia",
        year=2019,
        category=ResearchCategory.BUSINESS_CYCLE_CREDIT,
        model_area="Financial cycle",
        business_use="Combine financial cycle variables with term spread",
        main_idea="Credit and property prices add predictive power beyond yield curve",
        variables_added=["financial_cycle_index", "credit_gap", "property_cycle"],
        implementation_file="src/models/recession_risk/financial_cycle.py",
        signal_created="financial_cycle_recession_signal",
        output_affected="Recession risk and financial sector positioning",
        limitation="Financial cycle data may be lagging",
    ),

    # C16. Gilchrist and Zakrajsek - Credit Spreads
    "gz_credit_spreads": ResearchPaper(
        id="gz_credit_spreads",
        title="Credit Spreads and Business Cycle Fluctuations",
        authors="Gilchrist and Zakrajsek",
        year=2012,
        category=ResearchCategory.BUSINESS_CYCLE_CREDIT,
        model_area="Credit spreads",
        business_use="Make credit stress a leading indicator of future weakness",
        main_idea="Excess bond premium predicts business investment and employment",
        variables_added=["excess_bond_premium", "gz_credit_spread", "credit_impulse"],
        implementation_file="src/signals/credit_signals.py",
        signal_created="credit_stress_signal",
        output_affected="Credit positioning and cyclical sector allocation",
        limitation="Requires corporate bond price data",
    ),

    # C17. Lopez-Salido, Stein, Zakrajsek - Credit Sentiment
    "lsz_credit_sentiment": ResearchPaper(
        id="lsz_credit_sentiment",
        title="Credit Market Sentiment and the Business Cycle",
        authors="Lopez-Salido, Stein, and Zakrajsek",
        year=2017,
        category=ResearchCategory.BUSINESS_CYCLE_CREDIT,
        model_area="Credit sentiment",
        business_use="Add credit sentiment and risk appetite into recession model",
        main_idea="Credit market sentiment predicts future downturns",
        variables_added=["credit_sentiment_index", "credit_market_risk_appetite"],
        implementation_file="src/signals/credit_signals.py",
        signal_created="credit_impulse_signal",
        output_affected="Credit risk positioning",
        limitation="Sentiment measures can be noisy",
    ),

    # C18. Adrian, Boyarchenko, Giannone - Vulnerable Growth
    "abg_vulnerable": ResearchPaper(
        id="abg_vulnerable",
        title="Vulnerable Growth",
        authors="Adrian, Boyarchenko, and Giannone",
        year=2019,
        category=ResearchCategory.BUSINESS_CYCLE_CREDIT,
        model_area="Growth at risk",
        business_use="Estimate downside growth risk rather than only central case",
        main_idea="Quantile regression estimates conditional tail risks to growth",
        variables_added=["growth_at_risk_5pct", "growth_at_risk_10pct", "growth_risk_distribution"],
        implementation_file="src/models/business_conditions/growth_at_risk.py",
        signal_created="growth_at_risk",
        output_affected="Tail risk hedging and scenario analysis",
        limitation="Requires long history for quantile estimation",
    ),
})

# =============================================================================
# D. MACRO REGIMES AND ASSET ALLOCATION
# =============================================================================

PAPER_REGISTRY.update({
    # D19. Bridgewater - All Weather
    "bridgewater_all_weather": ResearchPaper(
        id="bridgewater_all_weather",
        title="All Weather Story",
        authors="Bridgewater Associates",
        year=1996,
        category=ResearchCategory.MACRO_REGIMES,
        model_area="Risk parity",
        business_use="Balance portfolio risk across growth and inflation environments",
        main_idea="Different assets perform in different growth/inflation regimes",
        variables_added=["environment_balance_score", "risk_parity_weights"],
        implementation_file="src/portfolio/risk_parity_allocator.py",
        signal_created="environment_balance_score",
        output_affected="Asset allocation weights",
        limitation="Assumes stable risk premia; leverage required",
    ),

    # D20. Hamilton - Regime Switching
    "hamilton_regime": ResearchPaper(
        id="hamilton_regime",
        title="Regime Switching and the Business Cycle",
        authors="James Hamilton",
        year=1989,
        category=ResearchCategory.MACRO_REGIMES,
        model_area="Regime probabilities",
        business_use="Move from hard labels to regime probabilities",
        main_idea="Markov-switching models estimate probability of being in each regime",
        variables_added=["regime_probability", "transition_probabilities"],
        implementation_file="src/models/macro_regime/regime_switching.py",
        signal_created="regime_probability",
        output_affected="Probabilistic regime positioning",
        limitation="Can be slow to detect regime changes",
    ),

    # D21. Ang and Timmermann - Regime Changes
    "at_regime_changes": ResearchPaper(
        id="at_regime_changes",
        title="Regime Changes and Financial Markets",
        authors="Andrew Ang and Allan Timmermann",
        year=2012,
        category=ResearchCategory.MACRO_REGIMES,
        model_area="Regime instability",
        business_use="Add regime instability and transition risk",
        main_idea="Regime changes are common in asset returns; transition risk matters",
        variables_added=["regime_stability_index", "transition_risk_premium"],
        implementation_file="src/models/macro_regime/regime_transition.py",
        signal_created="regime_transition_risk",
        output_affected="Position sizing during regime uncertainty",
        limitation="Multiple regimes hard to identify ex-ante",
    ),

    # D22. Insight Investment / BNY style
    "insight_macro_aa": ResearchPaper(
        id="insight_macro_aa",
        title="Macro-based Asset Allocation: An Empirical Analysis",
        authors="Insight Investment / BNY style framework",
        year=2015,
        category=ResearchCategory.MACRO_REGIMES,
        model_area="Transparent macro allocation",
        business_use="Use transparent macro regimes to guide allocation",
        main_idea="Systematic macro regimes drive asset class performance",
        variables_added=["macro_regime_allocation", "regime_factor_exposures"],
        implementation_file="src/models/portfolio_construction/macro_allocator.py",
        signal_created="macro_regime_allocation",
        output_affected="Strategic asset allocation",
        limitation="Regime classification can be subjective",
    ),

    # D23. EIB - Macro-based Asset Allocation
    "eib_macro_aa": ResearchPaper(
        id="eib_macro_aa",
        title="Macro-based Asset Allocation: An Empirical Analysis",
        authors="European Investment Bank",
        year=2018,
        category=ResearchCategory.MACRO_REGIMES,
        model_area="Macro-financial cycle",
        business_use="Connect macro-financial cycle turning points to asset allocation",
        main_idea="Macro-financial cycles predict asset returns better than static allocation",
        variables_added=["macro_financial_cycle_phase", "cycle_position_allocation"],
        implementation_file="src/models/portfolio_construction/cycle_allocator.py",
        signal_created="macro_financial_cycle_signal",
        output_affected="Tactical asset allocation",
        limitation="Cycle turning points difficult to identify in real-time",
    ),
})

# =============================================================================
# E. CROSS-ASSET MOMENTUM, VALUE, CARRY
# =============================================================================

PAPER_REGISTRY.update({
    # E24. Moskowitz, Ooi, Pedersen - Time Series Momentum
    "mop_tsmom": ResearchPaper(
        id="mop_tsmom",
        title="Time Series Momentum",
        authors="Moskowitz, Ooi, and Pedersen",
        year=2012,
        category=ResearchCategory.CROSS_ASSET_FACTORS,
        model_area="Trend following",
        business_use="Use price trends to confirm or reject macro signals",
        main_idea="Assets that trend up continue to trend up; trend down continue down",
        variables_added=["ts_momentum_12m", "ts_momentum_6m", "ts_momentum_1m"],
        implementation_file="src/signals/momentum_signals.py",
        signal_created="cross_asset_momentum_confirmation",
        output_affected="Timing of macro trades; trend confirmation",
        limitation="Works poorly in choppy markets; crash risk",
    ),

    # E25. Hurst, Ooi, Pedersen - Century of Trend Following
    "hop_trend": ResearchPaper(
        id="hop_trend",
        title="A Century of Evidence on Trend Following Investing",
        authors="Hurst, Ooi, and Pedersen",
        year=2017,
        category=ResearchCategory.CROSS_ASSET_FACTORS,
        model_area="Trend following",
        business_use="Add trend following as crisis alpha and timing overlay",
        main_idea="Trend following has worked across decades and asset classes",
        variables_added=["trend_following_score", "crisis_alpha_indicator"],
        implementation_file="src/signals/trend_following.py",
        signal_created="trend_following_overlay",
        output_affected="Risk-off timing; crisis protection",
        limitation="Can underperform in strong trending bull markets",
    ),

    # E26. Asness, Moskowitz, Pedersen - Value and Momentum
    "amp_valmom": ResearchPaper(
        id="amp_valmom",
        title="Value and Momentum Everywhere",
        authors="Asness, Moskowitz, and Pedersen",
        year=2013,
        category=ResearchCategory.CROSS_ASSET_FACTORS,
        model_area="Value and momentum",
        business_use="Apply value and momentum across asset classes",
        main_idea="Value and momentum work in equities, bonds, currencies, commodities",
        variables_added=["cross_asset_value_score", "cross_asset_momentum_score"],
        implementation_file="src/signals/value_momentum.py",
        signal_created="cross_asset_value_score",
        output_affected="Cross-asset allocation; factor timing",
        limitation="Value can underperform for long periods",
    ),

    # E27. Koijen, Moskowitz, Pedersen - Carry
    "kmp_carry": ResearchPaper(
        id="kmp_carry",
        title="Carry",
        authors="Koijen, Moskowitz, and Pedersen",
        year=2018,
        category=ResearchCategory.CROSS_ASSET_FACTORS,
        model_area="Carry trades",
        business_use="Add expected return from carry across asset classes",
        main_idea="High-yielding assets outperform low-yielding assets across markets",
        variables_added=["fx_carry_score", "rates_carry_score", "commodity_carry_score", "equity_carry_score"],
        implementation_file="src/signals/carry_signals.py",
        signal_created="carry_score",
        output_affected="Yield-seeking positions; risk appetite",
        limitation="Crashes during risk-off events; skewed returns",
    ),

    # E28. Cochrane and Piazzesi - Bond Risk Premia
    "cp_bond_rp": ResearchPaper(
        id="cp_bond_rp",
        title="Bond Risk Premia",
        authors="Cochrane and Piazzesi",
        year=2005,
        category=ResearchCategory.CROSS_ASSET_FACTORS,
        model_area="Bond risk premia",
        business_use="Improve rates and duration expected return model",
        main_idea="Linear combination of forward rates predicts bond returns",
        variables_added=["cochrane_piazzesi_factor", "bond_risk_premium"],
        implementation_file="src/signals/rates_signals.py",
        signal_created="bond_risk_premium",
        output_affected="Duration positioning",
        limitation="Out-of-sample performance weaker than in-sample",
    ),

    # E29. Campbell and Shiller - Yield Spreads
    "cs_yield_spreads": ResearchPaper(
        id="cs_yield_spreads",
        title="Yield Spreads and Interest Rate Movements",
        authors="Campbell and Shiller",
        year=1991,
        category=ResearchCategory.CROSS_ASSET_FACTORS,
        model_area="Yield spreads",
        business_use="Improve yield curve and rates interpretation",
        main_idea="Yield spread predicts future interest rate changes",
        variables_added=["yield_spread_signal", "term_premium_estimate"],
        implementation_file="src/signals/rates_signals.py",
        signal_created="yield_spread_signal",
        output_affected="Rates positioning",
        limitation="Low rates environment changes relationships",
    ),
})

# =============================================================================
# F. PORTFOLIO CONSTRUCTION
# =============================================================================

PAPER_REGISTRY.update({
    # F30. Black and Litterman - Global Portfolio Optimization
    "bl_optimization": ResearchPaper(
        id="bl_optimization",
        title="Global Portfolio Optimization",
        authors="Black and Litterman",
        year=1992,
        category=ResearchCategory.PORTFOLIO_CONSTRUCTION,
        model_area="Portfolio optimization",
        business_use="Translate macro views into portfolio weights without extreme allocations",
        main_idea="Combine equilibrium returns with investor views using Bayesian approach",
        variables_added=["bl_expected_returns", "bl_covariance_matrix", "bl_optimal_weights"],
        implementation_file="src/portfolio/black_litterman_allocator.py",
        signal_created="black_litterman_weights",
        output_affected="Portfolio allocation weights",
        limitation="Requires specifying view confidence levels",
    ),

    # F31. Moreira and Muir - Volatility-Managed Portfolios
    "mm_vol_manage": ResearchPaper(
        id="mm_vol_manage",
        title="Volatility-Managed Portfolios",
        authors="Moreira and Muir",
        year=2017,
        category=ResearchCategory.PORTFOLIO_CONSTRUCTION,
        model_area="Volatility targeting",
        business_use="Reduce exposure when realized volatility is high",
        main_idea="Returns are predictable from lagged volatility; scale exposure inversely",
        variables_added=["volatility_forecast", "volatility_adjusted_exposure"],
        implementation_file="src/portfolio/volatility_targeting.py",
        signal_created="volatility_managed_position",
        output_affected="Position sizing and risk budget",
        limitation="Transaction costs from frequent rebalancing",
    ),

    # F32. Barroso and Santa-Clara - Momentum Has Its Moments
    "bs_momentum_risk": ResearchPaper(
        id="bs_momentum_risk",
        title="Momentum Has Its Moments",
        authors="Barroso and Santa-Clara",
        year=2015,
        category=ResearchCategory.PORTFOLIO_CONSTRUCTION,
        model_area="Momentum risk management",
        business_use="Risk manage momentum signals",
        main_idea="Momentum crashes occur after volatile periods; target constant volatility",
        variables_added=["momentum_volatility", "momentum_crashes_risk"],
        implementation_file="src/portfolio/momentum_risk_management.py",
        signal_created="risk_managed_momentum",
        output_affected="Momentum signal sizing",
        limitation="May miss some momentum gains",
    ),

    # F33. Frazzini and Pedersen - Betting Against Beta
    "fp_bab": ResearchPaper(
        id="fp_bab",
        title="Betting Against Beta",
        authors="Frazzini and Pedersen",
        year=2014,
        category=ResearchCategory.PORTFOLIO_CONSTRUCTION,
        model_area="Low volatility anomaly",
        business_use="Understand leverage constraints and low-risk anomaly",
        main_idea="Leverage-constrained investors buy high-beta; low-beta outperforms",
        variables_added=["beta_arbitrage_score", "leverage_constraint_index"],
        implementation_file="src/portfolio/betting_against_beta.py",
        signal_created="beta_arbitrage",
        output_affected="Factor allocation; defensive positioning",
        limitation="Requires leverage to exploit fully",
    ),

    # F34. Asness, Frazzini, Pedersen - Leverage Aversion
    "afp_risk_parity": ResearchPaper(
        id="afp_risk_parity",
        title="Leverage Aversion and Risk Parity",
        authors="Asness, Frazzini, and Pedersen",
        year=2012,
        category=ResearchCategory.PORTFOLIO_CONSTRUCTION,
        model_area="Risk parity",
        business_use="Improve risk-balanced portfolio construction",
        main_idea="Risk parity balances risk contributions; leverage improves returns",
        variables_added=["risk_parity_weights", "risk_contribution_balance"],
        implementation_file="src/portfolio/risk_parity_allocator.py",
        signal_created="risk_parity_allocation",
        output_affected="Risk budget allocation",
        limitation="Requires leverage; assumes normal risk",
    ),

    # F35. Markowitz - Portfolio Selection
    "markowitz_portfolio": ResearchPaper(
        id="markowitz_portfolio",
        title="Portfolio Selection",
        authors="Harry Markowitz",
        year=1952,
        category=ResearchCategory.PORTFOLIO_CONSTRUCTION,
        model_area="Mean-variance optimization",
        business_use="Baseline mean-variance portfolio logic",
        main_idea="Optimal portfolios balance expected return and variance",
        variables_added=["mean_variance_efficient_frontier", "sharpe_optimal_portfolio"],
        implementation_file="src/portfolio/mean_variance_optimizer.py",
        signal_created="mean_variance_optimal",
        output_affected="Baseline portfolio construction",
        limitation="Sensitive to input estimates; corner solutions",
    ),
})


class ResearchLibrary:
    """Manager for the research paper library."""

    def __init__(self):
        self.papers = PAPER_REGISTRY

    def get_paper(self, paper_id: str) -> Optional[ResearchPaper]:
        """Get a paper by ID."""
        return self.papers.get(paper_id)

    def get_papers_by_category(self, category: ResearchCategory) -> List[ResearchPaper]:
        """Get all papers in a category."""
        return [p for p in self.papers.values() if p.category == category]

    def get_papers_by_signal(self, signal_name: str) -> List[ResearchPaper]:
        """Get papers that create a specific signal."""
        return [p for p in self.papers.values()
                if signal_name.lower() in p.signal_created.lower()]

    def get_implementation_status(self) -> Dict[str, int]:
        """Get implementation status summary."""
        status = {}
        for p in self.papers.values():
            status[p.implementation_status] = status.get(p.implementation_status, 0) + 1
        return status

    def get_signal_paper_map(self) -> Dict[str, List[str]]:
        """Get mapping of signals to their supporting papers."""
        mapping = {}
        for p in self.papers.values():
            signal = p.signal_created
            if signal not in mapping:
                mapping[signal] = []
            mapping[signal].append(p.id)
        return mapping

    def export_to_markdown(self, output_path: str) -> str:
        """Export the research library to markdown."""
        lines = ["# Research Library\n\n"]
        lines.append(f"Total papers: {len(self.papers)}\n\n")

        # By category
        for category in ResearchCategory:
            papers = self.get_papers_by_category(category)
            if papers:
                lines.append(f"## {category.value}\n\n")
                for p in papers:
                    lines.append(f"### {p.title}\n\n")
                    lines.append(f"- **Authors:** {p.authors}\n")
                    lines.append(f"- **Year:** {p.year}\n")
                    lines.append(f"- **Business Use:** {p.business_use}\n")
                    lines.append(f"- **Signal:** {p.signal_created}\n")
                    lines.append(f"- **Implementation:** {p.implementation_file}\n")
                    lines.append(f"- **Status:** {p.implementation_status}\n")
                    lines.append(f"- **Limitation:** {p.limitation}\n\n")

        content = "".join(lines)

        with open(output_path, "w") as f:
            f.write(content)

        return output_path


# Convenience functions
def get_paper(paper_id: str) -> Optional[ResearchPaper]:
    """Get a paper by ID."""
    return PAPER_REGISTRY.get(paper_id)


def get_papers_by_category(category: ResearchCategory) -> List[ResearchPaper]:
    """Get papers by category."""
    return [p for p in PAPER_REGISTRY.values() if p.category == category]


def get_papers_by_signal(signal_name: str) -> List[ResearchPaper]:
    """Get papers by signal."""
    return [p for p in PAPER_REGISTRY.values()
            if signal_name.lower() in p.signal_created.lower()]


def get_implementation_status() -> Dict[str, int]:
    """Get implementation status summary."""
    status = {}
    for p in PAPER_REGISTRY.values():
        status[p.implementation_status] = status.get(p.implementation_status, 0) + 1
    return status
