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

CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "us_economic_data.csv"

PIPELINE_BOUNDS = {
    "cpi_yoy":       (-5.0,    25.0),
    "gdp_growth":    (-15.0,   15.0),
    "hy_spread_bps": (50.0,    2500.0),
    "vix":           (5.0,     90.0),
    "fed_funds":     (0.0,     25.0),
    "yield_curve":   (-5.0,    5.0),     # percentage points (T10Y2Y), as stored in the CSV
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
    "m2_yoy":        (-20.0,   40.0),
}

def fetch_fred_value(series_id: str, api_key: str):
    """Latest observation of a FRED series. A `_PC1` / `_PCH` / `_PCA` suffix is a FRED
    `units` transform (e.g. CPIAUCSL_PC1 = CPI YoY %), not part of the series id — it used
    to be sent as the id, so CPI YoY never fetched."""
    import requests as req
    if not api_key:
        logger.warning(f"[PIPELINE] No FRED key for {series_id}")
        return None
    real_id, units = series_id, "lin"
    for suffix, unit in (("_PC1", "pc1"), ("_PCH", "pch"), ("_PCA", "pca")):
        if series_id.endswith(suffix):
            real_id, units = series_id[: -len(suffix)], unit
            break
    params = {"series_id": real_id, "units": units, "limit": 5, "sort_order": "desc",
              "api_key": api_key, "file_type": "json"}
    for attempt in range(3):          # FRED rate-limits bursts (HTTP 429): back off and retry
        try:
            r = req.get("https://api.stlouisfed.org/fred/series/observations",
                        params=params, timeout=12)
            if r.status_code == 429:
                time.sleep(2 * (attempt + 1))
                continue
            for obs in r.json().get("observations", []):
                if obs["value"] not in (".", ""):
                    val = float(obs["value"])
                    logger.info(f"[PIPELINE] FRED {series_id}={val}")
                    return val
            return None
        except Exception as e:
            logger.warning(f"[PIPELINE] FRED {series_id} attempt {attempt + 1} failed: {e}")
            time.sleep(1 + attempt)
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


def validate_pipeline_value(metric_name: str, raw_value):
    """The value as a float if it is numeric, finite and within PIPELINE_BOUNDS;
    otherwise None. Rejected values are NOT replaced with a default — the CSV cell stays
    empty rather than recording a made-up number as data."""
    if raw_value is None:
        logger.warning(f"[PIPELINE] {metric_name}: missing")
        return None
    try:
        v = float(raw_value)
    except (TypeError, ValueError):
        logger.error(f"[PIPELINE] {metric_name}: not numeric ({raw_value!r}) — rejected")
        return None
    if not math.isfinite(v):
        logger.error(f"[PIPELINE] {metric_name}: NaN/Inf — rejected")
        return None
    lo, hi = PIPELINE_BOUNDS.get(metric_name, (-1e9, 1e9))
    if not (lo <= v <= hi):
        logger.error(f"[PIPELINE] {metric_name}={v} outside [{lo},{hi}] — rejected")
        return None
    return v


# FRED series -> (bounds key, multiplier, CSV columns that hold this quantity).
# Every CSV column that represents the same quantity is written together so duplicate
# columns (e.g. yield_10y / us_10y_yield) can't disagree.
_FRED_MAP = {
    "CPIAUCSL_PC1":    ("cpi_yoy",       1.0,   ["us_cpi"]),
    "CPILFESL_PC1":    ("cpi_yoy",       1.0,   ["core_cpi_yoy"]),
    "A191RL1Q225SBEA": ("gdp_growth",    1.0,   ["gdp_growth"]),
    "FEDFUNDS":        ("fed_funds",     1.0,   ["us_fed_funds"]),
    "BAMLH0A0HYM2":    ("hy_spread_bps", 100.0, ["hy_spreads"]),
    "UNRATE":          ("unemployment",  1.0,   ["unemployment_rate", "us_unemployment"]),
    "M2SL":            ("m2_level",      1.0,   ["us_m2"]),
    "M2SL_PC1":        ("m2_yoy",        1.0,   ["money_supply_yoy", "us_m2_growth"]),
    "TB3MS":           ("yield_3m",      1.0,   ["yield_3m"]),
    "DGS2":            ("yield_2y",      1.0,   ["yield_2y", "us_2y_yield"]),
    "DGS5":            ("yield_5y",      1.0,   ["yield_5y"]),
    "DGS10":           ("yield_10y",     1.0,   ["yield_10y", "us_10y_yield", "us_treasury_10y"]),
    "DGS30":           ("yield_30y",     1.0,   ["yield_30y"]),
    "T10Y2Y":          ("yield_curve",   1.0,   ["yield_curve", "yield_curve_spread"]),   # pp, as stored
    "T10Y3M":          ("spread_3m10y",  1.0,   ["spread_3m10y"]),
}

