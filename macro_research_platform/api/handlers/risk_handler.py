"""Risk handler with real calculated data from market prices."""
import asyncio
from typing import Dict, Any
from datetime import datetime
import logging

from api.services.validation_orchestrator import validate_risk_payload
from api.services.event_logger import log_risk_event, log_validation_event
from api.handlers.dashboard_handler import get_dashboard_data

logger = logging.getLogger(__name__)


async def get_recession_data() -> Dict[str, Any]:
    """Recession risk: the dashboard's real model output (logistic, Estrella-Mishkin probit,
    FRED real-time Sahm rule, logged forecast history) plus the latest FRED indicators.

    This endpoint used to synthesise everything from the headline probability: the
    logistic/probit numbers were ×0.9/×1.1, the Sahm value ×1.2, the history ×0.7…0.95,
    unemployment 3.5 + 3×p and credit spreads 150 + 300×p.
    """
    logger.info("Serving recession data from the dashboard's models")
    dashboard = await get_dashboard_data(mode="live")
    rec = dashboard.recession.model_dump() if dashboard.recession else {}
    p = rec.get("probability")

    from api.handlers.macro_inputs import load_fred_series
    fred = await load_fred_series(["UNRATE", "BAMLH0A0HYM2", "T10Y2Y", "T10Y3M"])

    def _latest(sid):
        s = fred.get(sid)
        return (round(s.latest, 2), s.latest_date) if s else (None, None)

    unrate, unrate_d = _latest("UNRATE")
    hy, hy_d = _latest("BAMLH0A0HYM2")
    c2s10s, c_d = _latest("T10Y2Y")
    c3m10y, c3_d = _latest("T10Y3M")

    def _band(x, hi, mid):
        return None if x is None else "High" if x > hi else "Medium" if x > mid else "Low"

    data = {
        **rec,
        "probability": p,
        "regime": (None if p is None else "High Risk" if p > 0.4 else "Moderate Risk" if p > 0.2 else "Low Risk"),
        "models": {
            "logistic": {"probability": rec.get("logisticProb"), "signal": _band(rec.get("logisticProb"), 0.4, 0.2)},
            "estrella_mishkin": {"probability": rec.get("emProbitProb"), "signal": _band(rec.get("emProbitProb"), 0.4, 0.2)},
            "sahm": {"value": rec.get("sahmValue"), "signal": rec.get("sahmSignal"),
                     "note": "FRED SAHMREALTIME (pp); triggers at 0.50"},
        },
        "indicators": {
            "yield_curve_2s10s": c2s10s, "yield_curve_3m10y": c3m10y,
            "hy_oas_pct": hy, "unemployment_rate": unrate,
            "as_of": {"T10Y2Y": c_d, "T10Y3M": c3_d, "BAMLH0A0HYM2": hy_d, "UNRATE": unrate_d},
            "source": "FRED",
        },
        "lastUpdated": datetime.now().isoformat(),
    }

    validation = validate_risk_payload(data)
    if not validation.valid:
        logger.warning("[risk_handler] Recession data validation issues", extra={"issues": validation.issues})
    log_validation_event("risk_handler.get_recession_data", validation)
    log_risk_event("recession_probability", data, metadata={"handler": "risk_handler", "models": list(data["models"])})
    return data


async def get_advanced_indicators() -> Dict[str, Any]:
    """Advanced indicators: the dashboard's real ones (FRED real-time Sahm rule, bank-credit
    impulse, honest LEI unavailability, inverse-vol risk parity). Previously a "Sahm rule"
    and "LEI" were invented from the growth score."""
    dashboard = await get_dashboard_data(mode="live")
    adv = dashboard.advancedIndicators
    adv = adv.model_dump() if hasattr(adv, "model_dump") else dict(adv or {})
    adv.setdefault("lastUpdated", datetime.now().isoformat())
    return adv


