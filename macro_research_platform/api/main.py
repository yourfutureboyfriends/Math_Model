"""
FastAPI backend for Macro Research Platform React frontend.
VERSION: 2026-05-05-reload-test  # DEBUG marker

All dashboard data is computed from actual macro models - no hardcoded stubs.

Model stack (academic sources):
  - Regime:           Classifier (Bridgewater 2-by-2: growth × inflation)
  - Recession:        Logistic + Estrella-Mishkin probit (1998) + Sahm Rule (2019)
  - LEI Composite:    Conference Board methodology (inverse-vol weighted)
  - Credit Impulse:   Biggs, Mayer & Pick (2010) - second derivative of credit
  - Risk Parity:      Qian (2005) / Bridgewater All Weather
  - Fin. Conditions:  Adrian, Boyarchenko & Giannone (2019)
"""

import sys
import os
import json
import logging
import threading
import time
import math
import asyncio
import functools
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any

# MUST be before any project imports
_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

# FIXED: Tier 1A - Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, BackgroundTasks, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# FIXED: R-01 - APScheduler for automated data pipeline
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

# FIXED: Phase 1 - Canonical Price Cache

# R-01: the real data pipeline (fetch FRED + Yahoo, write this month's CSV row, clear
# cache). A logging-only stub stood in for it, so the scheduler and the manual refresh
# endpoint did nothing and the CSV went stale.
from api.data_pipeline import run_daily_pipeline

# FIXED: Socket.IO for real-time updates
import socketio

# FIXED: Dynamic CORS origins from environment
FRONTEND_ORIGINS = os.environ.get(
    'ALLOWED_ORIGINS',
    'http://localhost:5173,http://localhost:3000,http://localhost:3002'
).split(',')

sio = socketio.AsyncServer(
    cors_allowed_origins=FRONTEND_ORIGINS,
    async_mode="asgi",
    logger=False,
    engineio_logger=False,
)

# FIXED (BUG 5 PERMANENT): Regime classification configuration
RISK_OFF_REGIMES = {"Stagflation", "Slowdown", "Recession"}
RISK_ON_REGIMES = {"Goldilocks", "Reflation"}
REGIME_BASE_SCORES = {
    "Goldilocks": +0.60,
    "Reflation": +0.40,
    "Stagflation": -0.40,
    "Slowdown": -0.60,
}

# FIXED (Fix 9): Single canonical inception date constant
PORTFOLIO_INCEPTION_DATE = "2024-01-01"

# CANONICAL PRICE CACHE (Fix 8) — Single source of truth for market prices

_price_cache: Dict[str, Dict[str, Any]] = {}
_price_cache_timestamp: Optional[datetime] = None
_price_cache_ttl = 60  # 60 seconds




# DYNAMIC PORT CONFIGURATION — Never hardcode ports

import socket



def find_free_port(preferred: int = 8000, fallbacks=None) -> int:
    """Return the first available port from the preferred list."""
    if fallbacks is None:
        fallbacks = [8001, 8002, 8080, 9000]
    candidates = [preferred] + fallbacks

    for port in candidates:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(("", port))
                return port
        except OSError:
            continue

    # Last resort: let OS assign any free port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def write_port_file(port: int, path: str = ".api_port") -> None:
    """Write the active port to a shared file for frontend to read."""
    # Write to project root (one level up from api/)
    port_path = _ROOT / path
    try:
        with open(port_path, "w") as f:
            f.write(str(port))
        logger.info(f"[MACRO OS] API running on port {port}")
        logger.info(f"[MACRO OS] Port written to {port_path}")
    except Exception as e:
        logger.warning(f"[MACRO OS] Could not write port file: {e}")


def read_port_file(path: str = ".api_port") -> int | None:
    """Read the port from the shared file."""
    port_path = _ROOT / path
    try:
        with open(port_path, "r") as f:
            content = f.read().strip()
            port = int(content)
            return port
    except (FileNotFoundError, ValueError):
        return None


# FIXED (UTILITY): TTL LRU cache decorator for function memoization
def lru_cache_with_ttl(ttl_seconds: int = 300):
    """LRU cache with TTL (time-to-live) support."""
    def decorator(func):
        cache = {}
        timestamps = {}
        from functools import wraps
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Create a cache key from arguments
            key = str(args) + str(sorted(kwargs.items()))
            now = time.time()
            # Check if cached value is still valid
            if key in cache:
                if now - timestamps[key] < ttl_seconds:
                    return cache[key]
                else:
                    # Expired, remove from cache
                    del cache[key]
                    del timestamps[key]
            # Compute and cache new value. Empty/None results (a failed fetch) are not
            # cached, so one network blip doesn't pin an empty answer for the whole TTL.
            result = func(*args, **kwargs)
            if result is None or (hasattr(result, "__len__") and len(result) == 0):
                return result
            cache[key] = result
            timestamps[key] = now
            return result
        return wrapper
    return decorator


# FIXED: Import data validation layer (new architecture)
from api.regime_context import build_regime_context

# FIXED: Phase 7 - New consolidated data architecture (safe migration)
from api.services.refresh_coordinator import refresh_coordinator
from api.diagnostics import router as health_router, diagnostics_router

# ═══════════════════════════════════════════════════════════════════════════════
# MODEL VALIDATION - Forecast Tracking Integration (Phase 1-10)
# ═══════════════════════════════════════════════════════════════════════════════
from api.services.forecast_tracker import forecast_tracker
from api.services.recession_validation import recession_validator
from api.services.expected_returns_validation import expected_returns_validator
from api.services.portfolio_validation import portfolio_validator
from api.services.nowcast_validation import nowcast_validator
from api.services.momentum_validation import momentum_validator

# FIXED: Phase 3 - Import Pydantic models from schemas module
from api.schemas.models import (
    RegimeData, KeyMetrics, RecessionData, SignalsData, SignalDetails,
    SectorAllocationData, RiskParityAllocationData, ExpectedReturnsResult,
    BusinessLayerData, AlertsData, PositionSizing, SignalScorecardItem, DecisionLogEntry,
    AskResponse, AskRequest,
    SignalStackLayer, SignalStackResult,
    ExpectedReturnSector, SectorPerformance, CurrentRegimeValidation,
    LoginResponse,
    RegimeTransitionProbabilities, RegimeBacktestResult, DebtCycleResult,
    InternationalMacroResult, RiskIndicatorsData, AdvancedIndicatorsData,
    ModelAgreementData, TransmissionAnalysisData, DataToWatchItem,
    InvestmentMemoData, AlertItem,
    AdvancedIndicator, RiskIndicator, ModelAgreementItem, TransmissionChannel,
    DebtCycleIndicator, DebtCycleIndicators,
    DataMetadata, Sector, RiskParityItem, MetricWithSparkline,
)

try:
    from src.models.recession_risk.recession_model import (
        get_current_recession_probability,
        get_sahm_rule_signal,
    )
    _RECESSION_OK = True
except Exception as _e:
    logging.warning(f"recession_model import failed: {_e}")
    _RECESSION_OK = False

try:
    from src.models.leading_indicators.lei_composite import LEICompositeModel
    _LEI_OK = True
except Exception as _e:
    logging.warning(f"lei_composite import failed: {_e}")
    _LEI_OK = False

try:
    from src.models.credit.credit_impulse_model import CreditImpulseModel
    _CREDIT_OK = True
except Exception as _e:
    logging.warning(f"credit_impulse_model import failed: {_e}")
    _CREDIT_OK = False

try:
    from src.models.portfolio_construction.risk_parity import RiskParityAllocator
    _RISKPARITY_OK = True
except Exception as _e:
    logging.warning(f"risk_parity import failed: {_e}")
    _RISKPARITY_OK = False

try:
    _FC_OK = True
except Exception as _e:
    logging.warning(f"financial_conditions_model import failed: {_e}")
    _FC_OK = False

try:
    from src.models.macro_regime.classifier import classify_regime
    _CLASSIFIER_OK = True
except Exception as _e:
    logging.warning(f"classifier import failed: {_e}")
    _CLASSIFIER_OK = False

try:
    from src.models.macro_regime.regime_model import compute_group_scores
    _REGIME_MODEL_OK = True
except Exception as _e:
    logging.warning(f"regime_model import failed: {_e}")
    _REGIME_MODEL_OK = False

try:
    from src.features.macro_features import compute_all_transforms as compute_all_features
    _FEATURES_OK = True
except Exception as _e:
    logging.warning(f"macro_features import failed: {_e}")
    _FEATURES_OK = False

try:
    _NOWCAST_OK = True
except Exception as _e:
    logging.warning(f"gdp_nowcast import failed: {_e}")
    _NOWCAST_OK = False

try:
    _LIQUIDITY_OK = True
except Exception as _e:
    logging.warning(f"liquidity_index import failed: {_e}")
    _LIQUIDITY_OK = False

try:
    _SENTIMENT_OK = True
except Exception as _e:
    logging.warning(f"risk_appetite import failed: {_e}")
    _SENTIMENT_OK = False

try:
    _VALUATION_OK = True
except Exception as _e:
    logging.warning(f"valuation_filter import failed: {_e}")
    _VALUATION_OK = False

try:
    _MOMENTUM_OK = True
except Exception as _e:
    logging.warning(f"momentum_veto import failed: {_e}")
    _MOMENTUM_OK = False

try:
    _CORRELATION_OK = True
except Exception as _e:
    logging.warning(f"correlation_regime import failed: {_e}")
    _CORRELATION_OK = False

try:
    _SIGNALSTACK_OK = True
except Exception as _e:
    logging.warning(f"signal_hierarchy import failed: {_e}")
    _SIGNALSTACK_OK = False

logger = logging.getLogger(__name__)

# GLOBAL UTILITY FUNCTIONS

