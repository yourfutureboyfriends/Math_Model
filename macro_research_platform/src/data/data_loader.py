"""
data_loader.py — Load and validate the macro data CSV.

Financial context:
  Every indicator has a direction convention: does a HIGHER value mean the
  economy is getting BETTER or WORSE for that group?

  Examples:
    - Higher PMI = more business activity = GOOD for growth  → higher_is_positive: True
    - Higher unemployment = worse labour market = BAD for growth → higher_is_positive: False
    - Higher CPI = more inflation pressure → higher_is_positive: True  (for inflation group)
    - Higher credit spreads = tighter financial conditions = BAD for liquidity → False
    - Higher VIX = more fear = BAD for market sentiment → higher_is_positive: False

  This config is central to the model: it tells the scoring engine how to
  interpret each indicator's z-score when building group scores.
"""

import logging
import pandas as pd
from pathlib import Path

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Indicator configuration
# ---------------------------------------------------------------------------
# Each key maps to a column in sample_macro_data.csv.
# 'group'              → which score group this feeds into
# 'higher_is_positive' → True if a higher value signals improvement in that group
# 'description'        → plain-English explanation (used in educational output)

INDICATOR_CONFIG: dict[str, dict] = {
    # ---- Growth indicators ----
    "pmi": {
        "group": "growth",
        "higher_is_positive": True,
        "description": "Manufacturing PMI — composite of new orders, output, employment. "
                       "Above 50 = expansion, below 50 = contraction.",
    },
    "gdp_growth": {
        "group": "growth",
        "higher_is_positive": True,
        "description": "GDP growth (YoY %) — broadest measure of economic output.",
    },
    "industrial_production": {
        "group": "growth",
        "higher_is_positive": True,
        "description": "Industrial production (MoM %) — factory & mining output.",
    },
    "retail_sales": {
        "group": "growth",
        "higher_is_positive": True,
        "description": "Retail sales (MoM %) — proxy for consumer spending (~70% of GDP).",
    },
    "unemployment_rate": {
        "group": "growth",
        "higher_is_positive": False,   # higher unemployment = worse growth
        "description": "Unemployment rate (%) — inverted: lower is better for growth.",
    },
    # ---- FRED Live Data - Growth ----
    "us_industrial_production": {
        "group": "growth",
        "higher_is_positive": True,
        "description": "US Industrial Production (from FRED INDPRO).",
    },
    "us_retail_sales": {
        "group": "growth",
        "higher_is_positive": True,
        "description": "US Retail Sales (from FRED RSAFS).",
    },
    "us_unemployment_rate": {
        "group": "growth",
        "higher_is_positive": False,   # higher unemployment = worse growth
        "description": "US Unemployment Rate (from FRED UNRATE).",
    },
    # ---- Inflation indicators ----
    "cpi_yoy": {
        "group": "inflation",
        "higher_is_positive": True,
        "description": "CPI inflation (YoY %) — primary headline inflation gauge. Fed target: 2%.",
    },
    "core_cpi_yoy": {
        "group": "inflation",
        "higher_is_positive": True,
        "description": "Core CPI ex-food/energy (YoY %) — preferred Fed focus indicator.",
    },
    "ppi_yoy": {
        "group": "inflation",
        "higher_is_positive": True,
        "description": "Producer Price Index (YoY %) — upstream pricing; leads CPI by 3-6 months.",
    },
    "wage_growth_yoy": {
        "group": "inflation",
        "higher_is_positive": True,
        "description": "Wage growth (YoY %) — key driver of services inflation.",
    },
    "oil_price": {
        "group": "inflation",
        "higher_is_positive": True,
        "description": "Oil price (USD/bbl) — drives energy/transport costs globally.",
    },
    # ---- FRED Live Data - Inflation ----
    "us_cpi": {
        "group": "inflation",
        "higher_is_positive": True,
        "description": "US CPI (from FRED CPIAUCSL).",
    },
    "us_core_cpi": {
        "group": "inflation",
        "higher_is_positive": True,
        "description": "US Core CPI (from FRED CPILFESL).",
    },
    "us_ppi": {
        "group": "inflation",
        "higher_is_positive": True,
        "description": "US PPI (from FRED PPIACO).",
    },
    # ---- Liquidity indicators ----
    # Higher score = MORE accommodative (loose) financial conditions
    "policy_rate": {
        "group": "liquidity",
        "higher_is_positive": False,   # higher rates = tighter conditions
        "description": "Central bank policy rate (%) — price of money; higher = tighter.",
    },
    "yield_10y": {
        "group": "liquidity",
        "higher_is_positive": False,   # higher long yields = tighter financial conditions
        "description": "10Y government yield (%) — benchmark discount rate for equities.",
    },
    "yield_2y": {
        "group": "liquidity",
        "higher_is_positive": False,
        "description": "2Y government yield (%) — tracks expected policy over next 2 years.",
    },
    "yield_curve": {
        "group": "liquidity",
        "higher_is_positive": True,    # steeper curve = healthier financial system
        "description": "Yield curve slope (10Y-2Y %) — positive = normal, negative = inverted (recession signal).",
    },
    "credit_spreads": {
        "group": "liquidity",
        "higher_is_positive": False,   # wider spreads = tighter conditions for borrowers
        "description": "IG credit spreads (bps) — extra yield over govts; wider = more financial stress.",
    },
    "money_supply_yoy": {
        "group": "liquidity",
        "higher_is_positive": True,    # more money = more liquidity
        "description": "M2 money supply growth (YoY %) — measures liquidity in the system.",
    },
    # ---- FRED Live Data - Liquidity ----
    "us_fed_funds": {
        "group": "liquidity",
        "higher_is_positive": False,   # higher rates = tighter
        "description": "Fed Funds Rate (from FRED FEDFUNDS).",
    },
    "us_10y_yield": {
        "group": "liquidity",
        "higher_is_positive": False,   # higher yields = tighter
        "description": "US 10Y Treasury Yield (from FRED DGS10).",
    },
    "us_2y_yield": {
        "group": "liquidity",
        "higher_is_positive": False,
        "description": "US 2Y Treasury Yield (from FRED DGS2).",
    },
    "baa_credit_spread": {
        "group": "liquidity",
        "higher_is_positive": False,   # wider spreads = tighter
        "description": "BAA Credit Spread (from FRED BAA10Y).",
    },
    "us_3m_yield": {
        "group": "liquidity",
        "higher_is_positive": False,
        "description": "US 3M Treasury Yield (from FRED DGS3MO).",
    },
    # ---- Market risk indicators ----
    # Higher score = MORE risk in the market (not a 'good' direction — used differently)
    "vix": {
        "group": "risk",
        "higher_is_positive": False,   # higher VIX = more fear = bad for risk assets
        "description": "VIX volatility index — 'fear gauge'. Above 30 signals stress.",
    },
    "equity_momentum_12m": {
        "group": "risk",
        "higher_is_positive": True,    # positive momentum = risk-on environment
        "description": "Trailing 12-month equity return (%) — momentum signal; positive = risk-on.",
    },
    "dollar_index": {
        "group": "risk",
        "higher_is_positive": False,   # stronger USD = tighter global liquidity
        "description": "DXY dollar index — strong USD tightens global financial conditions.",
    },
    "hy_spreads": {
        "group": "risk",
        "higher_is_positive": False,   # wide HY spreads = credit stress
        "description": "High-yield credit spreads (bps) — most sensitive leading risk indicator.",
    },
    # ---- FRED Live Data - Risk ----
    "sp500": {
        "group": "risk",
        "higher_is_positive": True,    # higher equity = risk-on
        "description": "S&P 500 (from FRED SP500).",
    },
    "high_yield_spread": {
        "group": "risk",
        "higher_is_positive": False,   # wide spreads = stress
        "description": "High Yield Spreads (from FRED BAMLH0A0HYM2).",
    },
    "ted_spread": {
        "group": "risk",
        "higher_is_positive": False,   # higher TED = stress
        "description": "TED Spread (from FRED TEDRATE).",
    },

    # ---- FRED Live Data - New Quantitative Modules (2026) ----
    # GDP Nowcast inputs
    "us_payrolls": {
        "group": "growth",
        "higher_is_positive": True,
        "description": "Nonfarm Payrolls (from FRED PAYEMS) — GDP Nowcast input. Mariano & Murasawa (2010).",
    },
    "us_retail_sales_ex": {
        "group": "growth",
        "higher_is_positive": True,
        "description": "Retail Sales ex-Food Services (from FRED RSXFS) — GDP Nowcast input.",
    },
    "us_housing_starts": {
        "group": "growth",
        "higher_is_positive": True,
        "description": "Housing Starts (from FRED HOUST) — GDP Nowcast input.",
    },
    "us_initial_claims": {
        "group": "growth",
        "higher_is_positive": False,
        "description": "Initial Jobless Claims (from FRED ICSA) — GDP Nowcast input, weekly.",
    },

    # Liquidity Index inputs
    "us_m2": {
        "group": "liquidity",
        "higher_is_positive": True,
        "description": "M2 Money Supply (from FRED M2SL) — Liquidity Index. Ilmanen (2011).",
    },
    "us_fed_balance_sheet": {
        "group": "liquidity",
        "higher_is_positive": True,
        "description": "Fed Balance Sheet (from FRED WALCL) — Liquidity Index component.",
    },
    "us_sofr": {
        "group": "liquidity",
        "higher_is_positive": False,
        "description": "SOFR Secured Overnight Financing Rate (from FRED SOFR).",
    },

    # Valuation Filter inputs
    "us_10y_tips_yield": {
        "group": "liquidity",
        "higher_is_positive": False,
        "description": "10Y TIPS Real Yield (from FRED DFII10) — Valuation Filter. Campbell et al. (2014).",
    },
    "us_10y_breakeven": {
        "group": "inflation",
        "higher_is_positive": True,
        "description": "10Y Breakeven Inflation (from FRED T10YIE) — market inflation expectations.",
    },
    "ig_credit_spread": {
        "group": "risk",
        "higher_is_positive": False,
        "description": "IG Credit Spread (from FRED BAMLC0A0CM) — Valuation Filter. Gilchrist & Zakrajsek (2012).",
    },

    # Sentiment inputs
    "us_consumer_sentiment": {
        "group": "growth",
        "higher_is_positive": True,
        "description": "University of Michigan Consumer Sentiment (from FRED UMCSENT).",
    },
    "vix_3m": {
        "group": "risk",
        "higher_is_positive": False,
        "description": "VIX 3-Month (from FRED VIX3M) — Sentiment/Term Structure.",
    },
    "us_real_gdp": {
        "group": "growth",
        "higher_is_positive": True,
        "description": "Real GDP (from FRED GDPC1) — for Nowcast validation.",
    },

    # ==========================================================================
    # RESEARCH EXPANSION — 2026 upgrade
    # Estrella-Mishkin (1998), Biggs-Mayer-Pick (2010), Conference Board LEI,
    # Sahm (2019), Ilmanen (2011), Qian (2005)
    # ==========================================================================

    # ---- Leading indicators (Conference Board LEI methodology) ----
    "yield_curve_3m10y": {
        "group": "liquidity",
        "higher_is_positive": True,    # steeper = healthier bank funding
        "description": "3M-10Y yield curve slope — Estrella & Mishkin (1998) preferred recession predictor. "
                       "More predictive than 2Y-10Y for 12-month recession horizon.",
    },
    "initial_claims_4wk": {
        "group": "growth",
        "higher_is_positive": False,   # more claims = labour market stress
        "description": "4-week avg initial jobless claims — Conference Board LEI component 2. "
                       "Leading indicator: spikes before recessions.",
    },
    "building_permits": {
        "group": "growth",
        "higher_is_positive": True,
        "description": "Housing building permits — Conference Board LEI component 6. "
                       "Leads housing activity and construction employment by 6-12 months.",
    },
    "avg_mfg_hours": {
        "group": "growth",
        "higher_is_positive": True,
        "description": "Average weekly manufacturing hours — Conference Board LEI component 1. "
                       "Firms cut hours before cutting jobs; a very early recession signal.",
    },

    # ---- Labour depth ----
    "nonfarm_payrolls": {
        "group": "growth",
        "higher_is_positive": True,
        "description": "Total nonfarm payrolls (monthly change, 000s) — used in Sahm Rule denominator. "
                       "The broadest US employment measure.",
    },
    "job_openings": {
        "group": "growth",
        "higher_is_positive": True,
        "description": "JOLTS job openings — measures labour demand. High openings = tight labour market. "
                       "Beveridge Curve analysis: openings vs unemployment.",
    },
    "housing_starts": {
        "group": "growth",
        "higher_is_positive": True,
        "description": "Housing starts — highly cycle-sensitive. One of the first sectors to turn. "
                       "Multiplier effects: construction, materials, appliances, retail.",
    },
    "inv_sales_ratio": {
        "group": "growth",
        "higher_is_positive": False,   # high ratio = demand slack, destocking ahead
        "description": "Business inventory-to-sales ratio — rising ratio signals demand weakness; "
                       "firms will cut production to run down inventories.",
    },

    # ---- Inflation precision ----
    "core_pce_yoy": {
        "group": "inflation",
        "higher_is_positive": True,
        "description": "Core PCE ex food/energy (YoY %) — Fed's ACTUAL 2% inflation target. "
                       "Preferred over CPI: better weights, broader, fewer housing distortions.",
    },
    "inflation_breakeven_10y": {
        "group": "inflation",
        "higher_is_positive": True,
        "description": "10Y TIPS breakeven inflation — market-implied inflation expectations. "
                       "Forward-looking; incorporates bond market views on Fed credibility.",
    },
    "real_yield_10y": {
        "group": "liquidity",
        "higher_is_positive": False,   # higher real yield = tighter financial conditions
        "description": "10Y real yield (TIPS) — Ilmanen (2011): KEY driver of equity valuations. "
                       "Rising real yields compress P/E multiples; central to growth/value rotation.",
    },

    # ---- Credit impulse (Biggs, Mayer & Pick 2010) ----
    "commercial_loans": {
        "group": "growth",
        "higher_is_positive": True,
        "description": "Commercial & industrial loans outstanding — proxy for credit impulse. "
                       "Biggs, Mayer & Pick (2010): accelerating new credit → demand recovery.",
    },
    "consumer_credit": {
        "group": "growth",
        "higher_is_positive": True,
        "description": "Total consumer credit outstanding — measures household leveraging. "
                       "Strong consumer credit growth supports consumption; deceleration is a warning.",
    },
    "bbb_spread": {
        "group": "risk",
        "higher_is_positive": False,   # wider = financial stress
        "description": "BBB corporate spread — the 'fallen angel' threshold. "
                       "BBB downgrades to HY cause forced selling; watches cliff edge of credit cycle.",
    },
    "bank_reserves": {
        "group": "liquidity",
        "higher_is_positive": True,
        "description": "Bank reserves at Fed — measure of system-wide liquidity. "
                       "When QT drains reserves, financial conditions tighten; floor below money markets.",
    },

    # ---- Sentiment ----
    "consumer_sentiment": {
        "group": "growth",
        "higher_is_positive": True,
        "description": "University of Michigan consumer sentiment — Conference Board LEI component 10. "
                       "Consumer confidence drives spending intentions; leads retail sales.",
    },
}

