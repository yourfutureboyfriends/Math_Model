"""
Institutional Trade Recommendation Engine v2.0
Implements signal frameworks from:
  - AQR (Value/Momentum/QMJ/BAB/Carry Everywhere)
  - Bridgewater (Regime-Conditional Allocation, Pure Alpha)
  - Goldman Sachs (Cross-Asset Tactical Allocation)
  - Man AHL / Winton (Trend Following, Vol Targeting)
  - JPMorgan Macrosynergy (Quantamental Signals)

All signals are:
  1. Computed from live data (yfinance + FRED via df)
  2. Normalised to Z-scores before combination
  3. Weighted by regime probability vector (not modal regime)
  4. Scaled by a volatility target overlay
"""

import numpy as np
import pandas as pd
import yfinance as yf
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# SECTION A: ASSET UNIVERSE
# Defined by class + key attributes needed for signal computation.
# Tickers are yfinance-compatible for live data fetching.
# ──────────────────────────────────────────────────────────────

# Master universe — grouped by asset class.
# Each entry has the metadata needed across all 7 signal layers.
UNIVERSE = {

  # ── MACRO EQUITY ETFs ──────────────────────────────────────
  "SPY":  {"name":"S&P 500",           "class":"equity_etf",  "region":"US",
           "sector":"broad",  "beta_est":1.00, "div_yield":1.3,
           "carry_proxy":"div_yield"},
  "QQQ":  {"name":"Nasdaq 100",        "class":"equity_etf",  "region":"US",
           "sector":"technology","beta_est":1.18,"div_yield":0.6,
           "carry_proxy":"div_yield"},
  "IWM":  {"name":"Russell 2000",      "class":"equity_etf",  "region":"US",
           "sector":"small_cap","beta_est":1.12,"div_yield":1.4,
           "carry_proxy":"div_yield"},
  "EFA":  {"name":"MSCI EAFE",         "class":"equity_etf",  "region":"DM",
           "sector":"intl_dm", "beta_est":0.85, "div_yield":3.1,
           "carry_proxy":"div_yield"},
  "EEM":  {"name":"MSCI EM",           "class":"equity_etf",  "region":"EM",
           "sector":"intl_em", "beta_est":0.90, "div_yield":2.8,
           "carry_proxy":"div_yield"},
  "EWJ":  {"name":"Japan (MSCI)",      "class":"equity_etf",  "region":"JP",
           "sector":"intl_dm", "beta_est":0.70, "div_yield":2.4,
           "carry_proxy":"div_yield"},
  "EWZ":  {"name":"Brazil (MSCI)",     "class":"equity_etf",  "region":"EM",
           "sector":"intl_em", "beta_est":1.10, "div_yield":5.2,
           "carry_proxy":"div_yield"},
  "MCHI": {"name":"China (MSCI)",      "class":"equity_etf",  "region":"EM",
           "sector":"intl_em", "beta_est":0.95, "div_yield":2.0,
           "carry_proxy":"div_yield"},

  # ── SECTOR ETFs ────────────────────────────────────────────
  "XLE":  {"name":"Energy",            "class":"sector_etf",  "region":"US",
           "sector":"energy",  "beta_est":1.05, "div_yield":3.8,
           "carry_proxy":"div_yield"},
  "XLF":  {"name":"Financials",        "class":"sector_etf",  "region":"US",
           "sector":"financials","beta_est":1.10,"div_yield":1.9,
           "carry_proxy":"div_yield"},
  "XLK":  {"name":"Technology",        "class":"sector_etf",  "region":"US",
           "sector":"technology","beta_est":1.20,"div_yield":0.7,
           "carry_proxy":"div_yield"},
  "XLB":  {"name":"Materials",         "class":"sector_etf",  "region":"US",
           "sector":"materials","beta_est":1.05,"div_yield":1.8,
           "carry_proxy":"div_yield"},
  "XLI":  {"name":"Industrials",       "class":"sector_etf",  "region":"US",
           "sector":"industrials","beta_est":1.05,"div_yield":1.5,
           "carry_proxy":"div_yield"},
  "XLV":  {"name":"Healthcare",        "class":"sector_etf",  "region":"US",
           "sector":"healthcare","beta_est":0.75,"div_yield":1.6,
           "carry_proxy":"div_yield"},
  "XLP":  {"name":"Consumer Staples",  "class":"sector_etf",  "region":"US",
           "sector":"staples",  "beta_est":0.60, "div_yield":2.7,
           "carry_proxy":"div_yield"},
  "XLU":  {"name":"Utilities",         "class":"sector_etf",  "region":"US",
           "sector":"utilities","beta_est":0.50,"div_yield":3.2,
           "carry_proxy":"div_yield"},
  "XLRE": {"name":"Real Estate",       "class":"sector_etf",  "region":"US",
           "sector":"real_estate","beta_est":0.80,"div_yield":3.8,
           "carry_proxy":"div_yield"},
  "XLY":  {"name":"Consumer Disc",     "class":"sector_etf",  "region":"US",
           "sector":"discretionary","beta_est":1.15,"div_yield":0.8,
           "carry_proxy":"div_yield"},
  "XLC":  {"name":"Comm Services",     "class":"sector_etf",  "region":"US",
           "sector":"communication","beta_est":1.00,"div_yield":0.9,
           "carry_proxy":"div_yield"},

  # ── FACTOR ETFs ────────────────────────────────────────────
  "MTUM": {"name":"Momentum Factor",   "class":"factor_etf",  "region":"US",
           "sector":"factor",  "beta_est":1.05, "div_yield":1.2,
           "carry_proxy":"div_yield"},
  "VLUE": {"name":"Value Factor",      "class":"factor_etf",  "region":"US",
           "sector":"factor",  "beta_est":0.95, "div_yield":2.8,
           "carry_proxy":"div_yield"},
  "QUAL": {"name":"Quality Factor",    "class":"factor_etf",  "region":"US",
           "sector":"factor",  "beta_est":0.90, "div_yield":1.4,
           "carry_proxy":"div_yield"},
  "USMV": {"name":"Min Volatility",    "class":"factor_etf",  "region":"US",
           "sector":"factor",  "beta_est":0.65, "div_yield":1.8,
           "carry_proxy":"div_yield"},
  "DGRO": {"name":"Dividend Growth",   "class":"factor_etf",  "region":"US",
           "sector":"factor",  "beta_est":0.85, "div_yield":2.3,
           "carry_proxy":"div_yield"},
  "IWD":  {"name":"Large Cap Value",   "class":"factor_etf",  "region":"US",
           "sector":"factor",  "beta_est":0.95, "div_yield":2.1,
           "carry_proxy":"div_yield"},

  # ── FIXED INCOME ───────────────────────────────────────────
  "TLT":  {"name":"20Y Treasury",      "class":"fixed_income","region":"US",
           "sector":"duration", "beta_est":-0.30,"div_yield":4.2,
           "carry_proxy":"yield", "yield_key":"DGS20"},
  "IEF":  {"name":"7-10Y Treasury",    "class":"fixed_income","region":"US",
           "sector":"duration", "beta_est":-0.15,"div_yield":4.0,
           "carry_proxy":"yield", "yield_key":"DGS10"},
  "SHY":  {"name":"1-3Y Treasury",     "class":"fixed_income","region":"US",
           "sector":"short_dur","beta_est":-0.05,"div_yield":4.8,
           "carry_proxy":"yield", "yield_key":"DGS2"},
  "TIP":  {"name":"TIPS",              "class":"fixed_income","region":"US",
           "sector":"inflation","beta_est":-0.05,"div_yield":2.1,
           "carry_proxy":"real_yield"},
  "HYG":  {"name":"High Yield Corp",   "class":"fixed_income","region":"US",
           "sector":"credit",   "beta_est":0.40, "div_yield":6.1,
           "carry_proxy":"yield"},
  "LQD":  {"name":"Investment Grade",  "class":"fixed_income","region":"US",
           "sector":"credit",   "beta_est":0.10, "div_yield":5.1,
           "carry_proxy":"yield"},
  "EMB":  {"name":"EM USD Bonds",      "class":"fixed_income","region":"EM",
           "sector":"em_debt",  "beta_est":0.30, "div_yield":6.8,
           "carry_proxy":"yield"},
  "BNDX": {"name":"Intl Bonds Hedged", "class":"fixed_income","region":"DM",
           "sector":"duration", "beta_est":-0.10,"div_yield":3.1,
           "carry_proxy":"yield"},

  # ── COMMODITIES ─────────────────────────────────────────────
  "GLD":  {"name":"Gold",              "class":"commodity",   "region":"GLOBAL",
           "sector":"precious", "beta_est":-0.05,"div_yield":0.0,
           "carry_proxy":"basis"},
  "SLV":  {"name":"Silver",            "class":"commodity",   "region":"GLOBAL",
           "sector":"precious", "beta_est":0.05, "div_yield":0.0,
           "carry_proxy":"basis"},
  "USO":  {"name":"WTI Crude",         "class":"commodity",   "region":"GLOBAL",
           "sector":"energy",   "beta_est":0.20, "div_yield":0.0,
           "carry_proxy":"basis"},
  "UNG":  {"name":"Natural Gas",       "class":"commodity",   "region":"US",
           "sector":"energy",   "beta_est":0.05, "div_yield":0.0,
           "carry_proxy":"basis"},
  "DBC":  {"name":"Broad Commodity",   "class":"commodity",   "region":"GLOBAL",
           "sector":"diversified","beta_est":0.15,"div_yield":0.0,
           "carry_proxy":"basis"},
  "CPER": {"name":"Copper",            "class":"commodity",   "region":"GLOBAL",
           "sector":"industrial","beta_est":0.25,"div_yield":0.0,
           "carry_proxy":"basis"},
  "WEAT": {"name":"Wheat",             "class":"commodity",   "region":"GLOBAL",
           "sector":"agriculture","beta_est":0.02,"div_yield":0.0,
           "carry_proxy":"basis"},
  "PDBC": {"name":"Optimum Yield Cmd", "class":"commodity",   "region":"GLOBAL",
           "sector":"diversified","beta_est":0.18,"div_yield":0.0,
           "carry_proxy":"basis"},

  # ── FX (via ETFs) ───────────────────────────────────────────
  "UUP":  {"name":"USD Bull",          "class":"fx",          "region":"US",
           "sector":"dxy",     "beta_est":-0.20,"div_yield":0.0,
           "carry_proxy":"rate_diff", "base_rate_key":"FEDFUNDS"},
  "FXE":  {"name":"EUR/USD",           "class":"fx",          "region":"EU",
           "sector":"g10",     "beta_est":0.15, "div_yield":0.0,
           "carry_proxy":"rate_diff"},
  "FXY":  {"name":"JPY/USD",           "class":"fx",          "region":"JP",
           "sector":"g10",     "beta_est":-0.10,"div_yield":0.0,
           "carry_proxy":"rate_diff"},
  "FXB":  {"name":"GBP/USD",           "class":"fx",          "region":"UK",
           "sector":"g10",     "beta_est":0.15, "div_yield":0.0,
           "carry_proxy":"rate_diff"},
  "FXA":  {"name":"AUD/USD",           "class":"fx",          "region":"AU",
           "sector":"commodity_fx","beta_est":0.25,"div_yield":0.0,
           "carry_proxy":"rate_diff"},
  "FXC":  {"name":"CAD/USD",           "class":"fx",          "region":"CA",
           "sector":"commodity_fx","beta_est":0.20,"div_yield":0.0,
           "carry_proxy":"rate_diff"},
  "FXF":  {"name":"CHF/USD",           "class":"fx",          "region":"CH",
           "sector":"safe_haven","beta_est":-0.10,"div_yield":0.0,
           "carry_proxy":"rate_diff"},
}


