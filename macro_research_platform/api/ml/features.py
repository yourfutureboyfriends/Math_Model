"""
Feature store for the ML engine: monthly series, each value as it was known at that month (built from data through
the previous month), so any task can draw on them without look-ahead.

Sources are free: the Federal Reserve curve and EBP files and ALFRED payroll vintages (via the recession ensemble's
cached inputs), FRED monthly series, and Yahoo index closes. Each source is cached on disk for a day; a source that
fails is simply absent and the tasks that need it say so.
"""
from __future__ import annotations

import logging
from typing import Callable, Dict, List

import numpy as np

logger = logging.getLogger(__name__)

# key → (label, unit, how it is built)
FEATURES: Dict[str, tuple] = {
    "ts": ("10Y–3M Treasury spread", "pp", "Fed GSW zero-coupon curve, monthly average"),
    "ntfs": ("Near-term forward spread", "pp", "Engstrom–Sharpe, from the GSW curve"),
    "ebp": ("Excess bond premium", "pp", "Gilchrist–Zakrajšek, Federal Reserve"),
    "pay6": ("Payroll growth, 6m annualised", "%", "nonfarm payrolls as first published (ALFRED)"),
    "baa": ("Baa – 10Y spread", "pp", "Moody's Baa yield minus 10Y Treasury"),
    "spx6": ("S&P 500, 6-month return", "%", "log change of monthly average closes"),
    "spx_vol3": ("S&P 500 realised volatility, 3m", "% ann.", "daily returns over the last 3 months"),
    "y10": ("10Y Treasury yield", "%", "FRED GS10"),
    "y10_d3": ("10Y yield, 3-month change", "pp", "FRED GS10"),
    "ff": ("Fed funds rate", "%", "FRED FEDFUNDS"),
    "cpi_yoy": ("CPI inflation, y/y", "%", "FRED CPIAUCSL"),
    "cpi_d3": ("CPI inflation, 3-month change of y/y", "pp", "FRED CPIAUCSL"),
    "unemp_d6": ("Unemployment rate, 6-month change", "pp", "FRED UNRATE"),
    "oil6": ("Oil price, 6-month change", "%", "FRED WTISPLC"),
    "sent_d6": ("Consumer sentiment, 6-month change", "pts", "FRED UMCSENT"),
    "usd6": ("US dollar index, 6-month change", "%", "Yahoo DX-Y.NYB"),
}

# Text and news — numbers built from newspaper and press text (the 'text as data' sources central banks and macro
# funds use). Some start in 1985, so they are a separate block that models able to handle gaps (trees, the deep
# network) use, while the factor and logistic models keep their full history.
TEXT: Dict[str, tuple] = {
    "t_news": ("News sentiment (SF Fed)", "index", "Federal Reserve Bank of San Francisco Daily News Sentiment, monthly average"),
    "t_news_d3": ("News sentiment, 3-month change", "index", "SF Fed Daily News Sentiment"),
    "t_epu": ("Economic policy uncertainty", "log", "Baker, Bloom & Davis newspaper index (FRED USEPUINDXM)"),
    "t_emv": ("Equity-market volatility news tracker", "index", "Baker, Bloom, Davis & Kost (FRED EMVOVERALLEMV)"),
    "t_emv_macro": ("EMV tracker: macroeconomic news", "index", "FRED EMVMACROBUS"),
    "t_emv_fin": ("EMV tracker: financial-crisis news", "index", "FRED EMVFINCRISES"),
}
SF_NEWS_URL = "https://www.frbsf.org/wp-content/uploads/news_sentiment_data.xlsx"


def _known(s, months_lag: int = 1) -> Dict[str, float]:
    """A monthly pandas series → {YYYY-MM: value known at that month} (shifted by the publication lag)."""
    s = s.shift(months_lag).dropna()
    return {d.strftime("%Y-%m"): float(v) for d, v in s.items() if np.isfinite(v)}


def _fred_monthly(series_id: str):
    import pandas as pd
    from api.models_ml.recession_ensemble import _fred
    s = _fred().get_series(series_id).dropna()
    s.index = pd.to_datetime(s.index)
    return s.resample("MS").mean()


def _yahoo_daily(symbol: str):
    import pandas as pd
    from api.marketdata.core import yahoo_download
    df = yahoo_download(symbol, period="max", interval="1d", auto_adjust=True)
    c = df["Close"]
    if isinstance(c, pd.DataFrame):
        c = c.iloc[:, 0]
    c.index = pd.to_datetime(c.index).tz_localize(None)
    return c.dropna()


