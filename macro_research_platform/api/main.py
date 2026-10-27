"""
Macro Terminal API — application entry point.

Run (from macro_research_platform/):  uvicorn api.main:socket_app --port 8000      (socket_app = FastAPI + Socket.IO)

What lives here
    This module ASSEMBLES the application; endpoint logic lives in api/routers/ (one module per topic). It holds:
      1. App construction       FastAPI app, NaN-safe JSON responses (api/core/json_safe), global exception handler
      2. Middleware             GZip; CORS (FRONTEND_ORIGINS); authentication → fund selection → position, in that
                                order (api/core/access.auth_middleware)
      3. Router registration    every api/routers/* module (see the include_router block)
      4. Startup / shutdown     `lifespan`: the scheduler and its jobs, cache warm-up, background monitors
      5. Remaining endpoints    health and methodology, data freshness and the data pipeline, /api/ask, /api/regime,
                                the FOMC blackout calendar, the price WebSocket

Scheduled jobs (UTC; APScheduler, started in `lifespan`)
    06:00 daily        daily_pipeline_06utc        rebuild the processed macro dataset
    06:05 daily        apply_splits                stock splits on held positions, every fund (api/corporate_actions)
    06:30 weekdays     governance_reconcile        positions vs fills ledger, funds with governance on
    every 60 s         consolidated_price_refresh  prices for live tiles
    every 15 min       consolidated_macro_refresh  macro series
    every 5 min        mkt_price_alerts            user price alerts
    21:15 weekdays     post_close_refresh          after the US close
    21:30 weekdays     daily_nav_snapshot          NAV, positions and model P&L of every fund (+ catch-up at start)
    21:45 weekdays     stock_ideas_post_close      stock idea screen
    22:20 / 22:35      auto_book_run / macro_trader_run   the paper traders
    on start           catch-up pipeline, NAV catch-up, split check, if a scheduled run was missed while offline

Where to find things
    docs/CODEBASE_MAP.md lists every module with what it does; shared router helpers are in api/core/web.py.
    Data and regime state: api/regime_data.py · macro calendar: api/macro_calendar.py · the book and its risk:
    api/routers/book.py · research views: api/routers/research.py · sign-in: api/routers/auth.py.

Model stack (academic sources)
    Regime: growth × inflation classifier · Recession: logistic + Estrella–Mishkin probit (1998) + Sahm rule (2019)
    LEI composite: Conference Board method · Credit impulse: Biggs, Mayer & Pick (2010) · Risk parity: Qian (2005)
    Financial conditions: Adrian, Boyarchenko & Giannone (2019)
"""

import sys
import os
import logging
import threading
import time
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Optional, Any

# MUST be before any project imports
_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

# FIXED: Tier 1A - Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, BackgroundTasks, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from api.core.json_safe import SafeJSONResponse as JSONResponse  # NaN-safe

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




from api.macro_calendar import lru_cache_with_ttl, _fetch_fomc_meetings, _fomc_blackout_start


# FIXED: Import data validation layer (new architecture)

# FIXED: Phase 7 - New consolidated data architecture (safe migration)
from api.services.refresh_coordinator import refresh_coordinator
from api.diagnostics import router as health_router, diagnostics_router

# ═══════════════════════════════════════════════════════════════════════════════
# MODEL VALIDATION - Forecast Tracking Integration (Phase 1-10)
# ═══════════════════════════════════════════════════════════════════════════════

# FIXED: Phase 3 - Import Pydantic models from schemas module
from api.schemas.models import AskResponse, AskRequest

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

# Optional research models (src/): whether each module is present, without importing it. These flags only feed
# the health report — an empty `try` used to set them True unconditionally.
import importlib.util as _ilu


def _module_present(name: str) -> bool:
    try:
        return _ilu.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