# ──────────────────────────────────────────────────────────────
# SECTION B: DATA FETCHER
# Fetches live price history and fundamental proxies via
# yfinance. Caches within a single API call lifetime.
# ──────────────────────────────────────────────────────────────

_PRICE_CACHE: dict[str, pd.DataFrame] = {}
_CACHE_TS: dict[str, datetime] = {}
CACHE_TTL_MINUTES = 60


def _fetch_prices(ticker: str,
                  period: str = "2y",
                  interval: str = "1mo") -> pd.DataFrame:
    """Fetch price history from yfinance with in-memory cache."""
    cache_key = f"{ticker}_{period}_{interval}"
    now = datetime.utcnow()
    if (cache_key in _PRICE_CACHE and
            cache_key in _CACHE_TS and
            (now - _CACHE_TS[cache_key]).seconds < CACHE_TTL_MINUTES * 60):
        return _PRICE_CACHE[cache_key]
    try:
        hist = yf.download(ticker, period=period, interval=interval,
                           progress=False, auto_adjust=True)
        if hist.empty:
            return pd.DataFrame()
        hist = hist[["Close"]].dropna()
        hist.columns = ["close"]
        _PRICE_CACHE[cache_key] = hist
        _CACHE_TS[cache_key] = now
        return hist
    except Exception as e:
        logger.warning(f"[yfinance] {ticker}: {e}")
        return pd.DataFrame()


def _fetch_all_prices(tickers: list[str],
                      period: str = "2y") -> dict[str, pd.DataFrame]:
    """Batch fetch monthly prices for all tickers."""
    import concurrent.futures
    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as ex:
        futures = {ex.submit(_fetch_prices, t, period, "1mo"): t
                   for t in tickers}
        for future in concurrent.futures.as_completed(futures):
            t = futures[future]
            try:
                results[t] = future.result()
            except Exception as e:
                logger.warning(f"[batch_fetch] {t}: {e}")
                results[t] = pd.DataFrame()
    return results


# ──────────────────────────────────────────────────────────────
# SECTION C: SIGNAL LAYER IMPLEMENTATIONS
# Each function returns a dict {ticker -> float} where
# positive = bullish signal, negative = bearish.
# All outputs are Z-score normalised before combination.
# ──────────────────────────────────────────────────────────────

def _zscore_dict(raw: dict[str, float]) -> dict[str, float]:
    """Normalise a dict of scores to Z-scores."""
    vals = np.array(list(raw.values()), dtype=float)
    finite = vals[np.isfinite(vals)]
    if len(finite) < 2:
        return {k: 0.0 for k in raw}
    mu, sigma = finite.mean(), finite.std()
    if sigma < 1e-9:
        return {k: 0.0 for k in raw}
    return {k: float((v - mu) / sigma)
            if np.isfinite(v) else 0.0
            for k, v in raw.items()}


# ── LAYER 1: MACRO REGIME SIGNAL ───────────────────────────
# Bridgewater: each asset has a known return profile in each
# of the 4 regimes. Weight by REGIME PROBABILITY VECTOR
# not just the modal regime.

# Regime return profiles: (Goldilocks, Reflation, Stagflation, Slowdown)
# Values: expected excess return relative to cash in each regime
# Based on Bridgewater All-Weather framework + historical data
REGIME_RETURNS: dict[str, tuple] = {
    # (Goldilocks, Reflation, Stagflation, Slowdown)
    "SPY":  (+3.0, +2.0, -3.0, -2.0),
    "QQQ":  (+4.0, +1.0, -4.0, -1.5),
    "IWM":  (+3.0, +3.0, -3.0, -2.5),
    "EFA":  (+2.5, +2.0, -2.5, -1.5),
    "EEM":  (+3.0, +3.0, -3.0, -2.5),
    "EWJ":  (+2.0, +1.5, -1.5, -2.0),
    "EWZ":  (+2.0, +3.0, -2.0, -3.0),
    "MCHI": (+2.0, +2.5, -2.0, -2.5),
    "XLE":  (+1.0, +4.0, +2.0, -2.0),
    "XLF":  (+3.0, +3.0, -2.0, -3.0),
    "XLK":  (+4.0, +0.5, -4.0, -1.0),
    "XLB":  (+2.0, +4.0, +0.5, -3.0),
    "XLI":  (+2.5, +3.0, -1.5, -2.5),
    "XLV":  (+1.5, +0.5, +1.5, +2.0),
    "XLP":  (-1.0, -2.0, +2.0, +3.0),
    "XLU":  (-1.0, -3.0, +1.0, +3.0),
    "XLRE": (+1.5, +1.5, -2.0, -1.0),
    "XLY":  (+3.0, +1.0, -3.0, -2.5),
    "XLC":  (+2.5, +0.5, -2.0, -1.0),
    "MTUM": (+2.5, +2.5, -1.5, -1.0),
    "VLUE": (+1.0, +3.5, +0.5, -1.5),
    "QUAL": (+2.0, -0.5, +1.0, +2.5),
    "USMV": (+0.5, -2.0, +2.0, +2.0),
    "DGRO": (+1.5, +0.5, +1.0, +1.5),
    "IWD":  (+1.0, +3.0, +0.5, -1.5),
    "TLT":  (+2.0, -4.0, -2.0, +4.0),
    "IEF":  (+1.5, -2.5, -1.0, +3.0),
    "SHY":  (+0.5, -0.5, +0.5, +1.0),
    "TIP":  (+0.5, +3.5, +3.5, +0.5),
    "HYG":  (+2.5, +2.0, -3.5, -3.0),
    "LQD":  (+1.5, -1.0, -1.0, +1.5),
    "EMB":  (+1.5, +2.0, -2.0, -2.0),
    "BNDX": (+1.0, -1.5, -0.5, +2.0),
    "GLD":  (-1.0, +2.5, +3.5, +1.0),
    "SLV":  (-0.5, +2.0, +2.5, +0.5),
    "USO":  (+0.5, +4.0, +2.0, -2.5),
    "UNG":  (+0.0, +2.0, +2.5, -0.5),
    "DBC":  (+0.5, +3.5, +2.5, -2.0),
    "CPER": (+2.5, +3.0, -1.0, -3.0),
    "WEAT": (-0.5, +1.5, +2.5, -0.5),
    "PDBC": (+0.5, +3.5, +2.0, -2.0),
    "UUP":  (+0.5, -1.0, +1.5, +1.5),
    "FXE":  (+1.0, +1.5, -1.0, -0.5),
    "FXY":  (-1.0, -2.0, +0.5, +2.5),
    "FXB":  (+1.0, +0.5, -1.0, -0.5),
    "FXA":  (+1.5, +2.5, -1.5, -2.0),
    "FXC":  (+1.0, +2.5, -1.0, -1.5),
    "FXF":  (-0.5, -1.0, +1.5, +2.0),
}

