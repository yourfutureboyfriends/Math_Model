"""
config.py — Central configuration for the macro regime model.

All settings are overridable via environment variables using the pattern:
    export MACRO_ZSCORE_WINDOW=48

This allows production deployments, CI pipelines, and local development
to use different configurations without code changes.
"""

import os
from pathlib import Path

# Get project root (parent of this file)
PROJECT_ROOT = Path(__file__).parent

# =============================================================================
# Data Source Configuration
# =============================================================================
# Options: "sample" | "fred" | "mixed"
#   sample: Use local CSV files (default, no API key needed)
#   fred: Pull from FRED API (requires FRED_API_KEY)
#   mixed: Combine FRED data with manual overrides for indicators not on FRED
DATA_SOURCE = os.getenv("MACRO_DATA_SOURCE", "sample")

# Path to sample data CSV (used when DATA_SOURCE="sample" or as fallback)
SAMPLE_DATA_PATH = Path(
    os.getenv("MACRO_SAMPLE_DATA_PATH", PROJECT_ROOT / "data" / "raw" / "sample_macro_data.csv")
)

# Cache settings for FRED API data
REFRESH_CACHE_HOURS = int(os.getenv("MACRO_REFRESH_CACHE_HOURS", "24"))
FRED_CACHE_DIR = Path(
    os.getenv("MACRO_FRED_CACHE_DIR", PROJECT_ROOT / "data" / "processed" / "fred_cache")
)

# =============================================================================
# Model Hyperparameters
# =============================================================================
# Rolling window for z-score computation (months)
ZSCORE_WINDOW = int(os.getenv("MACRO_ZSCORE_WINDOW", "36"))

# Window for computing score direction/regime classification (months)
DIRECTION_WINDOW = int(os.getenv("MACRO_DIRECTION_WINDOW", "3"))

# Minimum observations required before computing z-scores
MIN_PERIODS = int(os.getenv("MACRO_MIN_PERIODS", "12"))

# Moving average window for smoothing (months)
MA_WINDOW = int(os.getenv("MACRO_MA_WINDOW", "3"))

# =============================================================================
# Scoring Thresholds
# =============================================================================
# Threshold for determining if a score direction has changed materially
DIRECTION_THRESHOLD = float(os.getenv("MACRO_DIRECTION_THRESHOLD", "0.10"))

# Sector signal thresholds
OVERWEIGHT_THRESHOLD = float(os.getenv("MACRO_OW_THRESHOLD", "0.5"))
UNDERWEIGHT_THRESHOLD = float(os.getenv("MACRO_UW_THRESHOLD", "-0.5"))

# =============================================================================
# Portfolio Construction Constraints
# =============================================================================
# Maximum single sector weight (as decimal, e.g., 0.25 = 25%)
MAX_SECTOR_WEIGHT = float(os.getenv("MACRO_MAX_SECTOR_WEIGHT", "0.25"))

# Minimum single sector weight
MIN_SECTOR_WEIGHT = float(os.getenv("MACRO_MIN_SECTOR_WEIGHT", "0.05"))

# Tilt magnitude applied to OW/UW signals (as decimal)
TILT_MAGNITUDE = float(os.getenv("MACRO_TILT_MAGNITUDE", "0.05"))

# =============================================================================
# Risk Monitoring Parameters
# =============================================================================
# Number of regime changes in 6 months to flag "high regime uncertainty"
REGIME_CHANGE_THRESHOLD = int(os.getenv("MACRO_REGIME_CHANGE_THRESHOLD", "2"))

# Z-score change threshold to flag "rapid macro shift" (in 1 month)
RAPID_SHIFT_THRESHOLD = float(os.getenv("MACRO_RAPID_SHIFT_THRESHOLD", "1.0"))

# =============================================================================
# FRED API Configuration
# =============================================================================
# FRED API key (should be set in .env file, never hardcoded)
FRED_API_KEY = os.getenv("FRED_API_KEY", "")