async def get_alerts_data() -> Dict[str, Any]:
    """Get active alerts from real market conditions."""
    logger.info("Fetching alerts data")

    # Get real dashboard data
    dashboard = await get_dashboard_data(mode="live")
    rec_prob = dashboard.recession.probability
    vix = dashboard.keyMetrics.vix
    ten_yr = dashboard.keyMetrics.tenYearYield
    two_yr = dashboard.keyMetrics.twoYearYield
    spread = ten_yr - two_yr if ten_yr and two_yr else None

    alerts = []

    # Generate alerts based on real conditions
    if spread is not None and spread < 0:
        alerts.append({
            "id": "alert-yield-curve",
            "type": "Recession",
            "severity": "High",
            "message": f"Yield curve inverted ({spread:+.2f}%) - recession risk elevated",
            "timestamp": datetime.now().isoformat(),
            "active": True,
        })

    if rec_prob > 0.3:
        alerts.append({
            "id": "alert-recession",
            "type": "Recession",
            "severity": "Medium",
            "message": f"Recession probability at {rec_prob:.0%} - monitor closely",
            "timestamp": datetime.now().isoformat(),
            "active": True,
        })

    if vix > 25:
        alerts.append({
            "id": "alert-vix",
            "type": "Volatility",
            "severity": "Medium",
            "message": f"VIX elevated at {vix:.1f} - risk-off conditions",
            "timestamp": datetime.now().isoformat(),
            "active": True,
        })

    if ten_yr and ten_yr > 5.0:
        alerts.append({
            "id": "alert-rates",
            "type": "Rates",
            "severity": "Medium",
            "message": f'10Y Treasury at {(ten_yr or 0.0):.2f}% - duration risk elevated',
            "timestamp": datetime.now().isoformat(),
            "active": True,
        })

    # Default alert if none triggered
    if not alerts:
        alerts.append({
            "id": "alert-normal",
            "type": "Status",
            "severity": "Low",
            "message": f'Market conditions normal - VIX at {(vix or 0.0):.1f}, yields {(ten_yr or 0.0):.2f}%',
            "timestamp": datetime.now().isoformat(),
            "active": True,
        })

    return {
        "alerts": alerts,
        "count": len(alerts),
        "lastUpdated": datetime.now().isoformat(),
    }


def _prev_day(dated: Dict[str, float], d: str) -> str:
    """The trading day before `d` in a dated close series."""
    earlier = [x for x in dated if x < d]
    return max(earlier) if earlier else d


