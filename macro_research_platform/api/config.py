"""Centralized configuration for Macro Terminal API."""

import os
from pathlib import Path
from typing import Dict, List, Optional
from dotenv import load_dotenv

# Load .env — walk up from api/ to find the project root .env
_here = Path(__file__).parent          # .../macro_research_platform/api/
_project_root = _here.parent           # .../macro_research_platform/
_dotenv_path = _project_root / ".env"
load_dotenv(dotenv_path=_dotenv_path, override=False)  # don't stomp real env vars
# Also try cwd as fallback (legacy behaviour)
load_dotenv(override=False)

# Base paths
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
CACHE_DIR = BASE_DIR / "cache"
REPORTS_DIR = BASE_DIR / "reports"

# Ensure directories exist
for dir_path in [DATA_DIR, CACHE_DIR, REPORTS_DIR]:
    dir_path.mkdir(parents=True, exist_ok=True)

# Database
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///macro_terminal.db")

# ═════════════════════════════════════════════════════════════════════════════
# SECURITY: JWT Authentication
# ═════════════════════════════════════════════════════════════════════════════

ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()
IS_TESTING = ENVIRONMENT in ("test", "ci", "testing")

# JWT Secret - MUST be set in production
_jwt_secret = os.getenv("JWT_SECRET")
if not _jwt_secret and not IS_TESTING:
    raise RuntimeError(
        "JWT_SECRET environment variable must be set in non-test environments. "
        "Generate a secure secret with: openssl rand -hex 32"
    )
JWT_SECRET = _jwt_secret or "test-secret-do-not-use-in-production"
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 480  # 8 hours (trading day)

# CORS
CORS_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
]

# Redis (for WebSocket broadcasting)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Celery
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")

# API Keys (external data sources)
FRED_API_KEY = os.getenv("FRED_API_KEY")
ALPHA_VANTAGE_KEY = os.getenv("ALPHA_VANTAGE_KEY")
POLYGON_KEY = os.getenv("POLYGON_KEY")

# Feature flags
ENABLE_WEBSOCKET = os.getenv("ENABLE_WEBSOCKET", "true").lower() == "true"
ENABLE_CELERY = os.getenv("ENABLE_CELERY", "true").lower() == "true"

# ═════════════════════════════════════════════════════════════════════════════
# Phase 5: Runtime Validation & Monitoring Flags
# ═════════════════════════════════════════════════════════════════════════════

# Runtime validation - validates payload data before returning from handlers
ENABLE_RUNTIME_VALIDATION = os.getenv("ENABLE_RUNTIME_VALIDATION", "true").lower() == "true"

# Event logging - logs signal, forecast, and risk events to database
ENABLE_EVENT_LOGGING = os.getenv("ENABLE_EVENT_LOGGING", "true").lower() == "true"

# Diagnostics - enables detailed diagnostics endpoints
ENABLE_DIAGNOSTICS = os.getenv("ENABLE_DIAGNOSTICS", "true").lower() == "true"

# Audit logging - logs all audit events to AuditLog table
ENABLE_AUDIT_LOGGING = os.getenv("ENABLE_AUDIT_LOGGING", "true").lower() == "true"

# Provenance tracking - tracks data lineage for all ingested data
ENABLE_PROVENANCE_TRACKING = os.getenv("ENABLE_PROVENANCE_TRACKING", "false").lower() == "true"

# ═════════════════════════════════════════════════════════════════════════════
# Role permissions mapping
# ═════════════════════════════════════════════════════════════════════════════

ROLE_PERMISSIONS: Dict[str, List[str]] = {
    "pm": [
        "master_signal", "key_metrics", "regime_engine",
        "ensemble", "signal_stack", "sector_allocation",
        "factor_rotation", "trade_ideas", "risk_indicators",
        "expected_returns", "investment_memo", "business_layer",
        "portfolio_fit", "var_drawdown"
    ],
    "analyst": [
        "master_signal", "key_metrics", "regime_engine",
        "ml_signals", "ensemble", "signal_stack", "sector_allocation",
        "factor_rotation", "risk_indicators", "debt_cycle",
        "advanced_indicators", "gdp_nowcast", "liquidity", "sentiment",
        "gmo_7year", "valuation", "expected_returns", "international_macro",
        "reflexivity", "transmission", "regime_transition", "correlation",
        "factor_decomp", "momentum_veto", "horizon_tensions",
        "model_agreement", "cta_trends", "news_sentiment",
        "equity_research", "investment_memo", "economic_calendar",
        "earnings_revisions"
    ],
    "risk": [
        "master_signal", "key_metrics",
        "risk_indicators", "debt_cycle", "advanced_indicators",
        "var_drawdown", "stress_tests", "factor_decomp",
        "risk_parity", "correlation", "system_health",
        "investment_memo"
    ],
    "quant": [
        "ml_signals", "ensemble", "signal_stack", "factor_rotation",
        "factor_decomp", "risk_parity", "momentum_veto",
        "horizon_tensions", "model_agreement", "cta_trends",
        "var_drawdown", "system_health", "trade_ideas",
        "earnings_revisions"
    ],
    "admin": ["*"]  # all permissions
}

# Cache settings
CACHE_TTL_MINUTES = {
    "market_data": 5,
    "indicators": 15,
    "signals": 5,
    "reports": 60,
}

# Scheduler settings
SCHEDULER_TIMEZONE = "America/New_York"
DAILY_PIPELINE_HOUR = 6
DAILY_PIPELINE_MINUTE = 30
