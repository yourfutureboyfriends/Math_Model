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
}

US_TENORS = [(1 / 12, "DGS1MO"), (0.25, "DGS3MO"), (0.5, "DGS6MO"), (1, "DGS1"), (2, "DGS2"),
             (3, "DGS3"), (5, "DGS5"), (7, "DGS7"), (10, "DGS10"), (20, "DGS20"), (30, "DGS30")]
# Display code -> OECD MEI 3M interbank / 10Y government yield series (the OECD code for
# the UK is GB).
FOREIGN_CURVES = {cc: {"3M": f"IR3TIB01{oecd}M156N", "10Y": f"IRLTLT01{oecd}M156N"}
                  for cc, oecd in (("UK", "GB"), ("DE", "DE"), ("JP", "JP"), ("CA", "CA"), ("AU", "AU"))}
# A monthly OECD observation older than this is too stale to show as the current curve.
FOREIGN_MAX_AGE_DAYS = 120

DEBT_SERIES = {"private": "QUSPAM770A", "public": "QUSGAM770A", "total": "QUSCAM770A",
               "dsr": "TDSP"}
OTHER_FRED = ["DFII10", "GDPNOW", "TOTBKCR", "GDP", "BAMLH0A0HYM2"]

_PE_CACHE: Dict[str, Any] = {"ts": 0.0, "pe": None}
_PE_TTL = 3600


def rates_fred_ids() -> List[str]:
    return [sid for _, sid in US_TENORS] + ["DFII10"] + [
        sid for c in FOREIGN_CURVES.values() for sid in c.values()]


@dataclass
class SectionInputs:
    prices: Dict[str, Dict[str, float]] = field(default_factory=dict)   # key -> {date: close}
    fred: Dict[str, DatedSeries] = field(default_factory=dict)
    spy_pe: Optional[float] = None

    def closes(self, key: str) -> List[float]:
        return ms.closes_of(self.prices.get(key) or {})

    def aligned(self, *keys: str) -> Optional[Dict[str, List[float]]]:
        if any(not self.prices.get(k) for k in keys):
            return None
        _, out = ms.align_dated({k: self.prices[k] for k in keys})
        return out

    def series(self, sid: str) -> DatedSeries:
        return self.fred.get(sid) or DatedSeries(sid)


def _spy_trailing_pe_sync() -> Optional[float]:
    import yfinance as yf
    pe = (yf.Ticker("SPY").info or {}).get("trailingPE")
    return float(pe) if isinstance(pe, (int, float)) and pe == pe and pe > 0 else None


async def _spy_trailing_pe() -> Optional[float]:
    now = time.time()
    if _PE_CACHE["pe"] is not None and now - _PE_CACHE["ts"] < _PE_TTL:
        return _PE_CACHE["pe"]
    try:
        pe = await asyncio.wait_for(asyncio.to_thread(_spy_trailing_pe_sync), timeout=10)
    except Exception as e:
        logger.warning("[dashboard_sections] SPY trailing P/E unavailable: %s", e)
        pe = None
    if pe is not None:
        _PE_CACHE.update(ts=now, pe=pe)
    return pe if pe is not None else _PE_CACHE["pe"]


async def load_section_inputs(timeout: float = 30.0) -> SectionInputs:
    from api.handlers.market_handler import _fetch_dated_closes_literal

    keys = list(PRICE_TICKERS)
    fred_ids = rates_fred_ids() + list(DEBT_SERIES.values()) + OTHER_FRED

    async def _prices():
        res = await asyncio.gather(
            *[_fetch_dated_closes_literal(PRICE_TICKERS[k], period="2y") for k in keys],
            return_exceptions=True)
        return {k: r for k, r in zip(keys, res) if isinstance(r, dict) and r}

    try:
        prices, fred, pe = await asyncio.wait_for(
            asyncio.gather(_prices(), load_fred_series(fred_ids, days=1100), _spy_trailing_pe()),
            timeout=timeout)
    except asyncio.TimeoutError:
        logger.warning("[dashboard_sections] input fetch timed out after %ss", timeout)
        return SectionInputs()
    missing = [k for k in keys if k not in prices] + [s for s in fred_ids if not fred.get(s)]
    if missing:
        logger.warning("[dashboard_sections] unavailable inputs: %s", ", ".join(missing))
    return SectionInputs(prices=prices, fred=fred, spy_pe=pe)


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
    carries for these countries. Stale or missing observations are left out."""
    today = today or date.today().isoformat()
    ids = FOREIGN_CURVES[cc]
    vals, dates = {}, {}
    for label, sid in ids.items():
        s = fred.get(sid)
        if s and (date.fromisoformat(today) - date.fromisoformat(s.latest_date)).days <= FOREIGN_MAX_AGE_DAYS:
            vals[label], dates[label] = s.latest, s.latest_date
    pts = [{"tenor": t, "yield": round(vals[k], 2)} for t, k in ((0.25, "3M"), (10, "10Y")) if k in vals]
    spread = (vals["10Y"] - vals["3M"]) * 100 if len(vals) == 2 else None
    return {
        "country": cc,
        "points": pts,
        "spread2s10s": None,
        "spread3m10y": round(spread, 1) if spread is not None else None,
        "shape": (None if spread is None else
                  "inverted" if spread < 0 else "flat" if spread < 50 else "steep"),
        "recessionProb": None,   # the probit is estimated on US data only
        "asOf": dates,
        "source": "FRED / OECD MEI (" + ", ".join(ids.values()) + ")",
    }