def compute_regime_signal(
    regime_probs: dict[str, float]
) -> dict[str, float]:
    """
    Bridgewater-style regime-conditional expected return.
    Takes REGIME PROBABILITY VECTOR (not modal regime) so that
    uncertainty is properly reflected in signal strength.
    regime_probs: {"Goldilocks":0.16,"Reflation":0.54,
                   "Stagflation":0.11,"Slowdown":0.19}
    """
    p = {
        "Goldilocks":  float(regime_probs.get("Goldilocks",  0.25)),
        "Reflation":   float(regime_probs.get("Reflation",   0.25)),
        "Stagflation": float(regime_probs.get("Stagflation", 0.25)),
        "Slowdown":    float(regime_probs.get("Slowdown",    0.25)),
    }
    # Normalise probabilities
    total = sum(p.values())
    if total > 0:
        p = {k: v / total for k, v in p.items()}

    raw = {}
    for ticker, returns in REGIME_RETURNS.items():
        gold, refl, stag, slow = returns
        expected = (p["Goldilocks"]  * gold +
                    p["Reflation"]   * refl +
                    p["Stagflation"] * stag +
                    p["Slowdown"]    * slow)
        raw[ticker] = float(expected)

    return _zscore_dict(raw)


# ── LAYER 2: VALUE SIGNAL ──────────────────────────────────
# AQR "Value Everywhere": different value metrics by asset class
# For ETFs: use P/E relative to history (from yfinance info)
# For bonds: yield vs long-run average (from FRED df)
# For FX: real effective exchange rate deviation (from df)
# For commodities: price vs 3Y historical average (mean reversion)

def compute_value_signal(
    prices: dict[str, pd.DataFrame],
    df: pd.DataFrame,  # FRED data
    fed_funds: float,
) -> dict[str, float]:
    """
    AQR Value Everywhere signal.
    Returns Z-scored value scores (high = cheap = bullish).
    """
    raw = {}

    for ticker, asset in UNIVERSE.items():
        hist = prices.get(ticker, pd.DataFrame())
        if hist.empty or len(hist) < 12:
            raw[ticker] = 0.0
            continue

        close = hist["close"]

        if asset["class"] in ("equity_etf","sector_etf","factor_etf"):
            # Value proxy: price vs its own 3Y trailing average
            # (mean reversion component of AQR value)
            avg_36 = close.tail(36).mean() if len(close) >= 36 \
                     else close.mean()
            current = float(close.iloc[-1])
            if avg_36 > 0:
                # Negative: cheaper (below avg) = positive value signal
                val = -(current / avg_36 - 1.0)
            else:
                val = 0.0
            # Also use div yield as carry/value proxy
            div_y = asset.get("div_yield", 0.0) / 100.0
            raw[ticker] = val * 0.6 + div_y * 0.4

        elif asset["class"] == "fixed_income":
            # Bond value = current yield vs 5Y average yield
            # Higher yield relative to history = cheap = positive
            yield_key = asset.get("yield_key")
            if yield_key and yield_key in df.columns:
                y_series = df[yield_key].dropna()
                if len(y_series) >= 12:
                    current_y = float(y_series.iloc[-1])
                    avg_y = float(y_series.tail(60).mean())
                    raw[ticker] = (current_y - avg_y) / max(avg_y, 0.01)
                else:
                    raw[ticker] = asset.get("div_yield", 3.0) / 100.0
            else:
                raw[ticker] = asset.get("div_yield", 3.0) / 100.0

        elif asset["class"] == "commodity":
            # Commodity value = price vs 3Y trailing average
            # (production cost mean reversion, AQR framework)
            if len(close) >= 12:
                avg_36 = close.tail(36).mean() if len(close) >= 36 \
                         else close.mean()
                current = float(close.iloc[-1])
                # Below 3Y avg = cheap = positive value
                raw[ticker] = -(current / avg_36 - 1.0) if avg_36 > 0 \
                               else 0.0
            else:
                raw[ticker] = 0.0

        elif asset["class"] == "fx":
            # FX value = real purchasing power parity deviation
            # Proxy: price vs 3Y average (simplified PPP)
            if len(close) >= 12:
                avg = close.tail(36).mean() if len(close) >= 36 \
                      else close.mean()
                raw[ticker] = -(float(close.iloc[-1]) / avg - 1.0) \
                              if avg > 0 else 0.0
            else:
                raw[ticker] = 0.0

    return _zscore_dict(raw)


# ── LAYER 3: MOMENTUM SIGNAL ───────────────────────────────
# AQR "Momentum Everywhere" + Man AHL trend following
# Combined: cross-sectional 12-1 + time-series EWMA trend
# Multiple horizons: 1M (short), 3M (medium), 12M (long)
# Vol-normalised as per Man AHL/Winton approach

def compute_momentum_signal(
    prices: dict[str, pd.DataFrame],
) -> dict[str, float]:
    """
    Combined cross-sectional and time-series momentum.
    AQR: 12-1 month cross-sectional momentum.
    Man AHL: EWMA fast/slow trend signal, vol-normalised.
    """
    raw_cs   = {}  # cross-sectional 12-1
    raw_ts1  = {}  # time-series 1M
    raw_ts3  = {}  # time-series 3M
    raw_ts12 = {}  # time-series 12M (12-1)

    for ticker in UNIVERSE:
        hist = prices.get(ticker, pd.DataFrame())
        if hist.empty:
            raw_cs[ticker] = raw_ts1[ticker] = 0.0
            raw_ts3[ticker] = raw_ts12[ticker] = 0.0
            continue

        close = hist["close"].dropna()
        if len(close) < 2:
            raw_cs[ticker] = raw_ts1[ticker] = 0.0
            raw_ts3[ticker] = raw_ts12[ticker] = 0.0
            continue

        # 1-month return
        r1 = float(close.iloc[-1] / close.iloc[-2] - 1) \
             if len(close) >= 2 else 0.0

        # 3-month return
        r3 = float(close.iloc[-1] / close.iloc[-4] - 1) \
             if len(close) >= 4 else 0.0

        # 12-1 momentum (skip last month, AQR convention to
        # avoid short-term reversal)
        r12 = float(close.iloc[-2] / close.iloc[-14] - 1) \
              if len(close) >= 14 else 0.0

        # Vol normalisation (Man AHL: divide by realised vol)
        monthly_rets = close.pct_change().dropna()
        vol = float(monthly_rets.tail(12).std()) \
              if len(monthly_rets) >= 6 else 0.05
        if vol < 1e-6:
            vol = 0.05

        raw_ts1[ticker]  = r1  / vol
        raw_ts3[ticker]  = r3  / vol
        raw_ts12[ticker] = r12 / vol

    # Cross-sectional: rank-based (AQR convention)
    all_r12 = {t: raw_ts12[t] for t in raw_ts12
               if np.isfinite(raw_ts12[t])}
    sorted_tickers = sorted(all_r12, key=lambda x: all_r12[x])
    n = len(sorted_tickers)
    ranks = {t: (i / max(n - 1, 1) - 0.5) * 2.0
             for i, t in enumerate(sorted_tickers)}
    for t in UNIVERSE:
        raw_cs[t] = ranks.get(t, 0.0)

    # Combine: weights from AQR/Man AHL research
    # 12-1 most predictive; 1M is noise; 3M medium
    combined = {}
    for t in UNIVERSE:
        combined[t] = (0.50 * raw_ts12.get(t, 0.0) +
                       0.30 * raw_ts3.get(t,  0.0) +
                       0.10 * raw_ts1.get(t,  0.0) +
                       0.10 * raw_cs.get(t,   0.0))

    return _zscore_dict(combined)


# ── LAYER 4: QUALITY MINUS JUNK PROXY ─────────────────────
# AQR QMJ: Profitability + Growth + Safety + Payout
# For ETFs: use volatility (safety proxy) + momentum stability
# Full QMJ needs fundamental data; proxy using available data

def compute_quality_signal(
    prices: dict[str, pd.DataFrame],
    df: pd.DataFrame,
) -> dict[str, float]:
    """
    AQR Quality Minus Junk proxy signal.
    Quality = high return stability, low drawdown, low vol.
    For ETFs without fundamental data: safety proxy only.
    """
    raw = {}

    for ticker, asset in UNIVERSE.items():
        hist = prices.get(ticker, pd.DataFrame())
        if hist.empty or len(hist) < 12:
            raw[ticker] = 0.0
            continue

        close = hist["close"].dropna()
        monthly_rets = close.pct_change().dropna()

        if len(monthly_rets) < 6:
            raw[ticker] = 0.0
            continue

        # Safety component (most impactful QMJ sub-score for ETFs)
        # Low vol relative to universe = safe = high quality
        vol_12 = float(monthly_rets.tail(12).std())

        # Sharpe proxy (risk-adjusted return stability)
        ret_12 = float(monthly_rets.tail(12).mean())
        sharpe_proxy = ret_12 / max(vol_12, 1e-6)

        # Drawdown component (low max drawdown = high quality)
        prices_12 = close.tail(13)
        if len(prices_12) > 1:
            running_max = prices_12.cummax()
            drawdowns   = (prices_12 - running_max) / running_max
            max_dd      = float(drawdowns.min())  # negative number
        else:
            max_dd = 0.0

        # Return stability: autocorrelation of returns
        # Positive autocorrelation = persistent trending = quality
        if len(monthly_rets) >= 12:
            ret_arr = monthly_rets.tail(12).values
            if len(ret_arr) > 2:
                autocorr = float(pd.Series(ret_arr).autocorr(lag=1))
            else:
                autocorr = 0.0
        else:
            autocorr = 0.0

        # Beta penalty: high beta = low quality (BAB integration)
        beta_est = asset.get("beta_est", 1.0)
        beta_penalty = -max(0.0, beta_est - 0.8) * 0.5

        quality_score = (
            sharpe_proxy * 0.40 +
            (-max_dd)    * 0.30 +  # positive: smaller drawdown
            autocorr     * 0.20 +
            beta_penalty * 0.10
        )

        # QMJ adjustment: defensive sectors get quality bonus
        if asset.get("sector") in ("healthcare","staples","utilities",
                                    "quality","safe_haven"):
            quality_score *= 1.2

        raw[ticker] = quality_score

    return _zscore_dict(raw)


