"""
Dashboard panels computed from observed market / FRED data.

These sections used to be formulas of the dashboard's own growth / inflation / risk
scores dressed up as data (e.g. "SPX 12m return" = (growth_score - 0.3) * 0.55). Each
builder here computes its numbers from real price history or FRED series instead, and
when an input is missing the value is None (or the whole section is None) — never an
invented number.

`load_section_inputs()` fetches everything concurrently (cached by the underlying
fetchers); the `build_*` functions are synchronous and only read those inputs.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional

from api.calculations import market_stats as ms
from api.handlers.macro_inputs import DatedSeries, load_fred_series

logger = logging.getLogger(__name__)

# yfinance tickers (2y daily history) used by the panels below.
PRICE_TICKERS: Dict[str, str] = {
    "SPX": "^GSPC", "NDX": "^NDX", "VIX": "^VIX", "VIX3M": "^VIX3M",
    "SPY": "SPY", "TLT": "TLT", "GLD": "GLD", "DXY": "DX-Y.NYB", "DBC": "DBC",
    "MTUM": "MTUM", "VLUE": "VLUE", "IWF": "IWF", "QUAL": "QUAL", "IWM": "IWM", "IWD": "IWD",
    "STOXX50": "^STOXX50E", "FTSE": "^FTSE", "N225": "^N225",
    "ES": "ES=F", "NQ": "NQ=F", "TY": "ZN=F", "GC": "GC=F", "CL": "CL=F",
    "EFA": "EFA", "EEM": "EEM", "AGG": "AGG",
}
# Sector proxies for the sector-allocation playbook (names as in calculate_sector_allocation).
SECTOR_PROXIES = {"Technology": "XLK", "Healthcare": "XLV", "Financials": "XLF", "Energy": "XLE",
                  "Utilities": "XLU", "Consumer": "XLY", "Consumer Staples": "XLP",
                  "Industrials": "XLI", "Materials": "XLB", "Small Cap": "IWM"}
PRICE_TICKERS.update({etf: etf for etf in SECTOR_PROXIES.values() if etf not in PRICE_TICKERS})
# ETFs whose trailing P/E feeds the CMA earnings yields.
PE_TICKERS = ["SPY", "IWM", "EFA", "EEM"]

US_TENORS = [(1 / 12, "DGS1MO"), (0.25, "DGS3MO"), (0.5, "DGS6MO"), (1, "DGS1"), (2, "DGS2"),
             (3, "DGS3"), (5, "DGS5"), (7, "DGS7"), (10, "DGS10"), (20, "DGS20"), (30, "DGS30")]
# Display code -> OECD MEI 3M interbank / 10Y government yield series (the OECD code for
# the UK is GB).
FOREIGN_CURVES = {cc: {"3M": f"IR3TIB01{oecd}M156N", "10Y": f"IRLTLT01{oecd}M156N"}
                  for cc, oecd in (("UK", "GB"), ("DE", "DE"), ("JP", "JP"), ("CA", "CA"), ("AU", "AU"))}
# Daily overnight rates used as the short end when the monthly OECD 3M series is stale
# (the UK 3M interbank series stopped updating in Jan-2026; SONIA is daily from the BoE).
OVERNIGHT_RATES = {"UK": ("IUDSOIA", "SONIA")}
# A monthly OECD observation older than this is too stale to show as the current curve.
FOREIGN_MAX_AGE_DAYS = 120

DEBT_SERIES = {"private": "QUSPAM770A", "public": "QUSGAM770A", "total": "QUSCAM770A",
               "dsr": "TDSP"}
OTHER_FRED = ["DFII10", "GDPNOW", "TOTBKCR", "GDP", "BAMLH0A0HYM2"]

_PE_CACHE: Dict[str, tuple] = {}          # ETF -> (ts, trailing P/E)
_PE_TTL = 3600

# Long monthly history (yfinance period="max") for regime-conditional return estimates.
MONTHLY_TICKERS = {"SPY": "SPY", "TLT": "TLT", "GLD": "GLD", "DBC": "DBC"}
_MONTHLY_PX_CACHE: Dict[str, tuple] = {}
_MONTHLY_PX_TTL = 12 * 3600


def rates_fred_ids() -> List[str]:
    return [sid for _, sid in US_TENORS] + ["DFII10"] + [
        sid for c in FOREIGN_CURVES.values() for sid in c.values()] + [
        sid for sid, _ in OVERNIGHT_RATES.values()]


@dataclass
class SectionInputs:
    prices: Dict[str, Dict[str, float]] = field(default_factory=dict)   # key -> {date: close}
    fred: Dict[str, DatedSeries] = field(default_factory=dict)
    spy_pe: Optional[float] = None
    trailing_pe: Dict[str, float] = field(default_factory=dict)          # ETF -> trailing P/E
    monthly_macro: Any = None                                            # load_monthly_macro() frame
    monthly_prices: Dict[str, Dict[str, float]] = field(default_factory=dict)  # key -> {YYYY-MM: close}
    forecast_stats: Optional[List[Dict[str, Any]]] = None                # forecast_history summary

    def closes(self, key: str) -> List[float]:
        return ms.closes_of(self.prices.get(key) or {})

    def aligned(self, *keys: str) -> Optional[Dict[str, List[float]]]:
        if any(not self.prices.get(k) for k in keys):
            return None
        _, out = ms.align_dated({k: self.prices[k] for k in keys})
        return out

    def series(self, sid: str) -> DatedSeries:
        return self.fred.get(sid) or DatedSeries(sid)


def _trailing_pe_sync(ticker: str) -> Optional[float]:
    import yfinance as yf
    pe = (yf.Ticker(ticker).info or {}).get("trailingPE")
    return float(pe) if isinstance(pe, (int, float)) and pe == pe and pe > 0 else None


async def _trailing_pes(tickers: List[str]) -> Dict[str, float]:
    """{ETF: trailing P/E} from Yahoo (cached 1h; last good value kept on failure)."""
    now = time.time()

    async def _one(t: str):
        hit = _PE_CACHE.get(t)
        if hit and now - hit[0] < _PE_TTL:
            return t, hit[1]
        try:
            pe = await asyncio.wait_for(asyncio.to_thread(_trailing_pe_sync, t), timeout=10)
        except Exception as e:
            logger.warning("[dashboard_sections] %s trailing P/E unavailable: %s", t, e)
            pe = None
        if pe is not None:
            _PE_CACHE[t] = (now, pe)
            return t, pe
        return t, (hit[1] if hit else None)

    return {t: pe for t, pe in await asyncio.gather(*[_one(t) for t in tickers]) if pe is not None}


async def load_section_inputs(timeout: float = 30.0) -> SectionInputs:
    from api.handlers.market_handler import _fetch_dated_closes_literal

    keys = list(PRICE_TICKERS)
    fred_ids = rates_fred_ids() + list(DEBT_SERIES.values()) + OTHER_FRED

    async def _prices():
        res = await asyncio.gather(
            *[_fetch_dated_closes_literal(PRICE_TICKERS[k], period="2y") for k in keys],
            return_exceptions=True)
        return {k: r for k, r in zip(keys, res) if isinstance(r, dict) and r}

    async def _optional(fn, *args):
        try:
            return await asyncio.to_thread(fn, *args)
        except Exception as e:
            logger.warning("[dashboard_sections] %s failed: %s", getattr(fn, "__name__", fn), e)
            return None

    from api.handlers.macro_inputs import load_monthly_macro
    try:
        prices, fred, pe, monthly, mpx, fstats = await asyncio.wait_for(
            asyncio.gather(_prices(), load_fred_series(fred_ids, days=1100), _trailing_pes(PE_TICKERS),
                           _optional(load_monthly_macro), _monthly_prices(),
                           _optional(_forecast_stats_sync)),
            timeout=timeout)
    except asyncio.TimeoutError:
        logger.warning("[dashboard_sections] input fetch timed out after %ss", timeout)
        return SectionInputs()
    missing = ([k for k in keys if k not in prices] + [s for s in fred_ids if not fred.get(s)]
               + [k for k in MONTHLY_TICKERS if k not in mpx]
               + (["monthly macro panel"] if monthly is None or getattr(monthly, "empty", True) else []))
    if missing:
        logger.warning("[dashboard_sections] unavailable inputs: %s", ", ".join(missing))
    return SectionInputs(prices=prices, fred=fred, spy_pe=pe.get("SPY"), trailing_pe=pe, monthly_macro=monthly,
                         monthly_prices=mpx, forecast_stats=fstats)


def _monthly_closes_sync(ticker: str) -> Dict[str, float]:
    import yfinance as yf
    hist = yf.Ticker(ticker).history(period="max", interval="1mo")
    if hist is None or hist.empty:
        return {}
    this_month = date.today().strftime("%Y-%m")
    out = {}
    for ts, close in zip(hist.index, hist["Close"].tolist()):
        m = str(ts)[:7]
        if m != this_month and isinstance(close, (int, float)) and close == close:
            out[m] = float(close)          # completed months only
    return out


async def _monthly_prices() -> Dict[str, Dict[str, float]]:
    now = time.time()
    out: Dict[str, Dict[str, float]] = {}

    async def _one(key: str, ticker: str):
        hit = _MONTHLY_PX_CACHE.get(key)
        if hit and now - hit[0] < _MONTHLY_PX_TTL:
            return key, hit[1]
        try:
            data = await asyncio.to_thread(_monthly_closes_sync, ticker)
        except Exception as e:
            logger.warning("[dashboard_sections] monthly history %s failed: %s", ticker, e)
            data = {}
        if data:
            _MONTHLY_PX_CACHE[key] = (now, data)
            return key, data
        return key, (hit[1] if hit else {})

    for key, data in await asyncio.gather(*[_one(k, t) for k, t in MONTHLY_TICKERS.items()]):
        if data:
            out[key] = data
    return out


def _forecast_stats_sync() -> List[Dict[str, Any]]:
    """Per-model summary of the persisted forecast log (database forecast_history)."""
    from database.db import get_db
    with get_db() as conn:
        rows = conn.execute("""
            SELECT model_name, COUNT(*) AS n, COUNT(directional_hit) AS evaluated,
                   AVG(directional_hit) AS hit_rate, MIN(forecast_date) AS first,
                   MAX(forecast_date) AS last
            FROM forecast_history GROUP BY model_name""").fetchall()
    return [dict(r) for r in rows]


def _r(v: Optional[float], nd: int = 4) -> Optional[float]:
    return round(v, nd) if v is not None else None


# ── Momentum veto ───────────────────────────────────────────────────────────────

def build_momentum_veto(inp: SectionInputs):
    """12-1 absolute momentum for SPX / NDX. Veto (dampen equity risk by half) when the
    S&P 500's 12-1 momentum is negative."""
    from api.schemas.models import MomentumVetoData
    stats = {a: ms.momentum_12_1(inp.closes(a)) for a in ("SPX", "NDX")}
    stats = {a: s for a, s in stats.items() if s is not None}
    if "SPX" not in stats:
        return None
    veto = stats["SPX"]["momentum12_1"] < 0
    damp = 0.5 if veto else 1.0
    assets = []
    for a, s in stats.items():
        m = s["momentum12_1"]
        assets.append({
            "asset": a,
            "return12m": round(s["return12m"], 4),
            "return1m": round(s["return1m"], 4),
            "momentum12_1": round(m, 4),
            "dampenedSignal": round(m * damp, 4),
            "rawSignal": "POSITIVE" if m >= 0 else "NEGATIVE",
            "interpretation": (f"{'VETO' if m < 0 else 'PASS'}: 12-1 momentum {m:+.1%}, "
                               f"last month {s['return1m']:+.1%}"),
        })
    m_spx = stats["SPX"]["momentum12_1"]
    return MomentumVetoData(
        vetoActive=veto,
        dampenerApplied=damp,
        assets=assets,
        portfolioAdjustment={
            "action": "REDUCE" if veto else "MAINTAIN",
            "magnitude": round(1 - damp, 2),
            "rationale": (f"S&P 500 12-1 momentum {m_spx:+.1%} — "
                          f"{'negative, equity signals halved' if veto else 'positive, no veto'}"),
        },
        reasoning="Absolute 12-1 momentum from Yahoo daily closes (12m return excluding the last month).",
    )


