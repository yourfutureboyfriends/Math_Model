"""
UniverseBuilder — discovers all tradeable instruments across major
global exchanges via Finnhub and enriches them with yfinance fundamentals.
"""

import os, json, time, logging, asyncio
from typing import Optional
from datetime import datetime, timedelta
import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

FINNHUB_KEY = os.environ.get("FINNHUB_API_KEY", "")

# ── EXCHANGES TO COVER ─────────────────────────────────────────────────────
EXCHANGES = [
    # North America
    {"code": "US",  "name": "United States",  "region": "NA",  "mic": None},
    {"code": "TO",  "name": "Toronto (TSX)",  "region": "NA",  "mic": None},
    {"code": "V",   "name": "TSX Venture",    "region": "NA",  "mic": None},
    # Europe
    {"code": "L",   "name": "London (LSE)",   "region": "EU",  "mic": None},
    {"code": "PA",  "name": "Paris (Euronext)","region": "EU", "mic": None},
    {"code": "DE",  "name": "Frankfurt (XETRA)","region":"EU", "mic": None},
    {"code": "AS",  "name": "Amsterdam (AEX)","region": "EU",  "mic": None},
    {"code": "MI",  "name": "Milan (BIT)",     "region": "EU", "mic": None},
    {"code": "MC",  "name": "Madrid (BME)",    "region": "EU", "mic": None},
    {"code": "ST",  "name": "Stockholm (OMX)", "region": "EU", "mic": None},
    # Asia-Pacific
    {"code": "T",   "name": "Tokyo (TSE)",     "region": "APAC","mic": None},
    {"code": "HK",  "name": "Hong Kong (HKEX)","region":"APAC","mic": None},
    {"code": "SI",  "name": "Singapore (SGX)", "region":"APAC","mic": None},
    {"code": "AU",  "name": "Australia (ASX)", "region":"APAC","mic": None},
    {"code": "NS",  "name": "NSE India",       "region":"APAC","mic": None},
    {"code": "BO",  "name": "BSE India",       "region":"APAC","mic": None},
    {"code": "KS",  "name": "Korea (KRX)",     "region":"APAC","mic": None},
    {"code": "SS",  "name": "Shanghai (SSE)",  "region":"APAC","mic": None},
    # Middle East / Other
    {"code": "TA",  "name": "Tel Aviv (TASE)", "region": "MENA","mic": None},
    {"code": "JO",  "name": "Johannesburg",    "region": "MENA","mic": None},
]

# ETF-only asset classes that are handled via known tickers
MACRO_ETF_TICKERS = [
    # Macro Equity
    "SPY","QQQ","IWM","EFA","EEM","VTI","VEA","VWO",
    # Sectors
    "XLE","XLF","XLK","XLB","XLI","XLV","XLP","XLU","XLRE","XLY","XLC",
    # Factors
    "MTUM","VLUE","QUAL","USMV","DGRO","IWD","IWF","EFAV","EMGF",
    # Bonds
    "TLT","IEF","SHY","TIP","HYG","LQD","EMB","BND","AGG","VCIT","VCSH",
    "MUB","BWX","BNDX","IGOV",
    # Commodities
    "GLD","IAU","SLV","USO","UNG","DBC","PDBC","CPER","WEAT","CORN","SOYB",
    "DBB","DBP","DBA",
    # FX (ETFs)
    "UUP","FXE","FXY","FXB","FXC","FXA","FXF","CEW",
    # Alternatives / Real Assets
    "VNQ","SCHH","REM","AMLP","MLPA","ICLN","TAN","FAN",
    # International Country ETFs
    "EWJ","EWZ","EWG","EWU","EWC","EWA","EWH","INDA","MCHI","EWT",
    "EWY","EWL","EWD","EWI","EWP","EWN","EWQ","EWO","EWS","EWM",
    # Volatility
    "VIXY","VXX","SVXY",
    # Crypto proxies (ETFs)
    "IBIT","FBTC","GBTC","ETHE",
]

# ── QUALITY FILTERS ───────────────────────────────────────────────────────
MIN_MARKET_CAP_USD = 500_000_000
MIN_AVG_VOLUME = 500_000
ALLOWED_TYPES = {"Common Stock", "EQS", "DR", "GDR"}

# ── SECTOR → REGIME MAPPING ────────────────────────────────────────────────
SECTOR_REGIME_MAP = {
    "Energy":                   {"Goldilocks": 0, "Reflation": 3, "Slowdown":-1, "Stagflation": 2},
    "Basic Materials":          {"Goldilocks": 1, "Reflation": 3, "Slowdown":-2, "Stagflation": 0},
    "Industrials":              {"Goldilocks": 2, "Reflation": 2, "Slowdown":-2, "Stagflation":-1},
    "Financial Services":       {"Goldilocks": 2, "Reflation": 2, "Slowdown":-2, "Stagflation":-1},
    "Consumer Cyclical":        {"Goldilocks": 2, "Reflation": 0, "Slowdown":-2, "Stagflation":-3},
    "Technology":               {"Goldilocks": 3, "Reflation":-1, "Slowdown": 0, "Stagflation":-2},
    "Communication Services":   {"Goldilocks": 2, "Reflation": 0, "Slowdown":-1, "Stagflation":-2},
    "Healthcare":               {"Goldilocks": 1, "Reflation": 0, "Slowdown": 2, "Stagflation": 1},
    "Consumer Defensive":       {"Goldilocks":-1, "Reflation":-2, "Slowdown": 2, "Stagflation": 1},
    "Utilities":                {"Goldilocks":-1, "Reflation":-3, "Slowdown": 2, "Stagflation": 0},
    "Real Estate":              {"Goldilocks": 1, "Reflation": 0, "Slowdown":-1, "Stagflation":-2},
    "Unknown":                  {"Goldilocks": 0, "Reflation": 0, "Slowdown": 0, "Stagflation": 0},
}