async def get_full_risk_data() -> Dict[str, Any]:
    """Risk analytics measured from realised daily returns.

    Portfolio = the current book (today's positions held over the past year, returns per $
    of gross exposure); with no positions, a clearly-labelled 60/40 SPY/TLT reference.
    Benchmark SPY. Correlations: realised 63-day, SPY/TLT/GLD/HYG (+ book names). Stress
    tests: the factor-based historical scenarios from /api/v1/risk/stress-test.
    """
    import numpy as _np
    from api import main as _m
    from api.calculations.factor_model import returns_from_closes
    from api.calculations.risk_analytics import performance_stats, drawdown_stats, correlation_block
    from api.handlers.market_handler import _fetch_dated_closes_literal

    logger.info("Computing full risk analytics from realised returns")
    matrix, reason, _ = await _m._position_return_matrix(None)
    if matrix is not None:
        mv = _np.array(matrix["market_values"], dtype=float)
        gross = float(_np.abs(mv).sum()) or 1.0
        port = list((matrix["R"] @ mv) / gross)
        dates = matrix["dates"][1:]
        basis = (f"Current book ({len(mv)} positions), today's weights held over the past "
                 f"{len(port)} trading days; returns per $ of gross exposure")
        held = list(matrix["symbols"])
    else:
        spy, tlt = await asyncio.gather(_fetch_dated_closes_literal("SPY"), _fetch_dated_closes_literal("TLT"))
        common = sorted(set(spy) & set(tlt))
        rs = returns_from_closes([spy[d] for d in common])
        rt = returns_from_closes([tlt[d] for d in common])
        port = [0.6 * a + 0.4 * b for a, b in zip(rs, rt)]
        dates = common[1:]
        basis = f"REFERENCE 60/40 SPY/TLT portfolio — no positions in the book ({reason})"
        held = []

    # Benchmark SPY returns on exactly the same days (needs the close before the first day).
    spy_dated = await _fetch_dated_closes_literal("SPY")
    bench = None
    if dates and all(d in spy_dated for d in dates):
        series = [spy_dated[_prev_day(spy_dated, dates[0])]] + [spy_dated[d] for d in dates]
        b = list(returns_from_closes(series))
        bench = b if len(b) == len(port) else None

    # Risk-free: the 3M T-bill (FRED DGS3MO).
    try:
        from api.handlers.macro_inputs import load_macro_inputs
        rf = ((await load_macro_inputs())["dgs3mo"].latest or 0.0) / 100.0
    except Exception:
        rf = 0.0

    perf = performance_stats(port, bench, rf_annual=rf)
    dd = drawdown_stats(port)

    # Realised correlations: macro proxies + book names.
    corr_syms = list(dict.fromkeys(["SPY", "TLT", "GLD", "HYG"] + held[:6]))
    closes = await asyncio.gather(*[_fetch_dated_closes_literal(t) for t in corr_syms])
    common = None
    for c in closes:
        common = set(c) if common is None else common & set(c)
    common = sorted(common or [])
    rets = {t: list(returns_from_closes([c[d] for d in common])) for t, c in zip(corr_syms, closes) if c}
    corr = correlation_block(rets, window=63)

    stress = []
    try:
        st = await _m.risk_stress_get_v1(None)
        if st.get("available"):
            mv_gross = float(_np.abs(_np.array(matrix["market_values"])).sum()) if matrix is not None else None
            for sc in st["scenarios"]:
                by = sc.get("by_factor") or {}
                worst = min(by.items(), key=lambda kv: kv[1])[0] if by else None
                stress.append({"name": sc["label"], "description": "Historical factor shocks applied to the book's dollar exposures",
                               "portfolioPnl": round(sc["total_pnl"], 0),
                               "portfolioPnlPct": round(sc["total_pnl"] / mv_gross * 100, 2) if mv_gross else None,
                               "worstComponent": worst, "status": "Historical analog"})
    except Exception as e:
        logger.warning(f"[risk_full] stress tests unavailable: {e}")

    data = {
        "basis": basis,
        "benchmark": "SPY",
        "riskFreeRate": round(rf * 100, 2),
        "sharpe": perf.get("sharpeRatio"), "sortino": perf.get("sortinoRatio"),
        "calmar": perf.get("calmarRatio"), "informationRatio": perf.get("informationRatio"),
        "beta": perf.get("betaVsSpy"),
        "var95": -perf["var95"] if perf.get("var95") is not None else None,
        "cvar95": -perf["cvar95"] if perf.get("cvar95") is not None else None,
        "maxDrawdown": round(dd["max_drawdown"] * 100, 1),
        "volatility": perf.get("annualVolatility"),
        "status": f"Measured from {perf.get('observations', 0)} daily returns",
        "drawdown": {
            "currentDrawdown": round(dd["current_drawdown"] * 100, 2),
            "maxDrawdown12m": round(dd["max_drawdown"] * 100, 2),
            "currentSeverity": dd["severity"],
            "daysInDrawdown": dd["days_in_drawdown"],
            "recoveryTimeEstimate": "not forecast",
        },
        "riskAdjustedReturns": {
            "sharpeRatio": perf.get("sharpeRatio"), "sortinoRatio": perf.get("sortinoRatio"),
            "calmarRatio": perf.get("calmarRatio"), "informationRatio": perf.get("informationRatio"),
            "betaVsSpy": perf.get("betaVsSpy"),
            "var95": -perf["var95"] if perf.get("var95") is not None else None,
            "cvar95": -perf["cvar95"] if perf.get("cvar95") is not None else None,
            "annualReturn": perf.get("annualReturn"), "annualVolatility": perf.get("annualVolatility"),
        },
        "correlation": corr,
        "stressTests": stress,
        "lastUpdated": datetime.now().isoformat(),
    }

    validation = validate_risk_payload(data)
    if not validation.valid:
        logger.warning("[risk_handler] Full risk data validation issues", extra={"issues": validation.issues})

    log_validation_event("risk_handler.get_full_risk_data", validation)
    log_risk_event("full_risk_metrics", data, metadata={"handler": "risk_handler", "status": data.get("status")})

    return data