# ── Correlation regime ──────────────────────────────────────────────────────────

def _pair_regime(c: float) -> str:
    return "positive" if c > 0.2 else "negative" if c < -0.2 else "neutral"


def build_correlation_regime(inp: SectionInputs, window: int = 60):
    """Rolling 60-day daily-return correlations of SPY vs TLT / GLD / DXY. A positive
    stock-bond correlation means bonds stop hedging equities → risk-parity adjustment."""
    from api.schemas.models import CorrelationRegimeData, CorrelationPair
    pairs = []
    stock_bond = None
    for other, label, what in (("TLT", "SPY-TLT", "Long Treasuries"),
                               ("GLD", "SPY-GLD", "Gold"), ("DXY", "SPY-DXY", "US dollar")):
        al = inp.aligned("SPY", other)
        c = ms.trailing_correlation(al["SPY"], al[other], window) if al else None
        if c is None:
            continue
        if other == "TLT":
            stock_bond = c
        pairs.append(CorrelationPair(
            assetPair=label, correlation60d=round(c, 3), regime=_pair_regime(c),
            interpretation=f"{what} vs S&P 500: {window}-day return correlation {c:+.2f}"))
    if stock_bond is None:
        return None
    switch = stock_bond > 0.2
    return CorrelationRegimeData(
        currentRegime="POSITIVE" if stock_bond > 0 else "NEGATIVE",
        switchTriggered=switch,
        equityBondCorrelation=round(stock_bond, 3),
        fallbackStrategy="RISK_PARITY_ADJUSTED" if switch else "STANDARD",
        correlations=pairs,
        riskParityAdjustment={
            "normalWeights": {"stocks": 0.6, "bonds": 0.4},
            "adjustedWeights": {"stocks": 0.5, "bonds": 0.5} if switch else {"stocks": 0.6, "bonds": 0.4},
            "rationale": (f"SPY-TLT {window}d correlation {stock_bond:+.2f}: "
                          + ("bonds not hedging equities — reduce equity weight" if switch
                             else "bonds still diversify equities — standard allocation")),
        },
    )