# FRED series IDs for key indicators
# Format: (series_id, frequency, units)
FRED_SERIES = {
    # Growth indicators
    "gdp_growth": ("GDP", "q", "pc1"),           # Real GDP, quarterly, YoY % change
    "unemployment_rate": ("UNRATE", "m", "lin"), # Unemployment rate, monthly
    "industrial_production": ("INDPRO", "m", "pc1"), # Industrial production, monthly, YoY %
    "retail_sales": ("RSXFS", "m", "pc1"),      # Retail sales, monthly, YoY %

    # Inflation indicators
    "cpi_yoy": ("CPIAUCSL", "m", "pc1"),        # CPI, monthly, YoY %
    "core_cpi_yoy": ("CPILFESL", "m", "pc1"),   # Core CPI ex food/energy, monthly, YoY %
    "ppi_yoy": ("PPIACO", "m", "pc1"),          # PPI, monthly, YoY %

    # Liquidity indicators
    "policy_rate": ("FEDFUNDS", "m", "lin"),      # Fed funds effective rate, monthly
    "yield_10y": ("DGS10", "d", "lin"),           # 10Y Treasury yield, daily
    "yield_2y": ("DGS2", "d", "lin"),             # 2Y Treasury yield, daily
    "money_supply_yoy": ("M2SL", "m", "pc1"),     # M2 money supply, monthly, YoY %

    # Risk indicators
    "vix": ("VIXCLS", "d", "lin"),                # VIX volatility index, daily
    "hy_spreads": ("BAMLH0A0HYM2", "m", "lin"),  # HY credit spreads, monthly
    "dollar_index": ("DTWEXBGS", "d", "lin"),     # Trade-weighted dollar index, daily

    # ==========================================================================
    # RESEARCH-BACKED EXPANSION — 2026 upgrade
    # Sources: Estrella-Mishkin (1998), Biggs-Mayer-Pick (2010), Conference Board
    # LEI, Sahm (2019), Ilmanen (2011), Chicago Fed NFCI
    # ==========================================================================

    # -- Recession / Leading indicators --
    "yield_curve_3m10y": ("T10Y3M", "d", "lin"),      # Estrella-Mishkin preferred spread
    "initial_claims_4wk": ("IC4WSA", "w", "lin"),      # 4-week avg initial claims (LEI)
    "building_permits":   ("PERMIT", "m", "lin"),       # Building permits (LEI component 6)
    "avg_mfg_hours":      ("AWHMAN", "m", "lin"),       # Avg manufacturing hours (LEI component 1)
    "sahm_rule":          ("SAHMREALTIME", "m", "lin"), # Sahm Rule real-time indicator (Claudia Sahm)

    # -- Labour / growth depth --
    "nonfarm_payrolls":   ("PAYEMS", "m", "lin"),       # Total nonfarm payrolls (Sahm Rule denominator)
    "job_openings":       ("JTSJOL", "m", "lin"),       # JOLTS: job openings (labour tightness)
    "housing_starts":     ("HOUST", "m", "lin"),        # Housing starts (cycle sensitivity)
    "inv_sales_ratio":    ("ISRATIO", "m", "lin"),      # Inventory-to-sales (demand slack signal)

    # -- Inflation precision (Fed's preferred gauges) --
    "core_pce_yoy":       ("PCEPILFE", "m", "pc1"),     # Core PCE YoY % — Fed's actual 2% target
    "inflation_breakeven_10y": ("T10YIE", "d", "lin"),  # 10Y TIPS breakeven (market inflation expectations)
    "real_yield_10y":     ("DFII10", "d", "lin"),       # 10Y real yield (Ilmanen: key risk premium driver)

    # -- Credit impulse (Biggs, Mayer & Pick 2010) --
    "commercial_loans":   ("BUSLOANS", "m", "lin"),     # C&I loans: flow proxy for credit impulse
    "consumer_credit":    ("TOTALSL", "m", "lin"),      # Total consumer credit outstanding
    "bbb_spread":         ("BAMLC0A4CBBB", "m", "lin"), # BBB spread (IG stress, wider than AAA)
    "bank_reserves":      ("WRESBAL", "w", "lin"),      # Bank reserves at Fed (liquidity backstop)

    # -- Sentiment / survey --
    "consumer_sentiment": ("UMCSENT", "m", "lin"),      # U-Mich consumer sentiment (LEI component 10)
}

# Series for recession model
FRED_RECESSION_SERIES = {
    "yield_curve":        ("T10Y2Y", "d", "lin"),       # 10Y-2Y spread (existing)
    "yield_curve_3m10y":  ("T10Y3M", "d", "lin"),       # 3M-10Y spread (Estrella-Mishkin preferred)
    "credit_spreads_aaa": ("BAMLC0A0CM", "m", "lin"),   # AAA credit spreads
    "unemployment_rate":  ("UNRATE", "m", "lin"),        # UNRATE for Sahm Rule
}

# NBER recession indicator (for model training/evaluation AND auto-calibration)
NBER_RECESSION_SERIES = "USREC"