_FC_OK = _module_present("src.models.macro_regime.financial_conditions_model")
_NOWCAST_OK = _module_present("src.models.nowcasting.gdp_nowcast")
_LIQUIDITY_OK = _module_present("src.models.liquidity.liquidity_index")
_SENTIMENT_OK = _module_present("src.models.sentiment.risk_appetite")
_VALUATION_OK = _module_present("src.models.valuation.valuation_filter")
_MOMENTUM_OK = _module_present("src.models.momentum.momentum_veto")
_CORRELATION_OK = _module_present("src.models.portfolio_construction.correlation_regime")
_SIGNALSTACK_OK = _module_present("src.models.signal_hierarchy")

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

logger = logging.getLogger(__name__)

# GLOBAL UTILITY FUNCTIONS



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


# FIXED: Tier 1D - Dashboard response caching with 5-minute TTL
# Reduces response time from ~4s to <100ms for cached responses
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
# Strong references to long-running startup tasks (asyncio keeps only weak ones, so an
# unreferenced warm loop can be garbage-collected and silently stop).
_BACKGROUND_TASKS: set = set()

from api.regime_data import PROJECT_ROOT, _fetch_fresh_fred_value, load_processed_data







# MODULE 4: VALUATION FILTER



# MODULE 5: CROSS-ASSET MOMENTUM VETO



# MODULE 6: CORRELATION REGIME ADJUSTMENT



# MODULE 7: SIGNAL HIERARCHY & OVERRIDE LOGIC