# ── Debt cycle ──────────────────────────────────────────────────────────────────

def _yoy_change(s: DatedSeries) -> Optional[float]:
    if len(s.values) < 5:
        return None
    return s.values[-1] - s.values[-5]   # quarterly series: 4 observations back


def build_debt_cycle(inp: SectionInputs):
    """BIS credit-to-GDP (FRED QUS*AM770A) and the Fed household debt-service ratio (TDSP)."""
    from api.schemas.models import DebtCycleData
    total = inp.series(DEBT_SERIES["total"])
    if not total:
        return None
    private, public, dsr = (inp.series(DEBT_SERIES[k]) for k in ("private", "public", "dsr"))
    d_total, d_dsr = _yoy_change(total), _yoy_change(dsr)
    trend = (None if d_total is None else
             "Rising" if d_total > 1.0 else "Falling" if d_total < -1.0 else "Stable")
    if d_total is None or d_dsr is None:
        phase = None
    elif d_total < -1.0 and d_dsr <= 0:
        phase = "Deleveraging"
    elif d_total > 1.0 and d_dsr > 0.2:
        phase = "Late Cycle"
    elif d_total > 1.0:
        phase = "Expansion"
    else:
        phase = "Mid Cycle"
    parts = [f"Total non-financial credit {total.latest:.1f}% of GDP ({total.latest_date}"
             + (f", {d_total:+.1f}pp y/y)" if d_total is not None else ")")]
    if dsr:
        parts.append(f"household debt service {dsr.latest:.1f}% of income ({dsr.latest_date}"
                     + (f", {d_dsr:+.2f}pp y/y)" if d_dsr is not None else ")"))
    return DebtCycleData(
        phase=phase,
        privateDebtGDP=_r(private.latest, 1),
        publicDebtGDP=_r(public.latest, 1),
        totalDebtGDP=_r(total.latest, 1),
        debtServiceRatio=_r(dsr.latest, 1),
        trend=trend,
        interpretation="; ".join(parts) + ". Source: BIS via FRED, Fed TDSP.",
    )


# ── International macro ─────────────────────────────────────────────────────────

_REGIONS = [("Europe", "STOXX50", "Euro Stoxx 50"), ("UK", "FTSE", "FTSE 100"),
            ("Japan", "N225", "Nikkei 225")]


def build_international_macro(inp: SectionInputs, us_regime: str, us_confidence: float,
                              us_growth: Optional[float]):
    """Each region's growth state from the same equity-momentum growth signal used for
    the US, applied to its own index; globalSync = mean pairwise 60d return correlation."""
    from api.calculations import calculate_growth_signal
    from api.schemas.models import InternationalMacroData, RegionMacro
    regions = [RegionMacro(region="US", regime=us_regime, confidence=us_confidence, divergence=0.0)]
    labels = []
    for name, key, index in _REGIONS:
        closes = inp.closes(key)
        g = calculate_growth_signal(None, closes)[0] if closes else None
        if g is None:
            continue
        state = "Expansion" if g > 0.6 else "Slowdown" if g < 0.4 else "Neutral"
        regions.append(RegionMacro(
            region=name, regime=state, confidence=None,
            divergence=round(abs(g - us_growth), 2) if us_growth is not None else None))
        labels.append(f"{name} {state.lower()} ({index} momentum {g:.2f})")
    if len(regions) == 1:
        return None
    keys = ["SPX"] + [k for _, k, _ in _REGIONS if inp.prices.get(k)]
    al = inp.aligned(*keys)
    sync = ms.mean_pairwise_correlation(al, 60) if al else None
    return InternationalMacroData(
        regions=regions,
        globalSync=_r(sync, 2),
        interpretation=(f"US in {us_regime}; " + "; ".join(labels) +
                        (f". Avg 60d cross-market equity correlation {sync:.2f}." if sync is not None else ".")
                        + " Regional states use equity momentum only (no regional inflation/liquidity inputs)."),
    )


# ── Factor rotation ─────────────────────────────────────────────────────────────

_FACTORS = [("momentum", "MTUM"), ("value", "VLUE"), ("growth", "IWF"), ("quality", "QUAL")]


def build_factor_rotation(inp: SectionInputs):
    """Factor score = percentile (0-1) of the factor ETF's 3-month return relative to SPY
    within its own trailing year."""
    from api.schemas.models import FactorRotationData
    scores, rel = {}, {}
    for name, etf in _FACTORS:
        al = inp.aligned(etf, "SPY")
        s = ms.relative_strength_score(al[etf], al["SPY"]) if al else None
        scores[name] = _r(s["percentile"], 2) if s else None
        if s:
            rel[name] = s["relativeReturn"]
    if not rel:
        return None
    leader = max(rel, key=rel.get)
    laggard = min(rel, key=rel.get)
    return FactorRotationData(
        **scores,
        interpretation=("3m return vs SPY: " + ", ".join(f"{k} {v:+.1%}" for k, v in rel.items())
                        + ". Score = percentile of that spread over the past year."),
        rotationSignal=f"{leader.title()} over {laggard.title()}" if leader != laggard else leader.title(),
    )


# ── GDP nowcast ─────────────────────────────────────────────────────────────────

def build_nowcast(inp: SectionInputs, now) -> Optional[Dict[str, Any]]:
    """Atlanta Fed GDPNow (FRED GDPNOW): real GDP growth, QoQ SAAR, for the latest quarter."""
    s = inp.series("GDPNOW")
    if not s:
        return None
    q = date.fromisoformat(s.latest_date)
    quarter = f"{q.year}Q{(q.month - 1) // 3 + 1}"
    return {
        "available": True,
        "gdpNowcast": round(s.latest, 2),
        "nowcastQoQ": round(s.latest, 2),
        "nowcastYoY": None,
        "quarter": quarter,
        "confidenceInterval": None,
        "components": [],
        "revisionHistory": [{"date": d, "value": round(v, 2)}
                            for d, v in zip(s.dates[-8:], s.values[-8:])],
        "methodology": f"Atlanta Fed GDPNow (FRED: GDPNOW), real GDP QoQ SAAR for {quarter}. "
                       "No YoY or confidence band is published with this series.",
        "source": "FRED GDPNOW",
        "lastUpdated": now.isoformat(),
    }


