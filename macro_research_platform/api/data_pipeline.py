# api/data_pipeline.py
# R-01: automated daily data pipeline for the Macro Terminal
# Fetches FRED + yfinance, validates, writes CSV, clears cache
# Runs on schedule via APScheduler — no manual refresh needed

import logging
import math
import os
import time
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

CSV_PATH = Path("data/us_economic_data.csv")

PIPELINE_BOUNDS = {
    "cpi_yoy":       (-5.0,    25.0),
    "gdp_growth":    (-15.0,   15.0),
    "hy_spread_bps": (50.0,    2500.0),
    "vix":           (5.0,     90.0),
    "fed_funds":     (0.0,     25.0),
    "yield_curve":   (-300.0,  300.0),
    "sahm_rule":     (-2.0,    5.0),
    "m2_level":      (10000.0, 35000.0),
    "unemployment":  (1.0,     20.0),
    # Yield curve tenor bounds
    "yield_3m":      (0.0,     15.0),
    "yield_2y":      (0.0,     15.0),
    "yield_5y":      (0.0,     15.0),
    "yield_10y":     (0.0,     15.0),
    "yield_30y":     (0.0,     15.0),
    "spread_3m10y":  (-5.0,    10.0),
}

PIPELINE_FALLBACKS = {
    "cpi_yoy":       3.3,
    "gdp_growth":    2.0,
    "hy_spread_bps": 283.0,
    "vix":           20.0,
    "fed_funds":     3.64,
    "yield_curve":   65.0,
    "sahm_rule":     0.20,
    "m2_level":      21500.0,
    "unemployment":  4.2,
    # Yield curve tenor fallbacks (approximate current values)
    "yield_3m":      4.3,
    "yield_2y":      3.8,
    "yield_5y":      3.9,
    "yield_10y":     4.2,
    "yield_30y":     4.5,
    "spread_3m10y":  -0.1,
}


def fetch_fred_value(series_id: str, api_key: str):
    import requests as req
    if not api_key:
        logger.warning(f"[PIPELINE] No FRED key for {series_id}")
        return None
    try:
        r = req.get(
            "https://api.stlouisfed.org/fred/series/observations",
            params={
                "series_id":  series_id,
                "limit":      5,
                "sort_order": "desc",
                "api_key":    api_key,
                "file_type":  "json",
            },
            timeout=12,
        )
        for obs in r.json().get("observations", []):
            if obs["value"] not in (".", ""):
                val = float(obs["value"])
                logger.info(f"[PIPELINE] FRED {series_id}={val}")
                return val
    except Exception as e:
        logger.warning(f"[PIPELINE] FRED {series_id} failed: {e}")
    return None


def fetch_yf_close(ticker: str, period: str = "5d"):
    try:
        hist = yf.Ticker(ticker).history(period=period)
        if not hist.empty:
            val = float(hist["Close"].iloc[-1])
            logger.info(f"[PIPELINE] YF {ticker}={val}")
            return val
    except Exception as e:
        logger.warning(f"[PIPELINE] YF {ticker} failed: {e}")
    return None


def validate_pipeline_value(metric_name: str, raw_value) -> float:
    fallback = PIPELINE_FALLBACKS.get(metric_name, 0.0)
    if raw_value is None:
        logger.warning(f"[PIPELINE] {metric_name}: None -> fallback {fallback}")
        return fallback
    try:
        v = float(raw_value)
    except (TypeError, ValueError):
        logger.error(f"[PIPELINE] {metric_name}: not numeric -> fallback {fallback}")
        return fallback
    if not math.isfinite(v):
        logger.error(f"[PIPELINE] {metric_name}: NaN/Inf -> fallback {fallback}")
        return fallback
    lo, hi = PIPELINE_BOUNDS.get(metric_name, (-1e9, 1e9))
    if not (lo <= v <= hi):
        logger.error(
            f"[PIPELINE] {metric_name}={v} outside [{lo},{hi}] -> fallback {fallback}"
        )
        return fallback
    return v