# FastAPI App

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Standardize log format across all app modules before anything else logs.
    """Start-up and shutdown: initialise databases, warm caches and start the scheduled jobs; stop them on exit."""
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

    # Live AIS collector (whole world): start with the server so SHIP has a picture when opened
    # and the worldwide satellite presence layer (GFW, refreshed daily) for areas without receivers
    if not os.getenv("PYTEST_CURRENT_TEST"):
        try:
            from api.marketdata.tracking import ais_collector, presence_start
            if os.getenv("AISSTREAM_API_KEY"):
                ais_collector()
            if os.getenv("GFW_API_TOKEN"):
                presence_start()
            from api.marketdata.flows import snapshots_start
            snapshots_start()                      # daily ETF shares-outstanding snapshots (fund flows)
            from api.marketdata.airtraffic import sweep_start
            sweep_start()                          # live ADS-B sweep of hubs OpenSky covers poorly
            import threading
            from api.marketdata import edge
            from api.marketdata import insights
            from api.marketdata import predmarkets, research, funds, fixed_income, bridgewater
            predmarkets.refresher_start()          # keeps PRED and the odds panels warm (Kalshi + Polymarket)

            def _warm():
                # spread out: hundreds of Yahoo requests at once (breadth, option chains) get the server
                # rate-limited, which then breaks ordinary quote screens for a while
                import time as _t
                _t.sleep(90)
                # Research-mode function screens that load cold in 7–13 s: ECO (calendar, the default 14-day
                # view), ECST, RMON (world country matrix) and MRGR (SEC merger deals)
                from api.marketdata import econ as _econ, countries as _countries, corporate as _corporate
                from api.marketdata import freedata as _freedata, eps_revisions as _eps
                for f in (lambda: _econ.calendar(14, None, "Low"), lambda: _econ.surprise_index("2010-01-01"),
                          _countries.world_data, _corporate.deals,
                          _freedata.shiller_cape, _freedata.aaii_sentiment, _freedata.nyfed_nowcast,
                          _freedata.cboe_put_call, _eps.sector_revisions):
                    try:
                        f()
                    except Exception as e:
                        logger.info(f"[STARTUP] warm-up research screen: {e}")
                    _t.sleep(5)
                from api.marketdata import tracking as _tracking, corporate as _corp2, monitors as _monitors
                from api.marketdata import flows as _flows
                # slowest cold sources first (IMF PortWatch ports ~110 s, trade nowcast ~70 s, ETF flows ~75 s): the
                # edge board, which combines them, is then ready early in the first pass after a restart
                heavy = (edge.ports_trade, edge.trade, _flows.etf, edge.cot, insights.implied_moves, insights.uoa, edge.board,
                         research.credit, fixed_income.treasuries, funds.etf_screener, bridgewater.environments,
                         bridgewater.debt_cycles, bridgewater.world_order, insights.vol, insights.risk, insights.breadth,
                         # 8–22 s cold on first open
                         _tracking.chokepoints, lambda: _corp2.actions_calendar(14), _monitors.money_markets,
                         lambda: _monitors.heatmap("US", 300), _countries.world_data, _corporate.deals)
                # Every 30 minutes, paced: with stale-while-revalidate in the cache (api/marketdata/core.py) a lapsed
                # screen is served at once and refreshed behind; this keeps every heavy screen inside that window.
                while True:
                    for f in heavy:
                        try:
                            f()
                        except Exception as e:                   # one slow source must not stop the rest
                            logger.info(f"[warm] markets {getattr(f, '__name__', f)}: {e}")
                        _t.sleep(20)
                    _t.sleep(1800)
            threading.Thread(target=_warm, name="warm-markets", daemon=True).start()
        except Exception as e:
            logger.warning(f"[STARTUP] ship collectors not started: {e}")

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
        from api.routers.fund import take_nav_snapshot as _take_one_snapshot

        async def take_nav_snapshot():
            """Every fund's daily NAV (each in its own database and base currency)."""
            from api import funds as _funds
            for f in _funds.list_funds():
                tok = _funds.CURRENT.set(f["id"])
                try:
                    await _take_one_snapshot()
                except Exception as e:                                    # noqa: BLE001 — one fund must not stop the rest
                    logger.warning("[nav] snapshot for fund %s failed: %s", f["id"], e)
                finally:
                    _funds.CURRENT.reset(tok)
        _scheduler.add_job(
            func=take_nav_snapshot,
            trigger=CronTrigger(day_of_week="mon-fri", hour=21, minute=30),
            id="daily_nav_snapshot",
            replace_existing=True,
        )
        logger.info("[STARTUP] Scheduled daily_nav_snapshot at 21:30 UTC weekdays")

        # The cron only fires while the server is up: when it starts after today's close and today's NAV is missing,
        # record it now (same day, so the marks are still today's). Earlier missed days stay as gaps — a snapshot taken
        # later would use later prices.
        async def _nav_catch_up():
            from datetime import datetime as _dt, timezone as _tz
            from api import fund_store
            now = _dt.now(_tz.utc)
            if now.weekday() < 5 and (now.hour, now.minute) >= (21, 30):
                from api import funds as _funds
                for f in _funds.list_funds():                             # each fund's own record
                    tok = _funds.CURRENT.set(f["id"])
                    try:
                        have = {r.get("date") for r in (fund_store.nav_history() or [])}
                        if now.date().isoformat() not in have:
                            await _take_one_snapshot()
                            logger.info("[STARTUP] daily_nav_snapshot caught up for fund %s, %s", f["id"], now.date())
                    except Exception as e:                                # noqa: BLE001
                        logger.warning("[STARTUP] NAV catch-up failed for fund %s: %s", f["id"], e)
                    finally:
                        _funds.CURRENT.reset(tok)
        _scheduler.add_job(func=_nav_catch_up, trigger="date", id="nav_catch_up", replace_existing=True)

        # Stock splits on held positions (every fund): unambiguous ones applied, the rest left for review.
        async def _apply_splits():
            from api import corporate_actions as _ca, funds as _funds
            for f in _funds.list_funds():
                tok = _funds.CURRENT.set(f["id"])
                try:
                    r = await asyncio.to_thread(_ca.apply_pending_automatically)
                    if r["applied"] or r["needs_review"]:
                        logger.info("[corp-actions] fund %s: %d applied, %d for review", f["id"],
                                    len(r["applied"]), len(r["needs_review"]))
                except Exception as e:                                    # noqa: BLE001
                    logger.warning("[corp-actions] fund %s failed: %s", f["id"], e)
                finally:
                    _funds.CURRENT.reset(tok)
        _scheduler.add_job(func=_apply_splits, trigger=CronTrigger(hour=6, minute=5), id="apply_splits",
                           replace_existing=True)
        _scheduler.add_job(func=_apply_splits, trigger="date", id="apply_splits_startup", replace_existing=True)

        # Massive (Polygon) store of daily bars for every US stock: backfill two years once (resumable, ~1¾ h at the
        # free plan's 5 requests a minute), then top up after each US close. No-op without MASSIVE_API_KEY.
        def _massive_topup():
            from api.providers import massive as _massive
            if _massive.start_backfill():
                logger.info("[massive] backfill / top-up started: %s missing days", _massive.status()["missing"])
        _scheduler.add_job(func=_massive_topup, trigger="date", id="massive_startup", replace_existing=True)
        _scheduler.add_job(func=_massive_topup, trigger=CronTrigger(day_of_week="mon-fri", hour=22, minute=20),
                           id="massive_topup", replace_existing=True)

        # T+1 reconciliation of positions against the fills ledger, for funds with governance on (a break halts).
        async def _reconcile_funds():
            from api import fund_store as _fs, funds as _funds, governance as _gov
            for f in _funds.list_funds():
                tok = _funds.CURRENT.set(f["id"])
                try:
                    if (await asyncio.to_thread(_fs.get_settings)).get("governance"):
                        r = await asyncio.to_thread(_gov.reconcile, "system")
                        logger.info("[governance] fund %s reconciliation: %s", f["id"], "clean" if r["ok"] else f"{len(r['breaks'])} breaks")
                except Exception as e:                                    # noqa: BLE001
                    logger.warning("[governance] reconciliation for fund %s failed: %s", f["id"], e)
                finally:
                    _funds.CURRENT.reset(tok)
        _scheduler.add_job(func=_reconcile_funds, trigger=CronTrigger(day_of_week="mon-fri", hour=6, minute=30),
                           id="governance_reconcile", replace_existing=True)

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

        # Stock ideas: rescreen the S&P 500 after the US close (an async job on the asyncio
        # scheduler). The ideas endpoint also rebuilds on demand when the list is stale.
        from api.stock_ideas import build_in_background as _ideas_build
        _scheduler.add_job(
            func=_ideas_build,
            trigger=CronTrigger(day_of_week="mon-fri", hour=21, minute=45),
            id="stock_ideas_post_close",
            replace_existing=True,
        )
        logger.info("[STARTUP] Scheduled stock_ideas_post_close at 21:45 UTC weekdays")

        # Auto (paper) book: one trading cycle after the ideas rebuild (fills pending orders
        # at the latest open, processes exits, places orders for the next session).
        from api.auto_trader import run as _auto_run
        _scheduler.add_job(
            func=_auto_run,
            trigger=CronTrigger(day_of_week="mon-fri", hour=22, minute=20),
            id="auto_book_run",
            replace_existing=True,
        )
        logger.info("[STARTUP] Scheduled auto_book_run at 22:20 UTC weekdays")

        # Macro Trader (paper): fills yesterday's orders at the open, marks to the close and
        # rebalances to the macro model's targets — after the auto book.
        from api.macro_trader import run as _macro_run
        _scheduler.add_job(
            func=_macro_run,
            trigger=CronTrigger(day_of_week="mon-fri", hour=22, minute=35),
            id="macro_trader_run",
            replace_existing=True,
        )
        logger.info("[STARTUP] Scheduled macro_trader_run at 22:35 UTC weekdays")

        # Markets price alerts: evaluated every 5 minutes for all users.
        from api.marketdata.usertools import check_alerts as _check_alerts
        _scheduler.add_job(func=_check_alerts, trigger="interval", minutes=5, id="mkt_price_alerts", replace_existing=True)
        logger.info("[STARTUP] Scheduled mkt_price_alerts every 5 minutes")

        # Catch-up: cron jobs only fire while the process is up, so a backend that was down
        # at 06:00 UTC left the CSV stale until the next day. If it is over 24h old, run the
        # pipeline once, a few minutes after startup (after the warm-up's FRED requests).
        _csv = PROJECT_ROOT / "data" / "us_economic_data.csv"
        _csv_age_h = (time.time() - _csv.stat().st_mtime) / 3600 if _csv.exists() else float("inf")
        if _csv_age_h > 24:
            def _catchup(attempt: int = 1):
                from api import fred_guard
                if fred_guard.is_open():          # FRED refusing requests: don't run a partial refresh
                    res = {"csv_updated": False}
                else:
                    res = run_daily_pipeline(_DASHBOARD_CACHE, _DASHBOARD_CACHE_LOCK)
                if (not res.get("csv_updated") or fred_guard.is_open()) and attempt < 8:
                    logger.warning("[PIPELINE] catch-up attempt %d did not update the CSV — retrying in 15 min", attempt)
                    _scheduler.add_job(func=_catchup, args=[attempt + 1], trigger="date",
                                       run_date=datetime.now(timezone.utc) + timedelta(minutes=15),
                                       id="catchup_pipeline", replace_existing=True)
            _scheduler.add_job(
                func=_catchup,
                trigger="date",
                run_date=datetime.now(timezone.utc) + timedelta(minutes=3),
                id="catchup_pipeline",
                replace_existing=True,
            )
            logger.info("[STARTUP] CSV is %.1fh old — catch-up pipeline run scheduled in 3 min", _csv_age_h)

    except Exception as e:
        logger.error(f"[STARTUP] Failed to initialize scheduler: {e}")

    # FIXED: Log FRED API key status at startup
    from api.config import FRED_API_KEY
    if FRED_API_KEY:
        logger.info("[config] FRED_API_KEY loaded: YES (%d characters)", len(FRED_API_KEY))   # never log key material
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
        # not under tests: a warm loop mid-fetch holds the test client's shutdown (and pytest's exit) for minutes
        if os.getenv("PYTEST_CURRENT_TEST") or os.getenv("MACRO_NO_BACKGROUND") == "1":
            raise RuntimeError("background loops disabled (tests / MACRO_NO_BACKGROUND)")
        _BACKGROUND_TASKS.add(_asyncio.create_task(_dashboard_warm_loop()))
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
        if os.getenv("PYTEST_CURRENT_TEST") or os.getenv("MACRO_NO_BACKGROUND") == "1":
            raise RuntimeError("background loops disabled (tests / MACRO_NO_BACKGROUND)")
        _BACKGROUND_TASKS.add(_asyncio.create_task(_risk_warm_loop()))
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
            from api.routers.model import model_latest as _model_latest   # 40y model + backtest: ~35s cold
            from api.routers.business import get_morning_brief as _morning_brief
            targets = [health_check, get_cot_data, get_economic_calendar,
                       get_rates, get_market_overview, get_yield_curve_signal,
                       # Heavy v1 analytics panels — pre-warm their TTL caches so a fresh
                       # dashboard load / fast scroll doesn't compute-storm the single backend
                       # and leave 9 panels showing "Unavailable — Timed out" on first paint.
                       quadrants_v1, stream_agreement_v1, factor_validation_v1,
                       risk_parity_compare_v1, regime_transition_v1, event_vol_v1,
                       correlation_matrix_v1, anomalies_v1, signal_attribution_v1,
                       get_cycle_risk_v1, _model_latest,
                       # out-of-sample evidence the ensemble weights by (6h cache)
                       signals_backtest_v1,
                       # 6–18 s cold: the Daily Brief, composite-signal history, next central-bank decisions,
                       # S&P 500 EPS revisions
                       _morning_brief, composite_history_v1, central_banks_next_v1, get_earnings_revisions]
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
        if os.getenv("PYTEST_CURRENT_TEST") or os.getenv("MACRO_NO_BACKGROUND") == "1":
            raise RuntimeError("background loops disabled (tests / MACRO_NO_BACKGROUND)")
        _BACKGROUND_TASKS.add(_asyncio.create_task(_endpoints_warm_loop()))
        logger.info("[STARTUP] Slow-endpoint warm loop started")
    except Exception as e:
        logger.warning(f"[STARTUP] Could not start endpoints warm loop: {e}")

    try:   # free-data source monitor: every source parsed and dated, every 6 hours (alerts on new failures)
        if os.getenv("PYTEST_CURRENT_TEST") or os.getenv("MACRO_NO_BACKGROUND") == "1":
            raise RuntimeError("background loops disabled (tests / MACRO_NO_BACKGROUND)")
        import threading as _th
        from api import source_monitor
        _th.Thread(target=source_monitor.loop, name="source-monitor", daemon=True).start()
        logger.info("[STARTUP] Source monitor started (every 6 h)")
    except Exception as e:
        logger.info(f"[STARTUP] Source monitor not started: {e}")

    try:   # Daily Brief delivery on a schedule (opt-in: BRIEF_DELIVERY_TIME + an alert channel in .env)
        from api import brief_delivery
        if os.getenv("PYTEST_CURRENT_TEST") or os.getenv("MACRO_NO_BACKGROUND") == "1":
            raise RuntimeError("background loops disabled (tests / MACRO_NO_BACKGROUND)")
        if brief_delivery.schedule()["enabled"]:
            _BACKGROUND_TASKS.add(_asyncio.create_task(brief_delivery.loop()))
            logger.info(f"[STARTUP] Daily Brief delivery at {brief_delivery.schedule()['time']} "
                        f"{brief_delivery.schedule()['tz']} (weekdays)")
    except Exception as e:
        logger.info(f"[STARTUP] Daily Brief delivery not scheduled: {e}")

    try:   # live ship positions: one persistent aisstream.io connection, if a key is configured
        from api.marketdata.tracking import ais_collector
        if ais_collector():
            logger.info("[STARTUP] AIS collector started")
    except Exception as e:
        logger.warning(f"[STARTUP] AIS collector not started: {e}")

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
        if os.getenv("PYTEST_CURRENT_TEST") or os.getenv("MACRO_NO_BACKGROUND") == "1":
            raise RuntimeError("background loops disabled (tests / MACRO_NO_BACKGROUND)")
        _BACKGROUND_TASKS.add(_asyncio.create_task(_pit_snapshot_loop()))
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
    except Exception:
        pass