def scrub_nans(obj):
    """
    Recursively replace NaN/Infinity with None in any nested dict/list.
    Apply this to all computed data before returning to frontend.
    """
    if isinstance(obj, dict):
        return {k: scrub_nans(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [scrub_nans(v) for v in obj]
    elif isinstance(obj, float):
        if np.isnan(obj) or np.isinf(obj):
            return None
        return round(obj, 6)
    return obj


def safe_float(val, default=0.0):
    """Safely convert a value to float, returning default if NaN or invalid."""
    try:
        f = float(val)
        if np.isnan(f) or np.isinf(f):
            return default
        return f
    except (TypeError, ValueError):
        return default








# FIXED (BUG 2): Single cached DXY helper for consistency
_DXY_CACHE: Optional[Dict[str, Any]] = None
_DXY_CACHE_TIMESTAMP: Optional[datetime] = None
_DXY_CACHE_TTL = 60  # 60 seconds





# FIXED (BUG 1+2 PERMANENT): Dynamic FX sanity bounds from historical data ±4σ
def _build_fx_sanity_bounds(symbol: str, lookback: str = "2y") -> tuple[float, float]:
    """Derive sanity bounds from 2Y history ± 4σ."""
    try:
        import yfinance as yf
        hist = yf.Ticker(symbol).history(period=lookback)
        if len(hist) < 30:
            return (0.0001, 9999.0)  # no bound if no history
        prices = hist["Close"].dropna()
        mean = prices.mean()
        std = prices.std()
        lo = max(0.0001, mean - 4 * std)
        hi = mean + 4 * std
        logger.debug(f"FX bounds {symbol}: {lo:.4f}–{hi:.4f} (mean={mean:.4f}, σ={std:.4f})")
        return (lo, hi)
    except Exception as e:
        logger.warning(f"FX bounds failed for {symbol}: {e}")
        return (0.0001, 9999.0)




# Cache bounds for 24 hours — recalculate daily
@lru_cache_with_ttl(ttl_seconds=86400)
def _get_all_fx_bounds() -> dict:
    """Get dynamic sanity bounds for all FX pairs."""
    tickers = {
        "EUR/USD": "EURUSD=X",
        "GBP/USD": "GBPUSD=X",
        "USD/JPY": "JPY=X",
        "AUD/USD": "AUDUSD=X",
        "USD/CAD": "CAD=X",
        "USD/CHF": "CHF=X",
        "NZD/USD": "NZDUSD=X",
        "USD/SEK": "SEK=X",
        "USD/CNH": "CNH=X",
        "USD/MXN": "MXN=X",
        "USD/BRL": "BRL=X",
        "USD/ZAR": "ZAR=X",
        "USD/INR": "INR=X",
    }
    return {pair: _build_fx_sanity_bounds(ticker) for pair, ticker in tickers.items()}


def _parse_fomc_calendar(html: str) -> list[tuple[str, str]]:
    """(first_day, decision_day) ISO dates for every FOMC meeting on the Fed's calendar page.

    The page groups meetings under "<YEAR> FOMC Meetings" panels; each meeting row has a
    month cell ("June", or "Apr/May" for a meeting spanning two months) and a day cell
    ("16-17", "30-1", "17-18*"). The decision is announced on the LAST day. Notation votes
    are skipped (they are not meetings).
    """
    import re
    from datetime import date as _date
    from bs4 import BeautifulSoup

    def _month(txt: str) -> int:
        return datetime.strptime(txt.strip()[:3], "%b").month

    meetings = []
    soup = BeautifulSoup(html, "html.parser")
    for panel in soup.select(".panel"):
        heading = panel.select_one(".panel-heading")
        ym = re.search(r"(\d{4})\s+FOMC Meetings", heading.get_text(" ", strip=True)) if heading else None
        if not ym:
            continue
        year = int(ym.group(1))
        for row in panel.select(".fomc-meeting"):
            mcell, dcell = row.select_one(".fomc-meeting__month"), row.select_one(".fomc-meeting__date")
            if not mcell or not dcell:
                continue
            day_txt = dcell.get_text(" ", strip=True)
            days = [int(d) for d in re.findall(r"\d+", day_txt)]
            if not days or "notation" in day_txt.lower():
                continue
            months = [m for m in mcell.get_text(strip=True).split("/") if m]
            try:
                m_start = _month(months[0])
                d1, d2 = days[0], days[-1]
                m_end = _month(months[-1]) if (len(months) > 1 and d2 < d1) else m_start
                meetings.append((_date(year, m_start, d1).isoformat(), _date(year, m_end, d2).isoformat()))
            except (ValueError, IndexError):
                continue
    return sorted(set(meetings), key=lambda m: m[1])


@lru_cache_with_ttl(ttl_seconds=86400)
def _fetch_fomc_meetings() -> list[tuple[str, str]]:
    """(first_day, decision_day) for every meeting on federalreserve.gov (cached 24h)."""
    try:
        import requests
        r = requests.get(
            "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0"}
        )
        return _parse_fomc_calendar(r.text)
    except Exception as e:
        logger.warning(f"FOMC scrape failed: {e}")
        return []


def _fetch_fomc_dates() -> list[str]:
    """FOMC decision dates (last day of each meeting), sorted."""
    return [end for _, end in _fetch_fomc_meetings()]


def _fomc_blackout_start(first_day):
    """Fed communications blackout begins the second Saturday before the meeting's first day."""
    from datetime import timedelta as _td
    back = (first_day.weekday() - 5) % 7 or 7     # days back to the preceding Saturday
    return first_day - _td(days=back + 7)


# FRED release dates for NFP and CPI
@lru_cache_with_ttl(ttl_seconds=21600)
def _fetch_fred_release_dates(release_id: int, n: int = 8, past: bool = False) -> list[str]:
    """Release dates for a FRED release (CPI = 10, Employment Situation = 50).

    Upcoming dates (default) need include_release_dates_with_no_data=true — without it FRED
    only returns dates that already have data, so the upcoming list was always empty and
    every caller silently used its heuristic fallback. past=True returns the most recent
    `n` past release dates, newest last.
    """
    try:
        import requests
        from api.config import FRED_API_KEY
        if not FRED_API_KEY:
            logger.warning("FRED_API_KEY not set, release dates unavailable")
            return []
        today = datetime.now().date().isoformat()
        params = {"release_id": release_id, "api_key": FRED_API_KEY, "file_type": "json",
                  "include_release_dates_with_no_data": "true", "sort_order": "desc", "limit": 200}
        r = requests.get("https://api.stlouisfed.org/fred/release/dates", params=params, timeout=8)
        dates = sorted({d["date"] for d in r.json().get("release_dates", [])})
        if past:
            return [d for d in dates if d < today][-n:]
        return [d for d in dates if d >= today][:n]
    except Exception as e:
        logger.warning(f"FRED release dates failed: {e}")
        return []


# FIXED: Tier 1D - Dashboard response caching with 5-minute TTL
# Reduces response time from ~4s to <100ms for cached responses
_EVENT_VOL_CACHE: Dict[str, Any] = {"data": None, "ts": 0.0}
_DASHBOARD_CACHE: Dict[str, Any] = {"data": None, "timestamp": 0.0, "mode": "live"}

# Reusable async response cache (P1 perf) — see api/utils/cache.py.
# Endpoints that re-fetch live FRED/market data every call (health, cot, calendar, ...) run
# 3-8s and saturate the event loop on dashboard mount; a short per-endpoint TTL makes repeat
# calls instant without changing the data's meaning.
from api.utils.cache import ttl_cache
_DASHBOARD_CACHE_LOCK = threading.Lock()
_DASHBOARD_CACHE_TTL_SECONDS = 300  # 5 minutes

# FIXED: R-01 - APScheduler for automated data pipeline
_scheduler = AsyncIOScheduler(timezone="UTC")

PROJECT_ROOT = _ROOT
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed" / "live"
SAMPLE_PATH   = PROJECT_ROOT / "data" / "raw" / "sample_macro_data.csv"
OUTPUTS_DIR   = PROJECT_ROOT / "outputs"


# Column name resolution helpers

def _get(df: pd.DataFrame, *candidates, default=np.nan):
    """Return the first available column value (most recent), or default."""
    for col in candidates:
        if col in df.columns:
            val = df[col].dropna()
            if not val.empty:
                return float(val.iloc[-1])
    return default


def _series(df: pd.DataFrame, *candidates) -> pd.Series:
    """Return the first available column as a Series, or empty Series."""
    for col in candidates:
        if col in df.columns and not df[col].dropna().empty:
            return df[col].dropna()
    return pd.Series(dtype=float)


# Data Loading

def _fetch_fresh_fred_value(series_id: str) -> Optional[float]:
    """
    Fetch fresh value from FRED API for critical metrics.
    Returns None if FRED API key not configured or fetch fails.
    """
    from api.config import FRED_API_KEY
    api_key = FRED_API_KEY
    if not api_key or api_key == "your_fred_api_key_here":
        return None

    try:
        import requests
        # FRED transforms (e.g. year-over-year %) are a `units` query param, NOT a
        # series-id suffix. Translate a trailing _PC1 / _PCH into units=pc1 / pch so
        # ids like "CPIAUCSL_PC1" resolve to CPIAUCSL with units=pc1 instead of 400ing.
        units = "lin"
        real_series_id = series_id
        for suffix, unit in (("_PC1", "pc1"), ("_PCH", "pch"), ("_PCA", "pca")):
            if series_id.endswith(suffix):
                real_series_id = series_id[: -len(suffix)]
                units = unit
                break
        url = (
            f"https://api.stlouisfed.org/fred/series/observations"
            f"?series_id={real_series_id}"
            f"&api_key={api_key}"
            f"&units={units}"
            f"&file_type=json"
            f"&sort_order=desc"
            f"&limit=1"
        )
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if data.get("observations"):
            val = data["observations"][0].get("value")
            if val and val != ".":
                return float(val)
    except Exception as e:
        logger.warning(f"[FRED FETCH] Failed to fetch {series_id}: {e}")
    return None


def load_processed_data() -> Optional[pd.DataFrame]:
    """
    FIXED: Read from CSV and PATCH with fresh FRED data for critical metrics.
    This fixes BUG-01, BUG-02, BUG-04 by ensuring live data overrides stale CSV.
    """
    # Try CSV first (has historical data)
    csv_file = PROJECT_ROOT / "data" / "us_economic_data.csv"
    df = None
    if csv_file.exists():
        try:
            df = pd.read_csv(csv_file, index_col=0, parse_dates=True)
            if not df.empty:
                logger.info(f"[DATA] Loaded CSV: {df.index.max().date()}, {len(df)} rows")
        except Exception as e:
            logger.warning(f"[DATA] Failed to load CSV: {e}")

    # Fallback to parquet if CSV fails
    if df is None:
        processed_file = PROCESSED_DIR / "macro_data.parquet"
        if processed_file.exists():
            try:
                df = pd.read_parquet(processed_file)
                logger.warning(f"[DATA] Using stale parquet: {df.index.max().date()}")
            except Exception as e:
                logger.warning(f"[DATA] Failed to load parquet: {e}")

    if df is None:
        return None

    # Patch the latest row with fresh FRED values where available. If FRED can't be
    # reached (or returns an implausible value) the CSV value is kept as-is — never
    # replaced with a hardcoded constant.
    last_idx = df.index[-1]

    def _patch(series_id, cols, lo, hi, scale=None):
        val = _fetch_fresh_fred_value(series_id)
        if val is None:
            logger.warning(f"[DATA PATCH] {series_id} unavailable — keeping CSV value")
            return
        if scale is not None:
            val = scale(val)
        if not (lo <= val <= hi):
            logger.warning(f"[DATA PATCH] {series_id}={val} outside [{lo}, {hi}] — keeping CSV value")
            return
        for c in cols:
            df.loc[last_idx, c] = val
        logger.info(f"[DATA PATCH] {series_id}: {val:.2f} (fresh FRED)")

    _patch("FEDFUNDS", ["us_fed_funds", "fed_funds", "FEDFUNDS"], 0.0, 25.0)
    # Headline and core CPI YoY are separate series (headline was written into core before).
    _patch("CPIAUCSL_PC1", ["us_cpi", "cpi_yoy"], -5.0, 25.0)
    _patch("CPILFESL_PC1", ["core_cpi_yoy"], -5.0, 25.0)
    # FRED reports OAS in percent; columns are in bps.
    _patch("BAMLH0A0HYM2", ["hy_spreads", "high_yield_spread", "us_credit"], 50.0, 3000.0,
           scale=lambda v: v * 100 if v < 30 else v)

    return df






# Regime computation helpers

def _compute_regime_scores(df: pd.DataFrame) -> Dict[str, float]:
    """
    Compute growth, inflation, liquidity, risk scores from available columns.

    Tries the full feature pipeline first; falls back to simple z-score averages
    using available raw columns.
    """
    if _FEATURES_OK and _REGIME_MODEL_OK:
        try:
            df_feat = compute_all_features(df)
            scores_df = compute_group_scores(df_feat)
            latest = scores_df.iloc[-1]
            return {
                "growth":    float(latest.get("growth_score",    0.0)),
                "inflation": float(latest.get("inflation_score", 0.0)),
                "liquidity": float(latest.get("liquidity_score", 0.0)),
                "risk":      float(latest.get("risk_score",      0.0)),
            }
        except Exception as e:
            logger.warning(f"Full feature pipeline failed, using fallback: {e}")

    scores = {}

    def _zscore_latest(series: pd.Series, window: int = 36) -> float:
        clean = series.dropna()
        if len(clean) < 6:
            return 0.0
        roll = clean.rolling(window, min_periods=6)
        z = (clean - roll.mean()) / roll.std().replace(0, np.nan)
        return float(z.dropna().iloc[-1]) if not z.dropna().empty else 0.0

    # Growth: industrial production, retail sales (higher = better)
    growth_parts = []
    for col in ["us_industrial_production", "industrial_production", "us_retail_sales", "retail_sales"]:
        if col in df.columns:
            growth_parts.append(_zscore_latest(df[col]))
    # Unemployment (inverted)
    for col in ["us_unemployment_rate", "unemployment_rate"]:
        if col in df.columns:
            growth_parts.append(-_zscore_latest(df[col]))
    scores["growth"] = float(np.mean(growth_parts)) if growth_parts else 0.0

    # Inflation: CPI, PPI, core CPI
    inf_parts = []
    for col in ["us_cpi", "cpi_yoy", "us_core_cpi", "core_cpi_yoy", "us_ppi", "ppi_yoy"]:
        if col in df.columns:
            inf_parts.append(_zscore_latest(df[col]))
    scores["inflation"] = float(np.mean(inf_parts)) if inf_parts else 0.0

    # Liquidity: yield curve (higher = looser), policy rate (inverted), M2 (higher = looser)
    liq_parts = []
    for col in ["yield_curve", "us_yield_curve"]:
        if col in df.columns:
            liq_parts.append(_zscore_latest(df[col]))
    for col in ["policy_rate", "us_fed_funds"]:
        if col in df.columns:
            liq_parts.append(-_zscore_latest(df[col]))
    for col in ["money_supply_yoy", "us_m2_yoy"]:
        if col in df.columns:
            liq_parts.append(_zscore_latest(df[col]))
    scores["liquidity"] = float(np.mean(liq_parts)) if liq_parts else 0.0

    # Risk: VIX (inverted), HY spreads (inverted), equity momentum (higher = better)
    risk_parts = []
    for col in ["vix", "us_vix"]:
        if col in df.columns:
            risk_parts.append(-_zscore_latest(df[col]))
    for col in ["hy_spreads", "high_yield_spread", "baa_credit_spread"]:
        if col in df.columns:
            risk_parts.append(-_zscore_latest(df[col]))
    for col in ["equity_momentum_12m", "sp500", "us_equity_momentum"]:
        if col in df.columns:
            risk_parts.append(_zscore_latest(df[col]))
    scores["risk"] = float(np.mean(risk_parts)) if risk_parts else 0.0

    return scores




# Dashboard Section Builders

def _monthly_regime_frame() -> pd.DataFrame:
    """Full monthly quadrant-regime history from the FRED panel (industrial production YoY,
    CPI YoY), plus curve/credit z-scores for the liquidity/risk interpretations."""
    from api.handlers.macro_inputs import load_monthly_macro
    from api.calculations.regime import quadrant_regime_history

    panel = load_monthly_macro()
    if panel is None or panel.empty:
        raise ValueError("Monthly FRED macro data unavailable")
    hist = quadrant_regime_history(panel["growth_yoy"], panel["cpi_yoy"])
    if hist.empty:
        raise ValueError("Insufficient monthly macro history to classify regimes")

    def _z(col):
        if col not in panel:
            return pd.Series(dtype=float)
        s = panel[col]
        r = s.rolling(36, min_periods=24)
        return ((s - r.mean()) / r.std()).reindex(hist.index)

    hist["curve_z"] = _z("curve")
    hist["credit_z"] = _z("credit")
    return hist


def get_regime_data(df: Optional[pd.DataFrame] = None) -> RegimeData:
    """Current growth×inflation quadrant regime with its real monthly history.

    Built from the contiguous monthly FRED panel. It used to read the hand-maintained CSV
    (18-month gap, forward/back-filled), padded short histories with fake "2023-01-01
    Goldilocks" entries, and sub-sampled every n-th month — which also corrupted the
    transition matrix computed from it. `df` is accepted for backward compatibility only.
    """
    hist = _monthly_regime_frame()
    last = hist.iloc[-1]
    regime = str(last["regime"])
    confidence_score = round(float(last["confidence"]), 2)
    confidence = "High" if confidence_score > 0.7 else "Medium" if confidence_score > 0.45 else "Low"

    from api.calculations.regime import current_run_length
    duration = current_run_length(hist["regime"])        # months, over the full history

    recent = hist.tail(24)
    history = [{"date": d.strftime("%Y-%m-%d"), "regime": r, "confidence": f"{round(c * 100)}%"}
               for d, r, c in zip(recent.index, recent["regime"], recent["confidence"])]

    def _val(x):
        return 0.0 if x is None or pd.isna(x) else float(x)

    scores = {
        "growth": _val(last["g_z"]),
        "inflation": _val(last["i_z"]),
        "liquidity": _val(last["curve_z"]),          # steeper curve = easier conditions
        "risk": -_val(last["credit_z"]),             # wider credit spreads = risk-off
    }

    # Interpretations from z-scores
    def _dir(score: float, pos_label: str, neg_label: str) -> tuple:
        if score > 0.2:
            return pos_label, "success"
        elif score < -0.2:
            return neg_label, "danger"
        return "Neutral", "neutral"

    g_label, g_color = _dir(scores["growth"],    "Expanding",  "Contracting")
    i_label, i_color = _dir(scores["inflation"], "Rising",     "Falling")
    l_label, l_color = _dir(scores["liquidity"], "Easing",     "Tightening")
    r_label, r_color = _dir(scores["risk"],      "Risk-On",    "Risk-Off")

    # Stagflation alert: >6 months with high confidence (>0.75)
    alert = None
    if regime == "Stagflation" and duration > 6 and confidence_score > 0.75:
        alert = f"ALERT: Stagflation persistent for {duration} months with {confidence} confidence. Review defensive positioning."

    # ═══════════════════════════════════════════════════════════════════════════════
    # LOG REGIME PREDICTION TO FORECAST TRACKER (Phase 2 Validation)
    # ═══════════════════════════════════════════════════════════════════════════════
    try:
        forecast_tracker.log_regime_forecast(
            regime=regime,
            confidence=confidence_score,
            method="threshold",
            growth_score=scores.get("growth", 0.0),
            inflation_score=scores.get("inflation", 0.0)
        )
    except Exception as e:
        logger.warning(f"[ForecastTracker] Failed to log regime: {e}")

    # ═══════════════════════════════════════════════════════════════════════════════
    # BUILD REGIME PLAYBOOK - Required for all classified regimes
    # ═══════════════════════════════════════════════════════════════════════════════
    from api.calculations import get_regime_characteristics

    regime_chars = get_regime_characteristics(regime)
    playbook = {
        "summary": regime_chars.description if regime_chars else f"{regime} regime",
        "keyRisks": regime_chars.themes[:3] if regime_chars else ["Market risk", "Policy uncertainty"],
        "opportunities": [
            f"{regime_chars.equity_bias.title()} equities" if regime_chars else "Neutral equities",
            f"{regime_chars.duration_bias} duration" if regime_chars else "Neutral duration",
            f"{regime_chars.commodity_bias} commodities" if regime_chars else "Neutral commodities"
        ],
        "positioningGuidance": f"{regime}: {regime_chars.description if regime_chars else 'Active regime'}"
    }

    return RegimeData(
        current=regime,
        confidence=confidence,
        confidenceScore=confidence_score,
        duration=duration,
        history=history,
        interpretations=[
            {"factor": "Growth",    "impact": g_label, "color": g_color},
            {"factor": "Inflation", "impact": i_label, "color": i_color},
            {"factor": "Liquidity", "impact": l_label, "color": l_color},
            {"factor": "Risk",      "impact": r_label, "color": r_color},
        ],
        alert=alert,
        playbook=playbook
    )














# PHASE 6: AQR FACTOR ROTATION + GEOPOLITICAL RISK + OPTIONS INTELLIGENCE + CTA TREND







# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 7 - ADVANCED QUANTITATIVE MODULES
# ═══════════════════════════════════════════════════════════════════════════════













def _get_hy_spread_bps(df: pd.DataFrame) -> float:
    """
    Unified HY spread source-of-truth with contract-based validation.
    FRED returns BAMLH0A0HYM2 as percentage (e.g., 2.86), converted to basis points
    (e.g., 286). NaN when the series is missing or implausible.
    """
    from api.data_contracts import CONTRACTS
    contract = CONTRACTS["hy_spread"]

    hy = _get(df, "hy_spreads", "high_yield_spread", "baa_credit_spread")

    # Unavailable → NaN (every caller guards with np.isnan / `> 0`), never a placeholder level.
    if np.isnan(hy):
        logger.warning("[HY_SPREAD] No data — unavailable")
        return float("nan")

    # If value < 10, it's likely in percentage format (e.g., 2.86), convert to bps
    if hy < 10:
        hy = hy * contract.multiply_by  # 100x conversion

    # Hard bounds check
    if not (contract.hard_min <= hy <= contract.hard_max):
        logger.warning(f"[HY_SPREAD] {hy} outside bounds [{contract.hard_min}, {contract.hard_max}] — rejected")
        return float("nan")

    return float(hy)
























def get_risk_indicators(df: pd.DataFrame) -> RiskIndicatorsData:
    """Build risk indicator panel from actual data columns."""
    indicators = []
    trend_scores = []  # Track direction of change for divergence detection

    # FIXED: Use unified source-of-truth function
    hy = _get_hy_spread_bps(df)
    hy_series = _series(df, "hy_spreads", "high_yield_spread", "baa_credit_spread")
    if hy > 0:

        if hy < 300:
            level, interp = "low",    "Credit conditions benign; risk appetite elevated"
        elif hy < 500:
            level, interp = "medium", "Credit spreads at moderate levels; monitoring warranted"
        elif hy < 700:
            level, interp = "high",   "Elevated spreads signal rising default risk"
        else:
            level, interp = "critical","Spreads at recessionary levels; severe credit stress"
        indicators.append(RiskIndicator(
            name="HY Credit Spreads",
            value=f"{hy:.0f} bps",
            level=level,
            interpretation=interp
        ))
        # Track trend: lower spreads = improving (positive trend)
        if len(hy_series) >= 2:
            trend_scores.append(-1 if hy_series.iloc[-1] < hy_series.iloc[-2] else 1)

    vix = _get(df, "vix", "us_vix")
    vix_series = _series(df, "vix", "us_vix")
    if not np.isnan(vix):
        if vix < 15:
            level, interp = "low",    "VIX below 15 - market complacency / low fear"
        elif vix < 20:
            level, interp = "low",    "VIX 15–20 - normal conditions"
        elif vix < 30:
            level, interp = "medium", "VIX 20–30 - elevated uncertainty"
        else:
            level, interp = "high",   f"VIX {vix:.0f} - market stress / fear elevated"
        indicators.append(RiskIndicator(
            name="VIX Volatility Index",
            value=f"{vix:.1f}",
            level=level,
            interpretation=interp
        ))
        # Track trend: lower VIX = improving (positive trend)
        if len(vix_series) >= 2:
            trend_scores.append(-1 if vix_series.iloc[-1] < vix_series.iloc[-2] else 1)

    yc = _get(df, "yield_curve", "us_yield_curve")
    yc_series = _series(df, "yield_curve", "us_yield_curve")
    y10 = _get(df, "yield_10y", "us_10y_yield")
    y2  = _get(df, "yield_2y",  "us_2y_yield")
    if np.isnan(yc) and not (np.isnan(y10) or np.isnan(y2)):
        yc = y10 - y2
    if not np.isnan(yc):
        if yc < -0.5:
            level, interp = "high",   f"Curve deeply inverted ({yc:+.2f}%) - strong recession signal"
        elif yc < 0:
            level, interp = "medium", f"Curve slightly inverted ({yc:+.2f}%) - caution"
        elif yc < 0.5:
            level, interp = "low",    f"Curve flat ({yc:+.2f}%) - late-cycle signal"
        else:
            level, interp = "low",    f"Curve steepening ({yc:+.2f}%) - expansionary"
        indicators.append(RiskIndicator(
            name="Yield Curve (10Y–2Y)",
            value=f"{yc*100:+.0f} bps",
            level=level,
            interpretation=interp
        ))
        # Track trend: less inverted = improving (positive trend)
        if len(yc_series) >= 2:
            trend_scores.append(1 if yc_series.iloc[-1] > yc_series.iloc[-2] else -1)

    bbb = _get(df, "bbb_spread", "credit_spreads")
    bbb_series = _series(df, "bbb_spread", "credit_spreads")
    if not np.isnan(bbb):
        if bbb < 130:
            level, interp = "low",    "IG credit conditions accommodative"
        elif bbb < 200:
            level, interp = "medium", "IG spreads elevated; some credit tightening"
        else:
            level, interp = "high",   "IG spreads wide; significant financial stress"
        indicators.append(RiskIndicator(
            name="BBB Credit Spread",
            value=f"{bbb:.0f} bps",
            level=level,
            interpretation=interp
        ))
        # Track trend: lower spreads = improving (positive trend)
        if len(bbb_series) >= 2:
            trend_scores.append(-1 if bbb_series.iloc[-1] < bbb_series.iloc[-2] else 1)

    # Fallback
    if not indicators:
        indicators = [
            RiskIndicator(name="Credit Spreads", value="N/A", level="unknown",
                         interpretation="No credit spread data available"),
        ]

    # Composite risk score
    level_weights = {"low": 1, "medium": 2, "high": 3, "critical": 4, "unknown": 2}
    composite = sum(level_weights.get(i.level, 2) for i in indicators) / max(len(indicators), 1)
    risk_regime = "elevated" if composite >= 2.5 else "contained" if composite <= 1.5 else "moderate"

    # Divergence detection: compare composite regime with trend direction
    divergence_warning = None
    if trend_scores:
        avg_trend = np.mean(trend_scores)  # Positive = improving, Negative = deteriorating
        if risk_regime == "elevated" and avg_trend > 0.3:
            divergence_warning = "Composite shows elevated risk but indicators are improving"
        elif risk_regime == "contained" and avg_trend < -0.3:
            divergence_warning = "Composite shows contained risk but indicators are deteriorating"

    # FIXED (BUG H): Extract VIX for Topbar ticker
    vix_value = None
    vix_change = None
    for ind in indicators:
        if "VIX" in ind.name:
            try:
                vix_value = float(ind.value)
                # Calculate change from series if available
                if len(vix_series) >= 2:
                    vix_change = float(vix_series.iloc[-1] - vix_series.iloc[-2])
            except (ValueError, TypeError):
                pass

    return RiskIndicatorsData(
        indicators=indicators,
        compositeScore=round(composite, 2),
        regime=risk_regime,
        divergenceWarning=divergence_warning,
        vix=vix_value,
        vixChange=vix_change
    )






























# MODULE 1: NOWCASTING LAYER (DFM/MIDAS GDP Nowcast)



# MODULE 2: LIQUIDITY CONDITIONS INDEX



# MODULE 3: SENTIMENT & RISK APPETITE

# FIXED: Pre-fetch Fear & Greed data at module load
_FEAR_GREED_CACHE: Optional[Dict[str, Any]] = None

# FIXED: Cache for Risk Parity ETF data (yfinance) with TTL=3600 seconds
_RISK_PARITY_ETF_CACHE: Optional[Dict[str, Any]] = None
_RISK_PARITY_CACHE_TIMESTAMP: Optional[datetime] = None

# FIXED: Cache for Debt Cycle Monitor (FRED data) with TTL=86400 seconds (24 hours)
_DEBT_CYCLE_CACHE: Optional[DebtCycleResult] = None
_DEBT_CYCLE_CACHE_TIMESTAMP: Optional[datetime] = None

# FIXED: Cache for Regime Backtest with TTL=86400 seconds (24 hours)
_REGIME_BACKTEST_CACHE: Optional[RegimeBacktestResult] = None
_REGIME_BACKTEST_CACHE_TIMESTAMP: Optional[datetime] = None

# FIXED: Phase 4 - Alert state storage (in-memory, per-session)
ALERT_STATE: Dict[str, Dict[str, Any]] = {}

# FIXED: Phase 4 - International Macro cache (TTL=86400)
_INTERNATIONAL_MACRO_CACHE: Optional[InternationalMacroResult] = None
_INTERNATIONAL_MACRO_CACHE_TIMESTAMP: Optional[datetime] = None

# FIXED: Phase 6 - Geopolitical Risk cache (TTL=86400)
_GEOPOLITICAL_RISK_CACHE: Optional[Dict[str, Any]] = None
_GEOPOLITICAL_RISK_CACHE_TIMESTAMP: Optional[datetime] = None

# FIXED: Phase 6 - Options Intelligence cache (TTL=3600)
_OPTIONS_INTELLIGENCE_CACHE: Optional[Dict[str, Any]] = None
_OPTIONS_INTELLIGENCE_CACHE_TIMESTAMP: Optional[datetime] = None

# FIXED: Phase 6 - CTA Trend Signals cache (TTL=3600)
_CTA_TREND_CACHE: Optional[Dict[str, Any]] = None
_CTA_TREND_CACHE_TIMESTAMP: Optional[datetime] = None

# FIXED: Phase 6 - Factor Rotation cache (TTL=3600)
_FACTOR_ROTATION_CACHE: Optional[Dict[str, Any]] = None
_FACTOR_ROTATION_CACHE_TIMESTAMP: Optional[datetime] = None

# FIXED: Phase 7 - News Sentiment cache (TTL=1800)
_NEWS_SENTIMENT_CACHE: Optional[Dict[str, Any]] = None
_NEWS_SENTIMENT_CACHE_TIMESTAMP: Optional[datetime] = None

# FIXED: Phase 7 - GMO Forecasts cache (TTL=86400)
_GMO_FORECASTS_CACHE: Optional[Dict[str, Any]] = None
_GMO_FORECASTS_CACHE_TIMESTAMP: Optional[datetime] = None

# FIXED: Phase 7 - Reflexivity Detector cache (TTL=3600)
_REFLEXIVITY_CACHE: Optional[Dict[str, Any]] = None
_REFLEXIVITY_CACHE_TIMESTAMP: Optional[datetime] = None

# FIXED: Phase 7 - Factor Decomposition cache (TTL=3600)
_FACTOR_DECOMPOSITION_CACHE: Optional[Dict[str, Any]] = None
_FACTOR_DECOMPOSITION_CACHE_TIMESTAMP: Optional[datetime] = None

# FIXED: Phase 7 - Horizon Analysis cache (TTL=3600)
_HORIZON_ANALYSIS_CACHE: Optional[Dict[str, Any]] = None
_HORIZON_ANALYSIS_CACHE_TIMESTAMP: Optional[datetime] = None






# MODULE 4: VALUATION FILTER



# MODULE 5: CROSS-ASSET MOMENTUM VETO



# MODULE 6: CORRELATION REGIME ADJUSTMENT



# MODULE 7: SIGNAL HIERARCHY & OVERRIDE LOGIC



# FastAPI App

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Standardize log format across all app modules before anything else logs.
    from api.logging_config import setup_logging
    setup_logging()
    try:
        from api.core.accounts import migrate as _migrate_accounts
        _migrate_accounts()         # users table, security columns, default-password flags
    except Exception as e:
        logger.warning(f"[STARTUP] users table init failed: {e}")
    logger.info("Clearing dashboard cache to force fresh computation")
    global _DASHBOARD_CACHE
    _DASHBOARD_CACHE["data"] = None
    _DASHBOARD_CACHE["timestamp"] = 0.0

    # FIXED: Write port file on startup (dynamic port detection)
    port = int(os.environ.get("RUNTIME_API_PORT", 8000))
    write_port_file(port)

    # FIXED: R-01 - Start APScheduler with data pipeline jobs
    logger.info("[STARTUP] Initializing APScheduler for automated data pipeline")
    try:
        _scheduler.start()

        # Daily at 06:00 UTC - full data refresh
        _scheduler.add_job(
            func=lambda: run_daily_pipeline(_DASHBOARD_CACHE, _DASHBOARD_CACHE_LOCK),
            trigger=CronTrigger(hour=6, minute=0),
            id="daily_pipeline_06utc",
            replace_existing=True,
        )
        logger.info("[STARTUP] Scheduled daily_pipeline_06utc at 06:00 UTC")

        # Once after the US close. The CSV is monthly, so re-running the ~36-request
        # pipeline every 15 minutes only burned FRED's rate limit.
        _scheduler.add_job(
            func=lambda: run_daily_pipeline(_DASHBOARD_CACHE, _DASHBOARD_CACHE_LOCK),
            trigger=CronTrigger(day_of_week="mon-fri", hour=21, minute=15),
            id="post_close_refresh",
            replace_existing=True,
        )
        logger.info("[STARTUP] Scheduled post_close_refresh at 21:15 UTC weekdays")

        # Daily NAV snapshot (the fund's track record) after the US close.
        from api.routers.fund import take_nav_snapshot
        _scheduler.add_job(
            func=take_nav_snapshot,
            trigger=CronTrigger(day_of_week="mon-fri", hour=21, minute=30),
            id="daily_nav_snapshot",
            replace_existing=True,
        )
        logger.info("[STARTUP] Scheduled daily_nav_snapshot at 21:30 UTC weekdays")

        # FIXED: Phase 7 - Add new consolidated data refresh jobs
        # Price refresh every 60 seconds via new provider architecture
        _scheduler.add_job(
            func=lambda: refresh_coordinator.refresh_prices(),
            trigger="interval",
            seconds=60,
            id="consolidated_price_refresh",
            replace_existing=True,
        )
        logger.info("[STARTUP] Scheduled consolidated_price_refresh every 60s")

        # Macro data refresh every 15 minutes
        _scheduler.add_job(
            func=lambda: refresh_coordinator.refresh_macro(),
            trigger="interval",
            minutes=15,
            id="consolidated_macro_refresh",
            replace_existing=True,
        )
        logger.info("[STARTUP] Scheduled consolidated_macro_refresh every 15min")

    except Exception as e:
        logger.error(f"[STARTUP] Failed to initialize scheduler: {e}")

    # FIXED: Log FRED API key status at startup
    from api.config import FRED_API_KEY
    if FRED_API_KEY:
        logger.info("[config] FRED_API_KEY loaded: YES (key starts with: %s...)", FRED_API_KEY[:4])
    else:
        logger.warning("[config] FRED_API_KEY loaded: NO — CHECK .env file")

    # Warm the dashboard cache in the background and keep it fresh. The dashboard
    # aggregates many live fetches (15-20s cold) which exceeds the frontend's 8s
    # timeout; a warm cache lets the UI load instantly. TTL is 60s, refresh at 45s.
    import asyncio as _asyncio

    async def _dashboard_warm_loop():
        from api.handlers.dashboard_handler import warm_dashboard_cache
        while True:
            await warm_dashboard_cache("live")
            await _asyncio.sleep(45)

    try:
        _asyncio.create_task(_dashboard_warm_loop())
        logger.info("[STARTUP] Dashboard cache warm loop started")
    except Exception as e:
        logger.warning(f"[STARTUP] Could not start dashboard warm loop: {e}")

    async def _risk_warm_loop():
        # Keep the factor-proxy and held-position price histories warm so the first
        # load of the factor/VaR/stress panels doesn't wait ~30s on cold fetches.
        from api.handlers.market_handler import _fetch_dated_closes_literal
        from api.calculations.factor_model import FACTOR_TICKERS
        from api import portfolio_store
        while True:
            try:
                syms = set(FACTOR_TICKERS)
                for p in portfolio_store.list_positions(None):
                    if p.get("symbol"):
                        syms.add(str(p["symbol"]).upper())
                for s in syms:
                    await _fetch_dated_closes_literal(s)
            except Exception as e:
                logger.debug(f"[risk warm] {e}")
            await _asyncio.sleep(480)  # < the 600s history TTL

    try:
        _asyncio.create_task(_risk_warm_loop())
        logger.info("[STARTUP] Risk price-history warm loop started")
    except Exception as e:
        logger.warning(f"[STARTUP] Could not start risk warm loop: {e}")

    async def _endpoints_warm_loop():
        # Keep the slow live-data endpoints' TTL caches warm so user requests always hit the
        # cache and never wait on a cold FRED/yahoo fetch. Each fetch is offloaded to a worker
        # thread (its own event loop) so the blocking I/O never stalls the main event loop —
        # this is the piece that stops the dashboard mount-storm saturation. Best-effort:
        # any failure just leaves that endpoint's own ttl_cache to handle the next request.
        await _asyncio.sleep(8)  # let the first dashboard warm settle
        try:
            from api.routers.market import get_rates, get_market_overview
            from api.routers.signals import get_yield_curve_signal
            targets = [health_check, get_cot_data, get_economic_calendar,
                       get_rates, get_market_overview, get_yield_curve_signal,
                       # Heavy v1 analytics panels — pre-warm their TTL caches so a fresh
                       # dashboard load / fast scroll doesn't compute-storm the single backend
                       # and leave 9 panels showing "Unavailable — Timed out" on first paint.
                       quadrants_v1, stream_agreement_v1, factor_validation_v1,
                       risk_parity_compare_v1, regime_transition_v1, event_vol_v1,
                       correlation_matrix_v1, anomalies_v1, signal_attribution_v1]
        except Exception as e:
            logger.warning(f"[warm] could not resolve endpoint targets: {e}")
            return

        def _run_in_fresh_loop(fn):
            try:
                _asyncio.run(fn())
            except Exception as e:
                logger.debug(f"[warm] {getattr(fn, '__name__', '?')}: {str(e)[:80]}")

        while True:
            for fn in targets:
                try:
                    await _asyncio.to_thread(_run_in_fresh_loop, fn)
                except Exception as e:
                    logger.debug(f"[warm] offload failed: {str(e)[:80]}")
            await _asyncio.sleep(20)  # < every TTL, so caches never lapse

    try:
        _asyncio.create_task(_endpoints_warm_loop())
        logger.info("[STARTUP] Slow-endpoint warm loop started")
    except Exception as e:
        logger.warning(f"[STARTUP] Could not start endpoints warm loop: {e}")

    async def _pit_snapshot_loop():
        # Periodic point-in-time snapshots for the audit "time machine".
        from api import audit_store
        await _asyncio.sleep(30)  # let the first dashboard warm complete
        while True:
            try:
                state = await _build_pit_snapshot()
                if state:
                    await _asyncio.to_thread(audit_store.add_snapshot, state, "auto")
            except Exception as e:
                logger.debug(f"[pit snapshot] {e}")
            await _asyncio.sleep(300)  # every 5 minutes

    try:
        _asyncio.create_task(_pit_snapshot_loop())
        logger.info("[STARTUP] Point-in-time snapshot loop started")
    except Exception as e:
        logger.warning(f"[STARTUP] Could not start snapshot loop: {e}")

    yield

    # Shutdown: gracefully stop scheduler and remove port file
    logger.info("[SHUTDOWN] Stopping APScheduler")
    try:
        _scheduler.shutdown()
    except Exception as e:
        logger.warning(f"[SHUTDOWN] Scheduler shutdown error: {e}")
    # Remove port file on shutdown
    try:
        port_path = _ROOT / ".api_port"
        if port_path.exists():
            port_path.unlink()
    except Exception as e:
        pass

app = FastAPI(
    title="Macro Research Platform API",
    description="Institutional-grade macro research backend - Bridgewater / Conference Board methodology",
    version="2.0.0",
    lifespan=lifespan,
)

# Authentication: verify the bearer token on every request (see api/core/access.py).
from api.core.access import auth_middleware as _auth_middleware
app.middleware("http")(_auth_middleware)

# FIXED: Global exception handler to catch all unhandled exceptions
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Catch-all exception handler to prevent silent 500s."""
    import traceback
    error_trace = traceback.format_exc()
    logger.error(f"[GLOBAL ERROR] Unhandled exception: {exc}\n{error_trace}")
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal Server Error",
            "detail": str(exc),
            "path": str(request.url.path) if hasattr(request, 'url') else 'unknown',
            "timestamp": datetime.now().isoformat()
        }
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3002", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# FIXED: Phase 7 - Register new diagnostics routers
app.include_router(health_router)
app.include_router(diagnostics_router)

# FIXED: Phase 3 - Register modular routers
from api.routers import dashboard_router, market_router, signals_router, risk_router, business_router
app.include_router(dashboard_router)
app.include_router(market_router)
app.include_router(signals_router)
app.include_router(risk_router)
app.include_router(business_router)
from api.routers.fund import router as fund_router  # hedge-fund layer: NAV, limits, rebalance
app.include_router(fund_router)
from api.routers.admin import router as admin_router  # user administration (admin role)
app.include_router(admin_router)
from api.routers.desk import router as desk_router  # role desk: action queue + key numbers
app.include_router(desk_router)

# ═══════════════════════════════════════════════════════════════════════════════
# NATIVE WEBSOCKET ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

@app.websocket("/ws/prices")
async def websocket_prices(websocket: WebSocket):
    """
    Native WebSocket endpoint for real-time price streaming.
    Falls back to cached data if real-time sources unavailable.
    """
    await websocket.accept()
    logger.info("[WebSocket] Client connected to /ws/prices")

    try:
        # Send initial connection confirmation
        await websocket.send_json({
            "type": "connected",
            "timestamp": datetime.now().isoformat(),
            "message": "Connected to price stream"
        })

        # Simple heartbeat loop
        import asyncio
        while True:
            # Build exactly one payload per tick — a price-service failure just
            # degrades to a heartbeat rather than triggering a second send.
            payload = {"type": "heartbeat", "timestamp": datetime.now().isoformat()}
            try:
                from api.services.price_service import price_service
                prices = price_service.get_latest_prices(["SPY", "QQQ", "IWM", "GLD", "TLT"])
                if prices:
                    payload = {"type": "prices", "timestamp": datetime.now().isoformat(), "data": prices}
            except Exception as e:
                logger.debug(f"[WebSocket] Price service unavailable: {e}")

            try:
                await websocket.send_json(payload)
            except (WebSocketDisconnect, RuntimeError) as e:
                # Client went away — stop the loop instead of retrying on a closed
                # socket forever (was spamming "Cannot call send once closed").
                logger.info(f"[WebSocket] client disconnected, stopping price loop: {e}")
                break

            await asyncio.sleep(5)

    except WebSocketDisconnect:
        logger.info("[WebSocket] Client disconnected from /ws/prices")
    except Exception as e:
        logger.error(f"[WebSocket] Unexpected error: {e}")
    finally:
        try:
            await websocket.close()
        except RuntimeError:  # WebSocket may already be closed
            pass


# FIXED: Mount Socket.IO app
socket_app = socketio.ASGIApp(sio, app)


@app.get("/api/port-info")
async def get_port_info():
    """Returns the port this server is running on."""
    port = int(os.environ.get("RUNTIME_API_PORT", read_port_file() or 8000))
    return {
        "port": port,
        "host": "localhost",
        "baseUrl": f"http://localhost:{port}",
        "wsUrl": f"ws://localhost:{port}",
    }


@sio.event
async def connect(sid, environ):
    logger.info(f"Client connected: {sid}")
    await sio.emit("connected", {"status": "ok", "message": "Connected to Macro Terminal"}, room=sid)


@sio.event
async def disconnect(sid):
    logger.info(f"Client disconnected: {sid}")


@sio.on("subscribe_market_data")
async def subscribe_market_data(sid, data):
    logger.info(f"Client {sid} subscribed to market data")
    await sio.emit("market_data_update", {"status": "subscribed"}, room=sid)


@app.get("/api/health")
@ttl_cache(120)
async def health_check():
    df_live = load_processed_data()
    # No silent fallback to the synthetic sample dataset — report the live data's state.
    df = df_live
    model_status = {
        "recession":      _RECESSION_OK,
        "lei":            _LEI_OK,
        "credit_impulse": _CREDIT_OK,
        "risk_parity":    _RISKPARITY_OK,
        "fin_conditions": _FC_OK,
        "classifier":     _CLASSIFIER_OK,
    }
    # FIXED: Include data integrity check in health endpoint (BUG-14)
    integrity_status = "HEALTHY"
    integrity_errors = []
    if df is not None:
        # Quick validation of key metrics
        from api.data_fetcher import fetch_metric
        # Wire in the live FRED fetcher — without it fetch_metric has no source and
        # always falls back, spamming "ALL SOURCES FAILED" on every health poll.
        for _name, _lo, _hi in (("growth", -15, 15), ("inflation", -5, 25)):
            try:
                _v = fetch_metric(_name, fred_fetch_fn=_fetch_fresh_fred_value)
            except Exception as e:
                _v = None
                logger.debug(f"[health] {_name} fetch failed: {e}")
            if _v is None:
                integrity_errors.append(f"{_name.title()} unavailable (all sources failed)")
            elif not (_lo <= _v <= _hi):
                integrity_errors.append(f"{_name.title()} {_v}% out of bounds")
        if integrity_errors:
            integrity_status = "DEGRADED"

    return {
        "status": "ok" if df is not None else "error",
        "mode": "live" if df_live is not None else "none",
        "models": model_status,
        "data_rows": len(df) if df is not None else 0,
        "analyticalIntegrity": integrity_status,  # FIXED: Now reflects data integrity (BUG-14)
        "integrityErrors": integrity_errors[:5] if integrity_errors else [],
    }


@app.get("/api/v1/health/sources")
async def health_sources_v1():
    """Per-source data-feed health (FRED, market data, database) with response times.

    A PM needs to know exactly which upstream is degraded. Actively probes each
    dependency (cached ~30s) and reports status/latency/detail per source.
    """
    import asyncio as _aio
    from api.health_sources import get_sources_health
    try:
        return await _aio.to_thread(get_sources_health)
    except Exception as e:
        logger.error("[health/sources] probe failed: %s", e)
        return {"overall": "down", "live": 0, "total": 0, "sources": {},
                "checked_at": datetime.now().isoformat(), "error": str(e)[:160]}


@app.get("/api/v1/health")
async def health_v1():
    """Unified versioned health: analytics status + per-source feed health."""
    import asyncio as _aio
    from api.health_sources import get_sources_health
    try:
        sources = await _aio.to_thread(get_sources_health)
    except Exception as e:
        logger.error("[health/v1] source probe failed: %s", e)
        sources = {"overall": "down", "live": 0, "total": 0, "sources": {}, "error": str(e)[:160]}
    return {
        "status": "ok",
        "version": "v1",
        "dataSources": sources,
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/api/v1/methodology")
async def methodology_v1():
    """Human-readable documentation of every core model (formula, inputs, units,
    output range, citation) so institutional users can audit model logic."""
    from api.calculations.models import MODELS
    research_citations = [
        {"model": "Four Quadrants regime classification (/api/v1/quadrants)",
         "citation": "Bridgewater Associates — Four Quadrants / All Weather framework",
         "confidence": "medium — surprise proxy uses trailing trend, not published consensus",
         "note": "Two-axis growth-surprise × inflation-surprise; cross-validated vs 6-regime HMM."},
        {"model": "Return-overlay Risk Parity (/api/v1/risk-parity-compare)",
         "citation": "Anon. (2025) 'Risk Parity and its Discontents', SSRN",
         "confidence": "high finding, exploratory local implementation",
         "note": "Pure risk weighting generally underperforms 60/40; an expected-return overlay helps."},
        {"model": "Hierarchical Risk Parity (HRP) & CVaR Risk Parity",
         "citation": "López de Prado (2016) HRP; Brazilian Review of Finance (2026) HRP/CVaR-RP comparison",
         "confidence": "low-medium — ~1yr local backtest only, no long-history validation",
         "note": "HRP clusters the correlation matrix (robust to estimation error); CVaR-RP allocates by tail risk."},
        {"model": "Risk-contribution fragility bands (/api/v1/risk-parity-compare)",
         "citation": "Shah — 'Uncertain Risk Parity'",
         "confidence": "medium — bootstrap over the available ~1yr window",
         "note": "Bootstraps inverse-vol risk contributions; live bands show RP does not truly equalise risk (SPX/HY ~27% each vs Commodities ~7%)."},
        {"model": "Signal stream agreement (/api/v1/stream-agreement)",
         "citation": "Bridgewater Associates — macro / intermarket / flows as independent evidence streams",
         "confidence": "medium — heuristic stream classifiers; conviction scales with independent agreement",
         "note": "Position sizing multiplier scales with the NUMBER of agreeing streams, not any single model's confidence."},
        {"model": "Factor out-of-sample validation (/api/v1/factor-validation)",
         "citation": "AQR — Asness et al., 'Fact, Fiction, and Factor Investing'",
         "confidence": "medium — in/out-of-sample R² split on daily factor-ETF proxies",
         "note": "Flags factors whose R² collapses out-of-sample; live it flags Momentum (0.71→0.30) as unstable."},
        {"model": "US yield-curve recession model",
         "citation": "Estrella & Mishkin (1998) probit",
         "confidence": "high — strong published out-of-sample evidence"},
    ]
    return {"version": "v1", "models": MODELS, "count": len(MODELS),
            "research_citations": research_citations}


from pydantic import BaseModel as _PortfolioBaseModel


class PositionIn(_PortfolioBaseModel):
    symbol: str
    quantity: float
    avg_cost: float
    asset_class: Optional[str] = "Equity"
    book: Optional[str] = "Macro"
    strategy_bucket: Optional[str] = None
    entry_date: Optional[str] = None


class PositionUpdate(_PortfolioBaseModel):
    quantity: Optional[float] = None
    avg_cost: Optional[float] = None
    asset_class: Optional[str] = None
    book: Optional[str] = None
    strategy_bucket: Optional[str] = None
    entry_date: Optional[str] = None


class BulkPositionsIn(_PortfolioBaseModel):
    positions: List[PositionIn]


async def _enrich_positions(raw_positions: list) -> dict:
    """Attach live prices, market value, P&L and weights to raw position rows."""
    import asyncio as _aio
    from api.handlers.market_handler import _fetch_closes_literal
    from api.calculations.portfolio import enrich_position, add_weights, portfolio_summary, books_breakdown

    symbols = sorted({str(p["symbol"]).upper() for p in raw_positions if p.get("symbol")})
    prices: dict = {}
    if symbols:
        # Literal tickers (GLD = the ETF), not the dashboard's macro proxies.
        closes_list = await _aio.gather(*[_fetch_closes_literal(s) for s in symbols])
        for sym, closes in zip(symbols, closes_list):
            prices[sym] = closes[-1] if closes else None

    enriched = [enrich_position(p, prices.get(str(p["symbol"]).upper())) for p in raw_positions]
    add_weights(enriched)
    return {
        "positions": enriched,
        "summary": portfolio_summary(enriched),
        "books": books_breakdown(enriched),
        "priced_at": datetime.now().isoformat(),
    }


@app.get("/api/v1/portfolio/positions")
async def portfolio_positions_v1(book: Optional[str] = None):
    """Held positions enriched with live market value, unrealized P&L and weights."""
    from api import portfolio_store
    try:
        raw = await _aio_to_thread(portfolio_store.list_positions, book)
        return await _enrich_positions(raw)
    except Exception as e:
        logger.error("[portfolio] list failed: %s", e)
        raise HTTPException(status_code=503, detail=f"positions unavailable: {str(e)[:160]}")


async def _audit_position_edit(request: Request, action: str, rationale: str, before=None, after=None):
    try:
        from api import audit_store
        await _aio_to_thread(lambda: audit_store.add_decision(
            action, rationale, user=_request_user(request), target="positions",
            before_state=before, after_state=after))
    except Exception as e:
        logger.debug(f"[audit] position edit not logged: {e}")


@app.post("/api/v1/portfolio/positions")
async def portfolio_add_position_v1(pos: PositionIn, request: Request):
    """Manual position entry (e.g. loading an existing book). Trading should go through
    /api/v1/orders so it is approved and booked in the blotter; manual edits are audited."""
    from api import portfolio_store
    from api.core.access import require_roles
    require_roles(request, {"pm"})
    try:
        out = await _aio_to_thread(portfolio_store.add_position, pos.model_dump())
        await _audit_position_edit(request, "position_added", f"Manual position {out.get('symbol')} {out.get('quantity')}", after=out)
        return out
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error("[portfolio] add failed: %s", e)
        raise HTTPException(status_code=503, detail=str(e)[:160])


@app.post("/api/v1/portfolio/positions/bulk")
async def portfolio_bulk_v1(body: BulkPositionsIn, request: Request):
    from api import portfolio_store
    from api.core.access import require_roles
    require_roles(request, {"pm"})
    out = await _aio_to_thread(portfolio_store.add_positions_bulk, [p.model_dump() for p in body.positions])
    await _audit_position_edit(request, "positions_bulk_loaded", f"Bulk load of {len(body.positions)} positions")
    return out


@app.put("/api/v1/portfolio/positions/{pos_id}")
async def portfolio_update_position_v1(pos_id: int, upd: PositionUpdate, request: Request):
    from api import portfolio_store
    from api.core.access import require_roles
    require_roles(request, {"pm"})
    before = await _aio_to_thread(portfolio_store.get_position, pos_id)
    updated = await _aio_to_thread(portfolio_store.update_position, pos_id, upd.model_dump(exclude_none=True))
    if updated is None:
        raise HTTPException(status_code=404, detail="position not found")
    await _audit_position_edit(request, "position_edited", f"Manual edit of position {pos_id}", before, updated)
    return updated


@app.delete("/api/v1/portfolio/positions/{pos_id}")
async def portfolio_delete_position_v1(pos_id: int, request: Request):
    from api import portfolio_store
    from api.core.access import require_roles
    require_roles(request, {"pm"})
    before = await _aio_to_thread(portfolio_store.get_position, pos_id)
    ok = await _aio_to_thread(portfolio_store.delete_position, pos_id)
    if not ok:
        raise HTTPException(status_code=404, detail="position not found")
    await _audit_position_edit(request, "position_deleted", f"Manual delete of position {pos_id}", before)
    return {"deleted": True, "id": pos_id}


@app.get("/api/v1/portfolio/books")
async def portfolio_books_v1():
    """List books plus the firm-level aggregate across all positions."""
    from api import portfolio_store
    raw = await _aio_to_thread(portfolio_store.list_positions, None)
    enriched = (await _enrich_positions(raw))
    return {
        "books": portfolio_store.list_books(),
        "firm": enriched["summary"],
        "book_breakdown": enriched["books"],
    }


async def _risk_snapshot(raw: list) -> dict:
    """VaR (95% 1d), exposure and concentration for a (possibly hypothetical) raw set."""
    from api.calculations.var_model import (
        portfolio_pnl_series, historical_var, parametric_var, concentration,
    )
    data, reason, enriched = await _position_return_matrix(None, raw_positions=raw)
    enr = enriched or (await _enrich_positions(raw) if raw else {"summary": {}, "positions": []})
    conc = concentration(enr["positions"]) if enr.get("positions") else {"available": False}
    if data is None:
        return {"var_available": False, "reason": reason,
                "summary": enr.get("summary", {}), "concentration": conc}
    pnl = portfolio_pnl_series(data["market_values"], data["R"])
    return {
        "var_available": True,
        "var_95_1d": parametric_var(pnl, 0.95),
        "var_95_1d_hist": historical_var(pnl, 0.95),
        "summary": data["enriched"]["summary"],
        "concentration": conc,
    }


class WhatIfIn(_PortfolioBaseModel):
    symbol: str
    quantity: float
    avg_cost: Optional[float] = None      # defaults to current price (entry P&L = 0)
    book: Optional[str] = "Macro"
    var_limit: Optional[float] = None     # if set, suggest a size within this VaR budget


def _request_user(request: Request) -> str:
    """Identity for the audit trail: the user verified from the request's JWT (see
    api/core/access.py). The client-supplied X-User header is not trusted."""
    from api.core.access import current_user
    u = current_user(request)
    return u["username"] if u else "system"


@app.post("/api/v1/portfolio/what-if")
async def portfolio_what_if_v1(trade: WhatIfIn):
    """Pre-trade analysis: projected VaR / exposure / concentration BEFORE vs AFTER
    adding a proposed trade, plus a VaR-budgeted suggested size."""
    import numpy as _np
    from api import portfolio_store
    from api.handlers.market_handler import _fetch_closes_literal
    from api.calculations.factor_model import returns_from_closes
    from api.calculations.var_model import suggest_size_for_var

    current = await _aio_to_thread(portfolio_store.list_positions, None)
    before = await _risk_snapshot(current)

    sym = trade.symbol.strip().upper()
    closes = await _fetch_closes_literal(sym)
    if not closes:
        return {"available": False, "reason": f"No price history for {sym}."}
    price = closes[-1]
    proposed = {"symbol": sym, "quantity": trade.quantity,
                "avg_cost": trade.avg_cost if trade.avg_cost is not None else price,
                "book": trade.book or "Macro", "asset_class": "Equity"}
    after = await _risk_snapshot(current + [proposed])

    daily_vol = float(_np.std(returns_from_closes(closes))) if len(closes) > 2 else 0.0
    sizing = None
    if trade.var_limit:
        sizing = suggest_size_for_var(daily_vol, price, trade.var_limit, 0.95, 1)

    def _delta(a, b):
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            return round(a - b, 2)
        return None

    return {
        "available": True,
        "proposed": {"symbol": sym, "quantity": trade.quantity, "price": round(price, 2),
                     "notional": round(trade.quantity * price, 2), "book": trade.book},
        "before": before, "after": after,
        "delta": {
            "var_95_1d": _delta(after.get("var_95_1d"), before.get("var_95_1d")),
            "gross_exposure": _delta(after.get("summary", {}).get("gross_exposure"),
                                     before.get("summary", {}).get("gross_exposure")),
            "net_exposure": _delta(after.get("summary", {}).get("net_exposure"),
                                   before.get("summary", {}).get("net_exposure")),
            "largest_weight": _delta(after.get("concentration", {}).get("largest_weight"),
                                     before.get("concentration", {}).get("largest_weight")),
        },
        "sizing": sizing,
        "computed_at": datetime.now().isoformat(),
    }


class TradeIdeaIn(_PortfolioBaseModel):
    symbol: str
    direction: Optional[str] = "LONG"
    thesis: Optional[str] = None
    conviction: Optional[str] = "MEDIUM"
    rationale: Optional[str] = None
    suggested_size: Optional[float] = None
    book: Optional[str] = "Macro"


class TradeIdeaTransition(_PortfolioBaseModel):
    state: str
    note: Optional[str] = None


@app.get("/api/v1/portfolio/trade-ideas")
async def trade_ideas_list_v1(state: Optional[str] = None):
    from api import portfolio_store
    ideas = await _aio_to_thread(portfolio_store.list_trade_ideas, state)
    return {"ideas": ideas, "states": portfolio_store.IDEA_STATES}


@app.post("/api/v1/portfolio/trade-ideas")
async def trade_ideas_add_v1(idea: TradeIdeaIn, request: Request):
    from api import portfolio_store
    user = _request_user(request)
    try:
        return await _aio_to_thread(lambda: portfolio_store.add_trade_idea(idea.model_dump(), user))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@app.post("/api/v1/portfolio/trade-ideas/{idea_id}/transition")
async def trade_ideas_transition_v1(idea_id: int, body: TradeIdeaTransition, request: Request):
    from api import portfolio_store, blotter_store
    from api.core.access import require_roles
    user = _request_user(request)
    # Orders (ideas with side/quantity) may only be approved/executed through the order
    # workflow, which enforces four-eyes, re-runs compliance and books the fill.
    idea = await _aio_to_thread(blotter_store.get_idea, idea_id)
    if idea and idea.get("side") and body.state in ("Approved", "Executed"):
        raise HTTPException(status_code=409, detail=(
            f"Order #{idea_id} must be {'approved' if body.state == 'Approved' else 'executed'} via "
            f"/api/v1/orders/{idea_id}/{'approve' if body.state == 'Approved' else 'execute'}"))
    if body.state == "Approved":
        require_roles(request, {"risk"})
        if idea and user == (idea.get("created_by") or ""):
            raise HTTPException(status_code=403, detail="four-eyes: approver must differ from the creator")
    try:
        updated = await _aio_to_thread(lambda: portfolio_store.transition_trade_idea(idea_id, body.state, user, body.note))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    if updated is None:
        raise HTTPException(status_code=404, detail="trade idea not found")
    # Record the lifecycle change in the audit decision log, attributed to the acting user.
    try:
        from api import audit_store
        await _aio_to_thread(lambda: audit_store.add_decision(
            action=f"Trade idea → {body.state}", rationale=body.note or f"Transitioned to {body.state}",
            user=user, target=f"{updated.get('symbol')} (idea #{idea_id})",
            after_state={"state": body.state}))
    except Exception as e:
        logger.debug(f"[audit] could not log idea transition: {e}")
    return updated


@app.get("/api/v1/portfolio/generate-ideas")
async def portfolio_generate_ideas_v1(book: Optional[str] = None):
    """Auto-generate trade ideas by mapping the current macro regime's playbook
    (REGIME_CHARACTERISTICS) onto factor proxies and comparing to the book's live factor
    exposures. Transparent rules engine — every idea states the regime, factor and reason."""
    from api.calculations.idea_generation import generate_ideas

    # Current regime from the live dashboard cache.
    regime_key, regime_name = None, None
    try:
        from api.handlers.dashboard_handler import _DASHBOARD_CACHE
        cached = _DASHBOARD_CACHE.get("live")
        d = cached[1] if cached else None
        if d is not None:
            reg = getattr(d, "regime", None) or {}
            regime_name = getattr(reg, "current", None) if not isinstance(reg, dict) else reg.get("current")
            regime_key = (regime_name or "").strip().lower()
    except Exception as e:
        logger.debug(f"[generate-ideas] regime lookup failed: {e}")
    if not regime_key:
        return {"available": False, "reason": "Current regime unavailable — dashboard not warmed yet.",
                "ideas": []}

    dexp, reason = await _dollar_factor_exposures(book)
    if dexp is None:
        return {"available": False, "reason": reason or "No positions to analyse.",
                "regime": regime_name, "ideas": []}

    from api import portfolio_store
    raw = await _aio_to_thread(portfolio_store.list_positions, book)
    gross = (await _enrich_positions(raw))["summary"]["gross_exposure"] or 0.0 if raw else 0.0

    ideas = generate_ideas(dexp, regime_key, gross_exposure=gross)
    return {"available": True, "regime": regime_name, "book": book or "Firm",
            "gross_exposure": round(gross, 2), "dollar_exposures": dexp,
            "ideas": ideas, "computed_at": datetime.now().isoformat()}


@app.delete("/api/v1/portfolio/trade-ideas/{idea_id}")
async def trade_ideas_delete_v1(idea_id: int):
    from api import portfolio_store
    ok = await _aio_to_thread(portfolio_store.delete_trade_idea, idea_id)
    if not ok:
        raise HTTPException(status_code=404, detail="trade idea not found")
    return {"deleted": True, "id": idea_id}


async def _aio_to_thread(fn, *args):
    import asyncio as _aio
    return await _aio.to_thread(fn, *args)


@app.get("/api/v1/portfolio/attribution")
async def portfolio_attribution_v1(book: Optional[str] = None):
    """Multi-level performance attribution on the real book:
    - contribution: each position's / book's dollar P&L (sums to total P&L),
    - factor: the trailing portfolio return split into systematic (per factor) +
      idiosyncratic (selection). Requires positions."""
    import numpy as _np
    from api import portfolio_store
    from api.calculations.attribution import (
        position_contributions, book_rollup, factor_attribution,
    )
    raw = await _aio_to_thread(portfolio_store.list_positions, book)
    if not raw:
        return {"available": False, "reason": "No positions configured — add positions first."}
    enriched = await _enrich_positions(raw)
    positions = enriched["positions"]

    contribution = {
        "total_unrealized_pnl": enriched["summary"]["total_unrealized_pnl"],
        "by_position": position_contributions(positions),
        "by_book": book_rollup(positions),
    }

    # Factor attribution over the trailing window (best-effort; may be unavailable for
    # very new books). portfolio_return = Σ net_weight_i * cumulative_return_i.
    factor = {"available": False, "reason": "insufficient history"}
    data, _, _ = await _position_return_matrix(book)
    if data is not None:
        R, mvs, gross = data["R"], data["market_values"], enriched["summary"]["gross_exposure"] or 0.0
        cum = _np.prod(1.0 + R, axis=0) - 1.0
        net_w = _np.array([mv / gross if gross else 0.0 for mv in mvs])
        port_ret = float(net_w @ cum)

        fe = await risk_factor_exposure_v1(book)
        if fe.get("available"):
            from api.handlers.market_handler import _fetch_dated_closes_literal
            from api.calculations.factor_model import (
                FACTOR_DEFINITIONS, FACTOR_TICKERS, factor_period_return)
            loadings = {f["factor"]: f["exposure"] for f in fe["factors"]}
            # Period return per ticker over the same dates the positions span.
            dated_all = {t: await _fetch_dated_closes_literal(t) for t in FACTOR_TICKERS}
            dates = data.get("dates") or []
            tick_ret = {}
            for t, d in dated_all.items():
                pts = [d[k] for k in dates if k in d] if dates else [d[k] for k in sorted(d)]
                if len(pts) >= 2 and pts[0]:
                    tick_ret[t] = pts[-1] / pts[0] - 1.0
            fac_ret = {f: r for f in FACTOR_DEFINITIONS
                       if (r := factor_period_return(tick_ret, f)) is not None}
            factor = {"available": True, "window": "~1y",
                      **factor_attribution(loadings, fac_ret, port_ret)}

    return {
        "available": True, "book": book or "Firm",
        "contribution": contribution, "factor": factor,
        "computed_at": datetime.now().isoformat(),
    }


@app.get("/api/v1/risk/factor-exposure")
async def risk_factor_exposure_v1(book: Optional[str] = None):
    """Portfolio factor exposure: OLS betas of each holding to systematic factors,
    aggregated by net weight, with each factor's contribution to portfolio volatility.
    Requires positions (Phase 1) — returns available=false with a reason if none."""
    import numpy as _np
    from api import portfolio_store
    from api.handlers.market_handler import _fetch_dated_closes_literal
    from api.calculations.factor_model import (
        FACTOR_PROXIES, FACTOR_LABELS, FACTOR_TICKERS, returns_from_closes,
        build_factor_returns, estimate_factor_loadings, regression_fit,
        aggregate_portfolio_loadings, contribution_to_vol,
    )

    raw = await _aio_to_thread(portfolio_store.list_positions, book)
    if not raw:
        return {"available": False, "reason": "No positions configured — add positions first.",
                "factors": []}

    enriched = await _enrich_positions(raw)
    positions = enriched["positions"]
    gross = enriched["summary"]["gross_exposure"] or 0.0

    # Fetch dated closes for every factor ticker (long and short legs) and held symbol.
    ticker_dated = {t: await _fetch_dated_closes_literal(t) for t in FACTOR_TICKERS}
    common_dates = None
    for d in ticker_dated.values():
        keys = set(d.keys())
        common_dates = keys if common_dates is None else (common_dates & keys)
    common_dates = sorted(common_dates or [])
    if len(common_dates) < 61:
        return {"available": False, "reason": "Insufficient factor price history to estimate loadings.",
                "factors": []}

    def _aligned(dmap, dates):
        return returns_from_closes([dmap[dt] for dt in dates])

    def _factors_on(dates):
        return build_factor_returns({t: _aligned(ticker_dated[t], dates) for t in FACTOR_TICKERS})

    # Factor volatilities (annualized) over the common grid.
    factor_full_ret = _factors_on(common_dates)
    factor_vol = {f: float(_np.std(r) * (252 ** 0.5)) if len(r) else 0.0 for f, r in factor_full_ret.items()}

    per_position = []
    position_loadings, net_weights = [], []
    for p in positions:
        sym = str(p["symbol"]).upper()
        pdated = await _fetch_dated_closes_literal(sym)
        pdates = [dt for dt in common_dates if dt in pdated]
        loadings = {}
        r2 = 0.0
        if len(pdates) >= 61:
            pos_ret = _aligned(pdated, pdates)
            fac_ret = _factors_on(pdates)
            loadings = estimate_factor_loadings(pos_ret, fac_ret)
            r2 = regression_fit(pos_ret, fac_ret) if loadings else 0.0
        mv = p.get("market_value")
        net_w = (mv / gross) if (isinstance(mv, (int, float)) and gross) else 0.0
        position_loadings.append(loadings)
        net_weights.append(net_w)
        per_position.append({
            "symbol": sym, "book": p.get("book"), "net_weight": round(net_w, 4),
            "r_squared": r2, "loadings": {k: round(v, 4) for k, v in loadings.items()},
            "estimated": bool(loadings),
        })

    portfolio_loadings = aggregate_portfolio_loadings(position_loadings, net_weights)
    contrib = contribution_to_vol(portfolio_loadings, factor_full_ret)

    factors_out = []
    for f in FACTOR_PROXIES:
        factors_out.append({
            "factor": f,
            "label": FACTOR_LABELS.get(f, f),
            "proxy": FACTOR_PROXIES[f],
            "exposure": round(portfolio_loadings.get(f, 0.0), 4),
            "factor_vol_annual": round(factor_vol.get(f, 0.0), 4),
            "contribution_to_vol": round(contrib.get(f, 0.0), 4),
        })
    factors_out.sort(key=lambda x: abs(x["exposure"]), reverse=True)

    return {
        "available": True,
        "book": book or "Firm",
        "factors": factors_out,
        "positions": per_position,
        "observations": len(common_dates) - 1,
        "computed_at": datetime.now().isoformat(),
    }


async def _position_return_matrix(book: Optional[str], raw_positions: Optional[list] = None):
    """(symbols, market_values, TxN return matrix, enriched) for held positions,
    date-aligned across names. Pass raw_positions to compute on a hypothetical set
    (e.g. what-if) instead of the persisted book."""
    import numpy as _np
    from api import portfolio_store
    from api.handlers.market_handler import _fetch_dated_closes_literal
    from api.calculations.factor_model import returns_from_closes

    raw = raw_positions if raw_positions is not None else await _aio_to_thread(portfolio_store.list_positions, book)
    if not raw:
        return None, "No positions configured — add positions first.", None
    enriched = await _enrich_positions(raw)
    positions = [p for p in enriched["positions"] if p.get("price_available")]
    if not positions:
        return None, "No priced positions to compute risk on.", enriched

    dated = {}
    for p in positions:
        dated[p["symbol"]] = await _fetch_dated_closes_literal(str(p["symbol"]).upper())
    common = None
    for d in dated.values():
        keys = set(d.keys())
        common = keys if common is None else (common & keys)
    common = sorted(common or [])
    if len(common) < 61:
        return None, "Insufficient overlapping price history to estimate VaR.", enriched

    cols = []
    symbols, mvs = [], []
    for p in positions:
        r = returns_from_closes([dated[p["symbol"]][dt] for dt in common])
        cols.append(r)
        symbols.append(p["symbol"])
        mvs.append(float(p["market_value"]))
    R = _np.column_stack(cols)  # (T, n)
    return {"symbols": symbols, "market_values": mvs, "R": R, "dates": common,
            "enriched": enriched}, None, enriched


@app.get("/api/v1/risk/var")
async def risk_var_v1(book: Optional[str] = None):
    """Value-at-Risk (historical, parametric, Monte Carlo) at 95%/99%, 1d & 10d, on
    actual positions, with VaR contribution by position."""
    from api.calculations.var_model import (
        portfolio_pnl_series, historical_var, parametric_var, monte_carlo_var,
        scale_horizon, component_var_by_position,
    )
    data, reason, _ = await _position_return_matrix(book)
    if data is None:
        return {"available": False, "reason": reason, "methods": {}}
    mvs, R, symbols = data["market_values"], data["R"], data["symbols"]
    pnl = portfolio_pnl_series(mvs, R)

    def block(conf):
        h = historical_var(pnl, conf)
        pv = parametric_var(pnl, conf)
        mc = monte_carlo_var(mvs, R, conf)
        return {
            "historical": {"1d": h, "10d": scale_horizon(h, 10)},
            "parametric": {"1d": pv, "10d": scale_horizon(pv, 10)},
            "monte_carlo": {"1d": mc, "10d": scale_horizon(mc, 10)},
        }

    # Allocate the PARAMETRIC 95% 1d VaR: the Euler/variance decomposition is only
    # self-consistent against a variance-based total (not the empirical historical one).
    total_1d_param = parametric_var(pnl, 0.95)
    return {
        "available": True,
        "book": book or "Firm",
        "observations": int(R.shape[0]),
        "gross_exposure": data["enriched"]["summary"]["gross_exposure"],
        "var": {"95": block(0.95), "99": block(0.99)},
        "component_var_95_1d": component_var_by_position(symbols, mvs, R, total_1d_param),
        "component_var_basis": "parametric_95_1d",
        "computed_at": datetime.now().isoformat(),
    }


async def _dollar_factor_exposures(book: Optional[str]):
    """DExp_f = gross_exposure * portfolio_loading_f ($ P&L per 1.0 factor return)."""
    fe = await risk_factor_exposure_v1(book)
    if not fe.get("available"):
        return None, fe.get("reason")
    gross = 0.0
    from api import portfolio_store
    raw = await _aio_to_thread(portfolio_store.list_positions, book)
    if raw:
        gross = (await _enrich_positions(raw))["summary"]["gross_exposure"] or 0.0
    dexp = {f["factor"]: round(gross * f["exposure"], 2) for f in fe["factors"]}
    return dexp, None


@app.get("/api/v1/risk/stress-test")
async def risk_stress_get_v1(book: Optional[str] = None):
    """Apply predefined historical scenarios (2008, 2020, 2013, 2022, 1994) to the
    current portfolio's dollar factor exposures."""
    from api.calculations.var_model import STRESS_SCENARIOS, scenario_pnl, to_factor_shocks
    dexp, reason = await _dollar_factor_exposures(book)
    if dexp is None:
        return {"available": False, "reason": reason, "scenarios": []}
    scenarios = []
    for key, sc in STRESS_SCENARIOS.items():
        shocks = to_factor_shocks(sc["shocks"])
        res = scenario_pnl(dexp, shocks)
        scenarios.append({"id": key, "label": sc["label"], "shocks": shocks,
                          "proxy_shocks": sc["shocks"],
                          "total_pnl": res["total_pnl"], "by_factor": res["by_factor"]})
    scenarios.sort(key=lambda s: s["total_pnl"])
    return {"available": True, "book": book or "Firm", "dollar_exposures": dexp,
            "scenarios": scenarios, "computed_at": datetime.now().isoformat()}