# ── Factor decomposition ────────────────────────────────────────────────────────

def build_factor_decomposition(inp: SectionInputs, now, window: int = 252) -> Optional[Dict[str, Any]]:
    """OLS of Nasdaq-100 daily returns on market and long-short factor returns over the
    last year: Market (SPY), Size (IWM−SPY), Value (IWD−IWF), Momentum (MTUM−SPY),
    Quality (QUAL−SPY), Rates (TLT)."""
    keys = ["NDX", "SPY", "IWM", "IWD", "IWF", "MTUM", "QUAL", "TLT"]
    al = inp.aligned(*keys)
    if not al:
        return None
    r = {k: ms.daily_returns(al[k])[-window:] for k in keys}
    factors = {
        "Market": r["SPY"], "Size": r["IWM"] - r["SPY"], "Value": r["IWD"] - r["IWF"],
        "Momentum": r["MTUM"] - r["SPY"], "Quality": r["QUAL"] - r["SPY"], "Rates": r["TLT"],
    }
    fit = ms.ols_decomposition(r["NDX"], factors)
    if not fit:
        return None

    def _sig(t):
        if t is None:
            return None
        return "Highly Significant" if abs(t) >= 3 else "Significant" if abs(t) >= 2 else "Weak"

    return {
        "available": True,
        "asset": "NDX",
        "rSquared": round(fit["rSquared"], 3),
        "factors": [{"factor": f["factor"], "exposure": round(f["beta"], 2),
                     "contribution": round(f["varianceShare"] * 100, 1),
                     "tStat": _r(f["tStat"], 2), "significance": _sig(f["tStat"])}
                    for f in fit["factors"]],
        "residual": round(1 - fit["rSquared"], 3),
        "observations": fit["observations"],
        "interpretation": (f"Nasdaq-100 daily returns regressed on ETF factor returns over "
                           f"{fit['observations']} days. Contribution = share of return variance."),
        "lastUpdated": now.isoformat(),
    }


# ── CTA trend signals ───────────────────────────────────────────────────────────

_CTA_ASSETS = [("ES", "ES"), ("NQ", "NQ"), ("TY", "TY"), ("GC", "GC"), ("CL", "CL"), ("DXY", "DXY")]
_CTA_LOOKBACKS = [("1m", ms.TRADING_DAYS_1M), ("3m", ms.TRADING_DAYS_3M), ("12m", ms.TRADING_DAYS_12M)]


def build_trend_signals(inp: SectionInputs, now) -> Optional[Dict[str, Any]]:
    """Time-series momentum (sign of the 1m / 3m / 12m return) on futures and the dollar."""
    signals = []
    for label, key in _CTA_ASSETS:
        closes = inp.closes(key)
        for tf, lb in _CTA_LOOKBACKS:
            t = ms.trend_signal(closes, lb) if closes else None
            if t is None:
                continue
            signals.append({"asset": label, "direction": t["direction"],
                            "strength": round(abs(t["return"]), 4), "timeframe": tf,
                            "confidence": _r(min(abs(t["tStat"]), 3.0) / 3.0 if t["tStat"] is not None else None, 2),
                            "tStat": _r(t["tStat"], 2)})
    if not signals:
        return None
    net = sum(1 if s["direction"] == "LONG" else -1 if s["direction"] == "SHORT" else 0 for s in signals)
    agg = net / len(signals)
    return {
        "available": True,
        "signals": signals,
        "aggregateScore": round(agg, 2),
        "regime": "TRENDING" if abs(agg) >= 0.5 else "RANGING",
        "methodology": "Sign of 1m/3m/12m return; strength = |return|, confidence = |t|/3 capped at 1.",
        "lastUpdated": now.isoformat(),
    }


# ── Sentiment ───────────────────────────────────────────────────────────────────

def build_sentiment(inp: SectionInputs, vix_level: Optional[float], risk_score: Optional[float],
                    now) -> Optional[Dict[str, Any]]:
    """Market-implied sentiment: VIX level (the risk signal), VIX term structure (VIX3M/VIX),
    VIX 1m change and cross-asset 3m momentum. AAII survey data isn't sourced → omitted."""
    vix_closes, vix3m_closes = inp.closes("VIX"), inp.closes("VIX3M")
    vix_now = vix_level if vix_level is not None else (vix_closes[-1] if vix_closes else None)
    vix3m = vix3m_closes[-1] if vix3m_closes else None
    ratio = vix3m / vix_now if (vix3m and vix_now) else None
    structure = (None if ratio is None else "backwardation" if ratio < 0.98
                 else "contango" if ratio > 1.02 else "flat")
    vix_1m = ms.period_return(vix_closes, ms.TRADING_DAYS_1M) if vix_closes else None

    gauges = []
    if vix_1m is not None:
        gauges.append({"name": "VIX 1M change", "value": round(vix_1m, 4),
                       "signal": "fear rising" if vix_1m > 0 else "fear easing"})
    if ratio is not None:
        gauges.append({"name": "VIX3M / VIX − 1", "value": round(ratio - 1, 4), "signal": structure})
    momentum = []
    for label, key in (("SPX", "SPX"), ("NDX", "NDX"), ("TLT", "TLT"), ("Gold", "GLD"), ("DXY", "DXY")):
        m = ms.period_return(inp.closes(key), ms.TRADING_DAYS_3M)
        if m is not None:
            momentum.append({"asset": label, "momentum3m": round(m, 4),
                             "signal": "Bullish" if m > 0 else "Bearish"})
    if risk_score is None and not gauges and not momentum:
        return None
    regime = (None if risk_score is None else
              "Risk-On" if risk_score > 0.7 else "Risk-Off" if risk_score < 0.4 else "Neutral")
    # Contrarian read of the term structure: backwardation = capitulation (contrarian
    # bullish); very low spot VIX in steep contango = complacency (contrarian bearish).
    contrarian = ("Bullish" if structure == "backwardation"
                  else "Bearish" if (structure == "contango" and vix_now is not None and vix_now < 13)
                  else "Neutral")
    return {
        "available": True,
        "compositeRiskAppetite": round(risk_score * 100, 1) if risk_score is not None else None,
        "riskLevel": regime,
        "regime": regime,
        "gauges": gauges,
        "vixTermStructure": {"ratio": _r(ratio, 3), "structure": structure,
                             "vix": _r(vix_now, 2), "vix3m": _r(vix3m, 2)} if ratio is not None else None,
        "aaiiSentiment": None,
        "crossAssetMomentum": {
            "averageMomentum": _r(sum(m["momentum3m"] for m in momentum) / len(momentum), 4) if momentum else None,
            "assets": momentum, "regime": regime},
        "contrarianSignal": contrarian if structure else None,
        "description": (f"Risk appetite from VIX ({vix_now:.1f})" if vix_now is not None else "Risk appetite")
                       + (f"; VIX term structure {structure} (VIX3M/VIX {ratio:.2f})." if ratio else ".")
                       + " AAII survey not sourced.",
        "source": "Yahoo (^VIX, ^VIX3M, index/ETF closes)",
        "lastUpdated": now.isoformat(),
    }