def fetch_all_latest_values() -> dict:
    from api.config import FRED_API_KEY as _config_fred_key
    api_key = _config_fred_key or os.getenv("FRED_API_KEY", "")

    today = date.today().isoformat()
    row   = {"date": today}

    fred_map = {
        "cpi_yoy":       ("CPIAUCSL_PC1",    "cpi_yoy",       1.0),
        "gdp_growth":    ("A191RL1Q225SBEA", "gdp_growth",    1.0),
        "fed_funds":     ("FEDFUNDS",        "fed_funds",     1.0),
        "hy_spread_bps": ("BAMLH0A0HYM2",   "hy_spread_bps", 100.0),
        "sahm_rule":     ("SAHMREALTIME",    "sahm_rule",     1.0),
        "t10y2y_bps":    ("T10Y2Y",          "yield_curve",   100.0),
        "unemployment":  ("UNRATE",          "unemployment",  1.0),
        "m2_level":      ("M2SL",            "m2_level",      1.0),
        # Yield curve tenors for rates endpoint
        "yield_3m":      ("TB3MS",           "yield_3m",      1.0),
        "yield_2y":      ("DGS2",            "yield_2y",      1.0),
        "yield_5y":      ("DGS5",            "yield_5y",      1.0),
        "yield_10y":     ("DGS10",           "yield_10y",     1.0),
        "yield_30y":     ("DGS30",           "yield_30y",     1.0),
        "spread_3m10y":  ("T10Y3M",          "spread_3m10y",  1.0),
    }

    for col, (series, metric, multiply) in fred_map.items():
        raw = fetch_fred_value(series, api_key)
        if raw is not None:
            raw = raw * multiply
        row[col] = validate_pipeline_value(metric, raw)
        time.sleep(0.1)  # Rate limit protection

    yf_map = {
        "spy_close": "SPY",
        "vix":       "^VIX",
        "tlt_close": "TLT",
        "gld_close": "GLD",
        "hyg_close": "HYG",
        "dbc_close": "DBC",
        "eem_close": "EEM",
        "efa_close": "EFA",
        "iwm_close": "IWM",
        "tip_close": "TIP",
        "dxy":       "DX-Y.NYB",
        "vvix":      "^VVIX",
    }

    for col, ticker in yf_map.items():
        val = fetch_yf_close(ticker)
        if val is not None and math.isfinite(val) and val > 0:
            row[col] = round(val, 4)
        else:
            logger.warning(f"[PIPELINE] {ticker} invalid: {val}")

    m2_current = row.get("m2_level")
    if m2_current:
        try:
            df     = pd.read_csv(CSV_PATH, index_col=0, parse_dates=True)
            df     = df.sort_index()
            m2_col = next(
                (c for c in df.columns if "m2" in c.lower()), None
            )
            if m2_col and len(df) >= 13:
                m2_year_ago = float(df[m2_col].iloc[-13])
                if m2_year_ago > 0:
                    row["m2_yoy"] = round(
                        (m2_current / m2_year_ago - 1) * 100, 2
                    )
                    logger.info(f"[PIPELINE] M2 YoY={row['m2_yoy']}%")
        except Exception as e:
            logger.warning(f"[PIPELINE] M2 YoY failed: {e}")

    logger.info(f"[PIPELINE] Fetched {len(row)} fields for {today}")
    return row


def validate_before_csv_write(df: pd.DataFrame) -> pd.DataFrame:
    """
    Validate and fix NaN values before writing CSV.
    Critical columns are forward-filled; others logged.
    """
    critical_cols = [
        'us_cpi', 'core_cpi_yoy', 'hy_spreads', 'equity_momentum_12m',
        'fed_funds_rate', 'vix', 'us_10y_yield', 'us_2y_yield',
        'yield_3m', 'yield_2y', 'yield_5y', 'yield_10y', 'yield_30y',
    ]

    for col in critical_cols:
        if col not in df.columns:
            logger.warning(f"[PIPELINE] Missing critical column: {col}")
            continue

        n_nan = df[col].isna().sum()
        if n_nan > 0:
            # Forward fill, then backward fill any remaining NaN at start
            df[col] = df[col].ffill().bfill()
            logger.warning(f"[PIPELINE] {col}: forward-filled {n_nan} NaN values")

        # Verify last value is not NaN
        if pd.isna(df[col].iloc[-1]):
            logger.error(f"[PIPELINE] {col} STILL NaN after fill — using last valid")
            last_valid = df[col].dropna().iloc[-1] if not df[col].dropna().empty else None
            if last_valid is not None:
                df.loc[df.index[-1], col] = last_valid

    return df


def update_csv(row: dict) -> bool:
    if len(row) < 5:
        logger.error(f"[PIPELINE] Only {len(row)} fields — aborting")
        return False
    try:
        df = pd.read_csv(CSV_PATH, index_col=0, parse_dates=True)
    except Exception as e:
        logger.error(f"[PIPELINE] Cannot read CSV: {e}")
        return False

    today_ts = pd.Timestamp(date.today().isoformat())
    if today_ts in df.index:
        df = df.drop(today_ts)
        logger.info(f"[PIPELINE] Replacing row for {today_ts.date()}")

    new_row = pd.Series(name=today_ts, dtype=object)
    for col in df.columns:
        new_row[col] = row.get(col, float("nan"))

    df = pd.concat([df, new_row.to_frame().T])
    df.index = pd.to_datetime(df.index)
    df = df.sort_index()

    # P1-FIX-3: Validate and fix NaN values before writing
    df = validate_before_csv_write(df)

    try:
        df.to_csv(CSV_PATH)
        logger.info(
            f"[PIPELINE] CSV updated: rows={len(df)} "
            f"latest={df.index.max().date()}"
        )
        return True
    except Exception as e:
        logger.error(f"[PIPELINE] CSV write failed: {e}")
        return False


def invalidate_cache(cache_obj: dict, lock) -> None:
    with lock:
        cache_obj["data"]      = None
        cache_obj["timestamp"] = 0.0
    logger.info("[PIPELINE] Cache cleared — next request recomputes")


def run_daily_pipeline(dashboard_cache: dict, cache_lock) -> dict:
    t0 = time.time()
    logger.info(f"[PIPELINE] Starting at {datetime.now().isoformat()}")

    status = {
        "started_at":       datetime.now().isoformat(),
        "fields_fetched":   0,
        "csv_updated":      False,
        "cache_cleared":    False,
        "duration_seconds": 0.0,
        "error":            None,
    }

    try:
        row = fetch_all_latest_values()
        status["fields_fetched"] = len(row)

        success = update_csv(row)
        status["csv_updated"] = success

        if success:
            invalidate_cache(dashboard_cache, cache_lock)
            status["cache_cleared"] = True

    except Exception as e:
        logger.error(f"[PIPELINE] Failed: {e}", exc_info=True)
        status["error"] = str(e)

    status["duration_seconds"] = round(time.time() - t0, 1)
    logger.info(f"[PIPELINE] Done: {status}")
    return status