# Factor classification by sector
SECTOR_FACTOR_MAP = {
    "Energy":                 "value",
    "Basic Materials":        "value",
    "Industrials":            "momentum",
    "Financial Services":     "value",
    "Consumer Cyclical":      "growth",
    "Technology":             "growth",
    "Communication Services": "growth",
    "Healthcare":             "quality",
    "Consumer Defensive":     "low_vol",
    "Utilities":              "low_vol",
    "Real Estate":            "low_vol",
}

# ── FACTOR WEIGHTS BY REGIME ─────────────────────────────────────────────
FACTOR_WEIGHTS_BY_REGIME = {
    "Goldilocks":  {"growth":0.30,"momentum":0.25,"quality":0.20,
                    "value":0.10,"size":0.08,"low_vol":0.05,
                    "inflation":0.02,"duration":0.00,"credit":0.00},
    "Reflation":   {"value":0.30,"momentum":0.25,"inflation":0.20,
                    "growth":0.10,"size":0.08,"quality":0.05,
                    "low_vol":0.02,"duration":0.00,"credit":0.00},
    "Slowdown":    {"quality":0.30,"low_vol":0.25,"duration":0.20,
                    "credit":0.10,"growth":0.08,"value":0.05,
                    "momentum":0.02,"inflation":0.00,"size":0.00},
    "Stagflation": {"inflation":0.35,"low_vol":0.20,"quality":0.15,
                    "value":0.15,"momentum":0.05,"duration":0.05,
                    "size":0.03,"credit":0.02,"growth":0.00},
}

# ── REDIS CACHE HELPERS ────────────────────────────────────────────────────
def _get_redis():
    """Get Redis client if available, else None."""
    try:
        import redis
        r = redis.Redis(host="localhost", port=6379, decode_responses=True)
        r.ping()
        return r
    except Exception:
        return None


UNIVERSE_CACHE_KEY = "trade_universe_v2"
UNIVERSE_CACHE_TTL = 6 * 3600  # 6 hours


def _load_from_cache() -> Optional[list[dict]]:
    r = _get_redis()
    if not r:
        cache_path = "/tmp/trade_universe_cache.json"
        try:
            import os
            if os.path.exists(cache_path):
                mtime = os.path.getmtime(cache_path)
                if time.time() - mtime < UNIVERSE_CACHE_TTL:
                    with open(cache_path) as f:
                        return json.load(f)
        except Exception:
            pass
        return None
    try:
        data = r.get(UNIVERSE_CACHE_KEY)
        if data:
            return json.loads(data)
    except Exception:
        pass
    return None


def _save_to_cache(universe: list[dict]):
    r = _get_redis()
    payload = json.dumps(universe)
    if r:
        try:
            r.setex(UNIVERSE_CACHE_KEY, UNIVERSE_CACHE_TTL, payload)
            return
        except Exception:
            pass
    try:
        with open("/tmp/trade_universe_cache.json", "w") as f:
            f.write(payload)
    except Exception:
        pass


# ── FINNHUB FETCHER ─────────────────────────────────────────────────────────
def _fetch_finnhub_symbols(exchange_code: str) -> list[dict]:
    """Fetch all symbols for a given exchange from Finnhub."""
    if not FINNHUB_KEY:
        return []
    try:
        import finnhub
        client = finnhub.Client(api_key=FINNHUB_KEY)
        symbols = client.stock_symbols(exchange_code)
        result = []
        for s in symbols:
            result.append({
                "ticker":        s.get("symbol", ""),
                "display_symbol":s.get("displaySymbol", ""),
                "description":   s.get("description", ""),
                "type":          s.get("type", ""),
                "mic":           s.get("mic", ""),
                "exchange_code": exchange_code,
                "currency":      s.get("currency", ""),
                "figi":          s.get("figi", ""),
                "isin":          s.get("isin", ""),
            })
        return result
    except Exception as e:
        logger.warning(f"Finnhub symbol fetch failed for {exchange_code}: {e}")
        return []