# Yahoo ticker -> CSV columns (closing levels).
_YF_MAP = {
    "^VIX": ["vix", "vixcls"], "DX-Y.NYB": ["dollar_index"], "^GSPC": ["equity_index"],
    "CL=F": ["oil_price"], "SPY": ["SPY"], "TLT": ["TLT"], "GLD": ["GLD"], "DBC": ["DBC"],
    "HYG": ["HYG"], "IEF": ["IEF"], "EFA": ["EFA"], "EEM": ["EEM"], "IWM": ["IWM"],
    "QQQ": ["QQQ"],
}


def fetch_all_latest_values() -> dict:
    """Latest real value for every CSV column the pipeline can source, keyed by CSV
    column. Columns whose source fails or is out of bounds are simply absent."""
    from api.config import FRED_API_KEY as _config_fred_key
    api_key = _config_fred_key or os.getenv("FRED_API_KEY", "")

    row: dict = {}
    for series, (bound_key, mult, cols) in _FRED_MAP.items():
        raw = fetch_fred_value(series, api_key)
        val = validate_pipeline_value(bound_key, raw * mult if raw is not None else None)
        if val is not None:
            for c in cols:
                row[c] = round(val, 4)
        time.sleep(0.1)  # Rate limit protection

    for ticker, cols in _YF_MAP.items():
        val = fetch_yf_close(ticker)
        if val is not None and math.isfinite(val) and val > 0:
            for c in cols:
                row[c] = round(val, 4)
        else:
            logger.warning(f"[PIPELINE] {ticker} invalid: {val}")

    logger.info(f"[PIPELINE] Fetched {len(row)} columns")
    return row


def _to_monthly(df: pd.DataFrame) -> pd.DataFrame:
    """One row per calendar month (indexed by month start), keeping each column's last
    real observation within the month. Folds in any stray intra-month daily rows."""
    df = df.copy()
    df.index = pd.to_datetime(df.index).to_period("M").to_timestamp()
    return df.groupby(level=0).last().sort_index()


def update_csv(row: dict) -> bool:
    """Write this month's row: the CSV is monthly, so the current month's row is replaced
    (not a new daily row appended). Columns without a fresh real value are left empty —
    no forward-fill and no defaults."""
    if len(row) < 5:
        logger.error(f"[PIPELINE] Only {len(row)} fields — aborting")
        return False
    try:
        df = pd.read_csv(CSV_PATH, index_col=0, parse_dates=True)
    except Exception as e:
        logger.error(f"[PIPELINE] Cannot read CSV: {e}")
        return False

    df = _to_monthly(df)
    month = pd.Timestamp(date.today().replace(day=1))
    new_row = pd.Series({c: row.get(c, float("nan")) for c in df.columns}, name=month, dtype=float)
    df = df.drop(month, errors="ignore")
    df = pd.concat([df, new_row.to_frame().T]).sort_index()
    df.index.name = None

    try:
        df.to_csv(CSV_PATH)
        logger.info(f"[PIPELINE] CSV updated: rows={len(df)} latest={df.index.max().date()} "
                    f"filled={int(new_row.notna().sum())}/{len(df.columns)} columns")
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