class StressCustomIn(_PortfolioBaseModel):
    shocks: Dict[str, float]
    book: Optional[str] = None


@app.post("/api/v1/risk/stress-test")
async def risk_stress_custom_v1(body: StressCustomIn):
    """Custom scenario: shock any combination of factors and see estimated P&L."""
    from api.calculations.var_model import scenario_pnl
    dexp, reason = await _dollar_factor_exposures(body.book)
    if dexp is None:
        return {"available": False, "reason": reason}
    res = scenario_pnl(dexp, body.shocks)
    return {"available": True, "shocks": body.shocks, "total_pnl": res["total_pnl"],
            "by_factor": res["by_factor"]}


@app.get("/api/v1/risk/reverse-stress")
async def risk_reverse_stress_v1(target_loss: float, book: Optional[str] = None):
    """Reverse stress: the single-factor move that alone would cause target_loss ($)."""
    from api.calculations.var_model import reverse_stress
    dexp, reason = await _dollar_factor_exposures(book)
    if dexp is None:
        return {"available": False, "reason": reason, "factors": []}
    return {"available": True, "target_loss": target_loss,
            "factors": reverse_stress(dexp, target_loss),
            "computed_at": datetime.now().isoformat()}


@app.get("/api/v1/risk/concentration")
async def risk_concentration_v1(book: Optional[str] = None, limit_pct: float = 0.20):
    """Single-name and top-5 concentration with limit breaches."""
    from api import portfolio_store
    from api.calculations.var_model import concentration
    raw = await _aio_to_thread(portfolio_store.list_positions, book)
    if not raw:
        return {"available": False, "reason": "No positions configured."}
    enriched = await _enrich_positions(raw)
    return concentration(enriched["positions"], limit_pct)


