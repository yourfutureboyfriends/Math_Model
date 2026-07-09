"""
Data Contracts — single source of truth for all metric expectations.
Every metric must be defined here BEFORE being implemented anywhere.
"""
from dataclasses import dataclass
from typing import Optional

@dataclass
class MetricContract:
    name: str
    fred_series: Optional[str]
    yf_ticker: Optional[str]
    unit: str                    # "percent", "bps", "index", "zscore"
    multiply_by: float = 1.0     # unit conversion factor
    hard_min: float = -1e9       # REJECT if outside (bad data)
    hard_max: float = 1e9
    typical_min: float = -1e9    # WARN if outside (unusual but possible)
    typical_max: float = 1e9
    fallback_value: Optional[float] = None
    description: str = ""

CONTRACTS = {
    "growth": MetricContract(
        name="GDP Growth QoQ Annualised",
        fred_series="A191RL1Q225SBEA",  # returns percent directly
        yf_ticker=None,
        unit="percent",
        multiply_by=1.0,
        hard_min=-15.0,    hard_max=15.0,
        typical_min=-6.0,  typical_max=8.0,
        fallback_value=2.0,
        description="BEA advance estimate. Q1 2026 = +2.0%",
    ),
    "inflation": MetricContract(
        name="CPI YoY",
        fred_series="CPIAUCSL_PC1",   # direct YoY %, NOT index level
        yf_ticker=None,
        unit="percent",
        multiply_by=1.0,
        hard_min=-5.0,    hard_max=25.0,
        typical_min=0.0,  typical_max=10.0,
        fallback_value=3.3,
        description="BLS Mar 2026 = 3.3%",
    ),
    "hy_spread": MetricContract(
        name="HY Credit Spread",
        fred_series="BAMLH0A0HYM2",   # FRED returns PERCENT (e.g. 2.83)
        yf_ticker=None,
        unit="bps",
        multiply_by=100.0,            # 2.83 × 100 = 283 bps
        hard_min=50.0,    hard_max=2500.0,
        typical_min=150.0, typical_max=1000.0,
        fallback_value=283.0,
        description="After conversion: ~283 bps (Apr 30 2026)",
    ),
    "vix": MetricContract(
        name="VIX",
        fred_series="VIXCLS",
        yf_ticker="^VIX",
        unit="index",
        multiply_by=1.0,
        hard_min=5.0,    hard_max=90.0,
        typical_min=10.0, typical_max=50.0,
        fallback_value=20.0,
    ),
    "yield_curve": MetricContract(
        name="10Y-2Y Yield Spread",
        fred_series="T10Y2Y",         # FRED returns percent (e.g. 0.51)
        yf_ticker=None,
        unit="bps",
        multiply_by=100.0,            # 0.51 × 100 = 51 bps
        hard_min=-300.0,  hard_max=300.0,
        typical_min=-200.0, typical_max=200.0,
        fallback_value=51.0,
    ),
    "fed_funds": MetricContract(
        name="Fed Funds Rate",
        fred_series="FEDFUNDS",
        yf_ticker=None,
        unit="percent",
        multiply_by=1.0,
        hard_min=0.0,  hard_max=25.0,
        typical_min=0.0, typical_max=10.0,
        fallback_value=3.64,  # FIXED: Mar/Apr 2026 actual, was 4.33 (pre-cut)
        description="FRED confirmed 3.64% Mar/Apr 2026. Previous 4.68% was pre-cut value.",
    ),
    "m2_yoy": MetricContract(
        name="M2 Money Supply YoY Growth",
        fred_series="M2SL",
        yf_ticker=None,
        unit="percent",
        multiply_by=1.0,
        hard_min=-20.0, hard_max=50.0,
        typical_min=-5.0, typical_max=25.0,
        fallback_value=8.1,  # Liquidity section shows 8.1%
        description="Compute YoY from level. Liquidity shows 8.1%, Transmission must match.",
    ),
    "sahm_rule": MetricContract(
        name="Sahm Rule Real-Time",
        fred_series="SAHMREALTIME",
        yf_ticker=None,
        unit="pp",
        multiply_by=1.0,
        hard_min=-2.0, hard_max=5.0,
        typical_min=0.0, typical_max=1.5,
        fallback_value=0.20,  # FRED Mar 2026 actual
        description="FRED Mar 2026 = 0.20pp. Trigger threshold = 0.50pp.",
    ),
    "recession_prob": MetricContract(
        name="Recession Probability (Ensemble)",
        fred_series=None,
        yf_ticker=None,
        unit="percent",
        multiply_by=1.0,
        hard_min=0.0,  hard_max=100.0,
        typical_min=2.0, typical_max=60.0,
        fallback_value=30.0,
        description="Ensemble of Sahm, LEI, yield curve, credit impulse",
    ),
    "all_weather_vol": MetricContract(
        name="All Weather Portfolio Volatility",
        fred_series=None,
        yf_ticker=None,
        unit="percent",
        multiply_by=1.0,
        hard_min=1.0,   hard_max=40.0,
        typical_min=3.0, typical_max=20.0,
        fallback_value=6.2,
        description="Annualised portfolio vol from inverse-vol risk parity",
    ),
}

# Fallback vols for All Weather when yfinance is unavailable
ALL_WEATHER_FALLBACK_VOLS = {
    "TLT": 0.14, "TIP": 0.07, "SPY": 0.18, "DBC": 0.22,
    "GLD": 0.16, "HYG": 0.08,
}

# Sahm Rule thresholds (Claudia Sahm, 2019)
SAHM_TRIGGER_THRESHOLD = 0.50   # Official recession trigger
SAHM_WARNING_THRESHOLD = 0.40   # Approaching trigger
SAHM_WATCH_THRESHOLD = 0.20     # Elevated monitoring