def _build_fred() -> Dict[str, Dict[str, float]]:
    out: Dict[str, Dict[str, float]] = {}
    jobs: List[tuple] = [
        ("y10", "GS10", lambda m: m), ("y10_d3", "GS10", lambda m: m.diff(3)), ("ff", "FEDFUNDS", lambda m: m),
        ("cpi_yoy", "CPIAUCSL", lambda m: (m / m.shift(12) - 1) * 100),
        ("cpi_d3", "CPIAUCSL", lambda m: ((m / m.shift(12) - 1) * 100).diff(3)),
        ("unemp_d6", "UNRATE", lambda m: m.diff(6)), ("oil6", "WTISPLC", lambda m: np.log(m).diff(6) * 100),
        ("sent_d6", "UMCSENT", lambda m: m.diff(6)),
    ]
    cache: Dict[str, object] = {}
    for key, sid, fn in jobs:
        try:
            if sid not in cache:
                cache[sid] = _fred_monthly(sid)
            out[key] = _known(fn(cache[sid]), 1)
        except Exception as e:                                         # noqa: BLE001 — absent feature, reported later
            logger.warning("[ml.features] %s (%s) unavailable: %s", key, sid, e)
    return out


def _build_market() -> Dict[str, Dict[str, float]]:
    out: Dict[str, Dict[str, float]] = {}
    try:
        spx = _yahoo_daily("^GSPC")
        m = spx.resample("MS").mean()
        out["spx6"] = _known(np.log(m).diff(6) * 100, 1)
        vol = np.log(spx).diff().rolling(63).std() * np.sqrt(252) * 100
        out["spx_vol3"] = _known(vol.resample("MS").last(), 1)
    except Exception as e:                                             # noqa: BLE001
        logger.warning("[ml.features] S&P 500 unavailable: %s", e)
    try:
        usd = _yahoo_daily("DX-Y.NYB").resample("MS").mean()
        out["usd6"] = _known(np.log(usd).diff(6) * 100, 1)
    except Exception as e:                                             # noqa: BLE001
        logger.warning("[ml.features] dollar index unavailable: %s", e)
    return out


def _build_text() -> Dict[str, Dict[str, float]]:
    import io
    import pandas as pd
    import requests
    out: Dict[str, Dict[str, float]] = {}
    try:
        r = requests.get(SF_NEWS_URL, headers={"User-Agent": "Mozilla/5.0 (macro research terminal)"}, timeout=60)
        r.raise_for_status()
        d = pd.read_excel(io.BytesIO(r.content), sheet_name="Data")
        s = d.set_index(pd.to_datetime(d["date"]))["News Sentiment"].astype(float).resample("MS").mean()
        out["t_news"] = _known(s, 1)
        out["t_news_d3"] = _known(s.diff(3), 1)
    except Exception as e:                                             # noqa: BLE001
        logger.warning("[ml.features] SF Fed news sentiment unavailable: %s", e)
    for key, sid, fn in (("t_epu", "USEPUINDXM", lambda m: np.log(m)), ("t_emv", "EMVOVERALLEMV", lambda m: m),
                         ("t_emv_macro", "EMVMACROBUS", lambda m: m), ("t_emv_fin", "EMVFINCRISES", lambda m: m)):
        try:
            out[key] = _known(fn(_fred_monthly(sid)), 1)
        except Exception as e:                                         # noqa: BLE001
            logger.warning("[ml.features] %s unavailable: %s", sid, e)
    return out


def load_text() -> Dict[str, Dict[str, float]]:
    from api import research_indicators as ri
    got, _ = ri._cached("ml_text", _build_text)
    return got or {}


def load() -> Dict[str, Dict[str, float]]:
    """{feature: {month: value}} for every available feature."""
    from api import research_indicators as ri
    from api.models_ml import recession_ensemble as R
    feats: Dict[str, Dict[str, float]] = {}
    data, _ = R._inputs()
    if data:
        for k in ("ts", "ntfs", "ebp", "pay6", "baa"):
            feats[k] = {r["month"]: r[k] for r in data["rows"] if r.get(k) is not None}
    for name, builder in (("ml_fred", _build_fred), ("ml_market", _build_market)):
        got, _ = ri._cached(name, builder)
        feats.update(got or {})
    return feats


def coverage(feats: Dict[str, Dict[str, float]]) -> Dict[str, Dict[str, object]]:
    return {k: {"label": FEATURES.get(k, (k,))[0], "from": min(v) if v else None, "to": max(v) if v else None, "months": len(v)}
            for k, v in feats.items()}


Builder = Callable[[], Dict[str, Dict[str, float]]]