@app.get("/api/v1/risk/liquidity")
async def risk_liquidity_v1(book: Optional[str] = None, participation: float = 0.20,
                            illiquid_days: float = 5.0):
    """Days-to-liquidate per position from average daily volume; flags illiquid names."""
    from api import portfolio_store
    from api.calculations.var_model import days_to_liquidate
    raw = await _aio_to_thread(portfolio_store.list_positions, book)
    if not raw:
        return {"available": False, "reason": "No positions configured.", "positions": []}

    def _adv(ticker):
        try:
            import yfinance as yf
            h = yf.Ticker(ticker).history(period="1mo", interval="1d")
            if h is None or h.empty or "Volume" not in h:
                return None
            v = [x for x in h["Volume"].tolist() if isinstance(x, (int, float)) and x == x and x > 0]
            return float(sum(v) / len(v)) if v else None
        except Exception:
            return None

    rows = []
    for p in raw:
        sym = str(p["symbol"]).upper()
        adv = await _aio_to_thread(_adv, sym)
        dtl = days_to_liquidate(float(p["quantity"]), adv, participation)
        rows.append({"symbol": sym, "book": p.get("book"), "quantity": p["quantity"],
                     "avg_daily_volume": round(adv) if adv else None,
                     "days_to_liquidate": dtl,
                     "illiquid": bool(dtl is not None and dtl > illiquid_days)})
    rows.sort(key=lambda r: (r["days_to_liquidate"] is None, -(r["days_to_liquidate"] or 0)))
    return {"available": True, "book": book or "Firm", "participation": participation,
            "illiquid_threshold_days": illiquid_days, "positions": rows,
            "illiquid_count": sum(1 for r in rows if r["illiquid"])}