# ── LAYER 5: BETTING AGAINST BETA SIGNAL ─────────────────
# AQR BAB: long low-beta, short high-beta
# Most effective when: funding tight, VIX elevated, crowding high

def compute_bab_signal(
    prices:   dict[str, pd.DataFrame],
    spy_prices: pd.DataFrame,
    vix: float,
    liquidity_score: float,
) -> dict[str, float]:
    """
    Frazzini-Pedersen BAB signal.
    BAB alpha is highest when constraints are tight:
      - VIX > 20 (elevated vol / funding pressure)
      - Liquidity score < 0 (tightening conditions)
    In those conditions: amplify low-beta LONG signals.
    In normal conditions: BAB still positive but smaller.
    """
    # BAB environment multiplier
    # Tight funding = BAB works best (Prop 3 in paper)
    funding_tight = (vix > 22) or (liquidity_score < -0.5)
    bab_mult = 1.5 if funding_tight else 1.0

    # Compute realised betas vs SPY
    spy_returns = None
    if not spy_prices.empty:
        spy_returns = spy_prices["close"].pct_change().dropna()

    raw = {}
    for ticker, asset in UNIVERSE.items():
        hist = prices.get(ticker, pd.DataFrame())
        if hist.empty or len(hist) < 12 or spy_returns is None:
            # Fall back to estimated beta
            beta = asset.get("beta_est", 1.0)
            raw[ticker] = -(beta - 1.0) * bab_mult
            continue

        asset_rets = hist["close"].pct_change().dropna()

        # Align date indices
        merged = pd.concat([asset_rets.rename("asset"),
                             spy_returns.rename("spy")],
                            axis=1).dropna()

        if len(merged) < 12:
            beta = asset.get("beta_est", 1.0)
            raw[ticker] = -(beta - 1.0) * bab_mult
            continue

        # OLS beta
        x = merged["spy"].values
        y = merged["asset"].values
        cov_xy = np.cov(x, y)[0, 1]
        var_x  = np.var(x)
        beta   = cov_xy / var_x if var_x > 1e-10 else asset.get("beta_est", 1.0)
        beta   = float(np.clip(beta, -0.5, 3.0))

        # BAB signal: low beta = positive (LONG), high beta = negative (SHORT)
        # Frazzini-Pedersen: rank by beta, not just sign
        raw[ticker] = -(beta - 1.0) * bab_mult

    return _zscore_dict(raw)


# ── LAYER 6: CARRY SIGNAL ─────────────────────────────────
# AQR/Koijen et al. (2018): Carry = return if mkt unchanged
# By asset class:
# - Bonds: yield (higher yield = positive carry)
# - FX: interest rate differential vs USD
# - Equity: dividend yield + buyback yield
# - Commodities: convenience yield (spot vs futures curve)
# Carry is separate from value and momentum, adds
# diversification. Combined carry + value + momentum
# Sharpe ≈ 1.5x standalone.

def compute_carry_signal(
    prices:  dict[str, pd.DataFrame],
    df:      pd.DataFrame,
    fed_funds: float,
) -> dict[str, float]:
    """
    Koijen et al. (2018) Carry signal across asset classes.
    Carry is orthogonal to value and momentum — adds alpha.
    """
    raw = {}

    # FX carry rates (approx central bank rates)
    FX_RATES = {
        "FXE": 3.65,   # ECB
        "FXY": 0.10,   # BOJ
        "FXB": 4.50,   # BOE
        "FXA": 4.35,   # RBA
        "FXC": 5.00,   # BOC
        "FXF": 1.75,   # SNB
        "UUP": fed_funds,
    }

    for ticker, asset in UNIVERSE.items():
        hist = prices.get(ticker, pd.DataFrame())
        cls = asset["class"]

        if cls in ("equity_etf","sector_etf","factor_etf"):
            # Equity carry = dividend yield (+ implicit buyback)
            # Higher div yield = positive carry
            div_y = asset.get("div_yield", 0.0)
            raw[ticker] = div_y / 100.0

        elif cls == "fixed_income":
            # Bond carry = coupon yield
            # Use FRED series if available, else div_yield proxy
            yield_key = asset.get("yield_key")
            if yield_key and yield_key in df.columns:
                y = float(df[yield_key].dropna().iloc[-1])
                raw[ticker] = y / 100.0
            else:
                raw[ticker] = asset.get("div_yield", 3.0) / 100.0

        elif cls == "fx":
            # FX carry = interest rate differential vs USD
            # Long the high-yielder vs USD
            fx_rate = FX_RATES.get(ticker, 2.0)
            carry = (fx_rate - fed_funds) / 100.0
            # For UUP (USD bull): negative carry when USD rates
            # are below others
            if ticker == "UUP":
                other_avg = np.mean([r for k, r in FX_RATES.items()
                                     if k != "UUP"])
                carry = (fed_funds - other_avg) / 100.0
            raw[ticker] = carry

        elif cls == "commodity":
            # Commodity carry = roll yield (spot - front futures)
            # For ETF proxies: use price momentum of front-month
            # as a proxy for backwardation/contango
            if not hist.empty and len(hist) >= 3:
                close = hist["close"].dropna()
                # Positive = backwardation (positive carry)
                # Proxy: 1M return relative to 3M annualised
                r1 = float(close.iloc[-1] / close.iloc[-2] - 1) \
                     if len(close) >= 2 else 0.0
                r3 = float(close.iloc[-1] / close.iloc[-4] - 1) \
                     if len(close) >= 4 else 0.0
                # If recent return > 3M trend: positive carry proxy
                raw[ticker] = r1 - r3 / 3.0
            else:
                raw[ticker] = 0.0

    return _zscore_dict(raw)


# ── LAYER 7: TREND FOLLOWING (Vol-Targeted) ───────────────
# Man AHL / Winton: EWMA signal normalised by realised vol
# Multiple lookbacks: 1M, 3M, 12M with weights 1:2:4
# Crisis alpha: trend following has negative equity correlation
# in drawdowns → include as diversifier

def compute_trend_signal(
    prices: dict[str, pd.DataFrame],
) -> dict[str, float]:
    """
    Man AHL / Winton style vol-targeted trend following.
    EWMA fast/slow crossover normalised by realised vol.
    Multiple time horizons aggregated with increasing weight
    for longer horizon (as per Hurst, Ooi, Pedersen 2013).
    """
    raw = {}

    for ticker in UNIVERSE:
        hist = prices.get(ticker, pd.DataFrame())
        if hist.empty or len(hist) < 6:
            raw[ticker] = 0.0
            continue

        close = hist["close"].dropna()

        # EWMA signals at multiple horizons
        # Man AHL uses spans of ~1, 3, 12 months
        signals = []
        weights = [1.0, 2.0, 4.0]  # longer horizon = more weight

        for months, wt in zip([1, 3, 12], weights):
            if len(close) < months + 1:
                signals.append((0.0, wt))
                continue
            # EWMA crossover: fast EWMA / slow EWMA - 1
            span_fast = max(2, months)
            span_slow = max(4, months * 4)
            ewma_fast = float(close.ewm(span=span_fast).mean().iloc[-1])
            ewma_slow = float(close.ewm(span=span_slow).mean().iloc[-1])
            if ewma_slow > 1e-6:
                trend_signal = ewma_fast / ewma_slow - 1.0
            else:
                trend_signal = 0.0
            signals.append((trend_signal, wt))

        # Volatility targeting normalisation
        monthly_rets = close.pct_change().dropna()
        vol = float(monthly_rets.tail(12).std()) \
              if len(monthly_rets) >= 6 else 0.05
        if vol < 1e-6:
            vol = 0.05

        # Weighted average trend signal, vol-normalised
        total_w = sum(w for _, w in signals)
        combined = sum(s * w for s, w in signals) / total_w
        raw[ticker] = combined / vol

    return _zscore_dict(raw)


# ──────────────────────────────────────────────────────────────
# SECTION D: SIGNAL AGGREGATION
# AQR finding: Value + Momentum combination improves Sharpe
# by ~50% due to negative correlation between them.
# Bridgewater: regime probability weighting.
# Layer weights determined by:
#   - Information ratio of each signal historically
#   - Regime-adaptive: some signals better in certain regimes
# ──────────────────────────────────────────────────────────────