# ── YFINANCE ENRICHMENT ─────────────────────────────────────────────────────
def _enrich_batch_yfinance(tickers: list[str], exchange_code: str) -> dict[str, dict]:
    """Fetch fundamentals for a batch of tickers via yfinance."""
    YF_SUFFIX = {
        "L":  ".L",  "PA": ".PA", "DE": ".DE", "AS": ".AS",
        "MI": ".MI", "MC": ".MC", "ST": ".ST",
        "T":  ".T",  "HK": ".HK", "SI": ".SI", "AU": ".AX",
        "NS": ".NS", "BO": ".BO", "KS": ".KS", "SS": ".SS",
        "TO": ".TO", "V":  ".V",  "TA": ".TA", "JO": ".JO",
        "US": "",
    }
    suffix = YF_SUFFIX.get(exchange_code, "")
    results = {}
    BATCH_SIZE = 200

    for i in range(0, len(tickers), BATCH_SIZE):
        batch = tickers[i:i+BATCH_SIZE]
        yf_tickers = [t + suffix for t in batch]
        ticker_map = dict(zip(yf_tickers, batch))

        try:
            tickers_obj = yf.Tickers(" ".join(yf_tickers))

            for yf_sym, orig_sym in ticker_map.items():
                try:
                    info = tickers_obj.tickers[yf_sym].fast_info
                    market_cap = getattr(info, "market_cap", None) or 0
                    avg_volume = getattr(info, "three_month_average_volume", None) or 0
                    last_price = getattr(info, "last_price", None) or 0
                    currency = getattr(info, "currency", "USD")
                    exchange_name = getattr(info, "exchange", "")

                    if market_cap >= MIN_MARKET_CAP_USD * 0.5:
                        full_info = tickers_obj.tickers[yf_sym].info
                        sector = full_info.get("sector", "Unknown")
                        industry = full_info.get("industry", "")
                        country = full_info.get("country", "")
                        pe_ratio = full_info.get("trailingPE", None)
                        pb_ratio = full_info.get("priceToBook", None)
                        ps_ratio = full_info.get("priceToSalesTrailing12Months", None)
                        div_yield = full_info.get("dividendYield", None)
                        beta = full_info.get("beta", None)
                        roe = full_info.get("returnOnEquity", None)
                        de_ratio = full_info.get("debtToEquity", None)
                        revenue_g = full_info.get("revenueGrowth", None)
                        eps_g = full_info.get("earningsGrowth", None)
                        short_ratio = full_info.get("shortRatio", None)
                        rec_mean = full_info.get("recommendationMean", None)
                        analyst_n = full_info.get("numberOfAnalystOpinions", 0)
                        long_name = full_info.get("longName", orig_sym)
                        mkt_cap_fmt = full_info.get("marketCap", market_cap)
                    else:
                        sector = industry = country = long_name = "Unknown"
                        pe_ratio = pb_ratio = ps_ratio = div_yield = None
                        beta = roe = de_ratio = revenue_g = eps_g = None
                        short_ratio = rec_mean = None
                        analyst_n = 0
                        mkt_cap_fmt = market_cap

                    results[orig_sym] = {
                        "yf_symbol": yf_sym,
                        "long_name": long_name,
                        "sector": sector,
                        "industry": industry,
                        "country": country,
                        "market_cap": float(mkt_cap_fmt or 0),
                        "avg_volume": float(avg_volume or 0),
                        "last_price": float(last_price or 0),
                        "currency": currency,
                        "exchange_name": exchange_name,
                        "pe": pe_ratio,
                        "pb": pb_ratio,
                        "ps": ps_ratio,
                        "div_yield": round(float(div_yield)*100, 2) if div_yield else None,
                        "beta": beta,
                        "roe": roe,
                        "de_ratio": de_ratio,
                        "revenue_growth": revenue_g,
                        "eps_growth": eps_g,
                        "short_ratio": short_ratio,
                        "analyst_rec": rec_mean,
                        "analyst_count": analyst_n,
                    }
                except Exception:
                    pass
        except Exception as e:
            logger.warning(f"yfinance batch enrich failed ({exchange_code}): {e}")

        time.sleep(0.5)

    return results


# ── QUALITY FILTER ──────────────────────────────────────────────────────────
def _passes_quality_filter(fundamentals: dict) -> bool:
    """Return True if this asset should be included in the universe."""
    if fundamentals.get("market_cap", 0) < MIN_MARKET_CAP_USD:
        return False
    if fundamentals.get("avg_volume", 0) < MIN_AVG_VOLUME:
        return False
    if fundamentals.get("last_price", 0) <= 0.1:
        return False
    return True


def _classify_size(market_cap: float) -> str:
    if market_cap >= 200e9:   return "Mega"
    elif market_cap >= 10e9:  return "Large"
    elif market_cap >= 2e9:   return "Mid"
    elif market_cap >= 300e6: return "Small"
    else:                     return "Micro"


# ── BUILD ASSET RECORD ──────────────────────────────────────────────────────
def _build_asset_record(ticker: str, finnhub_row: dict, fundamentals: dict, exchange: dict) -> dict:
    """Construct the full asset record used by the scoring engine."""
    sector = fundamentals.get("sector", "Unknown") or "Unknown"
    regime_v = SECTOR_REGIME_MAP.get(sector, SECTOR_REGIME_MAP["Unknown"])
    factor = SECTOR_FACTOR_MAP.get(sector, "momentum")

    cap_class = _classify_size(fundamentals.get("market_cap", 0))
    if cap_class in ("Small", "Micro"):
        factor = "size"

    pe = fundamentals.get("pe")
    pb = fundamentals.get("pb")
    roe = fundamentals.get("roe")
    rev_g = fundamentals.get("revenue_growth")
    beta = fundamentals.get("beta", 1.0) or 1.0

    fundamental_score = 0.0
    if pe is not None:
        if pe < 0:            fundamental_score -= 0.5
        elif pe < 10:         fundamental_score += 0.8
        elif pe < 15:         fundamental_score += 0.5
        elif pe < 25:         fundamental_score += 0.2
        elif pe < 40:         fundamental_score -= 0.2
        elif pe > 60:         fundamental_score -= 0.8
    if roe is not None:
        if roe > 0.25:        fundamental_score += 0.4
        elif roe > 0.15:      fundamental_score += 0.2
        elif roe < 0:         fundamental_score -= 0.5
    if rev_g is not None:
        if rev_g > 0.20:      fundamental_score += 0.3
        elif rev_g > 0.10:    fundamental_score += 0.15
        elif rev_g < -0.05:   fundamental_score -= 0.3
    if beta is not None:
        if beta > 2.5:        fundamental_score -= 0.3

    rec = fundamentals.get("analyst_rec")
    analyst_n = fundamentals.get("analyst_count", 0)
    analyst_adj = 0.0
    if rec is not None and analyst_n >= 3:
        analyst_adj = round((3.0 - rec) / 4.0 * 0.5, 3)

    return {
        "ticker": ticker,
        "yf_symbol": fundamentals.get("yf_symbol", ticker),
        "name": fundamentals.get("long_name", ticker),
        "isin": finnhub_row.get("isin", ""),
        "figi": finnhub_row.get("figi", ""),
        "asset_class": "stock",
        "sub_class": sector.lower().replace(" ", "_"),
        "sector": sector,
        "industry": fundamentals.get("industry", ""),
        "country": fundamentals.get("country", ""),
        "region": exchange.get("region", ""),
        "exchange": exchange.get("name", ""),
        "exchange_code": exchange.get("code", ""),
        "currency": fundamentals.get("currency", "USD"),
        "cap_class": cap_class,
        "regime": regime_v,
        "factor": factor,
        "market_cap": fundamentals.get("market_cap", 0),
        "avg_volume": fundamentals.get("avg_volume", 0),
        "last_price": fundamentals.get("last_price", 0),
        "pe": pe,
        "pb": pb,
        "ps": fundamentals.get("ps"),
        "div_yield": fundamentals.get("div_yield"),
        "beta": beta,
        "roe": roe,
        "de_ratio": fundamentals.get("de_ratio"),
        "revenue_growth": rev_g,
        "eps_growth": fundamentals.get("eps_growth"),
        "short_ratio": fundamentals.get("short_ratio"),
        "analyst_rec": rec,
        "analyst_count": analyst_n,
        "fundamental_score": round(fundamental_score, 4),
        "analyst_adj": round(analyst_adj, 4),
        "source": "finnhub+yfinance",
        "fetched_at": datetime.utcnow().isoformat(),
    }