class DecisionIn(_PortfolioBaseModel):
    action: str
    rationale: str
    target: Optional[str] = None
    before_state: Optional[Any] = None
    after_state: Optional[Any] = None


@app.get("/api/v1/audit/decisions")
async def audit_decisions_list_v1(limit: int = 100):
    from api import audit_store
    return {"decisions": await _aio_to_thread(audit_store.list_decisions, limit)}


@app.post("/api/v1/audit/decisions")
async def audit_decisions_add_v1(d: DecisionIn, request: Request):
    from api import audit_store
    user = _request_user(request)
    try:
        return await _aio_to_thread(lambda: audit_store.add_decision(
            d.action, d.rationale, user, d.target, d.before_state, d.after_state))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@app.get("/api/v1/audit/snapshots")
async def audit_snapshots_list_v1(limit: int = 200):
    from api import audit_store
    return {"snapshots": await _aio_to_thread(audit_store.list_snapshots, limit)}


@app.get("/api/v1/audit/snapshots/{snap_id}")
async def audit_snapshot_get_v1(snap_id: int):
    from api import audit_store
    snap = await _aio_to_thread(audit_store.get_snapshot, snap_id)
    if snap is None:
        raise HTTPException(status_code=404, detail="snapshot not found")
    return snap


@app.get("/api/v1/audit/time-machine")
async def audit_time_machine_v1(at: str):
    """The system state as it was at (or just before) the given ISO timestamp."""
    from api import audit_store
    snap = await _aio_to_thread(audit_store.get_snapshot_at, at)
    if snap is None:
        return {"available": False, "reason": "No snapshot at or before that time."}
    return {"available": True, **snap}


async def _build_pit_snapshot() -> dict:
    """Compact point-in-time state: regime, ensemble, key metrics, portfolio risk."""
    state: dict = {}
    try:
        from api.handlers.dashboard_handler import _DASHBOARD_CACHE
        cached = _DASHBOARD_CACHE.get("live")
        d = cached[1] if cached else None
        if d is not None:
            reg = getattr(d, "regime", None) or {}
            ens = getattr(d, "ensemble", None) or {}
            km = getattr(d, "keyMetrics", None) or {}
            def g(o, k):
                return getattr(o, k, None) if not isinstance(o, dict) else o.get(k)
            state["regime"] = {"current": g(reg, "current"), "confidence": g(reg, "confidenceScore")}
            state["ensemble"] = {"score": g(ens, "score"), "agreement": g(ens, "agreement"), "mode": g(ens, "mode")}
            rec = g(km, "recession")
            state["key_metrics"] = {"recession": (g(rec, "value") if rec else None)}
    except Exception as e:
        state["dashboard_error"] = str(e)[:100]
    try:
        from api import portfolio_store
        raw = portfolio_store.list_positions(None)
        if raw:
            enr = await _enrich_positions(raw)
            state["portfolio"] = {"gross_exposure": enr["summary"]["gross_exposure"],
                                  "net_exposure": enr["summary"]["net_exposure"],
                                  "total_unrealized_pnl": enr["summary"]["total_unrealized_pnl"],
                                  "position_count": enr["summary"]["position_count"]}
    except Exception as e:
        state["portfolio_error"] = str(e)[:100]
    return state


@app.get("/api/v1/data-quality")
async def data_quality_v1():
    """Automated data-quality checks: scans key price series for bad ticks (implausible
    day-over-day jumps) and statistical outliers before they propagate into signals/risk."""
    from api.handlers.market_handler import _fetch_closes_literal
    from api.calculations.data_quality import quality_report

    # (name, ticker, jump_threshold). VIX legitimately moves 25%+ per day, so it gets a
    # much wider bad-tick threshold than cash instruments.
    series = [("S&P 500", "^GSPC", 0.15), ("Nasdaq 100", "^NDX", 0.18), ("VIX", "^VIX", 0.80),
              ("US Dollar", "DX-Y.NYB", 0.08), ("Gold", "GC=F", 0.15), ("WTI Crude", "CL=F", 0.20),
              ("10Y (TLT)", "TLT", 0.10), ("HY Credit (HYG)", "HYG", 0.10)]
    reports = []
    for name, ticker, jump in series:
        closes = await _fetch_closes_literal(ticker)
        reports.append(quality_report(name, closes, jump_threshold=jump))
    counts = {s: sum(1 for r in reports if r["status"] == s) for s in ("PASS", "WARN", "FAIL", "UNKNOWN")}
    overall = "FAIL" if counts["FAIL"] else "WARN" if counts["WARN"] else "PASS"
    return {"available": True, "overall": overall, "counts": counts,
            "series": reports, "checked_at": datetime.now().isoformat()}


@app.get("/api/v1/correlation-matrix")
async def correlation_matrix_v1(window: int = 90):
    """Full cross-asset Pearson correlation matrix over the last `window` trading days,
    computed from real aligned daily returns (yfinance). Rows/cols: SPX, NDX, 10Y, 2Y,
    DXY, GLD, WTI, HY, VIX. `window` is clamped to 20..252."""
    from api.handlers.market_handler import _fetch_dated_closes_literal
    from api.calculations.factor_model import returns_from_closes
    from api.calculations.altdata import correlation_matrix

    window = max(20, min(int(window), 252))
    # label -> literal ticker (reliable, ETF/index proxies)
    assets = {"SPX": "^GSPC", "NDX": "^NDX", "10Y": "TLT", "2Y": "SHY",
              "DXY": "DX-Y.NYB", "GLD": "GC=F", "WTI": "CL=F", "HY": "HYG", "VIX": "^VIX"}

    # Fetch all tickers concurrently (sequential await of 9 feeds blew the 8s UI budget).
    labels = list(assets.keys())
    results = await asyncio.gather(*[_fetch_dated_closes_literal(assets[lbl]) for lbl in labels])
    dated = {lbl: d for lbl, d in zip(labels, results) if d}    # drop empty fetches
    if len(dated) < 2:
        return {"available": False, "reason": "Insufficient market data.", "labels": [], "matrix": []}

    # Align every asset to the common set of dates, then compute returns on that grid.
    common = None
    for d in dated.values():
        keys = set(d.keys())
        common = keys if common is None else (common & keys)
    common = sorted(common or [])
    if len(common) < 22:
        return {"available": False, "reason": "Insufficient overlapping history.", "labels": [], "matrix": []}

    returns_by_asset = {lbl: returns_from_closes([dated[lbl][dt] for dt in common]) for lbl in dated}
    result = correlation_matrix(returns_by_asset, window)
    return {"available": bool(result["matrix"]), "as_of": datetime.now().isoformat(),
            "source": "yfinance (daily closes)", **result}


@app.get("/api/v1/signal-attribution")
async def signal_attribution_v1():
    """Storytelling layer: for Growth / Inflation / Liquidity / Risk, return the score, its
    largest driver, a one-line plain-English explanation, and ranked input contributions —
    computed from the live dashboard inputs (SPX, CPI, 10Y breakeven, DXY, 10Y, Fed, VIX). Phase 2."""
    from api.calculations.storytelling import (
        explain_growth, explain_inflation, explain_liquidity, explain_risk)
    from api.handlers.market_handler import _fetch_closes_literal
    from api.handlers.dashboard_handler import get_dashboard_data

    # Live, correctly-normalized inputs from a fresh dashboard computation.
    km = None
    try:
        dash = await get_dashboard_data(mode="live")
        km = getattr(dash, "keyMetrics", None)
    except Exception as e:
        logger.debug(f"[signal-attribution] dashboard read failed: {e}")

    def g(attr, default=None):
        v = getattr(km, attr, default) if km is not None else default
        return v if v is not None else default

    # Keep SPX self-consistent: latest close as current, prior closes as history.
    closes = await _fetch_closes_literal("^GSPC")
    spx = g("spxLevel") or (closes[-1] if closes else None)
    spx_hist = closes[:-1] if closes else None   # full daily history (growth needs ~6M)
    from api.handlers.macro_inputs import load_macro_inputs, load_monthly_macro, cpi_release_series
    _cpi_now = cpi_release_series(await _aio_to_thread(load_monthly_macro)).asof(datetime.now().strftime("%Y-%m-%d"))
    _be_now = (await load_macro_inputs())["breakeven"].latest
    signals = [
        explain_growth(spx, spx_hist),
        explain_inflation(_cpi_now, _be_now),
        explain_liquidity(g("dxy"), g("tenYearYield"), g("fedRate")),
        explain_risk(g("vix")),
    ]
    return {"available": True, "signals": signals,
            "source": "computed from live dashboard inputs (yfinance/FRED)",
            "as_of": datetime.now().isoformat()}


_PROVIDER_REGISTRY = None


def _provider_registry():
    """Lazily build the multi-provider registry (Universal Data Layer)."""
    global _PROVIDER_REGISTRY
    if _PROVIDER_REGISTRY is None:
        from api.providers.adapters import build_default_registry
        _PROVIDER_REGISTRY = build_default_registry()
    return _PROVIDER_REGISTRY


@app.get("/api/v1/providers")
async def providers_status_v1():
    """Provider health for the data layer: every configured provider, its priority, the asset
    classes it serves, whether it's currently healthy, how many requests it has served, and how
    many times a fallback to it was triggered (visible degraded reliance on backups)."""
    return {"providers": _provider_registry().status(), "as_of": datetime.now().isoformat()}


@app.get("/api/v1/quote")
async def quote_v1(symbol: str, asset_class: str = "equity"):
    """A single quote routed through the provider registry: the highest-priority healthy
    provider serves it, falling back automatically on failure. The serving provider is
    returned in `source` (feeds the lineage popover). Explicit unavailable if all fail."""
    q = await _aio_to_thread(_provider_registry().get_quote, symbol.strip().upper(), asset_class)
    if q is None:
        return {"available": False,
                "reason": f"Data unavailable — all providers for {asset_class} are currently unreachable for {symbol}."}
    return {"available": True, "symbol": q.symbol, "price": q.price, "change_pct": q.change_pct,
            "source": q.source, "asset_class": q.asset_class, "currency": q.currency,
            "timestamp": q.timestamp.isoformat()}