# Base signal weights (calibrated from academic literature)
# AQR paper (2013): V+M combo SR ~0.9 vs ~0.5 standalone
# BAB SR ~0.7 (Frazzini-Pedersen 2014)
# Carry SR ~0.7-1.0 (Koijen et al. 2018)
# Trend SR ~0.5-0.7 (Man AHL / Hurst et al. 2013)
BASE_WEIGHTS = {
    "regime":   0.25,   # Bridgewater macro
    "value":    0.20,   # AQR value everywhere
    "momentum": 0.20,   # AQR momentum everywhere
    "quality":  0.15,   # AQR QMJ
    "bab":      0.10,   # AQR BAB
    "carry":    0.05,   # AQR carry
    "trend":    0.05,   # Man AHL trend
}

# Regime-adaptive weights (Goldman Sachs / JPMorgan insight:
# factor efficacy varies by regime phase)
REGIME_FACTOR_ADJUSTMENTS = {
    "Goldilocks":  {"momentum":+0.05,"quality":+0.05,"value":-0.05,
                    "bab":-0.05,"carry":0.0,"trend":0.0},
    "Reflation":   {"value":+0.10,"carry":+0.05,"momentum":+0.05,
                    "quality":-0.10,"bab":-0.05,"trend":-0.05},
    "Stagflation": {"trend":+0.10,"quality":+0.05,"carry":+0.05,
                    "value":0.0,"momentum":-0.10,"bab":-0.10},
    "Slowdown":    {"quality":+0.10,"bab":+0.10,"trend":+0.05,
                    "value":-0.05,"momentum":-0.10,"carry":-0.10},
}


def aggregate_signals(
    regime_sig:   dict[str, float],
    value_sig:    dict[str, float],
    momentum_sig: dict[str, float],
    quality_sig:  dict[str, float],
    bab_sig:      dict[str, float],
    carry_sig:    dict[str, float],
    trend_sig:    dict[str, float],
    modal_regime: str,
) -> dict[str, float]:
    """
    Combine all 7 signal layers with regime-adaptive weighting.
    Returns composite score per ticker.
    """
    # Adjust weights for current regime
    weights = BASE_WEIGHTS.copy()
    adj = REGIME_FACTOR_ADJUSTMENTS.get(modal_regime, {})
    for k, delta in adj.items():
        if k in weights:
            weights[k] = max(0.0, weights[k] + delta)

    # Normalise weights to sum to 1
    total = sum(weights.values())
    weights = {k: v / total for k, v in weights.items()}

    # Compute composite per ticker
    signal_layers = {
        "regime":   regime_sig,
        "value":    value_sig,
        "momentum": momentum_sig,
        "quality":  quality_sig,
        "bab":      bab_sig,
        "carry":    carry_sig,
        "trend":    trend_sig,
    }

    composite = {}
    for ticker in UNIVERSE:
        score = sum(
            weights[layer] * signals.get(ticker, 0.0)
            for layer, signals in signal_layers.items()
        )
        composite[ticker] = round(float(score), 4)

    return composite


# ──────────────────────────────────────────────────────────────
# SECTION E: POSITION SIZING (Kelly + Vol Target)
# Bridgewater Pure Alpha: position sizes driven by
# regime-adjusted volatility budgets (not fixed allocations).
# Kelly criterion: half-Kelly for real-world application.
# JPMorgan Cross-Asset: volatility-target sizing.
# ──────────────────────────────────────────────────────────────

TARGET_PORTFOLIO_VOL = 0.15  # 15% annual vol target


def compute_position_size(
    score:     float,
    asset_vol: float,
    max_pos:   float = 0.25,
) -> float:
    """
    Vol-targeted Kelly position sizing.
    Based on Bridgewater adaptive risk budgeting:
      - Each position sized so its contribution to
        portfolio vol is proportional to conviction.
      - Half-Kelly applied for robustness.
    """
    if asset_vol < 1e-6:
        asset_vol = 0.15

    abs_score = abs(score)

    # Win probability implied by score
    # Z-score of 2.0 → ~84th percentile → win prob ~0.62
    from scipy.stats import norm as _norm
    win_prob = float(_norm.cdf(abs_score * 0.5))
    win_prob = min(max(win_prob, 0.40), 0.75)

    # Kelly fraction (half-Kelly)
    kelly_f = (win_prob - (1 - win_prob)) / 1.0  # edge / odds
    half_kelly = max(0.0, kelly_f * 0.5)

    # Vol-scaled position: target_vol / asset_vol * kelly
    vol_scalar = (TARGET_PORTFOLIO_VOL / 12) / asset_vol
    position = half_kelly * vol_scalar

    # Clamp to max
    return round(min(position, max_pos), 3)


# ──────────────────────────────────────────────────────────────
# SECTION F: RECOMMENDATION BUILDER
# Convert scores to structured recommendations with:
# - Direction (LONG/SHORT)
# - Conviction tier (VERY HIGH / HIGH / MEDIUM / LOW)
# - Signal decomposition (which layers drove the call)
# - Risk metrics (R:R, stop, target)
# - Academic rationale
# ──────────────────────────────────────────────────────────────

def _score_to_conviction(abs_score: float) -> tuple[str, str]:
    if abs_score >= 1.8:
        return "VERY HIGH", "bloomberg"
    elif abs_score >= 1.2:
        return "HIGH", "green"
    elif abs_score >= 0.7:
        return "MEDIUM", "amber"
    else:
        return "LOW", "blue"


def build_recommendation(
    ticker:       str,
    composite:    float,
    layer_scores: dict[str, float],
    modal_regime: str,
    asset_vol:    float,
    weights:      dict[str, float],
) -> dict | None:
    """
    Build a full recommendation object from composite score.
    Includes signal attribution (which layer drove the call).
    """
    if abs(composite) < 0.5:
        return None  # below noise threshold

    asset    = UNIVERSE[ticker]
    direction = "LONG" if composite > 0 else "SHORT"
    abs_score = abs(composite)
    conviction, conv_color = _score_to_conviction(abs_score)

    # Position sizing
    pos_size = compute_position_size(composite, asset_vol)

    # Risk / Reward ratio
    # Based on conviction: AQR backtests show higher-conviction
    # trades have ~2-3x R:R before transaction costs
    rr_base = 1.5 + abs_score * 0.4
    rr = round(min(rr_base, 3.5), 1)

    # Signal attribution: which layers contributed most
    layer_contributions = {}
    total_abs = 0.0
    for layer, sig_dict in layer_scores.items():
        wt  = weights.get(layer, 0.1)
        sig = sig_dict.get(ticker, 0.0)
        contrib = wt * sig
        if direction == "SHORT":
            contrib = -contrib  # flip for short
        layer_contributions[layer] = round(contrib, 3)
        total_abs += abs(contrib)

    # Normalise to % contribution
    if total_abs > 0:
        layer_pct = {
            k: round(v / total_abs * 100, 1)
            for k, v in layer_contributions.items()
        }
    else:
        layer_pct = {k: 0.0 for k in layer_contributions}

    # Top 2 driving signals (for display)
    sorted_layers = sorted(layer_pct.items(),
                           key=lambda x: abs(x[1]), reverse=True)
    top_drivers = [
        {"layer": k, "pct": v, "polarity": "+" if v > 0 else "-"}
        for k, v in sorted_layers[:3]
    ]

    # Time horizon by asset class
    horizons = {
        "equity_etf":   "1-3 months",
        "sector_etf":   "1-3 months",
        "factor_etf":   "2-4 months",
        "fixed_income": "2-6 months",
        "commodity":    "1-3 months",
        "fx":           "3-8 weeks",
    }
    horizon = horizons.get(asset["class"], "1-3 months")

    # Academic rationale
    rationale = _build_academic_rationale(
        ticker, asset, direction, modal_regime,
        sorted_layers[:2], abs_score
    )

    return {
        "ticker":          ticker,
        "name":            asset["name"],
        "asset_class":     asset["class"],
        "sub_class":       asset.get("sector", ""),
        "region":          asset.get("region", ""),
        "direction":       direction,
        "composite_score": composite,
        "abs_score":       abs_score,
        "conviction":      conviction,
        "conviction_color":conv_color,
        "position_size_pct": round(pos_size * 100, 1),
        "risk_reward":     rr,
        "horizon":         horizon,
        "rationale":       rationale,
        "regime":          modal_regime,
        "regime_valid":    _is_regime_consistent(
                               ticker, direction, modal_regime),
        "layer_contributions": layer_pct,
        "top_drivers":     top_drivers,
        "div_yield":       asset.get("div_yield"),
        "beta_est":        asset.get("beta_est"),
        "tags":            _build_tags(
                               asset, direction, modal_regime,
                               layer_pct),
        "generated_at":    datetime.utcnow().isoformat(),
    }