# ── Valuation ───────────────────────────────────────────────────────────────────

def build_valuation(inp: SectionInputs, now) -> Optional[Dict[str, Any]]:
    """SPY trailing P/E (Yahoo), 10Y TIPS real yield (FRED DFII10, z-scored vs ~3y), and
    the equity yield gap (earnings yield − real yield)."""
    metrics = []
    real = inp.series("DFII10")
    if real:
        mean, z, pct = ms.zscore_and_percentile(real.latest, real.values[:-1])
        metrics.append({"name": "10Y Real Yield (TIPS)", "value": round(real.latest, 2),
                        "historicalMean": _r(mean, 2), "zScore": _r(z, 2),
                        "percentile": _r(pct, 0),
                        "interpretation": f"FRED DFII10 as of {real.latest_date}, vs. {len(real.values) - 1} prior days"})
    pe = inp.spy_pe
    if pe is not None:
        metrics.append({"name": "S&P 500 trailing P/E (SPY)", "value": round(pe, 1),
                        "historicalMean": None, "zScore": None, "percentile": None,
                        "signal": "n/a", "interpretation": "Yahoo SPY trailingPE (no history → no z-score)"})
        if real:
            gap = 100.0 / pe - real.latest
            metrics.append({"name": "Equity yield gap (E/P − real yield)", "value": round(gap, 2),
                            "historicalMean": None, "zScore": None, "percentile": None,
                            "signal": "n/a",
                            "interpretation": f"Earnings yield {100.0 / pe:.2f}% − TIPS {real.latest:.2f}%"})
    if not metrics:
        return None
    return {
        "available": True,
        "metrics": metrics,
        "summary": "; ".join(f"{m['name']} {m['value']}" for m in metrics) + ".",
        "lastUpdated": now.isoformat(),
    }


# ── Advanced indicators ─────────────────────────────────────────────────────────

def build_advanced_indicators(inp: SectionInputs, sahm: DatedSeries, now) -> Dict[str, Any]:
    """Sahm rule (FRED SAHMREALTIME), credit impulse (FRED TOTBKCR vs GDP), LEI
    (unavailable: OECD CLI for the US discontinued), inverse-vol risk-parity weights."""
    if sahm:
        sv = sahm.latest
        sahm_block = {"value": round(sv, 2),
                      "signal": "Recession" if sv >= 0.5 else "Warning" if sv >= 0.3 else "Normal",
                      "threshold": 0.5,
                      "description": f"FRED SAHMREALTIME, {sahm.latest_date}"}
    else:
        sahm_block = {"value": None, "signal": "Unavailable", "threshold": 0.5,
                      "description": "FRED SAHMREALTIME unavailable"}

    credit, gdp = inp.series("TOTBKCR"), inp.series("GDP")
    ci = ms.credit_impulse(credit.dates, credit.values, gdp.latest) if (credit and gdp) else None
    credit_block = ({"value": round(ci, 2), "signal": "Positive" if ci > 0 else "Negative",
                     "description": f"Δ12m bank credit flow, % of GDP (FRED TOTBKCR to {credit.latest_date}, GDP {gdp.latest_date})"}
                    if ci is not None else
                    {"value": None, "signal": "Unavailable", "description": "Bank credit / GDP history unavailable"})

    lei_block = {"value": None, "change": None, "signal": "Unavailable",
                 "description": "No leading-index source wired (OECD US CLI discontinued; Conference Board LEI not on FRED)"}

    al = inp.aligned("SPY", "TLT", "DBC")
    w = ms.inverse_vol_weights(al, 60) if al else None
    corr = ms.trailing_correlation(al["SPY"], al["TLT"], 60) if al else None
    rp_block = ({"regime": "Stress" if (corr is not None and corr > 0.2) else "Normal",
                 "allocations": {"stocks": round(w["SPY"], 2), "bonds": round(w["TLT"], 2),
                                 "commodities": round(w["DBC"], 2)},
                 "description": "Inverse 60d-vol weights for SPY/TLT/DBC"
                                + (f"; SPY-TLT corr {corr:+.2f}" if corr is not None else "")}
                if w else None)

    out = {"sahmRule": sahm_block, "creditImpulse": credit_block, "lei": lei_block,
           "lastUpdated": now.isoformat()}
    if rp_block:
        out["riskParity"] = rp_block
    return out


# ── Yield curves (used by /api/rates) ───────────────────────────────────────────

def us_curve_points(fred: Dict[str, DatedSeries]) -> List[Dict[str, float]]:
    pts = []
    for tenor, sid in US_TENORS:
        s = fred.get(sid)
        if s:
            pts.append({"tenor": round(tenor, 4), "yield": round(s.latest, 2)})
    return pts


def foreign_curve(cc: str, fred: Dict[str, DatedSeries], today: Optional[str] = None) -> Dict[str, Any]:
    """3M interbank and 10Y government yields (OECD MEI, monthly) — the only tenors FRED
    carries for these countries. Stale or missing observations are left out. When the 3M
    point is stale and a daily overnight rate exists (UK: SONIA), that is used as the
    short end, labelled as overnight (spreadShort10y), not passed off as a 3M rate."""
    today = today or date.today().isoformat()
    ids = FOREIGN_CURVES[cc]

    def _fresh(s: Optional[DatedSeries]) -> bool:
        return bool(s) and (date.fromisoformat(today) - date.fromisoformat(s.latest_date)).days <= FOREIGN_MAX_AGE_DAYS

    vals, dates = {}, {}
    for label, sid in ids.items():
        s = fred.get(sid)
        if _fresh(s):
            vals[label], dates[label] = s.latest, s.latest_date
    pts = [{"tenor": t, "yield": round(vals[k], 2)} for t, k in ((0.25, "3M"), (10, "10Y")) if k in vals]
    spread = (vals["10Y"] - vals["3M"]) * 100 if len(vals) == 2 else None
    sources = list(ids.values())

    short_label, short_spread = ("3M" if "3M" in vals else None), None
    if "3M" not in vals and cc in OVERNIGHT_RATES:
        sid, name = OVERNIGHT_RATES[cc]
        on = fred.get(sid)
        if _fresh(on):
            pts.insert(0, {"tenor": round(1 / 365, 4), "yield": round(on.latest, 2)})
            dates[name] = on.latest_date
            short_label = name
            sources.append(sid)
            if "10Y" in vals:
                short_spread = (vals["10Y"] - on.latest) * 100
    shape_spread = spread if spread is not None else short_spread
    return {
        "country": cc,
        "points": pts,
        "spread2s10s": None,
        "spread3m10y": round(spread, 1) if spread is not None else None,
        "spreadShort10y": round(short_spread, 1) if short_spread is not None else None,
        "shortRate": short_label,
        "shape": (None if shape_spread is None else
                  "inverted" if shape_spread < 0 else "flat" if shape_spread < 50 else "steep"),
        "recessionProb": None,   # the probit is estimated on US data only
        "asOf": dates,
        "source": "FRED / OECD MEI (" + ", ".join(sources) + ")",
    }