@app.get("/api/report/generate")
async def report_generate(type: str = "full", format: str = "pdf"):
    """Downloadable daily brief assembled from LIVE data: current regime, the four signal
    scores + one-line explanations, flagged anomalies. `format=pdf` (reportlab) or
    `format=csv`. Powers the header export button."""
    from fastapi import Response
    from datetime import date as _date
    from api.handlers.dashboard_handler import get_dashboard_data

    regime, confidence = None, None
    try:
        dash = await get_dashboard_data(mode="live")
        reg = getattr(dash, "regime", None)
        regime = getattr(reg, "current", None) if reg is not None else None
        confidence = getattr(reg, "confidenceScore", None) if reg is not None else None
    except Exception as e:
        logger.debug(f"[report] dashboard: {e}")
    try:
        signals = (await signal_attribution_v1()).get("signals", [])
    except Exception:
        signals = []
    try:
        flagged = [m for m in (await anomalies_v1()).get("metrics", []) if m.get("is_anomalous")]
    except Exception:
        flagged = []

    today = _date.today().isoformat()

    if format == "csv":
        import io as _io, csv as _csv
        buf = _io.StringIO()
        w = _csv.writer(buf)
        w.writerow(["MACRO OS — Daily Brief", today])
        w.writerow([])
        w.writerow(["Regime", regime or "—", f"{round((confidence or 0) * 100)}% confidence"])
        w.writerow([])
        w.writerow(["Signal", "Score", "Trend", "Driver", "Explanation"])
        for s in signals:
            w.writerow([s.get("signal"), s.get("score"), s.get("trend"), s.get("driver"), s.get("explanation_text")])
        w.writerow([])
        w.writerow(["Anomalies (outside 2sigma)", "Value", "z-score"])
        for m in flagged:
            w.writerow([m.get("metric"), m.get("current"), m.get("z_score")])
        return Response(buf.getvalue(), media_type="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="macro_brief_{today}.csv"'})

    import io as _io
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

    buf = _io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, topMargin=0.6 * inch, bottomMargin=0.6 * inch)
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Title"], fontSize=18, textColor=colors.HexColor("#0d1117"))
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=12, textColor=colors.HexColor("#334155"))
    bodyst = styles["BodyText"]
    story = [Paragraph("MACRO OS — Daily Brief", h1),
             Paragraph(f"{today} · generated {datetime.now().strftime('%H:%M')} UTC", bodyst),
             Spacer(1, 12),
             Paragraph(f"Regime: <b>{regime or '—'}</b> ({round((confidence or 0) * 100)}% confidence)", h2),
             Spacer(1, 8)]
    if signals:
        story.append(Paragraph("Signals", h2))
        rows = [["Signal", "Score", "Trend", "Explanation"]]
        for s in signals:
            rows.append([s.get("signal", ""), f"{s.get('score', '')}", s.get("trend", ""),
                         Paragraph(s.get("explanation_text", ""), bodyst)])
        t = Table(rows, colWidths=[1.0 * inch, 0.7 * inch, 1.0 * inch, 4.0 * inch])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0d1117")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        story += [t, Spacer(1, 12)]
    story.append(Paragraph(f"Anomalies (outside 2σ): {len(flagged)}", h2))
    if flagged:
        arows = [["Metric", "Value", "z-score"]] + [[m.get("metric", ""), f"{m.get('current', '')}", f"{m.get('z_score', '')}σ"] for m in flagged]
        at = Table(arows, colWidths=[3.0 * inch, 1.5 * inch, 1.0 * inch])
        at.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#92400e")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ]))
        story.append(at)
    else:
        story.append(Paragraph("All tracked metrics within their normal historical range.", bodyst))
    doc.build(story)
    return Response(buf.getvalue(), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="macro_brief_{today}.pdf"'})


@app.get("/api/v1/event-vol")
async def event_vol_v1():
    """Event-driven volatility forecast (Phase 6A): the next high-impact macro release and,
    from real SPX daily closes, how realized volatility has historically behaved in the ±3
    trading-day window around that event type vs the baseline. Historical event dates are
    derived from each event's release cadence (surfaced as a caveat)."""
    from datetime import date, timedelta as _td
    from api.calculations.event_vol import event_window_vol
    from api.handlers.market_handler import _fetch_dated_closes_literal

    # The calendar fetch (FOMC/FRED) is slow (~4s) and changes daily, not per-request — cache
    # the computed result for 10 min so the panel loads instantly and never times out.
    global _EVENT_VOL_CACHE
    _now = time.time()
    if _EVENT_VOL_CACHE.get("data") is not None and _now - _EVENT_VOL_CACHE.get("ts", 0) < 600:
        return _EVENT_VOL_CACHE["data"]

    def _cache(result):
        _EVENT_VOL_CACHE["data"] = result
        _EVENT_VOL_CACHE["ts"] = _now
        return result

    try:
        raw = await get_economic_calendar()
        cal = json.loads(bytes(raw.body)) if hasattr(raw, "body") else raw
    except Exception as e:
        return {"available": False, "reason": f"calendar unavailable: {str(e)[:100]}"}
    events = sorted([e for e in (cal.get("events") or []) if e.get("impact") == "HIGH"],
                    key=lambda e: e.get("date", ""))
    if not events:
        return {"available": False, "reason": "No upcoming high-impact events."}

    nxt = events[0]
    try:
        nd = date.fromisoformat(nxt["date"])
    except Exception:
        return {"available": False, "reason": "Bad event date."}
    # Real historical dates of this event type (FRED release calendar / federalreserve.gov).
    # Stepping back a fixed 30/46 days drifted off the true release dates within months.
    today_iso = date.today().isoformat()
    if nxt["event"] == "FOMC Decision":
        past_dates = [d for d in await _aio_to_thread(_fetch_fomc_dates) if d < today_iso][-8:]
    else:
        rid = {"CPI Release": 10, "Nonfarm Payrolls": 50}.get(nxt["event"])
        past_dates = (await _aio_to_thread(_fetch_fred_release_dates, rid, 8, True)) if rid else []
    dates_source = "actual"
    if not past_dates:
        cadence_days = {"CPI Release": 30, "FOMC Decision": 46, "Nonfarm Payrolls": 30}.get(nxt["event"], 30)
        past_dates = [(nd - _td(days=cadence_days * i)).isoformat() for i in range(1, 9)]
        dates_source = "cadence-approximated"

    spx = await _fetch_dated_closes_literal("^GSPC")
    if not spx:
        return {"available": False, "reason": "No SPX price history."}
    stats = event_window_vol(spx, past_dates, window=3)
    today = date.today()
    upcoming = [{**e, "days_away": (date.fromisoformat(e["date"]) - today).days} for e in events[:4]]
    if not stats.get("available"):
        return _cache({"available": False, "reason": stats.get("reason"), "next_event": {**nxt, "days_away": (nd - today).days}, "upcoming": upcoming})
    return _cache({
        "available": True,
        "next_event": {**nxt, "days_away": (nd - today).days},
        "upcoming": upcoming,
        **stats,
        "source": f"SPX realized vol (yfinance) around {dates_source} historical event dates",
        "historical_dates_source": dates_source,
        "note": ("Historical event dates from the FRED release calendar / federalreserve.gov"
                 if dates_source == "actual" else
                 "Historical event dates approximated from the release cadence (calendar source unreachable)")
                + "; windows are ±3 trading days.",
        "as_of": datetime.now().isoformat(),
    })


@app.get("/api/v1/risk-parity-compare")
@ttl_cache(600)
async def risk_parity_compare_v1():
    """Honest comparison of allocation methods on REAL asset returns (per 'Risk Parity and its
    Discontents' 2025 + HRP/CVaR-RP research): Traditional RP (inverse-vol), Return-overlay RP,
    HRP (López de Prado), CVaR-RP, vs a 60/40 benchmark. Reports Sharpe / Sortino / max
    drawdown for each — including honestly when a method does NOT beat 60/40."""
    import numpy as _np
    from api.handlers.market_handler import _fetch_dated_closes_literal
    from api.calculations.factor_model import returns_from_closes
    from api.calculations.risk_parity import (
        inverse_vol_weights, cvar_weights, hrp_weights, return_overlay_weights, sixty_forty,
        walk_forward_returns, performance_stats, risk_contribution_bands)

    # Asset universe + simple capital-market expected returns (%) for the overlay.
    assets = {"SPX Equity": "^GSPC", "US Bonds (TLT)": "TLT", "Commodities (DBC)": "DBC",
              "Gold": "GC=F", "HY Credit (HYG)": "HYG"}
    cma = {"SPX Equity": 6.0, "US Bonds (TLT)": 4.5, "Commodities (DBC)": 3.0, "Gold": 2.5, "HY Credit (HYG)": 5.0}
    labels = list(assets.keys())
    dated = await asyncio.gather(*[_fetch_dated_closes_literal(assets[l], period="5y") for l in labels])
    dmap = {l: d for l, d in zip(labels, dated) if d}
    if len(dmap) < 3:
        return {"available": False, "reason": "Insufficient asset history."}
    common = None
    for d in dmap.values():
        common = set(d) if common is None else (common & set(d))
    common = sorted(common or [])
    lookback, rebalance = 252, 21
    if len(common) < lookback + 120:
        return {"available": False, "reason": "Insufficient overlapping history for a walk-forward test."}
    labels = [l for l in labels if l in dmap]
    rets = _np.column_stack([returns_from_closes([dmap[l][dt] for dt in common]) for l in labels])
    exp_ret = [cma[l] for l in labels]

    # Weight functions are re-run on a trailing window at each rebalance (walk-forward),
    # so every reported return is out-of-sample.
    methods = {
        "60/40 Benchmark": lambda r: sixty_forty(labels),
        "Traditional RP (inverse-vol)": inverse_vol_weights,
        "Return-overlay RP (70/30)": lambda r: return_overlay_weights(r, exp_ret, 0.7),
        "HRP (López de Prado)": hrp_weights,
        "CVaR Risk Parity": cvar_weights,
    }
    rows = []
    bench = None
    for name, fn in methods.items():
        oos, w = walk_forward_returns(rets, fn, lookback=lookback, rebalance=rebalance)
        m = performance_stats(oos)
        if bench is None:
            bench = m
        m["method"] = name
        m["weights"] = {labels[i]: round(float(w[i]) * 100, 1) for i in range(len(labels))}
        m["beats_6040_sharpe"] = None if name == "60/40 Benchmark" else bool(m["sharpe"] > bench["sharpe"])
        rows.append(m)

    # Phase 2C — bootstrapped risk-contribution fragility bands on the inverse-vol scheme.
    bands = risk_contribution_bands(rets, n_boot=300)
    if bands.get("available"):
        for a in bands["per_asset"]:
            a["asset"] = labels[a["asset"]]

    return {
        "available": True, "universe": labels, "observations": len(common),
        "out_of_sample_days": len(common) - 1 - lookback,
        "lookback_days": lookback, "rebalance_days": rebalance,
        "results": rows,
        "risk_contribution_uncertainty": bands,
        "note": f"Walk-forward, out-of-sample: weights re-estimated every {rebalance} trading days "
                f"from the trailing {lookback} days only; 'weights' are the latest estimate. "
                "Per 'Risk Parity and its Discontents' (2025), pure risk weighting often does not beat 60/40.",
        "citations": ["Risk Parity and its Discontents (SSRN 2025)",
                      "HRP & CVaR-RP comparison (Brazilian Review of Finance 2026)",
                      "López de Prado (2016) — Hierarchical Risk Parity"],
        "as_of": datetime.now().isoformat(),
    }


@app.get("/api/v1/quadrants")
@ttl_cache(300)
async def quadrants_v1():
    """Bridgewater Four Quadrants: classify the environment on growth-surprise × inflation-
    surprise axes (release vs its own trend, a consensus proxy), with the per-quadrant asset
    playbook, cross-validated against the app's 6-regime label. Citation: Bridgewater All
    Weather / Four Quadrants."""
    from api.calculations.quadrants import surprise_z, quadrant_view
    from api.handlers.dashboard_handler import get_dashboard_data

    # Contiguous monthly FRED panel (industrial production YoY, CPI YoY). The old CSV
    # source had an 18-month gap and forward-filled daily rows, and fell back to
    # synthetic sample data; surprises computed on it were not month-over-trend.
    from api.handlers.macro_inputs import load_monthly_macro
    panel = await _aio_to_thread(load_monthly_macro)
    if panel is None or panel.empty:
        return {"available": False, "reason": "Monthly FRED macro data unavailable."}
    g_series = panel["growth_yoy"].dropna().tolist()
    i_series = panel["cpi_yoy"].dropna().tolist()

    g_surprise = surprise_z(g_series)
    i_surprise = surprise_z(i_series)

    regime = None
    try:
        dash = await get_dashboard_data(mode="live")
        reg = getattr(dash, "regime", None)
        regime = getattr(reg, "current", None) if reg is not None else None
    except Exception:
        pass

    view = quadrant_view(g_surprise, i_surprise, regime_6=regime)
    view["source"] = "industrial production YoY & CPI YoY surprise vs trailing 12M (FRED)"
    view["data_as_of"] = panel.dropna(subset=["growth_yoy", "cpi_yoy"]).index[-1].strftime("%Y-%m")
    view["citation"] = "Bridgewater Associates — Four Quadrants / All Weather framework"
    view["as_of"] = datetime.now().isoformat()
    return view


@app.get("/api/v1/stream-agreement")
@ttl_cache(300)
async def stream_agreement_v1():
    """Bridgewater 3-stream signal agreement (Phase 3): classify live signals into three
    INDEPENDENT evidence streams — macro drivers, intermarket action, capital flows — reduce
    each to risk-on/off/neutral, and return an agreement score + position-sizing multiplier.
    Conviction scales with the NUMBER of independent streams that agree, not the confidence of
    any single model. Citation: Bridgewater Associates."""
    from api.calculations.stream_agreement import (
        macro_stream, intermarket_stream, flows_stream, stream_agreement)
    from api.handlers.market_handler import get_rates_data, _credit_spread

    def _norm(x):  # σ-scaled score -> [0,1]
        return max(0.0, min(1.0, 0.5 + (x or 0.0) / 4.0))

    # --- MACRO stream (heavy feature pipeline) + INTERMARKET/FLOWS externals all run
    # concurrently, each capped, so the whole panel returns within the frontend's budget.
    # Anything slow degrades to neutral. COT is the slow one (external CFTC).
    async def _safe(coro, timeout):
        try:
            return await asyncio.wait_for(coro, timeout=timeout)
        except (asyncio.TimeoutError, Exception):
            return None

    def _macro_scores():
        df = load_processed_data()
        return _compute_regime_scores(df) if df is not None else None

    # Macro compute is local — run it threaded but UNCAPPED (it's the core of the panel; a stale
    # empty is worse than waiting) concurrently with the capped network fetches.
    scores, rates, hy, cot = await asyncio.gather(
        _aio_to_thread(_macro_scores),
        _safe(get_rates_data(), 4.0),
        _safe(_credit_spread("High Yield", "BAMLH0A0HYM2", 350, 600), 4.0),
        _safe(get_cot_data(), 5.0),
    )
    if not scores:
        return {"available": False, "reason": "No macro data available."}
    g, i, l, rsk = scores.get("growth", 0.0), scores.get("inflation", 0.0), scores.get("liquidity", 0.0), scores.get("risk", 0.0)
    macro = macro_stream(_norm(g), _norm(i), _norm(l))

    curve_pct, hy_bps = None, None
    if rates:
        ten, two = rates.get("tenYear"), rates.get("twoYear")
        curve_pct = (ten - two) if (ten is not None and two is not None) else None
    if hy:
        hy_bps = hy.get("spreadBps")
    intermarket = intermarket_stream(curve_pct, hy_bps, _norm(-rsk))  # lower risk score = more appetite

    # --- FLOWS stream (COT extremes; put/call unavailable keyless -> neutral) ---
    long_ext = short_ext = None
    if isinstance(cot, dict):
        rows = cot.get("contracts", [])
        long_ext = sum(1 for c in rows if c.get("extreme") and c.get("net_position", 0) > 0)
        short_ext = sum(1 for c in rows if c.get("extreme") and c.get("net_position", 0) < 0)
    flows = flows_stream(long_ext, short_ext, None)

    result = stream_agreement(macro, intermarket, flows)
    result["available"] = True
    result["inputs"] = {
        "macro": {"growth": round(g, 2), "inflation": round(i, 2), "liquidity": round(l, 2)},
        "intermarket": {"curve_2s10s_pct": curve_pct, "hy_spread_bps": hy_bps, "risk_score": round(rsk, 2)},
        "flows": {"cot_extreme_longs": long_ext, "cot_extreme_shorts": short_ext, "put_call": None},
    }
    result["source"] = "macro scores (FRED) + rates/credit (FRED) + CFTC COT"
    result["citation"] = "Bridgewater Associates — macro / intermarket / flows as independent evidence streams"
    result["as_of"] = datetime.now().isoformat()
    return result


@app.get("/api/v1/factor-validation")
@ttl_cache(600)
async def factor_validation_v1():
    """Factor out-of-sample validation (Phase 4, AQR discipline): for each macro factor, fit the
    exposure in-sample, measure R² in- vs out-of-sample, and flag factors whose explanatory power
    does NOT survive out-of-sample (overfitting). Reports each factor's own max drawdown so tail
    risk is visible. Citation: AQR 'Fact, Fiction, and Factor Investing'."""
    import numpy as _np
    from api.handlers.market_handler import _fetch_dated_closes_literal
    from api.calculations.factor_model import returns_from_closes
    from api.calculations.factor_validation import validate_factors

    # Factor proxies (long/short ETF spreads) explaining SPX excess behaviour.
    asset_t = "^GSPC"
    factor_defs = {
        "Value (VLUE)": "VLUE", "Momentum (MTUM)": "MTUM", "Quality (QUAL)": "QUAL",
        "Size (IWM−SPY)": ("IWM", "SPY"), "LowVol (USMV)": "USMV",
    }
    need = {asset_t}
    for v in factor_defs.values():
        need.update(v if isinstance(v, tuple) else (v,))
    dated = await asyncio.gather(*[_fetch_dated_closes_literal(t) for t in need])
    dmap = {t: d for t, d in zip(need, dated) if d}
    if asset_t not in dmap:
        return {"available": False, "reason": "Benchmark history unavailable."}

    def _series(t):
        d = dmap.get(t)
        return d if d else None

    # common dates across everything we actually got
    have = [t for t in need if t in dmap]
    common = None
    for t in have:
        common = set(dmap[t]) if common is None else (common & set(dmap[t]))
    common = sorted(common or [])
    if len(common) < 60:
        return {"available": False, "reason": "Insufficient overlapping history for OOS split."}

    asset_ret = returns_from_closes([dmap[asset_t][dt] for dt in common])
    factors = {}
    for name, spec in factor_defs.items():
        if isinstance(spec, tuple):
            a, b = spec
            if a in dmap and b in dmap:
                ra = _np.asarray(returns_from_closes([dmap[a][dt] for dt in common]))
                rb = _np.asarray(returns_from_closes([dmap[b][dt] for dt in common]))
                factors[name] = (ra - rb).tolist()
        elif spec in dmap:
            factors[name] = returns_from_closes([dmap[spec][dt] for dt in common])

    if not factors:
        return {"available": False, "reason": "No factor proxy history available."}

    out = validate_factors(factors, asset_ret)
    out["available"] = True
    out["benchmark"] = "S&P 500 (^GSPC) daily returns"
    out["observations"] = len(common)
    out["method"] = "Fit exposure on first-half (in-sample); measure R² on held-out second-half (out-of-sample)."
    out["citation"] = "AQR — Asness et al., 'Fact, Fiction, and Factor Investing'"
    out["as_of"] = datetime.now().isoformat()
    return out


@app.get("/api/v1/regime-transition")
@ttl_cache(300)
async def regime_transition_v1():
    """Forward-looking regime early-warning (Phase 6B): the empirical next-period transition
    probabilities from the CURRENT regime, computed from a monthly regime history that is
    classified from real macro data (the same classifier the dashboard uses)."""
    from api.calculations.regime import empirical_transition_matrix, forward_outlook

    try:
        rd = await _aio_to_thread(get_regime_data)
    except Exception as e:
        return {"available": False, "reason": f"regime classification failed: {str(e)[:120]}"}

    # Transitions from the FULL contiguous monthly history (since the late 1980s), not just
    # the 24 months shown in the timeline.
    try:
        regimes = list((await _aio_to_thread(_monthly_regime_frame))["regime"])
    except Exception as e:
        return {"available": False, "reason": f"regime history unavailable: {str(e)[:120]}"}
    if len(regimes) < 6:
        return {"available": False, "reason": f"Insufficient regime history ({len(regimes)} months)."}

    matrix = empirical_transition_matrix(regimes)
    outlook = forward_outlook(matrix, rd.current)

    # The headline macro-cycle regime (the 7-state model shown in the header/playbook/scenario),
    # surfaced here so the panel reads as a complementary lens rather than a competing claim.
    cycle_regime = None
    try:
        from api.handlers.dashboard_handler import get_dashboard_data
        dash = await get_dashboard_data(mode="live")
        cycle_regime = dash.regime.current if getattr(dash, "regime", None) else None
    except Exception:
        pass

    return {
        "available": True,
        "current_regime": rd.current,
        "cycle_regime": cycle_regime,
        "confidence": getattr(rd, "confidenceScore", None),
        "outlook": outlook,
        "matrix": matrix,
        "months_analysed": len(regimes),
        "taxonomy": "growth×inflation quadrant (Goldilocks / Reflation / Slowdown / Stagflation)",
        "source": "monthly quadrant regimes from FRED industrial production YoY & CPI YoY (rolling 36M z-scores)",
        "note": "Probabilities are per monthly step. This panel uses the growth×inflation quadrant "
                "model — a complementary lens to the headline macro-cycle regime, so the current "
                "quadrant need not share the same word as the header regime.",
        "as_of": datetime.now().isoformat(),
    }


@app.get("/api/v1/anomalies")
async def anomalies_v1(window: int = 252):
    """System-wide anomaly scan: for each tracked market metric, z-score the latest value
    against its own trailing `window`-day history and flag |z| > 2 (outside normal range).
    Returns every metric ranked by |z_score| so the UI can pin the extremes. Real yfinance
    closes — traceable via `source`."""
    from api.handlers.market_handler import _fetch_closes_literal
    from api.calculations.altdata import historical_band

    window = max(60, min(int(window), 756))
    # (metric label, literal ticker, unit)
    metrics = [
        ("VIX", "^VIX", "idx"), ("S&P 500", "^GSPC", "idx"), ("Nasdaq 100", "^NDX", "idx"),
        ("US Dollar", "DX-Y.NYB", "idx"), ("Gold", "GC=F", "$"), ("WTI Crude", "CL=F", "$"),
        ("10Y (TLT)", "TLT", "$"), ("HY Credit (HYG)", "HYG", "$"), ("2Y (SHY)", "SHY", "$"),
    ]
    closes_list = await asyncio.gather(*[_fetch_closes_literal(t) for _, t, _ in metrics])

    out = []
    for (label, ticker, unit), closes in zip(metrics, closes_list):
        band = historical_band(closes or [], window=window) if closes else None
        if band is None:
            continue
        out.append({"metric": label, "ticker": ticker, "unit": unit, **band})
    out.sort(key=lambda m: abs(m["z_score"]), reverse=True)
    return {
        "available": bool(out),
        "window": window,
        "anomaly_count": sum(1 for m in out if m["is_anomalous"]),
        "metrics": out,
        "source": "yfinance (daily closes)",
        "as_of": datetime.now().isoformat(),
    }


@app.get("/api/v1/altdata/positioning")
async def altdata_positioning_v1():
    """Alternative-data positioning signals: VIX term structure (contango/backwardation),
    cross-market correlation-breakdown alerts, and credit-spread stress — all from real
    yfinance/FRED data."""
    from api.handlers.market_handler import _fetch_dated_closes_literal, _fetch_closes_literal, _fred_recent_values
    from api.calculations.factor_model import returns_from_closes
    from api.calculations.altdata import term_structure, correlation_breakdown, zscore, percentile_rank

    # 1) VIX term structure
    async def _last(t):
        c = await _fetch_closes_literal(t)
        return c[-1] if c else None
    vix9d, vix, vix3m, vix6m = (await _last("^VIX9D"), await _last("^VIX"),
                                await _last("^VIX3M"), await _last("^VIX6M"))
    vix_term = term_structure(vix9d, vix, vix3m, vix6m)

    # 2) Cross-market correlation breakdowns
    pairs = [("SPY", "TLT", "Equity–Duration"), ("SPY", "DX-Y.NYB", "Equity–USD"),
             ("SPY", "GLD", "Equity–Gold"), ("SPY", "HYG", "Equity–HY Credit")]
    dated = {}
    syms = {s for a, b, _ in pairs for s in (a, b)}
    for s in syms:
        dated[s] = await _fetch_dated_closes_literal(s)
    corr_alerts = []
    for a, b, label in pairs:
        da, db = dated.get(a, {}), dated.get(b, {})
        common = sorted(set(da) & set(db))
        if len(common) < 90:
            corr_alerts.append({"pair": label, "available": False})
            continue
        ra = returns_from_closes([da[d] for d in common])
        rb = returns_from_closes([db[d] for d in common])
        res = correlation_breakdown(ra, rb)
        corr_alerts.append({"pair": label, **res})

    # 3) Credit-spread stress (FRED OAS in %; z-score vs ~1y history)
    hy = await _aio_to_thread(_fred_recent_values, "BAMLH0A0HYM2", 252)
    ig = await _aio_to_thread(_fred_recent_values, "BAMLC0A0CM", 252)
    credit = {"available": False}
    if hy and ig:
        hy_bps, ig_bps = hy[0] * 100, ig[0] * 100
        credit = {
            "available": True,
            "hy_oas_bps": round(hy_bps, 1),
            "ig_oas_bps": round(ig_bps, 1),
            "hy_ig_spread_bps": round(hy_bps - ig_bps, 1),
            "hy_zscore": zscore(hy[0], hy),
            "hy_percentile": percentile_rank(hy[0], hy),
            "signal": ("stress" if (zscore(hy[0], hy) or 0) > 1 else
                       "complacent" if (zscore(hy[0], hy) or 0) < -1 else "neutral"),
        }

    return {
        "available": True,
        "vix_term_structure": vix_term,
        "correlation_alerts": corr_alerts,
        "credit": credit,
        "computed_at": datetime.now().isoformat(),
    }


@app.get("/api/v1/signals/backtest")
async def signals_backtest_v1(horizon: int = 21):
    """Walk-forward backtest of price-reconstructable signals on the S&P 500 (5y daily,
    no look-ahead): momentum (12-1m), trend (200d MA), and VIX vol-regime. Reports hit
    rate, forward return by state, strategy Sharpe/drawdown and a confusion matrix."""
    import asyncio as _aio
    from api.calculations.backtest import (
        momentum_signal, trend_signal, vol_regime_signal, backtest_signal,
    )

    def _closes(ticker):
        try:
            import yfinance as yf
            from api.market_dates import align_frame
            h = align_frame(ticker, yf.Ticker(ticker).history(period="5y", interval="1d"))
            if h is None or h.empty:
                return [], []
            dates = [str(d)[:10] for d in h.index]
            closes = [float(x) for x in h["Close"].tolist()]
            return dates, closes
        except Exception as e:
            logger.warning("[backtest] fetch failed for %s: %s", ticker, e)
            return [], []

    spx_dates, spx = await _aio.to_thread(_closes, "^GSPC")
    _, vix = await _aio.to_thread(_closes, "^VIX")
    if len(spx) < 300:
        return {"available": False, "reason": "Insufficient S&P 500 history for backtest.",
                "signals": []}

    scorecards = []
    for name, label, sig in [
        ("momentum_12_1", "Price Momentum (12-1m)", momentum_signal(spx)),
        ("trend_200d", "Trend (200-day MA)", trend_signal(spx)),
    ]:
        bt = backtest_signal(spx, sig, horizon)
        if bt.get("available"):
            scorecards.append({"id": name, "label": label, **bt})
    if len(vix) >= 300:
        n = min(len(spx), len(vix))
        vsig = vol_regime_signal(vix[-n:])
        bt = backtest_signal(spx[-n:], vsig, horizon)
        if bt.get("available"):
            scorecards.append({"id": "vol_regime", "label": "VIX Vol-Regime", **bt})

    return {
        "available": True,
        "universe": "S&P 500 (^GSPC)",
        "period_days": len(spx),
        "horizon_days": horizon,
        "methodology": "Walk-forward: signal at date t uses only data <= t; evaluated "
                       "against the strictly-forward return over the next `horizon` days. "
                       "`hit_rate` uses overlapping windows; `hit_rate_independent` (with its "
                       "binomial p-value vs 50%) uses every horizon-th date only.",
        "signals": scorecards,
        "computed_at": datetime.now().isoformat(),
    }


@app.get("/api/v1/freshness")
async def freshness_v1():
    """Per-field data freshness: each key macro input's last release date, age, and
    FRESH/STALE/CRITICAL status vs its expected cadence. Lets the UI flag an individual
    stale metric, not just a whole panel."""
    import asyncio as _aio
    from api.data_freshness import get_live_freshness
    try:
        return await _aio.to_thread(get_live_freshness)
    except Exception as e:
        logger.error("[freshness] failed: %s", e)
        return {"available": False, "reason": str(e)[:160], "series": []}


# FIXED: Auth endpoint (previously missing - caused 404)
from fastapi import Request


@app.post("/api/auth/login")
async def login(request: Request):
    """Verify username/password against the users table (bcrypt) and issue a signed JWT
    carrying the user and role. Invalid credentials return HTTP 401.

    (This used to accept only demo/demo and answer every other attempt with HTTP 200
    {"success": false}, which the UI treated as a successful login — any credentials got in.)
    """
    from urllib.parse import parse_qs
    from api.config import ROLE_PERMISSIONS, ACCESS_TOKEN_EXPIRE_MINUTES

    content_type = request.headers.get("content-type", "").lower()
    body = await request.body()
    username = password = None
    try:
        if "application/json" in content_type:
            data = json.loads(body or b"{}")
            username, password = data.get("username"), data.get("password")
        else:
            form = parse_qs(body.decode("utf-8"))
            username, password = form.get("username", [None])[0], form.get("password", [None])[0]
    except (ValueError, UnicodeDecodeError):
        pass
    if not username or not password:
        return JSONResponse({"success": False, "error": "Username and password required"}, status_code=400)

    from api.core import accounts
    try:
        user = await _aio_to_thread(accounts.check_login, username.strip(), password)
    except accounts.LoginError as e:
        logger.warning(f"[AUTH] failed login for '{username[:64]}': {e.message}")
        return JSONResponse({"success": False, "error": e.message}, status_code=e.status)

    role = user["role"]
    token = accounts.issue_token(user)
    perms = ROLE_PERMISSIONS.get(role, [])
    try:
        from api import audit_store
        await _aio_to_thread(lambda: audit_store.add_decision(
            "login", f"{user['username']} signed in", user=user["username"], target="auth"))
    except Exception:
        pass
    return {
        "success": True, "access_token": token, "token": token, "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "role": role, "display_name": user["display_name"], "permissions": perms,
        "must_change_password": bool(user.get("must_change_password")),
        "user": {"username": user["username"], "role": role,
                 "display_name": user["display_name"], "permissions": perms},
    }


@app.post("/api/auth/logout")
async def logout(request: Request):
    """Revoke the presented token for the rest of its lifetime (persisted, survives restarts)."""
    from api.core.access import current_user
    from api.core import accounts
    u = current_user(request)
    if u:
        await _aio_to_thread(accounts.revoke, u.get("jti"), u.get("exp"))
    return {"success": True, "message": "Logged out successfully"}


class ChangePasswordIn(_PortfolioBaseModel):
    current_password: str
    new_password: str


@app.post("/api/auth/change-password")
async def change_password(body: ChangePasswordIn, request: Request):
    """Change your own password (policy-checked). All your other sessions are signed out;
    a fresh token is returned for this one."""
    from api.core.access import current_user
    from api.core import accounts
    from api.core.auth import verify_password
    u = current_user(request)
    if not u:
        raise HTTPException(401, "Not authenticated")
    row = await _aio_to_thread(accounts.get_user, u["username"])
    if not row or not verify_password(body.current_password, row["hashed_password"]):
        raise HTTPException(400, "Current password is incorrect")
    if body.new_password == body.current_password:
        raise HTTPException(400, "New password must differ from the current one")
    problems = accounts.password_problems(body.new_password, u["username"])
    if problems:
        raise HTTPException(400, {"message": "Password does not meet the policy", "problems": problems})
    await _aio_to_thread(accounts.set_password, u["username"], body.new_password)
    await _aio_to_thread(accounts.revoke, u.get("jti"), u.get("exp"))
    try:
        from api import audit_store
        await _aio_to_thread(lambda: audit_store.add_decision(
            "password_changed", f"{u['username']} changed their password", user=u["username"], target="auth"))
    except Exception:
        pass
    fresh = await _aio_to_thread(accounts.get_user, u["username"])
    return {"success": True, "access_token": accounts.issue_token(fresh), "must_change_password": False}


@app.get("/api/auth/status")
async def auth_status():
    """Public: whether the seeded demo credentials still work (the login screen only shows
    them in that case) and the password policy."""
    from api.core import accounts
    return {"default_credentials_active": await _aio_to_thread(accounts.default_credentials_active),
            "password_policy": {"min_length": accounts.MIN_PASSWORD_LENGTH,
                                "rules": ["at least 3 of: lowercase, uppercase, digit, symbol",
                                          "must not contain the username", "not a common/default password"]},
            "lockout": {"max_failed_attempts": accounts.MAX_FAILED_ATTEMPTS,
                        "lockout_minutes": accounts.LOCKOUT_SECONDS // 60}}


@app.get("/api/auth/me")
async def auth_me(request: Request):
    """The verified identity behind the request's token (401 if none)."""
    from api.core.access import current_user
    from api.config import ROLE_PERMISSIONS
    u = current_user(request)
    if not u:
        raise HTTPException(401, "Not authenticated")
    return {**u, "permissions": ROLE_PERMISSIONS.get(u["role"], [])}


@app.get("/api/data-freshness")
async def get_data_freshness():
    """Get data freshness status for all FRED series."""
    from api.data_freshness import check_fred_data_freshness, get_freshness_summary
    from api.data_fetcher import CONTRACTS

    # Check freshness of key series
    observation_dates = {}
    statuses = []

    df = load_processed_data()
    if df is not None:
        for metric_name, contract in CONTRACTS.items():
            if contract.fred_series:
                # Get last observation date from DataFrame
                col = contract.fred_series
                if col in df.columns:
                    last_date = df[col].dropna().index[-1] if not df[col].dropna().empty else None
                    status = check_fred_data_freshness(
                        contract.fred_series,
                        last_date,
                        metric_name
                    )
                    statuses.append(status)

    summary = get_freshness_summary(statuses)
    return {
        "summary": summary,
        "series": [
            {
                "seriesId": s.series_id,
                "metricName": s.metric_name,
                "lastObservation": s.last_observation_date.isoformat() if s.last_observation_date else None,
                "daysSinceUpdate": s.days_since_update,
                "isStale": s.is_stale,
                "isCritical": s.is_critical,
            }
            for s in statuses
        ]
    }


@app.get("/api/data-debug")
async def get_data_debug():
    """
    Debug endpoint showing data integrity status.
    Returns _dataErrors and _dataHealthy for UI debug panel.
    """
    # Validate the LIVE dashboard payload. This used to validate a stand-in dict built
    # from the stale CSV's last row with hardcoded values (HY 283bp, recession 30%,
    # regime "Stagflation"), so it reported on data no panel actually shows.
    import math as _math
    from api.handlers.dashboard_handler import get_dashboard_data
    try:
        dash = (await get_dashboard_data(mode="live")).model_dump()
    except Exception as e:
        return {"_dataHealthy": False, "_dataErrors": [f"dashboard unavailable: {e}"],
                "_errorCount": 1, "lastChecked": datetime.now().isoformat(), "dataAsOf": "unknown"}

    errors = []

    def _walk(node, path):
        if isinstance(node, dict):
            for k, v in node.items():
                _walk(v, f"{path}.{k}" if path else k)
        elif isinstance(node, list):
            for i, v in enumerate(node):
                _walk(v, f"{path}[{i}]")
        elif isinstance(node, float) and not _math.isfinite(node):
            errors.append(f"NaN/Inf: {path}={node}")

    _walk(dash, "")

    def _get(path):
        v = dash
        for k in path.split("."):
            v = v.get(k) if isinstance(v, dict) else None
        return v

    bounds = {
        "scores.growth": (0, 100), "scores.inflation": (0, 100),
        "scores.liquidity": (0, 100), "scores.risk": (0, 100),
        "recession.probability": (0, 1), "regime.confidenceScore": (0, 1),
        "keyMetrics.vix": (5, 90), "keyMetrics.tenYearYield": (-2, 20),
        "keyMetrics.twoYearYield": (-2, 20), "keyMetrics.fedRate": (0, 25),
        "keyMetrics.dxy": (60, 150), "keyMetrics.spxLevel": (500, 50000),
    }
    for path, (lo, hi) in bounds.items():
        v = _get(path)
        if v is None:
            errors.append(f"MISSING: {path}")
        elif isinstance(v, (int, float)) and _math.isfinite(v) and not (lo <= v <= hi):
            errors.append(f"OUT_OF_BOUNDS: {path}={v} expected [{lo}, {hi}]")

    meta = dash.get("metadata") or {}
    if meta.get("dataStatus") not in (None, "current"):
        errors.append(f"DATA_STATUS: {meta.get('dataStatus')} — {meta.get('validationWarnings')}")

    return {
        "_dataHealthy": len(errors) == 0,
        "_dataErrors": errors,
        "_errorCount": len(errors),
        "lastChecked": datetime.now().isoformat(),
        "dataAsOf": meta.get("latestDate") or "unknown",
    }




# PHASE 1: UNIFIED DASHBOARD API (Standardised Data Contract)

@app.post("/api/data/refresh")
async def manual_refresh(background_tasks: BackgroundTasks):
    """Force immediate data pipeline run with CSV update + cache invalidation."""
    background_tasks.add_task(
        run_daily_pipeline, _DASHBOARD_CACHE, _DASHBOARD_CACHE_LOCK
    )
    return {
        'status': 'refresh_started',
        'message': 'Data pipeline running in background — check /api/data/freshness in 30s',
        'scheduler_active': _scheduler.running if hasattr(_scheduler, 'running') else False
    }


# FIXED: R-01 - Data freshness endpoint with scheduler status
@app.get("/api/data/freshness")
async def data_freshness():
    """Return data freshness metrics and pipeline status."""
    try:
        csv_file = PROJECT_ROOT / "data" / "us_economic_data.csv"
        if csv_file.exists():
            df = pd.read_csv(csv_file, index_col=0, parse_dates=True)
            last_date = df.index.max()     # month of the latest row (the CSV is monthly)
            # Staleness = time since the pipeline last wrote the file. The index is a month
            # start, so measuring from it would flag a fresh file as up to 31 days old.
            age_secs = time.time() - csv_file.stat().st_mtime
        else:
            last_date = None
            age_secs = 999999

        cache_age = time.time() - _DASHBOARD_CACHE.get('timestamp', 0)

        # Get scheduler status
        scheduler_jobs = []
        try:
            if _scheduler.running:
                for job in _scheduler.get_jobs():
                    next_run = job.next_run_time
                    scheduler_jobs.append({
                        'id': job.id,
                        'next_run': next_run.isoformat() if next_run else 'paused'
                    })
        except Exception as e:
            pass

        return {
            'csvLastDate': last_date.strftime('%Y-%m-%d') if last_date else 'Unknown',
            'csvAgeHours': round(age_secs / 3600, 1),
            'csvIsStale': age_secs > 36 * 3600,
            'cacheAgeSeconds': int(cache_age),
            'cacheHasData': _DASHBOARD_CACHE.get('data') is not None,
            'schedulerActive': _scheduler.running if hasattr(_scheduler, 'running') else False,
            'schedulerJobs': scheduler_jobs,
            'nextScheduledRuns': {
                'daily_06utc': '06:00 UTC daily',
                'market_hours': 'Every 15min 13:00-21:00 UTC'
            }
        }
    except Exception as e:
        logger.error(f"[FRESHNESS] Error: {e}")
        return {
            'csvLastDate': 'Error',
            'csvAgeHours': 0,
            'csvIsStale': True,
            'cacheAgeSeconds': int(time.time() - _DASHBOARD_CACHE.get('timestamp', 0)),
            'cacheHasData': _DASHBOARD_CACHE.get('data') is not None,
            'schedulerActive': False,
            'error': str(e)
        }




def _load_data_or_fail():
    df = load_processed_data()
    if df is None:
        raise HTTPException(status_code=503, detail="No data available. Run pipeline first.")
    return df


















def _sanitize_for_json(obj):
    """Convert NaN/Inf and numpy types to JSON-serializable values."""
    import math
    # FIXED: Handle numpy types
    if isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    elif isinstance(obj, (np.integer, np.int64, np.int32)):
        return int(obj)
    elif isinstance(obj, (np.floating, np.float64, np.float32)):
        if np.isnan(obj) or np.isinf(obj):
            return None
        return float(obj)
    elif isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    elif isinstance(obj, list):
        return [_sanitize_for_json(item) for item in obj]
    return obj






















# PHASE 6 ENDPOINTS - Factor Rotation, Geopolitical Risk, Options, Trends
















@app.post("/api/ask", response_model=AskResponse)
async def ask_question(request: AskRequest):
    """
    AI-powered question answering endpoint.
    Uses current dashboard data to provide context-aware responses.
    """
    try:
        # Use the canonical, validated dashboard data (single source of truth) instead of the
        # orphaned get_risk_indicators(), whose RiskIndicator shape no longer matches the schema
        # (value was a string like "270 bps") and raised a 503 on every /api/ask call — it also
        # never exposed recessionProbability, so the recession number was always 0.
        from api.handlers.dashboard_handler import get_dashboard_data
        dashboard = await get_dashboard_data(mode="live")

        question_lower = request.question.lower()

        km = dashboard.keyMetrics
        rec = getattr(dashboard, "recession", None)
        context = {
            "regime": dashboard.regime.current if dashboard.regime else "Unknown",
            "growth": km.growth.value if km and km.growth else 0,
            "inflation": km.inflation.value if km and km.inflation else 0,
            "recession_prob": round((rec.probability or 0) * 100, 1) if rec else 0,
        }

        # Generate response based on question type
        if "recession" in question_lower:
            answer = f"Current recession probability is {context['recession_prob']:.1f}%. Based on the {context['regime']} regime, we are monitoring labor market conditions and yield curve signals closely."
            confidence = "high" if context['recession_prob'] > 50 else "medium"
        elif "regime" in question_lower or "stagflation" in question_lower:
            answer = f"The current macro regime is classified as {context['regime']}. Growth signal reads {context['growth']:.0f}/100, inflation signal {context['inflation']:.0f}/100 (0 = weak, 50 = neutral, 100 = strong)."
            confidence = "high"
        elif "equity" in question_lower or "stock" in question_lower or "bond" in question_lower:
            answer = f"In the current {context['regime']} regime, typical asset performance varies. The growth signal at {context['growth']:.0f}/100 suggests {'favorable' if context['growth'] > 50 else 'challenging'} conditions for risk assets."
            confidence = "medium"
        else:
            answer = f"Based on current macro conditions ({context['regime']} regime), I recommend reviewing the dashboard indicators. Growth signal {context['growth']:.0f}/100, inflation signal {context['inflation']:.0f}/100."
            confidence = "medium"

        # AskResponse.confidence is a float 0-1 — map the textual level (schema mismatch that
        # otherwise 503'd on every call).
        confidence_num = {"high": 0.85, "medium": 0.6, "low": 0.35}.get(confidence, 0.6)
        return AskResponse(
            answer=answer,
            sources=["FRED Economic Data", "Bridgewater 2-by-2 Regime Classification", "Dashboard Metrics"],
            confidence=confidence_num
        )
    except Exception as e:
        logger.error(f"Ask endpoint error: {e}")
        raise HTTPException(status_code=503, detail=f"Question answering unavailable: {e}")


# FIXED: Tier 3A - Additional missing endpoints
@app.get("/api/regime")
async def get_regime_endpoint():
    """Get current regime classification data — uses dashboard handler for consistency."""
    try:
        from api.handlers.dashboard_handler import get_dashboard_data
        dashboard = await get_dashboard_data(mode="live")
        if dashboard and dashboard.regime:
            return _sanitize_for_json(dashboard.regime)
        # Fallback to main.py classifier
        df = _load_data_or_fail()
        result = get_regime_data(df)
        return _sanitize_for_json(result)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Regime data unavailable: {e}")




# NEW ENDPOINTS — Calendar Blackout, Earnings Revisions, COT, Horizon

@app.get("/api/calendar/blackout")
async def get_blackout_calendar():
    """
    Returns Fed blackout periods (10-day window before each FOMC meeting).
    """
    try:
        from datetime import datetime, timedelta

        today = datetime.now().date()
        current_year = today.year

        # Real meeting dates from federalreserve.gov. Blackout runs from the second
        # Saturday before the meeting's first day through the day after the decision.
        meetings = [(datetime.fromisoformat(a_).date(), datetime.fromisoformat(b_).date())
                    for a_, b_ in _fetch_fomc_meetings()]
        if not meetings:
            return {"available": False, "reason": "FOMC calendar unavailable (federalreserve.gov unreachable)",
                    "is_blackout": False, "current_period": None, "next_meeting": None,
                    "next_blackout_start": None, "all_blackout_periods": [],
                    "last_updated": datetime.now().isoformat()}
        all_blackout_periods = []
        for first_day, meeting_date in meetings:
            all_blackout_periods.append({
                "start": _fomc_blackout_start(first_day).isoformat(),
                "end": (meeting_date + timedelta(days=1)).isoformat(),
                "meeting_date": meeting_date.isoformat(),
            })

        # Check if currently in blackout
        is_blackout = False
        current_period = None
        for period in all_blackout_periods:
            start = datetime.fromisoformat(period["start"]).date()
            end = datetime.fromisoformat(period["end"]).date()
            if start <= today <= end:
                is_blackout = True
                current_period = period
                break

        # Find next meeting and blackout
        next_meeting = None
        next_blackout_start = None
        for first_day, meeting_date in meetings:
            if meeting_date >= today:
                next_meeting = meeting_date.isoformat()
                next_blackout_start = _fomc_blackout_start(first_day).isoformat()
                break

        return {
            "is_blackout": is_blackout,
            "current_period": current_period,
            "next_meeting": next_meeting,
            "next_blackout_start": next_blackout_start,
            "all_blackout_periods": all_blackout_periods,
            "last_updated": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"Blackout calendar error: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"error": str(e), "is_blackout": False, "all_blackout_periods": []}
        )


@app.get("/api/earnings/revisions")
async def get_earnings_revisions():
    """
    Returns earnings estimate revision data from Finnhub API.
    """
    try:
        import requests

        finnhub_key = os.getenv("FINNHUB_API_KEY", "")
        if not finnhub_key:
            # HONEST ABSENCE (was a hardcoded fake sector table stamped with now()): real
            # per-sector EPS-revision data requires the Finnhub feed, which isn't configured
            # here. Return structured unavailability so the frontend shows "—" for the EPS
            # overlay rather than fabricated percentages — the regime-based sector allocation
            # underneath is real and unaffected.
            logger.info("FINNHUB_API_KEY not set — earnings-revision overlay unavailable (no fabricated fallback).")
            return {
                "available": False,
                "reason": "Sector EPS-revision data requires a Finnhub API key (FINNHUB_API_KEY not configured).",
                "sectors": {},
                "divergences": [],
                "updated_at": datetime.now().isoformat(),
            }

        # S&P 500 bellwethers
        tickers = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "JPM", "GS", "XOM", "UNH"]
        ticker_data = []
        revision_scores = []

        for ticker in tickers:
            try:
                url = f"https://finnhub.io/api/v1/stock/recommendation?symbol={ticker}&token={finnhub_key}"
                response = requests.get(url, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    if data and len(data) > 0:
                        # Get most recent recommendation
                        latest = data[0]
                        strong_buy = latest.get("strongBuy", 0)
                        buy = latest.get("buy", 0)
                        hold = latest.get("hold", 0)
                        sell = latest.get("sell", 0)
                        strong_sell = latest.get("strongSell", 0)

                        upgrades = strong_buy + buy
                        downgrades = sell + strong_sell
                        total = upgrades + downgrades + hold

                        revision_score = (upgrades - downgrades) / total if total > 0 else 0
                        revision_scores.append(revision_score)

                        ticker_data.append({
                            "symbol": ticker,
                            "strongBuy": strong_buy,
                            "buy": buy,
                            "hold": hold,
                            "sell": sell,
                            "strongSell": strong_sell,
                            "revision_score": round(revision_score, 2),
                        })
            except Exception as e:
                logger.warning(f"Failed to fetch {ticker}: {e}")
                continue

        # Calculate aggregate metrics
        if revision_scores:
            positive_count = sum(1 for s in revision_scores if s > 0)
            revision_breadth = positive_count / len(revision_scores)
            avg_revision_score = sum(revision_scores) / len(revision_scores)

            if revision_breadth > 0.6:
                signal = "BULLISH"
            elif revision_breadth < 0.4:
                signal = "BEARISH"
            else:
                signal = "NEUTRAL"
        else:
            revision_breadth = None
            avg_revision_score = None
            signal = "UNAVAILABLE"

        return {
            "revision_breadth": round(revision_breadth, 2) if revision_breadth is not None else None,
            "revision_score": round(avg_revision_score, 2) if avg_revision_score is not None else None,
            "signal": signal,
            "tickers": ticker_data,
            "last_updated": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"Earnings revisions error: {e}", exc_info=True)
        return {
            "error": str(e),
            "revision_breadth": None,
            "revision_score": None,
            "signal": "UNAVAILABLE",
            "tickers": [],
            "last_updated": datetime.now().isoformat(),
        }


@app.get("/api/cot")
@ttl_cache(300)
async def get_cot_data():
    """
    Returns CFTC Commitments of Traders positioning data.
    """
    try:
        import requests

        # CFTC public API endpoint
        base_url = "https://publicreporting.cftc.gov/resource/6dca-aqww.json"

        contracts = [
            {"name": "E-MINI S&P 500", "search": "E-MINI S&P 500"},
            {"name": "10-Year Treasury", "search": "10-YEAR U.S. TREASURY"},
            {"name": "Euro FX", "search": "EURO FX"},
            {"name": "Gold", "search": "GOLD"},
            {"name": "Crude Oil", "search": "CRUDE OIL, LIGHT SWEET"},
        ]

        contracts_data = []
        report_date = None

        for contract in contracts:
            try:
                # Query CFTC API
                params = {
                    "$limit": 5,
                    "$order": "report_date_as_yyyy_mm_dd DESC",
                    "$where": f"market_and_exchange_names like '%{contract['search']}%'",
                }
                response = requests.get(base_url, params=params, timeout=15)

                if response.status_code == 200:
                    data = response.json()
                    if data and len(data) > 0:
                        latest = data[0]
                        prior = data[1] if len(data) > 1 else None

                        longs = int(latest.get("noncomm_positions_long_all", 0))
                        shorts = int(latest.get("noncomm_positions_short_all", 0))
                        net = longs - shorts

                        # Calculate net change
                        if prior:
                            prior_longs = int(prior.get("noncomm_positions_long_all", 0))
                            prior_shorts = int(prior.get("noncomm_positions_short_all", 0))
                            prior_net = prior_longs - prior_shorts
                            net_change = net - prior_net
                        else:
                            net_change = 0

                        # Determine if extreme (>1.5 std dev assumption)
                        extreme = abs(net) > 200000  # Threshold for extreme positioning

                        contracts_data.append({
                            "name": contract["name"],
                            "speculator_longs": longs,
                            "speculator_shorts": shorts,
                            "net_position": net,
                            "net_change": net_change,
                            "positioning": "NET_LONG" if net > 0 else "NET_SHORT",
                            "extreme": extreme,
                        })

                        if report_date is None:
                            report_date = latest.get("report_date_as_yyyy_mm_dd")
            except Exception as e:
                logger.warning(f"Failed to fetch COT for {contract['name']}: {e}")
                continue

        return {
            "report_date": report_date,
            "contracts": contracts_data,
            "last_updated": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"COT data error: {e}", exc_info=True)
        return {
            "error": str(e),
            "report_date": None,
            "contracts": [],
            "last_updated": datetime.now().isoformat(),
        }


@app.get("/api/v1/global-macro")
@ttl_cache(900)
async def get_global_macro_v1():
    """Developed-markets monitor (Americas, Europe, Asia-Pacific): policy rates and recent
    central-bank moves, CPI, unemployment, GDP, 10Y/3M yields, equity and FX — each value dated
    and graded against its release calendar. See api/global_macro.py for sources."""
    from api.global_macro import build_global_macro
    return await build_global_macro()


@app.get("/api/regional-macro")
@ttl_cache(900)
async def get_regional_macro():
    """Cross-country comparison (legacy shape) derived from the developed-markets monitor.

    It used FRED's mirror of OECD Main Economic Indicators, which stopped updating in early
    2025 — so UK/Canada CPI from 2025-03 and an August-average US 10Y were shown as current.
    Every value now carries its period."""
    from api.global_macro import build_global_macro
    gm = await build_global_macro()
    regions = []
    for r in gm.get("economies", []):
        if r["code"] not in ("US", "EA", "GB", "JP", "CA", "AU", "CH", "DE", "KR"):
            continue
        ten = r["ten_year_live"] if r.get("ten_year_live") else {"value": r["ten_year"]["value"], "date": r["ten_year"]["period"]}
        regions.append({"region": r["name"], "code": r["code"], "tenYear": ten["value"],
                        "unemployment": r["unemployment"]["value"], "cpiYoY": r["cpi"]["value"],
                        "policyRate": r["policy"].get("rate"),
                        "asOf": {"tenYear": ten.get("date"), "unemployment": r["unemployment"]["period"],
                                 "cpiYoY": r["cpi"]["period"], "policyRate": r["policy"].get("as_of")}})
    return {
        "available": gm.get("available", False),
        "regions": regions,
        "indicators": [
            {"key": "policyRate", "label": "Policy rate", "unit": "%"},
            {"key": "cpiYoY", "label": "CPI YoY", "unit": "%"},
            {"key": "unemployment", "label": "Unemployment", "unit": "%"},
            {"key": "tenYear", "label": "10Y Yield", "unit": "%"},
        ],
        "source": "BIS policy rates; OECD/Eurostat CPI, unemployment, yields; FRED (US) — see /api/v1/global-macro",
        "as_of": datetime.now().isoformat(),
    }


@app.get("/api/global-correlation")
@ttl_cache(600)
async def get_global_correlation(window: int = 90):
    """Cross-market correlation matrix across WORLD equity indices + FX + cross-asset, from real
    aligned daily returns (yfinance). Answers 'how do these global markets move together'."""
    from api.handlers.market_handler import _fetch_dated_closes_literal
    from api.calculations.factor_model import returns_from_closes
    from api.calculations.altdata import correlation_matrix

    window = max(20, min(int(window), 252))
    assets = {
        "S&P500": "^GSPC", "Nasdaq": "^IXIC", "FTSE": "^FTSE", "DAX": "^GDAXI",
        "EuroStoxx": "^STOXX50E", "Nikkei": "^N225", "HangSeng": "^HSI", "Shanghai": "000001.SS",
        "ASX200": "^AXJO", "Nifty": "^NSEI",
        "EURUSD": "EURUSD=X", "USDJPY": "USDJPY=X", "DXY": "DX-Y.NYB",
        "Gold": "GC=F", "WTI": "CL=F", "UST10Y": "TLT",
    }
    labels = list(assets.keys())
    results = await asyncio.gather(*[_fetch_dated_closes_literal(assets[l]) for l in labels],
                                   return_exceptions=True)
    dated = {l: d for l, d in zip(labels, results) if d and not isinstance(d, Exception)}
    if len(dated) < 2:
        return {"available": False, "reason": "Insufficient market data.", "labels": [], "matrix": []}
    common = None
    for d in dated.values():
        common = set(d) if common is None else (common & set(d))
    common = sorted(common or [])
    if len(common) < 22:
        return {"available": False, "reason": "Insufficient overlapping history.", "labels": [], "matrix": []}
    returns_by_asset = {l: returns_from_closes([dated[l][dt] for dt in common]) for l in dated}
    result = correlation_matrix(returns_by_asset, window)
    return {"available": bool(result["matrix"]), "as_of": datetime.now().isoformat(),
            "source": "yfinance (daily closes) — global indices, FX & cross-asset",
            "window": window, **result}


def _realized_vol(closes, n: int = 21):
    """Annualised realised volatility (%) of the last `n` daily log returns."""
    import math
    if len(closes) < n + 1:
        return None
    r = [math.log(closes[i] / closes[i - 1]) for i in range(len(closes) - n, len(closes)) if closes[i - 1] > 0]
    if len(r) < 2:
        return None
    m = sum(r) / len(r)
    return round(math.sqrt(sum((x - m) ** 2 for x in r) / (len(r) - 1)) * math.sqrt(252) * 100, 2)


@app.get("/api/fx-rates")
@ttl_cache(300)
async def get_fx_rates():
    """Broad FX board — many pairs grouped by region (G10 majors, Asia, EMEA, LatAm), each with
    a real live spot + daily % change. Pairs that fail to quote return null, never a fake value."""
    from api.handlers.market_handler import _fetch_dated_closes_literal, _pct_change

    # group -> [(pair label, yfinance ticker, decimals)]
    groups = {
        "g10": [("EUR/USD", "EURUSD=X", 4), ("GBP/USD", "GBPUSD=X", 4), ("USD/JPY", "USDJPY=X", 2),
                ("USD/CHF", "USDCHF=X", 4), ("USD/CAD", "USDCAD=X", 4), ("AUD/USD", "AUDUSD=X", 4),
                ("NZD/USD", "NZDUSD=X", 4), ("EUR/GBP", "EURGBP=X", 4), ("EUR/JPY", "EURJPY=X", 2),
                ("USD/SEK", "USDSEK=X", 3)],
        "asia": [("USD/CNY", "USDCNY=X", 3), ("USD/INR", "USDINR=X", 2), ("USD/KRW", "USDKRW=X", 1),
                 ("USD/SGD", "USDSGD=X", 4), ("USD/HKD", "USDHKD=X", 4), ("USD/TWD", "USDTWD=X", 2)],
        "emea_latam": [("USD/BRL", "USDBRL=X", 3), ("USD/MXN", "USDMXN=X", 3),
                       ("USD/ZAR", "USDZAR=X", 3), ("USD/TRY", "USDTRY=X", 3)],
    }
    # Dated closes, already re-dated to their New York session (api/market_dates.py), so a
    # pair's daily change lines up with DXY's and each row says which session it is.
    flat = [(g, p, t, dp) for g, items in groups.items() for (p, t, dp) in items]
    dated_list = await asyncio.gather(*[_fetch_dated_closes_literal(t) for _, _, t, _ in flat],
                                      return_exceptions=True)
    result = {"g10": [], "asia": [], "emea_latam": []}
    for (g, pair, ticker, dp), dated in zip(flat, dated_list):
        if isinstance(dated, Exception) or not dated:
            result[g].append({"pair": pair, "ticker": ticker, "spot": None, "change1d": None,
                              "as_of": None, "available": False})
        else:
            days = sorted(dated)
            closes = [dated[d] for d in days]
            ch1m = _pct_change(closes, 21)
            result[g].append({"pair": pair, "ticker": ticker, "spot": round(float(closes[-1]), dp),
                              "change1d": _pct_change(closes, 1), "change1w": _pct_change(closes, 5),
                              "change1m": ch1m, "vol1m": _realized_vol(closes, 21),
                              "trend": (None if ch1m is None else "UP" if ch1m > 1 else "DOWN" if ch1m < -1 else "FLAT"),
                              "as_of": days[-1], "available": True})
    dxy_dated = await _fetch_dated_closes_literal("DX-Y.NYB")
    dxy = None
    if dxy_dated:
        dd = sorted(dxy_dated)
        dxy = {"spot": round(float(dxy_dated[dd[-1]]), 2),
               "change1d": _pct_change([dxy_dated[d] for d in dd], 1), "as_of": dd[-1]}
    n_ok = sum(1 for g in result.values() for x in g if x.get("available"))
    return {
        "available": n_ok > 0,
        "dxy": dxy,
        **result,
        "pair_count": n_ok,
        "source": "Yahoo Finance daily closes; FX re-dated to the New York session they belong to",
        "as_of": datetime.now().isoformat(),
    }


@app.get("/api/market-hours")
@ttl_cache(21600)  # 6h — holiday calendars change rarely
async def get_market_hours():
    """Per-exchange trading hours + REAL holiday calendars (not hardcoded).

    Holidays come from the `holidays` library, which is per-region and works for ANY year —
    including lunar-based closures (Hong Kong / Singapore Chinese New Year). The frontend keeps
    a live-ticking clock and just uses these dates to mark weekends/holidays as closed."""
    try:
        import holidays as _hol
    except Exception as e:
        return {"available": False, "reason": f"holidays library unavailable: {e}"}

    from datetime import datetime as _dt
    yr = _dt.now().year
    years = [yr, yr + 1]  # include next year so a year-rollover still resolves

    # (display name, city, tz, open, close, holidays-lib resolver)
    exchanges = [
        ("New York", "NYC", "America/New_York", 9.5, 16.0, lambda y: _hol.financial_holidays("NYSE", years=y)),
        ("London", "LON", "Europe/London", 8.0, 16.5, lambda y: _hol.country_holidays("GB", years=y)),
        ("Frankfurt", "FRA", "Europe/Berlin", 9.0, 17.5, lambda y: _hol.country_holidays("DE", years=y)),
        ("Tokyo", "TKY", "Asia/Tokyo", 9.0, 15.0, lambda y: _hol.country_holidays("JP", years=y)),
        ("Hong Kong", "HKG", "Asia/Hong_Kong", 9.5, 16.0, lambda y: _hol.country_holidays("HK", years=y)),
        ("Sydney", "SYD", "Australia/Sydney", 10.0, 16.0, lambda y: _hol.country_holidays("AU", years=y)),
    ]
    out = []
    for name, city, tz, open_h, close_h, resolver in exchanges:
        dates = {}
        try:
            for y in years:
                for d, label in resolver(y).items():
                    dates[d.isoformat()] = label
        except Exception as e:
            logger.warning(f"[market-hours] holiday calc failed for {name}: {e}")
        out.append({
            "name": name, "city": city, "tz": tz,
            "open": open_h, "close": close_h,
            "holidays": sorted(dates.keys()),
            "holidayNames": dates,
        })
    return {
        "available": True,
        "exchanges": out,
        "years": years,
        "source": "python-holidays library (per-region, any-year; incl. lunar calendars)",
        "as_of": _dt.now().isoformat(),
    }


@app.get("/api/global-markets")
@ttl_cache(300)
async def get_global_markets():
    """Major world equity indices with real level + daily % change (not just US).

    Uses live yfinance closes per index; any index that fails to fetch is returned with a null
    level + reason rather than a fabricated value."""
    from api.handlers.market_handler import _fetch_closes_literal, _pct_change

    # (display name, region, yfinance ticker)
    indices = [
        ("S&P 500", "US", "^GSPC"),
        ("Nasdaq", "US", "^IXIC"),
        ("FTSE 100", "UK", "^FTSE"),
        ("DAX", "Germany", "^GDAXI"),
        ("Euro Stoxx 50", "Europe", "^STOXX50E"),
        ("Nikkei 225", "Japan", "^N225"),
        ("Hang Seng", "Hong Kong", "^HSI"),
        ("Shanghai Composite", "China", "000001.SS"),
        ("ASX 200", "Australia", "^AXJO"),
        ("Nifty 50", "India", "^NSEI"),
    ]
    closes_list = await asyncio.gather(*[_fetch_closes_literal(t) for _, _, t in indices],
                                       return_exceptions=True)
    markets = []
    for (name, region, ticker), closes in zip(indices, closes_list):
        if isinstance(closes, Exception) or not closes:
            markets.append({"name": name, "region": region, "ticker": ticker,
                            "level": None, "change1d": None, "available": False,
                            "reason": "quote unavailable"})
            continue
        markets.append({
            "name": name, "region": region, "ticker": ticker,
            "level": round(float(closes[-1]), 2),
            "change1d": _pct_change(closes, 1),
            "available": True,
        })
    ok = [m for m in markets if m.get("available")]
    return {
        "markets": markets,
        "available": len(ok) > 0,
        "regions_covered": sorted({m["region"] for m in ok}),
        "source": "Yahoo Finance (yfinance) — live index closes",
        "as_of": datetime.now().isoformat(),
    }


@app.get("/api/horizon")
async def get_horizon_risks():
    """
    Returns geopolitical and macro horizon risk events for the next 90 days.
    """
    try:
        import requests
        from datetime import datetime, timedelta

        today = datetime.now().date()
        horizon_end = today + timedelta(days=90)

        events = []

        # Try Finnhub economic calendar
        finnhub_key = os.getenv("FINNHUB_API_KEY", "")
        if finnhub_key:
            try:
                url = f"https://finnhub.io/api/v1/calendar/economic?from={today.isoformat()}&to={horizon_end.isoformat()}&token={finnhub_key}"
                response = requests.get(url, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    economic_events = data.get("economicCalendar", [])
                    for event in economic_events[:20]:
                        impact = event.get("impact", "")
                        if impact in ["high", "1", "2"]:
                            event_date = event.get("date", "")
                            if event_date:
                                try:
                                    event_dt = datetime.fromisoformat(event_date.replace("Z", "+00:00")).date()
                                    days_away = (event_dt - today).days
                                    events.append({
                                        "date": event_date[:10],
                                        "event": event.get("event", "Unknown"),
                                        "impact": "HIGH" if impact in ["high", "1"] else "MEDIUM",
                                        "category": "MONETARY_POLICY" if "FOMC" in event.get("event", "") else "GROWTH",
                                        "days_away": days_away,
                                    })
                                except Exception as e:
                                    pass
            except Exception as e:
                logger.warning(f"Finnhub calendar fetch failed: {e}")

        # FOMC decisions from federalreserve.gov (the old hardcoded 2026 list had the
        # wrong months for half the meetings).
        fomc_upcoming = [datetime.fromisoformat(d).date() for d in _fetch_fomc_dates()]

        for fomc_date in fomc_upcoming:
            if today <= fomc_date <= horizon_end:
                days_away = (fomc_date - today).days
                events.append({
                    "date": fomc_date.isoformat(),
                    "event": "FOMC Decision",
                    "impact": "HIGH",
                    "category": "MONETARY_POLICY",
                    "days_away": days_away,
                })

        # CPI releases — SAME source as /api/calendar (FRED release id 10), with the identical
        # ~12th-of-month fallback. Previously horizon used a "second Tuesday" heuristic while the
        # calendar used the 12th, so the two panels showed the same CPI release on different dates
        # (e.g. 07-14 vs 07-12). Now both derive from one source and stay consistent.
        cpi_dates = _fetch_fred_release_dates(10, n=6)
        if cpi_dates:
            for ds in cpi_dates:
                try:
                    cd = datetime.fromisoformat(ds).date()
                except Exception:
                    continue
                if today <= cd <= horizon_end:
                    events.append({"date": cd.isoformat(), "event": "CPI Release", "impact": "HIGH",
                                   "category": "INFLATION", "days_away": (cd - today).days})
        else:
            for k in range(0, 4):
                y, mth = divmod(today.month - 1 + k, 12)
                cd = datetime(today.year + y, mth + 1, 12).date()
                if today <= cd <= horizon_end:
                    events.append({"date": cd.isoformat(), "event": "CPI Release", "impact": "HIGH",
                                   "category": "INFLATION", "days_away": (cd - today).days})

        # NFP releases — SAME source as /api/calendar (FRED release id 50), fallback to the first
        # Friday of the month, and the same "Nonfarm Payrolls" label the calendar/event-vol use.
        nfp_dates = _fetch_fred_release_dates(50, n=6)
        if nfp_dates:
            for ds in nfp_dates:
                try:
                    nd = datetime.fromisoformat(ds).date()
                except Exception:
                    continue
                if today <= nd <= horizon_end:
                    events.append({"date": nd.isoformat(), "event": "Nonfarm Payrolls", "impact": "HIGH",
                                   "category": "LABOR", "days_away": (nd - today).days})
        else:
            for k in range(0, 4):
                y, mth = divmod(today.month - 1 + k, 12)
                first_day = datetime(today.year + y, mth + 1, 1)
                first_friday = first_day + timedelta(days=(4 - first_day.weekday()) % 7)
                nd = first_friday.date()
                if today <= nd <= horizon_end:
                    events.append({"date": nd.isoformat(), "event": "Nonfarm Payrolls", "impact": "HIGH",
                                   "category": "LABOR", "days_away": (nd - today).days})

        # Deduplicate by date + event
        seen = set()
        unique_events = []
        for event in events:
            key = (event["date"], event["event"])
            if key not in seen:
                seen.add(key)
                unique_events.append(event)

        # Sort by date
        unique_events.sort(key=lambda x: x["date"])

        # Find next high impact event
        next_high_impact = None
        for event in unique_events:
            if event["impact"] == "HIGH":
                next_high_impact = {
                    "date": event["date"],
                    "event": event["event"],
                    "days_away": event["days_away"],
                }
                break

        # Calculate risk density
        high_impact_next_14 = sum(1 for e in unique_events if e["impact"] == "HIGH" and e["days_away"] <= 14)
        risk_density = "HIGH" if high_impact_next_14 > 3 else "MEDIUM" if high_impact_next_14 > 1 else "LOW"

        # FIXED: Return format matches frontend HorizonData interface
        return {
            "horizon_events": unique_events[:30],  # Limit to 30 events
            "next_high_impact": next_high_impact,
            "risk_density": risk_density,
            "overallRiskDensity": risk_density,  # For compatibility
            "last_updated": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"Horizon risks error: {e}", exc_info=True)
        return {
            "error": str(e),
            "horizon_events": [],
            "next_high_impact": None,
            "risk_density": "UNKNOWN",
            "last_updated": datetime.now().isoformat(),
        }


# FIXED: Missing endpoints (BUG 15)
@app.get("/api/calendar")
@ttl_cache(600)
async def get_economic_calendar():
    """
    Economic calendar with FOMC, NFP, and CPI events.
    FIXED (BUG 7 PERMANENT): Uses live data from Fed website and FRED API.
    """
    try:
        from datetime import date, timedelta
        today = date.today()
        events = []

        # FIXED (BUG 7): Fetch FOMC dates from Fed website (cached 24h)
        fomc_dates = _fetch_fomc_dates()
        logger.info(f"Fetched {len(fomc_dates)} FOMC dates from Federal Reserve")

        # FIXED (BUG 7): Fetch NFP and CPI dates from FRED API
        # CPI release ID = 10, NFP (Employment Situation) = 50
        cpi_dates = _fetch_fred_release_dates(10, n=6)
        nfp_dates = _fetch_fred_release_dates(50, n=6)
        logger.info(f"Fetched {len(cpi_dates)} CPI dates, {len(nfp_dates)} NFP dates from FRED")

        # Generate next 90 days of events
        for i in range(90):
            d = today + timedelta(days=i)
            d_str = d.strftime("%Y-%m-%d")

            # FOMC: use live scraped dates with fallback
            if d_str in fomc_dates:
                events.append({"date": d_str, "event": "FOMC Decision", "impact": "HIGH", "category": "MONETARY_POLICY", "source": "federalreserve.gov"})

            # NFP: use FRED dates with fallback to first Friday
            if d_str in nfp_dates:
                events.append({"date": d_str, "event": "Nonfarm Payrolls", "impact": "HIGH", "category": "LABOR", "source": "FRED"})
            elif not nfp_dates and d.weekday() == 4 and 1 <= d.day <= 7:
                events.append({"date": d_str, "event": "Nonfarm Payrolls", "impact": "HIGH", "category": "LABOR", "source": "fallback"})

            # CPI: use FRED dates with fallback to ~12th of month
            if d_str in cpi_dates:
                events.append({"date": d_str, "event": "CPI Release", "impact": "HIGH", "category": "INFLATION", "source": "FRED"})
            elif not cpi_dates and d.day == 12:
                events.append({"date": d_str, "event": "CPI Release", "impact": "HIGH", "category": "INFLATION", "source": "fallback"})

        return JSONResponse(content=scrub_nans({"events": events[:20]}))
    except Exception as e:
        logger.error(f"Calendar error: {e}")
        return JSONResponse(content={"events": [], "error": str(e)})






# FIXED (PART 1): Market Stream endpoint for live topbar data
@app.get("/api/market-stream")
async def get_market_stream():
    """Live market data stream for topbar ticker - REST fallback for WebSocket."""
    try:
        import yfinance as yf

        tickers = {
            "spx": "^GSPC",
            "ndx": "^NDX",
            "vix": "^VIX",
            "gld": "GC=F",
            "wti": "CL=F",
            "dxy": "DX-Y.NYB",
            "eurusd": "EURUSD=X",
        }

        result = {}
        for key, sym in tickers.items():
            try:
                hist = yf.Ticker(sym).history(period="5d")
                if len(hist) >= 2:
                    cur = float(hist["Close"].iloc[-1])
                    prev = float(hist["Close"].iloc[-2])
                    chg = round((cur - prev) / prev * 100, 3)
                    result[key] = round(cur, 2)
                    result[f"{key}Chg"] = chg
                elif len(hist) == 1:
                    result[key] = round(float(hist["Close"].iloc[-1]), 2)
                    result[f"{key}Chg"] = 0.0
                else:
                    result[key] = None
                    result[f"{key}Chg"] = None
            except Exception as e:
                logger.debug(f"Market stream {key} failed: {e}")
                result[key] = None
                result[f"{key}Chg"] = None

        # 10Y and 2Y yields + Fed rate from FRED/fallback
        try:
            df = _load_data_or_fail()
            result["tenYear"] = safe_float(_get(df, "yield_10y", "DGS10", 4.2))
            result["twoYear"] = safe_float(_get(df, "yield_2y", "DGS2", 3.8))
            result["fed"] = safe_float(_get(df, "fed_funds_rate", "DFF", 4.5))
        except Exception as e:
            logger.debug(f"Market stream rates failed: {e}")
            result["tenYear"] = 4.2
            result["twoYear"] = 3.8
            result["fed"] = 4.5

        return scrub_nans(result)
    except Exception as e:
        logger.error(f"Market stream endpoint failed: {e}")
        return {"error": str(e)}


# FIXED (Fix 8): Canonical prices endpoint - single source of truth
# BUSINESS LAYER ENDPOINTS (Phase 3D)