from api.core.json_safe import SafeJSONResponse

app = FastAPI(
    default_response_class=SafeJSONResponse,   # NaN/Inf → null on every route (api/core/json_safe.py)
    title="Macro Research Platform API",
    description="Macro research and portfolio management API",
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

from fastapi.middleware.gzip import GZipMiddleware
app.add_middleware(GZipMiddleware, minimum_size=2048, compresslevel=5)   # world ship / flight snapshots are several MB of JSON

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
from api.routers.model import router as model_router  # systematic macro model
app.include_router(model_router)
from api.routers.stock import router as stock_router  # stock entry timing + screener
app.include_router(stock_router)
from api.routers.portfolios import router as portfolios_router  # model review, optimiser, auto book
app.include_router(portfolios_router)
from api.routers.governance import router as governance_router  # fund governance (model gates, controls, reporting)
from api.routers.portfolio_analytics import router as portfolio_analytics_router  # Brinson, TE, LVaR, lots, TCA
app.include_router(portfolio_analytics_router)
app.include_router(governance_router)
from api.routers.events import router as events_router  # macro event dataset (point-in-time releases, reactions)
app.include_router(events_router)
from api.routers.mfa import router as mfa_router  # two-factor sign-in (TOTP)
app.include_router(mfa_router)
from api.routers.auth import router as auth_router  # sign in / out, password, identity
app.include_router(auth_router)
from api.routers.audit import router as audit_router  # decision log and snapshots
app.include_router(audit_router)
from api.routers.book import router as book_router  # positions, trade ideas, VaR / stress / liquidity
app.include_router(book_router)
from api.routers.research import router as research_router  # macro, cross-asset and data-quality views
app.include_router(research_router)
from api.routers.positions import router as positions_router  # positions & tiers per fund
app.include_router(positions_router)
from api.routers.broker_ibkr import router as broker_ibkr_router  # IBKR link per fund (read-only)
app.include_router(broker_ibkr_router)
from api.routers.trading_desk import router as trading_desk_router   # pitch review (PMC) + pre-trade feasibility
app.include_router(trading_desk_router)
from api.routers.funds import router as funds_router   # several funds, each in its own database
app.include_router(funds_router)
from api.routers.data_export import router as data_export_router  # spreadsheet / API access (CSV, JSON)
app.include_router(data_export_router)
from api.routers.strategies import router as strategies_router  # Strategy Lab
app.include_router(strategies_router)
from api.routers.quant import router as quant_router  # Quant Lab + Quant Trader + Macro Trader
app.include_router(quant_router)
from api.routers.optresearch import router as optresearch_router  # Quant Lab → Options research
app.include_router(optresearch_router)
from api.routers.data_sources import router as data_sources_router  # SEC EDGAR, ALFRED, DBnomics, factors
app.include_router(data_sources_router)
from api.routers.marketdata import router as marketdata_router  # Markets mode: universal search/quotes/screener
app.include_router(marketdata_router)
from api.routers.ai import router as ai_router  # AI research assistant (local Ollama / Groq)
app.include_router(ai_router)

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
    """Socket.IO connection opened."""
    logger.info(f"Client connected: {sid}")
    await sio.emit("connected", {"status": "ok", "message": "Connected to Macro Terminal"}, room=sid)


@sio.event
async def disconnect(sid):
    """Socket.IO connection closed."""
    logger.info(f"Client disconnected: {sid}")


@sio.on("subscribe_market_data")
async def subscribe_market_data(sid, data):
    """Acknowledge a client's market-data subscription."""
    logger.info(f"Client {sid} subscribed to market data")
    await sio.emit("market_data_update", {"status": "subscribed"}, room=sid)


@app.get("/api/health")
@ttl_cache(120, offload=True)
async def health_check():
    """Liveness check for load balancers and the frontend."""
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

    from api import fred_guard
    return {
        "fred_circuit_breaker": fred_guard.status(),
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
         "citation": "Growth × inflation regime framework; risk parity per Qian (2005)",
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
         "citation": "Independent evidence streams: macro data, intermarket prices, positioning/flows",
         "confidence": "medium — heuristic stream classifiers; conviction scales with independent agreement",
         "note": "Position sizing multiplier scales with the NUMBER of agreeing streams, not any single model's confidence."},
        {"model": "Factor out-of-sample validation (/api/v1/factor-validation)",
         "citation": "Harvey, Liu & Zhu (2016), '...and the Cross-Section of Expected Returns', Review of Financial Studies",
         "confidence": "medium — in/out-of-sample R² split on daily factor-ETF proxies",
         "note": "Flags factors whose R² collapses out-of-sample; live it flags Momentum (0.71→0.30) as unstable."},
        {"model": "US yield-curve recession model",
         "citation": "Estrella & Mishkin (1998) probit",
         "confidence": "high — strong published out-of-sample evidence"},
    ]
    return {"version": "v1", "models": MODELS, "count": len(MODELS),
            "research_citations": research_citations}