# ── Reflexivity: feedback loops measured on observed moves ──────────────────────

def _z_of(inp: SectionInputs, key: str, lookback: int, pct: bool = True) -> Optional[Dict[str, float]]:
    vals = inp.closes(key)
    return ms.change_zscore(vals, lookback, pct=pct) if vals else None


def _trend_word(z: float) -> str:
    """Direction of a move relative to its usual size (the z-score sign), which is what
    decides whether a loop is reinforcing — so the arrows agree with the activation."""
    return "rising" if z > 0 else "falling" if z < 0 else "flat"


def build_reflexivity(inp: SectionInputs, regime_name: str, now) -> Optional[Dict[str, Any]]:
    """Self-reinforcing loops (Soros), each read from two observed series: a loop is
    active when cause and effect have both moved > 1σ (vs their own past year of rolling
    moves) in the mutually reinforcing direction. Strength = min(|z|)/3, capped at 1."""
    hy = inp.series("BAMLH0A0HYM2")
    hy_z = ms.change_zscore(hy.values, 63, pct=False) if hy else None
    defs = [
        # id, name, cause (label, z), effect (label, z), reinforcing sign (+1: same direction)
        ("equity-credit", "Equity prices ↔ credit spreads (collateral loop)",
         ("S&P 500 3m return vs past year", _z_of(inp, "SPX", 63)), ("HY OAS 3m change vs past year", hy_z), -1,
         "Higher equity prices ease credit (tighter spreads), which supports further equity gains — and the reverse in a sell-off.",
         "Spreads stop moving against equities (either |z| < 1)."),
        ("vol-deleveraging", "Volatility ↔ deleveraging",
         ("VIX 1m change vs past year", _z_of(inp, "VIX", 21)), ("S&P 500 1m return vs past year", _z_of(inp, "SPX", 21)), -1,
         "Rising volatility forces vol-targeting / risk-parity deleveraging, pushing prices down and volatility up (or a vol-selling melt-up in reverse).",
         "VIX and equity moves revert inside ±1σ."),
        ("dollar-conditions", "US dollar ↔ global financial conditions",
         ("DXY 3m change vs past year", _z_of(inp, "DXY", 63)), ("Euro Stoxx 50 3m return vs past year", _z_of(inp, "STOXX50", 63)), -1,
         "A stronger dollar tightens global dollar funding, weighing on non-US risk assets, which pushes capital back into dollars.",
         "Dollar and non-US equities stop moving in opposite directions."),
    ]
    loops = []
    for lid, name, (cname, cz), (ename, ez), sign, implication, brk in defs:
        if cz is None or ez is None:
            continue
        reinforcing = (cz["z"] * ez["z"] * sign) > 0
        active = reinforcing and abs(cz["z"]) > 1 and abs(ez["z"]) > 1
        strength = min(abs(cz["z"]), abs(ez["z"])) / 3.0 if reinforcing else 0.0
        loops.append({
            "id": lid, "loop": name, "active": active, "strength": round(min(strength, 1.0), 2),
            "variables": {"cause": {"name": cname, "trend": _trend_word(cz["z"]), "z": round(cz["z"], 2),
                                    "change": round(cz["change"], 4)},
                          "effect": {"name": ename, "trend": _trend_word(ez["z"]), "z": round(ez["z"], 2),
                                     "change": round(ez["change"], 4)}},
            "implication": implication,
            "interpretation": f"{cname} z {cz['z']:+.2f}, {ename} z {ez['z']:+.2f}"
                              + (" — reinforcing" if reinforcing else " — not reinforcing"),
            "breakCondition": brk,
        })
    if not loops:
        return None
    active = [l for l in loops if l["active"]]
    inactive = [l for l in loops if not l["active"]]
    return {
        "available": True,
        "activeLoops": active,
        "inactiveLoops": inactive,
        "loopCount": {"active": len(active), "inactive": len(inactive)},
        "reflexivityAlert": bool(active),
        "alertMessage": ("Active feedback loop: " + "; ".join(l["loop"] for l in active)) if active else None,
        "regimeImplication": ("Self-reinforcing moves can extend the current regime and make reversals abrupt."
                              if active else None),
        "aggregateDivergence": round(max(l["strength"] for l in loops), 2),
        "regime": regime_name,
        "interpretation": "Loops measured as z-scores of observed moves vs their own past year.",
        "lastUpdated": now.isoformat(),
    }


# ── Pure alpha: cross-asset momentum z-scores ───────────────────────────────────

# (display name, category, price key, short label used in trade ideas)
_ALPHA_UNIVERSE = [
    ("S&P 500", "equity", "SPX", "S&P 500"), ("Nasdaq 100", "equity", "NDX", "Nasdaq 100"),
    ("Euro Stoxx 50", "equity", "STOXX50", "Euro Stoxx 50"), ("Nikkei 225", "equity", "N225", "Nikkei"),
    ("Long Treasuries (TLT)", "rates", "TLT", "TLT"), ("10Y note future", "rates", "TY", "10Y notes"),
    ("Gold", "commodity", "GC", "gold"), ("Crude oil", "commodity", "CL", "crude"),
    ("Commodities (DBC)", "commodity", "DBC", "DBC"), ("US dollar (DXY)", "fx", "DXY", "USD"),
]