# Include USREC directly in the main pipeline so it's available for auto-calibration
FRED_SERIES["nber_recession"] = ("USREC", "m", "lin")   # NBER recession binary 0/1

# =============================================================================
# Alpha Vantage API Configuration (free tier: 25 calls/day)
# =============================================================================
ALPHA_VANTAGE_KEY = os.getenv("ALPHA_VANTAGE_KEY", "")

# =============================================================================
# BEA API Configuration (free, register at apps.bea.gov/API/signup)
# =============================================================================
BEA_API_KEY = os.getenv("BEA_API_KEY", "")

# =============================================================================
# BLS API Configuration (free, optional key for higher rate limits)
# =============================================================================
BLS_API_KEY = os.getenv("BLS_API_KEY", "")

# =============================================================================
# OECD API Configuration
# No API key required — uses public SDMX endpoint
# Documentation: https://data-explorer.oecd.org/
# =============================================================================
OECD_BASE_URL = "https://sdmx.oecd.org/public/rest/data"
OECD_SERIES = {
    # Key OECD Main Economic Indicators
    # Format: (dataset, filter_expression, local_name)
    "oecd_us_cli":        ("MEI_CLI", "USA.LOLITOAA.A", "OECD US Composite Leading Indicator"),
    "oecd_eu_cli":        ("MEI_CLI", "EA19.LOLITOAA.A", "OECD Euro Area CLI"),
    "oecd_china_cli":     ("MEI_CLI", "CHN.LOLITOAA.A", "OECD China CLI"),
    "oecd_g7_cli":        ("MEI_CLI", "G-7.LOLITOAA.A", "OECD G7 CLI"),
    "oecd_us_cpi":        ("MEI_PRICES", "USA.CPALTT01.GY.M", "OECD US CPI YoY"),
    "oecd_eu_cpi":        ("MEI_PRICES", "EA19.CPALTT01.GY.M", "OECD Euro Area CPI YoY"),
    "oecd_us_unemployment":("MEI_LABOUR", "USA.LRHUTTTT.ST.M", "OECD US Unemployment Rate"),
}

# =============================================================================
# ECB Statistical Data Warehouse (free, no key, SDMX REST API)
# Documentation: https://data.ecb.europa.eu/
# =============================================================================
ECB_BASE_URL = "https://data-api.ecb.europa.eu/service/data"
ECB_SERIES = {
    # Key ECB indicators
    "ecb_deposit_rate":      ("FM/B.U2.EUR.RT.MM.EURIBOR1MD_.HSTA", "ECB Deposit Rate"),
    "ecb_main_refi_rate":    ("FM/B.U2.EUR.RT.MM.EURIBOR3MD_.HSTA", "ECB Main Refinancing Rate"),
    "ecb_hicp":              ("ICP/M.U2.N.000000.4.ANR", "Euro Area HICP Inflation YoY"),
    "ecb_core_hicp":         ("ICP/M.U2.N.XEF000.4.ANR", "Euro Area Core HICP YoY"),
    "ecb_eu_10y_yield":      ("YC/B.U2.EUR.4F.G_N_A.SV_C_YM.SR_10Y", "Euro Area 10Y Government Yield"),
    "ecb_m3_growth":         ("BSI/M.U2.Y.V.M30.X.I.U2.2300.Z01.E", "Euro Area M3 Money Supply YoY"),
}

# =============================================================================
# US Treasury API (free, public)
# Yield curve data direct from US Treasury
# Documentation: https://home.treasury.gov/resource-center/data-chart-center/interest-rates
# =============================================================================
TREASURY_BASE_URL = "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml"
TREASURY_SERIES = {
    "treasury_1m":  "1 Mo",
    "treasury_3m":  "3 Mo",
    "treasury_6m":  "6 Mo",
    "treasury_1y":  "1 Yr",
    "treasury_2y":  "2 Yr",
    "treasury_5y":  "5 Yr",
    "treasury_10y": "10 Yr",
    "treasury_30y": "30 Yr",
}

# =============================================================================
# Derived Paths
# =============================================================================
def ensure_directories():
    """Create necessary data directories if they don't exist."""
    directories = [
        PROJECT_ROOT / "data" / "raw",
        PROJECT_ROOT / "data" / "processed",
        PROJECT_ROOT / "data" / "processed" / "backtest_results",
        FRED_CACHE_DIR,
    ]
    for d in directories:
        d.mkdir(parents=True, exist_ok=True)

# Run on import to ensure directories exist
ensure_directories()