# moved to api/routers/book.py; imported here for main's own use (snapshots) and older callers
from api.routers.book import _enrich_positions


async def _aio_to_thread(fn, *args):
    return await asyncio.to_thread(fn, *args)


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


@app.get("/api/data-freshness")
async def get_data_freshness():
    """Get data freshness status for all FRED series."""
    from api.data_freshness import check_fred_data_freshness, get_freshness_summary
    from api.data_fetcher import CONTRACTS

    # Check freshness of key series
    observation_dates = {}
    statuses = []

    df = await asyncio.to_thread(load_processed_data)
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
        except Exception:
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
            sources=["FRED Economic Data", "Growth × inflation regime classification", "Dashboard metrics"],
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
        # No fallback to the legacy CSV classifier: it could name a different regime than
        # the rest of the terminal.
        raise HTTPException(status_code=503, detail="Regime unavailable")
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




# FIXED (Fix 8): Canonical prices endpoint - single source of truth
# BUSINESS LAYER ENDPOINTS (Phase 3D)

# moved to api/routers/research.py; imported for main's startup warm-up and older callers
from api.routers.research import anomalies_v1, central_banks_next_v1, composite_history_v1, correlation_matrix_v1, event_vol_v1, factor_validation_v1, get_cot_data, get_cycle_risk_v1, get_earnings_revisions, get_economic_calendar, quadrants_v1, regime_transition_v1, risk_parity_compare_v1, signal_attribution_v1, signals_backtest_v1, stream_agreement_v1