def _build_academic_rationale(
    ticker, asset, direction, regime,
    top_layers, abs_score
) -> str:
    """Generate rationale citing academic framework."""
    layer_names = {
        "regime":   "Bridgewater regime model",
        "value":    "AQR Value Everywhere",
        "momentum": "AQR Momentum Everywhere",
        "quality":  "AQR Quality-Minus-Junk",
        "bab":      "Frazzini-Pedersen BAB",
        "carry":    "Koijen et al. Carry",
        "trend":    "Man AHL Trend Following",
    }

    top = [(layer_names.get(k, k), abs(v))
           for k, v in top_layers if abs(v) > 5]
    driver_str = " + ".join(f"{name} ({pct:.0f}%)"
                            for name, pct in top[:2]) \
                 if top else "multi-factor composite"

    regime_desc = {
        "Reflation":   "rising growth + inflation",
        "Goldilocks":  "strong growth, contained inflation",
        "Slowdown":    "decelerating growth",
        "Stagflation": "falling growth + persistent inflation",
    }
    r = regime_desc.get(regime, regime)

    sector = asset.get("sector", "")
    cls    = asset["class"]

    prefix = "" if direction == "LONG" else "SHORT "
    return (
        f"{prefix}{asset['name']}: {driver_str} align on "
        f"{direction.lower()} signal in {r} regime. "
        f"Composite Z-score: "
        f"{'+'if direction=='LONG' else '-'}{abs_score:.2f}σ."
    )


def _is_regime_consistent(ticker, direction, regime) -> bool:
    returns = REGIME_RETURNS.get(ticker)
    if not returns:
        return False
    gold, refl, stag, slow = returns
    regime_ret = {
        "Goldilocks": gold, "Reflation": refl,
        "Stagflation": stag, "Slowdown": slow,
    }.get(regime, 0.0)
    if direction == "LONG":
        return regime_ret > 0.5
    else:
        return regime_ret < -0.5


def _build_tags(asset, direction, regime, layer_pct) -> list[str]:
    tags = [regime[:5]]
    cls_map = {
        "equity_etf":"Equity ETF","sector_etf":"Sector ETF",
        "factor_etf":"Factor ETF","fixed_income":"Fixed Income",
        "commodity":"Commodity","fx":"FX",
    }
    tags.append(cls_map.get(asset["class"], asset["class"]))

    # Signal source tag
    top_layer = max(layer_pct.items(), key=lambda x: abs(x[1]),
                    default=("", 0))
    source_map = {
        "regime":"Macro","value":"Value","momentum":"Momentum",
        "quality":"Quality","bab":"BAB","carry":"Carry",
        "trend":"Trend",
    }
    if top_layer[0]:
        tags.append(source_map.get(top_layer[0], top_layer[0]))

    if direction == "SHORT":
        tags.append("Short")
    if asset.get("div_yield", 0) > 3.0:
        tags.append("High Yield")
    if asset.get("beta_est", 1.0) < 0.7:
        tags.append("Low Beta")

    return tags[:5]


# ──────────────────────────────────────────────────────────────
# SECTION G: PAIR TRADE GENERATOR
# Academic basis: long/short pairs reduce market beta to zero
# (AQR market-neutral strategies). Pairs are identified where:
#  1. Both legs have high conviction in opposite directions
#  2. Historically correlated (same sector or macro factor)
#  3. Pair spread is at an extreme relative to history
# ──────────────────────────────────────────────────────────────

CANONICAL_PAIRS = {
    # (long_candidate, short_candidate, description, rationale)
    # Bridgewater / Goldman regime pairs
    "Reflation": [
        ("XLE",  "XLU",  "Energy vs Utilities",
         "Reflation pair: inflation proxy vs rate-sensitive sector"),
        ("XLB",  "TLT",  "Materials vs Long Duration",
         "Hard assets vs paper in rising inflation"),
        ("VLUE", "USMV", "Value vs Min-Vol",
         "AQR factor rotation: value outperforms in reflation"),
        ("GLD",  "IEF",  "Gold vs Nominal Bonds",
         "Real vs nominal rates: classic inflation hedge pair"),
        ("EEM",  "FXY",  "EM Equities vs JPY",
         "Risk-on EM vs safe-haven carry unwind"),
        ("CPER", "XLU",  "Copper vs Utilities",
         "Industrial metals vs rate-sensitive defensives"),
        ("HYG",  "TLT",  "High Yield vs Duration",
         "Credit carry vs duration risk in steepening curve"),
    ],
    "Goldilocks": [
        ("QQQ",  "XLE",  "Growth Tech vs Energy",
         "Goldilocks: growth dominates, commodity inflation fades"),
        ("QUAL", "VLUE", "Quality vs Value",
         "In Goldilocks, quality growth commands a premium"),
        ("IWM",  "TLT",  "Small Cap vs Duration",
         "Risk-on: small cap benefits, long duration underperforms"),
        ("MTUM", "USMV", "Momentum vs Min-Vol",
         "AQR factor momentum: strong markets reward trend"),
        ("EEM",  "GLD",  "EM vs Gold",
         "Risk appetite drives EM over safe haven"),
    ],
    "Slowdown": [
        ("TLT",  "XLE",  "Duration vs Energy",
         "Flight to quality + commodity demand falls"),
        ("XLV",  "XLF",  "Healthcare vs Financials",
         "Defensives vs credit-cycle exposure"),
        ("QUAL", "MTUM", "Quality vs Momentum",
         "Quality factor outperforms in late/contraction cycle"),
        ("GLD",  "HYG",  "Gold vs High Yield",
         "Safe haven vs credit stress pair"),
        ("FXY",  "FXA",  "JPY vs AUD",
         "Safe haven vs commodity FX in risk-off"),
    ],
    "Stagflation": [
        ("GLD",  "QQQ",  "Gold vs Growth Tech",
         "Hard money vs high-multiple growth in stagflation"),
        ("TIP",  "TLT",  "TIPS vs Nominal Duration",
         "Real vs nominal bonds: classic stagflation pair"),
        ("USO",  "XLK",  "Oil vs Technology",
         "Energy benefits, tech faces margin + multiple pressure"),
        ("USMV", "IWM",  "Min-Vol vs Small Cap",
         "Quality defence vs leveraged cyclicals"),
        ("XLP",  "XLY",  "Staples vs Discretionary",
         "Consumer resilience pair: necessities vs wants"),
    ],
}


def generate_pair_trades(
    longs:   list[dict],
    shorts:  list[dict],
    prices:  dict[str, pd.DataFrame],
    regime:  str,
) -> list[dict]:
    """
    Generate L/S pair trades from canonical list.
    Validates that both legs are in the recommendation lists.
    Adds spread Z-score to show if pair is at an extreme.
    """
    long_map  = {r["ticker"]: r for r in longs}
    short_map = {r["ticker"]: r for r in shorts}
    pairs_out = []

    for long_t, short_t, desc, rationale in \
            CANONICAL_PAIRS.get(regime, []):

        if long_t not in long_map or short_t not in short_map:
            continue

        long_rec  = long_map[long_t]
        short_rec = short_map[short_t]

        # Spread analysis: compute historical spread Z-score
        long_hist  = prices.get(long_t,  pd.DataFrame())
        short_hist = prices.get(short_t, pd.DataFrame())
        spread_z   = 0.0

        if not long_hist.empty and not short_hist.empty:
            try:
                lp = long_hist["close"].dropna()
                sp = short_hist["close"].dropna()
                # Normalise to common base (rebased to 100)
                lp_n = lp / lp.iloc[0] * 100
                sp_n = sp / sp.iloc[0] * 100
                spread = lp_n - sp_n
                if len(spread.dropna()) > 12:
                    mean_s = float(spread.mean())
                    std_s  = float(spread.std())
                    if std_s > 0:
                        spread_z = float(
                            (spread.iloc[-1] - mean_s) / std_s
                        )
            except Exception:
                spread_z = 0.0

        net_conviction = (long_rec["abs_score"] +
                          short_rec["abs_score"]) / 2.0

        pairs_out.append({
            "long":             long_rec,
            "short":            short_rec,
            "description":      desc,
            "rationale":        rationale,
            "spread_z":         round(spread_z, 2),
            "spread_extreme":   abs(spread_z) > 1.5,
            "net_conviction":   round(net_conviction, 3),
            "regime":           regime,
            "combined_signal":  round(
                long_rec["abs_score"] + short_rec["abs_score"], 2
            ),
        })

    # Sort by combined signal strength
    pairs_out.sort(key=lambda x: x["combined_signal"], reverse=True)
    return pairs_out[:4]


# ══════════════════════════════════════════════════════════════
# UPGRADE 1 — FACTOR CROWDING DETECTOR
# Research basis: MSCI Integrated Factor Crowding Model (2025),
# Summer 2025 Quant Wobble post-mortem, Resonanz Capital paper
# "Crowding, Deleveraging: A Manual for the Next Quant Unwind"
# ══════════════════════════════════════════════════════════════

CROWDING_THRESHOLDS = {
    "low":    0.30,
    "medium": 0.50,
    "high":   0.65,
    "extreme": 0.80,
}

LAYER_CROWDING_WEIGHTS = {
    "momentum": 0.30,
    "quality":  0.20,
    "value":    0.20,
    "bab":      0.15,
    "regime":   0.10,
    "carry":    0.03,
    "trend":    0.02,
}