# ── ETF ASSET CLASS MAPPING ─────────────────────────────────────────────────
# Maps ETFs to asset classes with regime sensitivity scores
ETF_ASSET_CLASS_MAP = {
    # Macro Equity
    "SPY": {"asset_class": "equity", "sub_class": "broad_us", "factor": "momentum", "regime": {"Goldilocks": 3, "Reflation": 2, "Slowdown": -1, "Stagflation": -2}},
    "QQQ": {"asset_class": "equity", "sub_class": "tech", "factor": "growth", "regime": {"Goldilocks": 3, "Reflation": -1, "Slowdown": 0, "Stagflation": -3}},
    "IWM": {"asset_class": "equity", "sub_class": "small_cap", "factor": "size", "regime": {"Goldilocks": 2, "Reflation": 3, "Slowdown": -3, "Stagflation": -2}},
    "EFA": {"asset_class": "equity", "sub_class": "developed_intl", "factor": "value", "regime": {"Goldilocks": 2, "Reflation": 1, "Slowdown": -1, "Stagflation": -1}},
    "EEM": {"asset_class": "equity", "sub_class": "emerging", "factor": "momentum", "regime": {"Goldilocks": 2, "Reflation": 3, "Slowdown": -3, "Stagflation": -2}},
    "VTI": {"asset_class": "equity", "sub_class": "total_us", "factor": "momentum", "regime": {"Goldilocks": 3, "Reflation": 1, "Slowdown": -1, "Stagflation": -2}},
    "VEA": {"asset_class": "equity", "sub_class": "developed_intl", "factor": "value", "regime": {"Goldilocks": 2, "Reflation": 1, "Slowdown": -1, "Stagflation": -1}},
    "VWO": {"asset_class": "equity", "sub_class": "emerging", "factor": "momentum", "regime": {"Goldilocks": 2, "Reflation": 3, "Slowdown": -3, "Stagflation": -2}},
    # Sectors
    "XLE": {"asset_class": "sector", "sub_class": "energy", "factor": "value", "regime": {"Goldilocks": 0, "Reflation": 3, "Slowdown": -1, "Stagflation": 2}},
    "XLF": {"asset_class": "sector", "sub_class": "financials", "factor": "value", "regime": {"Goldilocks": 2, "Reflation": 2, "Slowdown": -2, "Stagflation": -1}},
    "XLK": {"asset_class": "sector", "sub_class": "technology", "factor": "growth", "regime": {"Goldilocks": 3, "Reflation": -1, "Slowdown": 0, "Stagflation": -2}},
    "XLB": {"asset_class": "sector", "sub_class": "materials", "factor": "value", "regime": {"Goldilocks": 1, "Reflation": 3, "Slowdown": -2, "Stagflation": 0}},
    "XLI": {"asset_class": "sector", "sub_class": "industrials", "factor": "momentum", "regime": {"Goldilocks": 2, "Reflation": 2, "Slowdown": -2, "Stagflation": -1}},
    "XLV": {"asset_class": "sector", "sub_class": "healthcare", "factor": "quality", "regime": {"Goldilocks": 1, "Reflation": 0, "Slowdown": 2, "Stagflation": 1}},
    "XLP": {"asset_class": "sector", "sub_class": "consumer_staples", "factor": "low_vol", "regime": {"Goldilocks": -1, "Reflation": -2, "Slowdown": 2, "Stagflation": 1}},
    "XLU": {"asset_class": "sector", "sub_class": "utilities", "factor": "low_vol", "regime": {"Goldilocks": -1, "Reflation": -3, "Slowdown": 2, "Stagflation": 0}},
    "XLRE": {"asset_class": "sector", "sub_class": "real_estate", "factor": "low_vol", "regime": {"Goldilocks": 1, "Reflation": 0, "Slowdown": -1, "Stagflation": -2}},
    "XLY": {"asset_class": "sector", "sub_class": "consumer_discretionary", "factor": "growth", "regime": {"Goldilocks": 2, "Reflation": 0, "Slowdown": -2, "Stagflation": -3}},
    "XLC": {"asset_class": "sector", "sub_class": "communication", "factor": "growth", "regime": {"Goldilocks": 2, "Reflation": 0, "Slowdown": -1, "Stagflation": -2}},
    # Factors
    "MTUM": {"asset_class": "factor", "sub_class": "momentum", "factor": "momentum", "regime": {"Goldilocks": 3, "Reflation": 2, "Slowdown": -1, "Stagflation": -2}},
    "VLUE": {"asset_class": "factor", "sub_class": "value", "factor": "value", "regime": {"Goldilocks": 1, "Reflation": 3, "Slowdown": -1, "Stagflation": 0}},
    "QUAL": {"asset_class": "factor", "sub_class": "quality", "factor": "quality", "regime": {"Goldilocks": 2, "Reflation": 1, "Slowdown": 3, "Stagflation": 1}},
    "USMV": {"asset_class": "factor", "sub_class": "min_vol", "factor": "low_vol", "regime": {"Goldilocks": 0, "Reflation": -2, "Slowdown": 3, "Stagflation": 1}},
    "DGRO": {"asset_class": "factor", "sub_class": "dividend_growth", "factor": "quality", "regime": {"Goldilocks": 2, "Reflation": 0, "Slowdown": 2, "Stagflation": 1}},
    "IWD": {"asset_class": "factor", "sub_class": "value", "factor": "value", "regime": {"Goldilocks": 1, "Reflation": 3, "Slowdown": -1, "Stagflation": 0}},
    "IWF": {"asset_class": "factor", "sub_class": "growth", "factor": "growth", "regime": {"Goldilocks": 3, "Reflation": -1, "Slowdown": 0, "Stagflation": -2}},
    "EFAV": {"asset_class": "factor", "sub_class": "min_vol_intl", "factor": "low_vol", "regime": {"Goldilocks": 0, "Reflation": -2, "Slowdown": 3, "Stagflation": 1}},
    "EMGF": {"asset_class": "factor", "sub_class": "emerging_multifactor", "factor": "momentum", "regime": {"Goldilocks": 2, "Reflation": 2, "Slowdown": -2, "Stagflation": -1}},
    # Bonds - Duration sensitive
    "TLT": {"asset_class": "bond", "sub_class": "treasury_long", "factor": "duration", "regime": {"Goldilocks": 0, "Reflation": -3, "Slowdown": 3, "Stagflation": 1}},
    "IEF": {"asset_class": "bond", "sub_class": "treasury_intermediate", "factor": "duration", "regime": {"Goldilocks": 1, "Reflation": -2, "Slowdown": 2, "Stagflation": 1}},
    "SHY": {"asset_class": "bond", "sub_class": "treasury_short", "factor": "duration", "regime": {"Goldilocks": 2, "Reflation": -1, "Slowdown": 1, "Stagflation": 2}},
    "TIP": {"asset_class": "bond", "sub_class": "tips", "factor": "inflation", "regime": {"Goldilocks": 1, "Reflation": 2, "Slowdown": 1, "Stagflation": 3}},
    "HYG": {"asset_class": "bond", "sub_class": "high_yield", "factor": "credit", "regime": {"Goldilocks": 2, "Reflation": 2, "Slowdown": -2, "Stagflation": -1}},
    "LQD": {"asset_class": "bond", "sub_class": "investment_grade", "factor": "credit", "regime": {"Goldilocks": 1, "Reflation": 0, "Slowdown": 2, "Stagflation": 0}},
    "EMB": {"asset_class": "bond", "sub_class": "emerging_debt", "factor": "credit", "regime": {"Goldilocks": 2, "Reflation": 2, "Slowdown": -2, "Stagflation": -1}},
    "BND": {"asset_class": "bond", "sub_class": "aggregate", "factor": "duration", "regime": {"Goldilocks": 1, "Reflation": -1, "Slowdown": 2, "Stagflation": 1}},
    "AGG": {"asset_class": "bond", "sub_class": "aggregate", "factor": "duration", "regime": {"Goldilocks": 1, "Reflation": -1, "Slowdown": 2, "Stagflation": 1}},
    "VCIT": {"asset_class": "bond", "sub_class": "ig_intermediate", "factor": "credit", "regime": {"Goldilocks": 1, "Reflation": 0, "Slowdown": 2, "Stagflation": 0}},
    "VCSH": {"asset_class": "bond", "sub_class": "ig_short", "factor": "credit", "regime": {"Goldilocks": 2, "Reflation": -1, "Slowdown": 1, "Stagflation": 1}},
    "MUB": {"asset_class": "bond", "sub_class": "muni", "factor": "duration", "regime": {"Goldilocks": 1, "Reflation": -1, "Slowdown": 2, "Stagflation": 1}},
    "BWX": {"asset_class": "bond", "sub_class": "intl_treasury", "factor": "duration", "regime": {"Goldilocks": 0, "Reflation": -1, "Slowdown": 2, "Stagflation": 0}},
    "BNDX": {"asset_class": "bond", "sub_class": "intl_aggregate", "factor": "duration", "regime": {"Goldilocks": 0, "Reflation": -1, "Slowdown": 2, "Stagflation": 0}},
    "IGOV": {"asset_class": "bond", "sub_class": "intl_treasury", "factor": "duration", "regime": {"Goldilocks": 0, "Reflation": -1, "Slowdown": 2, "Stagflation": 0}},
    # Commodities - Inflation sensitive
    "GLD": {"asset_class": "commodity", "sub_class": "gold", "factor": "inflation", "regime": {"Goldilocks": 0, "Reflation": 1, "Slowdown": 1, "Stagflation": 3}},
    "IAU": {"asset_class": "commodity", "sub_class": "gold", "factor": "inflation", "regime": {"Goldilocks": 0, "Reflation": 1, "Slowdown": 1, "Stagflation": 3}},
    "SLV": {"asset_class": "commodity", "sub_class": "silver", "factor": "inflation", "regime": {"Goldilocks": 1, "Reflation": 2, "Slowdown": 0, "Stagflation": 2}},
    "USO": {"asset_class": "commodity", "sub_class": "oil", "factor": "inflation", "regime": {"Goldilocks": 0, "Reflation": 3, "Slowdown": -2, "Stagflation": 3}},
    "UNG": {"asset_class": "commodity", "sub_class": "natural_gas", "factor": "inflation", "regime": {"Goldilocks": -1, "Reflation": 2, "Slowdown": -1, "Stagflation": 2}},
    "DBC": {"asset_class": "commodity", "sub_class": "broad", "factor": "inflation", "regime": {"Goldilocks": 0, "Reflation": 3, "Slowdown": -1, "Stagflation": 2}},
    "PDBC": {"asset_class": "commodity", "sub_class": "broad", "factor": "inflation", "regime": {"Goldilocks": 0, "Reflation": 3, "Slowdown": -1, "Stagflation": 2}},
    "CPER": {"asset_class": "commodity", "sub_class": "copper", "factor": "inflation", "regime": {"Goldilocks": 2, "Reflation": 3, "Slowdown": -2, "Stagflation": 1}},
    "WEAT": {"asset_class": "commodity", "sub_class": "agriculture", "factor": "inflation", "regime": {"Goldilocks": 0, "Reflation": 2, "Slowdown": 0, "Stagflation": 3}},
    "CORN": {"asset_class": "commodity", "sub_class": "agriculture", "factor": "inflation", "regime": {"Goldilocks": 0, "Reflation": 2, "Slowdown": 0, "Stagflation": 3}},
    "SOYB": {"asset_class": "commodity", "sub_class": "agriculture", "factor": "inflation", "regime": {"Goldilocks": 0, "Reflation": 2, "Slowdown": 0, "Stagflation": 3}},
    "DBB": {"asset_class": "commodity", "sub_class": "base_metals", "factor": "inflation", "regime": {"Goldilocks": 1, "Reflation": 3, "Slowdown": -2, "Stagflation": 1}},
    "DBP": {"asset_class": "commodity", "sub_class": "precious_metals", "factor": "inflation", "regime": {"Goldilocks": 0, "Reflation": 1, "Slowdown": 1, "Stagflation": 2}},
    "DBA": {"asset_class": "commodity", "sub_class": "agriculture", "factor": "inflation", "regime": {"Goldilocks": 0, "Reflation": 2, "Slowdown": 0, "Stagflation": 3}},
    # FX
    "UUP": {"asset_class": "fx", "sub_class": "dollar_bull", "factor": "value", "regime": {"Goldilocks": 1, "Reflation": -1, "Slowdown": 2, "Stagflation": 1}},
    "FXE": {"asset_class": "fx", "sub_class": "euro", "factor": "value", "regime": {"Goldilocks": 0, "Reflation": 1, "Slowdown": -1, "Stagflation": -1}},
    "FXY": {"asset_class": "fx", "sub_class": "yen", "factor": "low_vol", "regime": {"Goldilocks": -1, "Reflation": -1, "Slowdown": 2, "Stagflation": 1}},
    "FXB": {"asset_class": "fx", "sub_class": "pound", "factor": "value", "regime": {"Goldilocks": 0, "Reflation": 1, "Slowdown": -1, "Stagflation": -1}},
    "FXC": {"asset_class": "fx", "sub_class": "cad", "factor": "value", "regime": {"Goldilocks": 1, "Reflation": 2, "Slowdown": -1, "Stagflation": 0}},
    "FXA": {"asset_class": "fx", "sub_class": "aud", "factor": "momentum", "regime": {"Goldilocks": 2, "Reflation": 3, "Slowdown": -2, "Stagflation": -1}},
    "FXF": {"asset_class": "fx", "sub_class": "swiss", "factor": "low_vol", "regime": {"Goldilocks": -1, "Reflation": -2, "Slowdown": 2, "Stagflation": 2}},
    "CEW": {"asset_class": "fx", "sub_class": "emerging_fx", "factor": "momentum", "regime": {"Goldilocks": 2, "Reflation": 2, "Slowdown": -2, "Stagflation": -2}},
    # Real Assets / Alternatives
    "VNQ": {"asset_class": "reit", "sub_class": "us_reit", "factor": "low_vol", "regime": {"Goldilocks": 2, "Reflation": 1, "Slowdown": -1, "Stagflation": -2}},
    "SCHH": {"asset_class": "reit", "sub_class": "us_reit", "factor": "low_vol", "regime": {"Goldilocks": 2, "Reflation": 1, "Slowdown": -1, "Stagflation": -2}},
    "REM": {"asset_class": "reit", "sub_class": "mortgage_reit", "factor": "credit", "regime": {"Goldilocks": 1, "Reflation": 2, "Slowdown": -2, "Stagflation": -3}},
    "AMLP": {"asset_class": "equity", "sub_class": "mlp", "factor": "value", "regime": {"Goldilocks": 1, "Reflation": 2, "Slowdown": -2, "Stagflation": 1}},
    "MLPA": {"asset_class": "equity", "sub_class": "mlp", "factor": "value", "regime": {"Goldilocks": 1, "Reflation": 2, "Slowdown": -2, "Stagflation": 1}},
    "ICLN": {"asset_class": "equity", "sub_class": "clean_energy", "factor": "growth", "regime": {"Goldilocks": 2, "Reflation": 1, "Slowdown": -1, "Stagflation": 0}},
    "TAN": {"asset_class": "equity", "sub_class": "solar", "factor": "growth", "regime": {"Goldilocks": 2, "Reflation": 1, "Slowdown": -2, "Stagflation": -1}},
    "FAN": {"asset_class": "equity", "sub_class": "wind", "factor": "growth", "regime": {"Goldilocks": 2, "Reflation": 1, "Slowdown": -1, "Stagflation": 0}},
    # International Country ETFs
    "EWJ": {"asset_class": "equity", "sub_class": "japan", "factor": "value", "regime": {"Goldilocks": 1, "Reflation": 0, "Slowdown": 0, "Stagflation": -1}},
    "EWZ": {"asset_class": "equity", "sub_class": "brazil", "factor": "momentum", "regime": {"Goldilocks": 2, "Reflation": 3, "Slowdown": -2, "Stagflation": -1}},
    "EWG": {"asset_class": "equity", "sub_class": "germany", "factor": "value", "regime": {"Goldilocks": 2, "Reflation": 1, "Slowdown": -1, "Stagflation": -1}},
    "EWU": {"asset_class": "equity", "sub_class": "uk", "factor": "value", "regime": {"Goldilocks": 1, "Reflation": 0, "Slowdown": -1, "Stagflation": -1}},
    "EWC": {"asset_class": "equity", "sub_class": "canada", "factor": "value", "regime": {"Goldilocks": 2, "Reflation": 2, "Slowdown": -1, "Stagflation": 0}},
    "EWA": {"asset_class": "equity", "sub_class": "australia", "factor": "value", "regime": {"Goldilocks": 2, "Reflation": 2, "Slowdown": -1, "Stagflation": 0}},
    "EWH": {"asset_class": "equity", "sub_class": "hong_kong", "factor": "value", "regime": {"Goldilocks": 1, "Reflation": 1, "Slowdown": -1, "Stagflation": -1}},
    "INDA": {"asset_class": "equity", "sub_class": "india", "factor": "growth", "regime": {"Goldilocks": 3, "Reflation": 2, "Slowdown": -1, "Stagflation": -1}},
    "MCHI": {"asset_class": "equity", "sub_class": "china", "factor": "momentum", "regime": {"Goldilocks": 2, "Reflation": 2, "Slowdown": -2, "Stagflation": -2}},
    "EWT": {"asset_class": "equity", "sub_class": "taiwan", "factor": "growth", "regime": {"Goldilocks": 3, "Reflation": 1, "Slowdown": -2, "Stagflation": -2}},
    "EWY": {"asset_class": "equity", "sub_class": "south_korea", "factor": "growth", "regime": {"Goldilocks": 3, "Reflation": 1, "Slowdown": -2, "Stagflation": -2}},
    "EWL": {"asset_class": "equity", "sub_class": "switzerland", "factor": "quality", "regime": {"Goldilocks": 1, "Reflation": 0, "Slowdown": 1, "Stagflation": 0}},
    "EWD": {"asset_class": "equity", "sub_class": "sweden", "factor": "growth", "regime": {"Goldilocks": 2, "Reflation": 1, "Slowdown": -1, "Stagflation": -1}},
    "EWI": {"asset_class": "equity", "sub_class": "italy", "factor": "value", "regime": {"Goldilocks": 1, "Reflation": 0, "Slowdown": -1, "Stagflation": -1}},
    "EWP": {"asset_class": "equity", "sub_class": "spain", "factor": "value", "regime": {"Goldilocks": 1, "Reflation": 0, "Slowdown": -1, "Stagflation": -1}},
    "EWN": {"asset_class": "equity", "sub_class": "netherlands", "factor": "value", "regime": {"Goldilocks": 2, "Reflation": 1, "Slowdown": -1, "Stagflation": -1}},
    "EWQ": {"asset_class": "equity", "sub_class": "france", "factor": "value", "regime": {"Goldilocks": 2, "Reflation": 1, "Slowdown": -1, "Stagflation": -1}},
    "EWO": {"asset_class": "equity", "sub_class": "austria", "factor": "value", "regime": {"Goldilocks": 1, "Reflation": 0, "Slowdown": -1, "Stagflation": -1}},
    "EWS": {"asset_class": "equity", "sub_class": "singapore", "factor": "value", "regime": {"Goldilocks": 1, "Reflation": 1, "Slowdown": 0, "Stagflation": -1}},
    "EWM": {"asset_class": "equity", "sub_class": "malaysia", "factor": "value", "regime": {"Goldilocks": 1, "Reflation": 1, "Slowdown": -1, "Stagflation": -1}},
    # Volatility
    "VIXY": {"asset_class": "volatility", "sub_class": "vix_long", "factor": "low_vol", "regime": {"Goldilocks": -3, "Reflation": -2, "Slowdown": 3, "Stagflation": 2}},
    "VXX": {"asset_class": "volatility", "sub_class": "vix_short", "factor": "low_vol", "regime": {"Goldilocks": -3, "Reflation": -2, "Slowdown": 3, "Stagflation": 2}},
    "SVXY": {"asset_class": "volatility", "sub_class": "short_vix", "factor": "momentum", "regime": {"Goldilocks": 3, "Reflation": 2, "Slowdown": -3, "Stagflation": -2}},
    # Crypto proxies
    "IBIT": {"asset_class": "crypto", "sub_class": "bitcoin", "factor": "momentum", "regime": {"Goldilocks": 2, "Reflation": 1, "Slowdown": -2, "Stagflation": 0}},
    "FBTC": {"asset_class": "crypto", "sub_class": "bitcoin", "factor": "momentum", "regime": {"Goldilocks": 2, "Reflation": 1, "Slowdown": -2, "Stagflation": 0}},
    "GBTC": {"asset_class": "crypto", "sub_class": "bitcoin", "factor": "momentum", "regime": {"Goldilocks": 2, "Reflation": 1, "Slowdown": -2, "Stagflation": 0}},
    "ETHE": {"asset_class": "crypto", "sub_class": "ethereum", "factor": "momentum", "regime": {"Goldilocks": 3, "Reflation": 2, "Slowdown": -2, "Stagflation": -1}},
}