def build_pure_alpha(inp: SectionInputs, now) -> Optional[Dict[str, Any]]:
    """Cross-asset signals: each instrument's 3-month return as a z-score vs its own past
    year of rolling 3-month returns (time-series momentum)."""
    signals = []
    for name, cat, key, short in _ALPHA_UNIVERSE:
        closes = inp.closes(key)
        cz = ms.change_zscore(closes, ms.TRADING_DAYS_3M) if closes else None
        if cz is None:
            continue
        z = cz["z"]
        signals.append({
            "name": name, "category": cat, "label": short,
            "direction": "long" if z > 0 else "short" if z < 0 else "neutral",
            "zScore": round(z, 2),
            "percentile": round(cz["percentile"] * 100),
            "strength": "strong" if abs(z) >= 2 else "moderate" if abs(z) >= 1 else "weak",
            "confidence": round(min(abs(z), 3.0) / 3.0, 2),
            "return3m": round(cz["change"], 4),
        })
    if not signals:
        return None
    intensity = sum(min(abs(s["zScore"]), 3.0) / 3.0 for s in signals) / len(signals)
    ranked = sorted(signals, key=lambda s: abs(s["zScore"]), reverse=True)
    ideas = [f"{'Long' if s['zScore'] > 0 else 'Short'} {s['label']}" for s in ranked if abs(s["zScore"]) >= 1][:3]
    n_strong = sum(1 for s in signals if s["strength"] != "weak")
    regime = "trending" if intensity >= 0.33 else "quiet"
    return {
        "available": True,
        "signals": signals,
        "compositeScore": round(intensity, 2),
        "topIdeas": ideas,
        "regime": regime,
        "regimeDescription": (f"{n_strong} of {len(signals)} instruments have a 3-month move beyond 1σ "
                              f"of their past year; average |z| intensity {intensity:.2f}."),
        "methodology": "3m return z-scored vs trailing 1y of rolling 3m returns; percentile within that year.",
        "lastUpdated": now.isoformat(),
    }


# ── Regime transitions & regime-conditional returns (monthly FRED panel) ────────

def _quadrant_labels(inp: SectionInputs) -> Optional[List[tuple]]:
    """[(YYYY-MM, quadrant)] from the shared monthly classifier
    (api.calculations.regime.quadrant_regime_history — the same one /api/v1/regime-transition
    uses), so both panels agree."""
    from api.calculations.regime import quadrant_regime_history
    df = inp.monthly_macro
    if df is None or getattr(df, "empty", True) or "growth_yoy" not in df or "cpi_yoy" not in df:
        return None
    q = quadrant_regime_history(df["growth_yoy"], df["cpi_yoy"])
    hist = [(ts.strftime("%Y-%m"), r) for ts, r in zip(q.index, q["regime"])]
    return hist or None


def build_regime_transitions(inp: SectionInputs, cycle_regime: str, now) -> Optional[Dict[str, Any]]:
    """Empirical month-to-month transition probabilities between growth×inflation
    quadrants, classified from FRED industrial production and CPI since 1985."""
    from api.calculations.regime import empirical_transition_matrix, forward_outlook
    hist = _quadrant_labels(inp)
    if not hist or len(hist) < 24:
        return None
    seq = [q for _, q in hist]
    tm = empirical_transition_matrix(seq)
    current = seq[-1]
    out = forward_outlook(tm, current)
    ranked = [r for r in out["ranked"] if r["regime"] != current]
    first = ranked[0] if ranked else None
    second = ranked[1] if len(ranked) > 1 else None
    return {
        "available": True,
        "currentRegime": current,
        "cycleRegime": cycle_regime,
        "asOfMonth": hist[-1][0],
        "stayProbability": out["stay_prob"],
        "expectedPersistenceMonths": out["expected_persistence_periods"],
        "mostLikelyNext": first["regime"] if first else None,
        "nextRegimeProbability": first["prob"] if first else None,
        "secondMostLikely": second["regime"] if second else None,
        "secondProbability": second["prob"] if second else None,
        "transitions": tm["matrix"],
        "monthsAnalysed": tm["observations"],
        "warning": (f"{first['regime']} is {first['prob']:.0%} likely next month"
                    if first and first["prob"] >= 0.3 else ""),
        "taxonomy": "growth×inflation quadrant (sign of rolling 36M z-scores of INDPRO YoY and "
                    "CPI YoY) — a complementary lens to the headline cycle regime",
        "source": "FRED INDPRO, CPIAUCSL (monthly, since 1985)",
        "lastUpdated": now.isoformat(),
    }


_ER_ASSETS = [("US equities (SPY)", "SPY"), ("Long Treasuries (TLT)", "TLT"),
              ("Gold (GLD)", "GLD"), ("Commodities (DBC)", "DBC")]


def _sixty_forty(mpx: Dict[str, Dict[str, float]]) -> Dict[str, float]:
    """Monthly-rebalanced 60/40 SPY/TLT index built from the two monthly series."""
    spy, tlt = mpx.get("SPY") or {}, mpx.get("TLT") or {}
    months = sorted(set(spy) & set(tlt))
    level, out = 100.0, {}
    for i, m in enumerate(months):
        if i:
            p = months[i - 1]
            level *= 1 + 0.6 * (spy[m] / spy[p] - 1) + 0.4 * (tlt[m] / tlt[p] - 1)
        out[m] = level
    return out


def build_expected_returns(inp: SectionInputs, transitions: Optional[Dict[str, Any]], now):
    """Historical regime-conditional returns: each asset's annualized mean monthly return
    in past months that were in the CURRENT quadrant (label lagged 2 months so it was
    published beforehand). A historical average, not a forecast model."""
    from api.schemas.models import ExpectedReturnsResult
    hist = _quadrant_labels(inp)
    if not hist or not inp.monthly_prices:
        return ExpectedReturnsResult(sectors=[], weightedPortfolioReturn=None,
                                     methodology="Unavailable: monthly macro or price history missing",
                                     lastUpdated=now.isoformat())
    labels = dict(hist)
    current = hist[-1][1]
    by_asset, risk_adj = {}, {}
    for name, key in _ER_ASSETS:
        st = ms.conditional_return_stats(inp.monthly_prices.get(key) or {}, labels, current)
        if st:
            by_asset[name] = round(st["annualReturn"], 4)
            if st["returnToVol"] is not None:
                risk_adj[name] = round(st["returnToVol"], 2)
    sf = _sixty_forty(inp.monthly_prices)
    port = ms.conditional_return_stats(sf, labels, current) if sf else None
    scenarios = []
    for nxt, prob in sorted(((transitions or {}).get("transitions") or {}).get(current, {}).items(),
                            key=lambda kv: kv[1], reverse=True):
        st = ms.conditional_return_stats(sf, labels, nxt) if sf else None
        if st and prob > 0:
            scenarios.append({"scenario": nxt, "probability": prob,
                              "expectedReturn": round(st["annualReturn"], 4),
                              "confidenceInterval": [round(st["ci95"][0], 4), round(st["ci95"][1], 4)],
                              "months": st["months"]})
    return ExpectedReturnsResult(
        sectors=[],
        weightedPortfolioReturn=round(port["annualReturn"] * 100, 1) if port else None,
        currentQuadrant=current,
        byAssetClass=by_asset,
        riskAdjustedReturns=risk_adj,
        next12Months=scenarios,
        methodology=(f"Historical 60/40 (SPY/TLT) and asset returns in {current} months "
                     f"({port['months'] if port else 0} months), quadrant read 2 months earlier; "
                     "scenarios are next-month quadrant probabilities × that quadrant's historical "
                     "60/40 return (95% CI). Historical averages, not a forecast model."),
        lastUpdated=now.isoformat(),
    )