def compute_factor_crowding(
    prices:       dict[str, pd.DataFrame],
    composite:    dict[str, float],
    layer_scores: dict[str, dict[str, float]],
) -> dict:
    """
    Compute factor crowding score across the universe.
    High pairwise correlation among co-directional assets = crowded.
    """
    import itertools

    factor_crowding = {}
    crowding_scores = {}

    for layer, sig_dict in layer_scores.items():
        # Find co-directional assets (signal and composite agree)
        co_longs  = [t for t in UNIVERSE
                     if sig_dict.get(t, 0) > 0.3
                     and composite.get(t, 0) > 0]
        co_shorts = [t for t in UNIVERSE
                     if sig_dict.get(t, 0) < -0.3
                     and composite.get(t, 0) < 0]
        co_directional = co_longs + co_shorts
        n_pos = len(co_directional)

        if n_pos < 4:
            factor_crowding[layer] = {
                "score": 0.0, "level": "low",
                "direction": "neutral", "n_positions": n_pos,
            }
            crowding_scores[layer] = 0.0
            continue

        # Compute pairwise 3-month return correlations
        recent_rets = {}
        for ticker in co_directional:
            hist = prices.get(ticker, pd.DataFrame())
            if not hist.empty and len(hist) >= 4:
                rets = hist["close"].pct_change().dropna().tail(3)
                if len(rets) >= 2:
                    recent_rets[ticker] = rets.reset_index(drop=True)

        valid_tickers = list(recent_rets.keys())
        if len(valid_tickers) < 4:
            factor_crowding[layer] = {
                "score": 0.0, "level": "low",
                "direction": "neutral", "n_positions": n_pos,
            }
            crowding_scores[layer] = 0.0
            continue

        # Build returns matrix and compute pairwise correlations
        ret_matrix = pd.DataFrame(recent_rets)
        try:
            corr_matrix = ret_matrix.corr()
        except Exception:
            factor_crowding[layer] = {
                "score": 0.0, "level": "low",
                "direction": "neutral", "n_positions": n_pos,
            }
            crowding_scores[layer] = 0.0
            continue

        # Average off-diagonal correlation
        n = len(valid_tickers)
        pairs = [(i, j) for i, j in itertools.combinations(range(n), 2)]
        if not pairs:
            factor_crowding[layer] = {
                "score": 0.0, "level": "low",
                "direction": "neutral", "n_positions": n_pos,
            }
            crowding_scores[layer] = 0.0
            continue

        pair_corrs = []
        for i, j in pairs:
            t1, t2 = valid_tickers[i], valid_tickers[j]
            c = corr_matrix.loc[t1, t2]
            if np.isfinite(c):
                pair_corrs.append(c)

        avg_corr = float(np.mean(pair_corrs)) if pair_corrs else 0.0
        avg_corr = max(-1.0, min(1.0, avg_corr))

        # Determine crowding level
        if avg_corr >= CROWDING_THRESHOLDS["extreme"]:
            level = "extreme"
        elif avg_corr >= CROWDING_THRESHOLDS["high"]:
            level = "high"
        elif avg_corr >= CROWDING_THRESHOLDS["medium"]:
            level = "medium"
        else:
            level = "low"

        # Detect unwind (correlation dropping from 6M to 3M)
        long_rets = {}
        for ticker in valid_tickers:
            hist = prices.get(ticker, pd.DataFrame())
            if not hist.empty and len(hist) >= 7:
                rets = hist["close"].pct_change().dropna().tail(6)
                if len(rets) >= 3:
                    long_rets[ticker] = rets.reset_index(drop=True)

        if len(long_rets) >= 4:
            long_matrix = pd.DataFrame(long_rets)
            try:
                long_corr_matrix = long_matrix.corr()
                long_pair_corrs = []
                valid_long = list(long_rets.keys())
                pairs_long = [(i, j) for i, j in
                              itertools.combinations(range(len(valid_long)), 2)]
                for i, j in pairs_long:
                    t1, t2 = valid_long[i], valid_long[j]
                    if t1 in long_corr_matrix and t2 in long_corr_matrix.columns:
                        c = long_corr_matrix.loc[t1, t2]
                        if np.isfinite(c):
                            long_pair_corrs.append(c)
                long_avg = float(np.mean(long_pair_corrs)) if long_pair_corrs else avg_corr
                corr_direction = ("falling" if avg_corr < long_avg - 0.05
                                  else "rising" if avg_corr > long_avg + 0.05
                                  else "stable")
            except Exception:
                corr_direction = "neutral"
        else:
            corr_direction = "neutral"

        factor_crowding[layer] = {
            "score": round(avg_corr, 3),
            "level": level,
            "direction": corr_direction,
            "n_positions": n_pos,
            "pair_count": len(pair_corrs),
        }
        crowding_scores[layer] = avg_corr

    # Portfolio-level weighted crowding score
    port_crowd = sum(
        crowding_scores.get(layer, 0.0) * w
        for layer, w in LAYER_CROWDING_WEIGHTS.items()
    ) / sum(LAYER_CROWDING_WEIGHTS.values())

    # Size multiplier: scale down positions when crowded
    low_t = CROWDING_THRESHOLDS["low"]
    ext_t = CROWDING_THRESHOLDS["extreme"]
    if port_crowd <= low_t:
        size_mult = 1.0
    elif port_crowd >= ext_t:
        size_mult = 0.50
    else:
        frac = (port_crowd - low_t) / (ext_t - low_t)
        size_mult = round(1.0 - frac * 0.50, 3)

    # Alert level
    if port_crowd >= CROWDING_THRESHOLDS["extreme"]:
        alert = "EXTREME"
    elif port_crowd >= CROWDING_THRESHOLDS["high"]:
        alert = "HIGH"
    elif port_crowd >= CROWDING_THRESHOLDS["medium"]:
        alert = "MEDIUM"
    else:
        alert = "LOW"

    worst = max(crowding_scores, key=lambda k: crowding_scores[k], default="momentum")
    unwind = any(v.get("direction") == "falling" for v in factor_crowding.values())

    return {
        "factor_crowding": factor_crowding,
        "portfolio_crowding_score": round(float(port_crowd), 3),
        "size_multiplier": size_mult,
        "alert_level": alert,
        "worst_factor": worst,
        "unwind_signal": unwind,
        "interpretation": (
            f"Factor crowding {alert.lower()}. All position sizes scaled to {size_mult:.0%}. "
            + ("⚠️ Correlation falling — possible unwind in progress." if unwind else "")
        ),
    }


# ══════════════════════════════════════════════════════════════
# UPGRADE 2 — ROLLING IC MONITOR
# Research basis: Lopez de Prado (2018) Chapter 3;
# Standard quant practice for live signal health monitoring
# ══════════════════════════════════════════════════════════════


def compute_rolling_ic(
    prices: dict[str, pd.DataFrame],
    layer_scores: dict[str, dict[str, float]],
    lookback_months: int = 3,
) -> dict:
    """
    Compute rolling 3-month Information Coefficient for each signal layer.
    IC = rank correlation between predicted signal and next-period return.
    """
    from scipy.stats import spearmanr

    ic_results = {}

    for layer, sig_dict in layer_scores.items():
        monthly_ics = []

        for lag in range(1, lookback_months + 1):
            pairs = []
            for ticker in UNIVERSE:
                sig_val = sig_dict.get(ticker, 0.0)
                if not np.isfinite(sig_val):
                    continue

                hist = prices.get(ticker, pd.DataFrame())
                if hist.empty or len(hist) < lag + 2:
                    continue

                close = hist["close"].dropna()
                if len(close) >= lag + 1:
                    fwd_ret = float(close.iloc[-lag] / close.iloc[-lag - 1] - 1)
                    if np.isfinite(fwd_ret):
                        pairs.append((sig_val, fwd_ret))

            if len(pairs) < 10:
                continue

            sigs, rets = zip(*pairs)
            try:
                ic, _ = spearmanr(sigs, rets)
                if np.isfinite(ic):
                    monthly_ics.append(float(ic))
            except Exception:
                continue

        if not monthly_ics:
            rolling_ic = 0.0
            ic_stability = 0.0
        else:
            rolling_ic = float(np.mean(monthly_ics))
            ic_stability = 1.0 - float(np.std(monthly_ics)) if len(monthly_ics) > 1 else 0.5

        # Health classification and weight multiplier
        if rolling_ic >= 0.05:
            health, weight_mult = "HEALTHY", 1.00
        elif rolling_ic >= 0.03:
            health, weight_mult = "ACCEPTABLE", 0.75
        elif rolling_ic >= 0.01:
            health, weight_mult = "MARGINAL", 0.50
        else:
            health, weight_mult = "DECAYED", 0.25

        ic_ir = (rolling_ic / max(np.std(monthly_ics), 0.001) if len(monthly_ics) > 1 else 0.0)

        ic_results[layer] = {
            "rolling_ic": round(rolling_ic, 4),
            "monthly_ics": [round(ic, 4) for ic in monthly_ics],
            "ic_stability": round(ic_stability, 3),
            "icir": round(float(ic_ir), 3),
            "health": health,
            "weight_mult": weight_mult,
            "months_tracked": len(monthly_ics),
        }

    weight_adjustments = {layer: data["weight_mult"] for layer, data in ic_results.items()}

    decayed_layers = [layer for layer, data in ic_results.items() if data["health"] == "DECAYED"]
    healthy_layers = [layer for layer, data in ic_results.items() if data["health"] == "HEALTHY"]

    return {
        "layer_ic": ic_results,
        "weight_adjustments": weight_adjustments,
        "decayed_layers": decayed_layers,
        "healthy_layers": healthy_layers,
        "overall_signal_health": (
            "STRONG" if len(healthy_layers) >= 5 else
            "MODERATE" if len(healthy_layers) >= 3 else
            "WEAK"
        ),
        "alert": (f"⚠️ Decayed layers: {', '.join(decayed_layers)}" if decayed_layers else None),
    }