# ── BUILD ETF RECORD ───────────────────────────────────────────────────────
def _build_etf_record(ticker: str, fundamentals: dict) -> dict:
    """Construct ETF record with regime/factor mappings."""
    mapping = ETF_ASSET_CLASS_MAP.get(ticker, {
        "asset_class": "equity",
        "sub_class": "unknown",
        "factor": "momentum",
        "regime": {"Goldilocks": 0, "Reflation": 0, "Slowdown": 0, "Stagflation": 0}
    })

    return {
        "ticker": ticker,
        "yf_symbol": fundamentals.get("yf_symbol", ticker),
        "name": fundamentals.get("long_name", ticker),
        "isin": "",
        "figi": "",
        "asset_class": mapping["asset_class"],
        "sub_class": mapping["sub_class"],
        "sector": "ETF",
        "industry": mapping["sub_class"],
        "country": "Global",
        "region": "Global",
        "exchange": "US",
        "exchange_code": "US",
        "currency": fundamentals.get("currency", "USD"),
        "cap_class": "ETF",
        "regime": mapping["regime"],
        "factor": mapping["factor"],
        "market_cap": fundamentals.get("market_cap", 0),
        "avg_volume": fundamentals.get("avg_volume", 0),
        "last_price": fundamentals.get("last_price", 0),
        "pe": None,
        "pb": None,
        "ps": None,
        "div_yield": fundamentals.get("div_yield"),
        "beta": fundamentals.get("beta", 1.0),
        "roe": None,
        "de_ratio": None,
        "revenue_growth": None,
        "eps_growth": None,
        "short_ratio": fundamentals.get("short_ratio"),
        "analyst_rec": None,
        "analyst_count": 0,
        "fundamental_score": 0.0,
        "analyst_adj": 0.0,
        "source": "yfinance",
        "fetched_at": datetime.utcnow().isoformat(),
    }


