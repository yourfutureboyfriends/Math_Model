"""
Macro data and regime state: loading the processed macro dataset and turning it into the regime, its scores and the
risk indicators that the dashboard, the Daily Brief, /api/regime and the fund panels read.

Public functions
    load_processed_data()              the latest processed macro dataset (data/processed/live), or None — never the
                                       synthetic sample silently
    get_regime_data(df=None)           current regime (Goldilocks / Reflation / Stagflation / Slowdown / Recession),
                                       growth and inflation scores, confidence and drivers (RegimeData schema);
                                       logs the forecast to the forecast tracker
    get_risk_indicators(df)            credit spreads, curve, volatility and other risk gauges (RiskIndicatorsData)
    _monthly_regime_frame()            month-by-month regime history (used by the model scorecard)
    _fetch_fresh_fred_value(series)    a single FRED series' latest value, cached briefly
    _get(df, *names) / _series(...)    tolerant column access on the dataset (first matching name wins)

Model inputs
    When the research library is available (src.features.macro_features, src.models.macro_regime.regime_model),
    group scores come from it; otherwise a documented fallback scoring is used and reported as such.

Data honesty
    Missing inputs are reported as missing — values are never fabricated. Stale data is labelled by its date.
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

from api.schemas.models import (DebtCycleResult, InternationalMacroResult, RegimeBacktestResult, RegimeData,
                                RiskIndicator, RiskIndicatorsData)
from api.services.forecast_tracker import forecast_tracker

logger = logging.getLogger(__name__)

try:                                   # optional research library (src/): richer group scores when present
    from src.models.macro_regime.regime_model import compute_group_scores
    _REGIME_MODEL_OK = True
except Exception as _e:                # noqa: BLE001
    logger.warning("regime_model import failed: %s", _e)
    _REGIME_MODEL_OK = False
try:
    from src.features.macro_features import compute_all_transforms as compute_all_features
    _FEATURES_OK = True
except Exception as _e:                # noqa: BLE001
    logger.warning("macro_features import failed: %s", _e)
    _FEATURES_OK = False


PROJECT_ROOT = Path(__file__).resolve().parent.parent
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

_FRESH_FRED: dict = {}   # series_id -> (expires_at, value); these are monthly/daily series
_FRESH_FRED_TTL, _FRESH_FRED_FAIL_TTL = 1800, 300


def _fetch_fresh_fred_value(series_id: str) -> Optional[float]:
    """
    Fresh value from FRED for critical metrics, cached 30 min (5 min after a failure) —
    FRED is rate-limited and these series move monthly, so re-fetching on every request
    only queued callers behind the rate-limit guard.
    Returns None if FRED API key not configured or fetch fails.
    """
    import time as _t
    hit = _FRESH_FRED.get(series_id)
    if hit and hit[0] > _t.time():
        return hit[1]
    val = _fetch_fresh_fred_value_uncached(series_id)
    _FRESH_FRED[series_id] = (_t.time() + (_FRESH_FRED_TTL if val is not None else _FRESH_FRED_FAIL_TTL), val)
    return val


def _fetch_fresh_fred_value_uncached(series_id: str) -> Optional[float]:
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


_CSV_CACHE: dict = {}


def _read_csv_cached(path) -> pd.DataFrame:
    """read_csv keyed by the file's mtime; returns a copy so callers can patch it."""
    mtime = path.stat().st_mtime
    hit = _CSV_CACHE.get(str(path))
    if not hit or hit[0] != mtime:
        hit = (mtime, pd.read_csv(path, index_col=0, parse_dates=True))
        _CSV_CACHE[str(path)] = hit
    return hit[1].copy()


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
            df = _read_csv_cached(csv_file)
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