# ──────────────────────────────────────────────────────────────
# SECTION H: MASTER ENTRY POINT
# Called from api/main.py endpoint and get_dashboard()
# ──────────────────────────────────────────────────────────────

def generate_all_recommendations(
    regime_probs:    dict[str, float],
    modal_regime:    str,
    growth_score:    float,
    inflation_score: float,
    liquidity_score: float,
    risk_score:      float,
    df:              pd.DataFrame,
    fed_funds:       float = 5.25,
    max_longs:       int   = 20,
    max_shorts:      int   = 12,
) -> dict:
    """
    Master function implementing all 7 signal layers.
    Called from /api/trade-recommendations endpoint.
    """
    tickers = list(UNIVERSE.keys())

    # ── 1. Fetch all prices in parallel ───────────────────
    logger.info("[TradeEngine] Fetching prices for "
                f"{len(tickers)} assets...")
    prices = _fetch_all_prices(tickers, period="2y")

    # ── 2. Compute each signal layer ──────────────────────
    logger.info("[TradeEngine] Computing signal layers...")

    regime_sig   = compute_regime_signal(regime_probs)

    value_sig    = compute_value_signal(prices, df, fed_funds)

    momentum_sig = compute_momentum_signal(prices)

    quality_sig  = compute_quality_signal(prices, df)

    spy_prices   = prices.get("SPY", pd.DataFrame())
    vix          = float(df["VIXCLS"].dropna().iloc[-1]) \
                   if "VIXCLS" in df.columns else 18.0
    bab_sig      = compute_bab_signal(
                       prices, spy_prices, vix, liquidity_score)

    carry_sig    = compute_carry_signal(prices, df, fed_funds)

    trend_sig    = compute_trend_signal(prices)

    # ── 3. Aggregate with regime-adaptive weights ─────────
    composite = aggregate_signals(
        regime_sig, value_sig, momentum_sig, quality_sig,
        bab_sig, carry_sig, trend_sig, modal_regime
    )

    # Compute actual weights used (for attribution display)
    weights = BASE_WEIGHTS.copy()
    adj = REGIME_FACTOR_ADJUSTMENTS.get(modal_regime, {})
    for k, delta in adj.items():
        if k in weights:
            weights[k] = max(0.0, weights[k] + delta)
    total_w = sum(weights.values())
    weights = {k: v / total_w for k, v in weights.items()}

    # ── 4. Build recommendations ──────────────────────────
    layer_scores = {
        "regime": regime_sig, "value": value_sig,
        "momentum": momentum_sig, "quality": quality_sig,
        "bab": bab_sig, "carry": carry_sig, "trend": trend_sig,
    }

    all_recs = []
    for ticker, score in composite.items():
        # Asset vol (annualised monthly vol * sqrt(12))
        hist = prices.get(ticker, pd.DataFrame())
        if not hist.empty and len(hist) >= 6:
            monthly_rets = hist["close"].pct_change().dropna()
            asset_vol = float(monthly_rets.tail(12).std()) \
                        * (12 ** 0.5)
            asset_vol = max(asset_vol, 0.05)
        else:
            asset_vol = 0.15

        rec = build_recommendation(
            ticker, score, layer_scores,
            modal_regime, asset_vol, weights
        )
        if rec:
            all_recs.append(rec)

    all_recs.sort(key=lambda x: x["abs_score"], reverse=True)

    longs  = [r for r in all_recs if r["direction"] == "LONG"]
    shorts = [r for r in all_recs if r["direction"] == "SHORT"]

    # ── 5. Generate pair trades ───────────────────────────
    pair_trades = generate_pair_trades(
        longs, shorts, prices, modal_regime
    )

    # ── 6. Conviction distribution ────────────────────────
    conv_dist = {}
    for tier in ["VERY HIGH","HIGH","MEDIUM","LOW"]:
        conv_dist[tier] = sum(1 for r in all_recs
                               if r["conviction"] == tier)

    # ── 7. Factor summary (which signals are bullish/bearish)
    factor_summary = {
        layer: {
            "avg_score":  round(
                float(np.mean(list(sig.values()))), 3
            ),
            "bullish_count": sum(
                1 for v in sig.values() if v > 0.5
            ),
            "bearish_count": sum(
                1 for v in sig.values() if v < -0.5
            ),
            "weight_pct": round(weights.get(layer, 0) * 100, 1),
        }
        for layer, sig in layer_scores.items()
    }

    # ══════════════════════════════════════════════════════════════
    # UPGRADE 1: Factor Crowding Detector
    # ══════════════════════════════════════════════════════════════
    logger.info("[TradeEngine] Computing factor crowding...")
    crowding_result = compute_factor_crowding(
        prices, composite, layer_scores
    )

    # ══════════════════════════════════════════════════════════════
    # UPGRADE 2: Rolling IC Monitor
    # ══════════════════════════════════════════════════════════════
    logger.info("[TradeEngine] Computing rolling IC...")
    ic_result = compute_rolling_ic(prices, layer_scores, lookback_months=3)

    # Apply IC-adjusted weight multipliers to existing weights
    ic_adjustments = ic_result.get("weight_adjustments", {})

    # ══════════════════════════════════════════════════════════════
    # UPGRADE 3: Meta-Labeling Pass
    # ══════════════════════════════════════════════════════════════
    logger.info("[TradeEngine] Applying meta-labels...")

    # Import meta-labeler
    from signalling.meta_labeler import apply_meta_labels

    # VIX percentile (1Y lookback)
    vix_series = df["VIXCLS"].dropna() if "VIXCLS" in df.columns else pd.Series([18.0])
    vix_1y = vix_series.tail(252) if len(vix_series) >= 252 else vix_series.tail(60)
    vix_pct = float((vix_1y < vix).sum() / len(vix_1y)) if len(vix_1y) > 1 else 0.5

    all_recs_meta = apply_meta_labels(
        all_recs,
        crowding_result,
        ic_result,
        vix,
        vix_pct,
        modal_regime,
    )

    longs = [r for r in all_recs_meta if r["direction"] == "LONG"]
    shorts = [r for r in all_recs_meta if r["direction"] == "SHORT"]

    # Re-run pair trades on meta-filtered longs/shorts
    pair_trades = generate_pair_trades(
        longs, shorts, prices, modal_regime
    )

    return {
        "longs":          longs[:max_longs],
        "shorts":         shorts[:max_shorts],
        "top_picks":      sorted(all_recs_meta,
                                  key=lambda x: x["meta"]["meta_score"] * x["abs_score"],
                                  reverse=True)[:5],
        "pair_trades":    pair_trades,
        "class_summary":  _class_summary(longs, shorts),
        "factor_summary": factor_summary,
        "signal_weights": {k: round(v * 100, 1)
                           for k, v in weights.items()},
        "total_longs":    len(longs),
        "total_shorts":   len(shorts),
        "regime":         modal_regime,
        "regime_probs":   regime_probs,
        "conviction_dist":conv_dist,
        "methodology":    {
            "regime":   "Bridgewater All-Weather (Dalio 2012)",
            "value":    "AQR Value Everywhere (Asness et al. 2013)",
            "momentum": "AQR Momentum Everywhere (Asness et al. 2013)"
                        " + Man AHL Trend",
            "quality":  "AQR Quality-Minus-Junk (Asness et al. 2014)",
            "bab":      "Betting Against Beta (Frazzini & Pedersen 2014)",
            "carry":    "Carry (Koijen, Moskowitz, Pedersen 2018)",
            "trend":    "Trend Following (Hurst, Ooi, Pedersen 2013)",
        },
        # ══════════════════════════════════════════════════════════════
        # PRODUCTION UPGRADES — Three Sigma / DE Shaw / Lopez de Prado
        # ══════════════════════════════════════════════════════════════
        "crowding":       crowding_result,
        "signal_health":  ic_result,
        "meta_stats": {
            "total_candidates":   len(all_recs),
            "passed_meta":        len(all_recs_meta),
            "filtered_out":       len(all_recs) - len(all_recs_meta),
            "avg_meta_score":     round(
                float(np.mean([r["meta"]["meta_score"]
                               for r in all_recs_meta])), 3
            ) if all_recs_meta else 0.0,
            "crowding_alert":     crowding_result["alert_level"],
            "signal_health":      ic_result["overall_signal_health"],
            "unwind_detected":    crowding_result["unwind_signal"],
        },
        "generated_at": datetime.utcnow().isoformat(),
    }


def _class_summary(longs, shorts) -> dict:
    summary = {}
    for r in longs + shorts:
        cls = r["asset_class"]
        if cls not in summary:
            summary[cls] = {"longs":0,"shorts":0}
        summary[cls][r["direction"].lower()+"s"] += 1
    return summary