# ── Risk parity (inverse volatility) ────────────────────────────────────────────

RP_ASSETS = [("SPY", "US equities"), ("TLT", "Long Treasuries"), ("GLD", "Gold"), ("DBC", "Commodities")]
# Portfolio volatility target — a policy setting of this allocation, not a market input.
RP_TARGET_VOL = 0.10


def build_risk_parity(inp: SectionInputs, now) -> Dict[str, Any]:
    """Inverse-60d-vol weights on SPY/TLT/GLD/DBC with the realized portfolio vol,
    diversification ratio, leverage to the vol target, and a 20-day weight-drift check."""
    import numpy as np
    keys = [k for k, _ in RP_ASSETS]
    al = inp.aligned(*keys)
    w = ms.inverse_vol_weights(al, 60) if al else None
    base = {"holdings": [], "totalHoldings": 0, "lastRebalanced": None,
            "methodology": "Inverse 60-day volatility (naive risk parity): SPY / TLT / GLD / DBC",
            "regimeAdjustmentActive": False, "targetVolatility": RP_TARGET_VOL,
            "portfolioVol": None, "portfolioVolatility": None, "diversificationRatio": None,
            "leverage": None, "rebalancingNeeded": None, "lastUpdated": now.isoformat()}
    if not w:
        return base
    rets = np.column_stack([ms.daily_returns(al[k])[-60:] for k in keys])
    wv = np.array([w[k] for k in keys])
    port_vol = float((rets @ wv).std(ddof=1) * np.sqrt(252))
    vols = {k: ms.annualized_vol(al[k], 60) for k in keys}
    div = float(sum(w[k] * vols[k] for k in keys) / port_vol) if port_vol > 0 else None
    w_prev = ms.inverse_vol_weights({k: al[k][:-20] for k in keys}, 60)
    drift = max(abs(w[k] - w_prev[k]) for k in keys) if w_prev else None
    holdings = []
    for k, label in RP_ASSETS:
        t = ms.trend_signal(al[k], ms.TRADING_DAYS_3M)
        tstat = t["tStat"] if t else None
        holdings.append({
            "ticker": k, "sector": label,
            "annualisedVol": round(vols[k], 4), "baseWeight": round(w[k], 4),
            "signalScore": round(tstat, 2) if tstat is not None else 0.0,
            "signal": t["direction"] if t else "N/A",
            "conviction": ("High" if tstat is not None and abs(tstat) >= 2 else
                           "Medium" if tstat is not None and abs(tstat) >= 1 else "Low"),
            "adjustedWeight": round(w[k], 4),
            "targetAllocationPct": round(w[k] * 100, 1),
        })
    return {**base, "holdings": holdings, "totalHoldings": len(holdings),
            "portfolioVol": round(port_vol, 4), "portfolioVolatility": round(port_vol, 4),
            "diversificationRatio": round(div, 2) if div else None,
            "leverage": round(RP_TARGET_VOL / port_vol, 2) if port_vol > 0 else None,
            "rebalancingNeeded": (drift > 0.05) if drift is not None else None,
            "weightDrift20d": round(drift, 4) if drift is not None else None}


# ── Performance tracking (persisted forecast log) ───────────────────────────────

MIN_EVALUATED = 20


def build_performance_tracking(inp: SectionInputs, now) -> Optional[Dict[str, Any]]:
    """Forecast-accuracy tracking from the forecast_history table. Accuracy is reported
    only for models with at least MIN_EVALUATED realized outcomes."""
    stats = inp.forecast_stats
    if stats is None:
        return None
    total = sum(r["n"] for r in stats)
    evaluated = sum(r["evaluated"] for r in stats)
    firsts = [r["first"] for r in stats if r["first"]]
    lasts = [r["last"] for r in stats if r["last"]]
    acc = {r["model_name"]: round(r["hit_rate"], 4) for r in stats
           if r["evaluated"] >= MIN_EVALUATED and r["hit_rate"] is not None}
    regime_acc = acc.get("regime_threshold")
    return {
        "available": True,
        "trackingPeriod": f"{min(firsts)} → {max(lasts)}" if firsts else None,
        "totalPredictions": total,
        "evaluatedPredictions": evaluated,
        "regimeAccuracy": regime_acc,
        "modelAccuracies": acc,
        "ensembleCalibration": None,
        "weightAdaptations": [],
        "models": [{"model": r["model_name"], "forecasts": r["n"], "evaluated": r["evaluated"]} for r in stats],
        "note": (f"{total} forecasts logged, {evaluated} with realized outcomes. Accuracy is shown "
                 f"for models with ≥{MIN_EVALUATED} evaluated forecasts."),
        "lastUpdated": now.isoformat(),
    }


# ── Sector relative strength (feeds the sector-allocation playbook) ─────────────

def build_sector_stats(inp: SectionInputs) -> Dict[str, Dict[str, float]]:
    """{playbook sector: {etf, relativeReturn, percentile, z}} — each sector proxy's 3-month
    return minus SPY, ranked / z-scored within its own past year."""
    out = {}
    for sector, etf in SECTOR_PROXIES.items():
        al = inp.aligned(etf, "SPY")
        rs = ms.relative_strength_score(al[etf], al["SPY"]) if al else None
        if rs:
            out[sector] = {"etf": etf, **rs}
    return out


# ── Long-term capital-market assumptions ────────────────────────────────────────

def build_cma(inp: SectionInputs, ten_yr: Optional[float], risk_free: Optional[float],
              breakeven: Optional[float], now) -> Dict[str, Any]:
    """CMA from observed inputs: ETF earnings yields (100 / trailing P/E), 10Y breakeven,
    10Y yield and realized 2y daily volatility of each proxy ETF."""
    from api.calculations.cma import longterm_forecasts, ASSETS
    ey = {t: 100.0 / pe for t, pe in inp.trailing_pe.items() if pe}
    vols = {}
    for _, etf, _ in ASSETS:
        closes = inp.closes(etf)
        v = ms.annualized_vol(closes, window=len(closes) - 1) if len(closes) > 250 else None
        if v is not None:
            vols[etf] = v * 100
    return longterm_forecasts(ten_yr, now, risk_free=risk_free, breakeven=breakeven,
                              earnings_yields=ey, vols=vols)