# ── MASTER UNIVERSE BUILDER ────────────────────────────────────────────────
def build_universe(force_refresh: bool = False) -> list[dict]:
    """
    Build the complete tradeable universe.

    Returns a list of asset records with regime scores and factor mappings.
    Uses 6-hour cache unless force_refresh=True.
    """
    if not force_refresh:
        cached = _load_from_cache()
        if cached:
            logger.info(f"Loaded {len(cached)} assets from cache")
            return cached

    universe = []

    # 1. Fetch individual stocks from exchanges
    for exchange in EXCHANGES:
        logger.info(f"Fetching symbols for {exchange['name']}...")
        symbols = _fetch_finnhub_symbols(exchange["code"])
        logger.info(f"  Found {len(symbols)} symbols")

        if not symbols:
            continue

        # Filter to tradeable types
        filtered = [s for s in symbols if s.get("type") in ALLOWED_TYPES]
        tickers = [s["ticker"] for s in filtered if s.get("ticker")]

        if not tickers:
            continue

        # Enrich with yfinance
        logger.info(f"  Enriching {len(tickers)} tickers from {exchange['code']}...")
        fundamentals = _enrich_batch_yfinance(tickers, exchange["code"])

        # Build asset records
        for sym_row in filtered:
            ticker = sym_row.get("ticker", "")
            fund = fundamentals.get(ticker)
            if not fund:
                continue
            if not _passes_quality_filter(fund):
                continue

            record = _build_asset_record(ticker, sym_row, fund, exchange)
            universe.append(record)

        logger.info(f"  Added {len([r for r in universe if r['exchange_code'] == exchange['code']])} assets from {exchange['code']}")

    # 2. Add macro ETFs
    logger.info(f"Fetching {len(MACRO_ETF_TICKERS)} macro ETFs...")
    etf_funds = _enrich_batch_yfinance(MACRO_ETF_TICKERS, "US")
    for ticker in MACRO_ETF_TICKERS:
        fund = etf_funds.get(ticker)
        if not fund:
            continue
        # ETFs have lower volume requirements
        if fund.get("avg_volume", 0) < 100_000:
            continue
        if fund.get("last_price", 0) <= 0.1:
            continue

        record = _build_etf_record(ticker, fund)
        universe.append(record)

    logger.info(f"Total universe size: {len(universe)} assets")

    # Cache results
    _save_to_cache(universe)
    return universe


# ── GET UNIVERSE BY ASSET CLASS ─────────────────────────────────────────────
def get_universe_by_class(asset_class: str, universe: list[dict] = None) -> list[dict]:
    """Filter universe by asset class."""
    if universe is None:
        universe = build_universe()
    return [a for a in universe if a["asset_class"] == asset_class]


def get_universe_by_factor(factor: str, universe: list[dict] = None) -> list[dict]:
    """Filter universe by factor exposure."""
    if universe is None:
        universe = build_universe()
    return [a for a in universe if a["factor"] == factor]


def get_universe_by_regime_score(regime: str, min_score: int = 1, universe: list[dict] = None) -> list[dict]:
    """Filter universe by minimum regime score."""
    if universe is None:
        universe = build_universe()
    return [a for a in universe if a.get("regime", {}).get(regime, 0) >= min_score]