GROUPS = ["growth", "inflation", "liquidity", "risk"]

INDICATORS_BY_GROUP: dict[str, list[str]] = {
    group: [k for k, v in INDICATOR_CONFIG.items() if v["group"] == group]
    for group in GROUPS
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_macro_data(filepath: str | Path) -> pd.DataFrame:
    """Load and lightly validate the macro CSV.

    Returns a DataFrame indexed by date, sorted chronologically.
    Raises ValueError if required columns are missing.
    """
    df = pd.read_csv(filepath, parse_dates=["date"])
    df = df.sort_values("date").reset_index(drop=True)
    df = df.set_index("date")

    _validate(df)
    return df


def get_indicator_config() -> dict[str, dict]:
    """Return the full indicator configuration dictionary."""
    return INDICATOR_CONFIG


def get_indicators_by_group() -> dict[str, list[str]]:
    """Return indicator names grouped by category."""
    return INDICATORS_BY_GROUP


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _validate(df: pd.DataFrame) -> None:
    """
    Check that indicator columns exist in the DataFrame.

    UPDATED: Changed from hard error to warning for missing columns so the
    dashboard remains functional when new FRED series haven't been downloaded
    yet (e.g. after adding series to settings.py but before running
    `pipeline.py --mode refresh-live-data`).  Models that use a column will
    gracefully skip it if absent; only a full absence of all columns is fatal.
    """
    if df.empty:
        raise ValueError("Loaded DataFrame is empty — check the CSV path.")

    # Separate CORE series (in sample data) from EXPANSION series added in 2026
    CORE_INDICATORS = {
        "pmi", "gdp_growth", "industrial_production", "retail_sales",
        "unemployment_rate", "cpi_yoy", "core_cpi_yoy", "ppi_yoy",
        "policy_rate", "yield_10y", "yield_2y", "yield_curve",
        "credit_spreads", "money_supply_yoy", "vix", "hy_spreads",
    }
    missing_core = [col for col in CORE_INDICATORS if col not in df.columns]
    missing_expansion = [
        col for col in INDICATOR_CONFIG
        if col not in CORE_INDICATORS and col not in df.columns
    ]

    if missing_core:
        # Core series missing: may be live mode with different column names — warn only
        logger.warning(
            "Some core indicator columns not found: %s. "
            "Models will use available alternatives.",
            missing_core,
        )

    if missing_expansion:
        logger.info(
            "%d expansion series not yet in data (run `pipeline.py --mode refresh-live-data` "
            "to fetch): %s",
            len(missing_expansion),
            missing_expansion[:5],   # log first 5 to keep log clean
        )
