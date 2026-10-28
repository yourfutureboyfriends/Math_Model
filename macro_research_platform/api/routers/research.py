"""
Research endpoints: macro, cross-asset and data-quality views that the Overview, Signals, Risk and Markets panels
read. None of them touches a fund's book (that is api/routers/book.py).

Endpoints (grouped)
    Data quality     GET /api/v1/data-quality, /api/v1/system/sources (+ POST .../check), /api/v1/providers,
                     /api/v1/quote, /api/report/generate
    Signals          GET /api/v1/correlation-matrix, /api/v1/signal-attribution, /api/v1/event-vol,
                     /api/v1/risk-parity-compare, /api/v1/quadrants, /api/v1/stream-agreement,
                     /api/v1/signals/composite-history, /api/v1/factor-validation, /api/v1/regime-transition,
                     /api/v1/anomalies, /api/v1/altdata/positioning, /api/v1/signals/backtest
    Calendar         GET /api/v1/central-banks/next, /api/calendar, /api/earnings/revisions
    Macro & markets  GET /api/cot, /api/v1/risk/cycle, /api/v1/global-macro, /api/regional-macro,
                     /api/global-correlation, /api/fx-rates, /api/market-hours, /api/global-markets, /api/horizon,
                     /api/market-stream

Conventions
    * Slow upstream calls are cached per endpoint (api/utils/cache.ttl_cache) and run off the event loop.
    * NaN / Inf never reach the client (scrub_nans and the app's NaN-safe JSON response).
    * Unavailable inputs are returned as null with a reason — never estimated silently.
    * Several endpoints are also called directly by api/main.py's startup warm-up and by the desk; they stay plain
      async functions so that works.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException, Request

from api.core.json_safe import SafeJSONResponse as JSONResponse
from api.macro_calendar import _calendar_release_dates, _fetch_fomc_dates, _fetch_fred_release_dates
from api.regime_data import _monthly_regime_frame, get_regime_data
from api.utils.cache import ttl_cache
from api.utils.helpers import scrub_nans

logger = logging.getLogger(__name__)
router = APIRouter(tags=["research"])
_EVENT_VOL_CACHE: Dict[str, Any] = {"data": None, "ts": 0.0}   # event-volatility result, refreshed hourly


@router.get("/api/v1/data-quality")
async def data_quality_v1():
    """Automated data-quality checks: scans key price series for bad ticks (implausible
    day-over-day jumps) and statistical outliers before they propagate into signals/risk."""
    from api.handlers.market_handler import _fetch_closes_literal
    from api.calculations.data_quality import quality_report

    # (name, ticker, jump_threshold). VIX legitimately moves 25%+ per day, so it gets a
    # much wider bad-tick threshold than cash instruments.
    series = [("S&P 500", "^GSPC", 0.15), ("Nasdaq 100", "^NDX", 0.18), ("VIX", "^VIX", 0.80),
              ("US Dollar", "DX-Y.NYB", 0.08), ("Gold", "GC=F", 0.15), ("WTI Crude", "CL=F", 0.20),
              ("10Y (TLT)", "TLT", 0.10), ("HY Credit (HYG)", "HYG", 0.10)]
    reports = []
    for name, ticker, jump in series:
        closes = await _fetch_closes_literal(ticker)
        reports.append(quality_report(name, closes, jump_threshold=jump))
    counts = {s: sum(1 for r in reports if r["status"] == s) for s in ("PASS", "WARN", "FAIL", "UNKNOWN")}
    overall = "FAIL" if counts["FAIL"] else "WARN" if counts["WARN"] else "PASS"
    return {"available": True, "overall": overall, "counts": counts,
            "series": reports, "checked_at": datetime.now().isoformat()}


@router.get("/api/v1/correlation-matrix")
async def correlation_matrix_v1(window: int = 90):
    """Full cross-asset Pearson correlation matrix over the last `window` trading days,
    computed from real aligned daily returns (yfinance). Rows/cols: SPX, NDX, 10Y, 2Y,
    DXY, GLD, WTI, HY, VIX. `window` is clamped to 20..252."""
    from api.handlers.market_handler import _fetch_dated_closes_literal
    from api.calculations.factor_model import returns_from_closes
    from api.calculations.altdata import correlation_matrix

    window = max(20, min(int(window), 252))
    # label -> literal ticker (reliable, ETF/index proxies)
    assets = {"SPX": "^GSPC", "NDX": "^NDX", "10Y": "TLT", "2Y": "SHY",
              "DXY": "DX-Y.NYB", "GLD": "GC=F", "WTI": "CL=F", "HY": "HYG", "VIX": "^VIX"}

    # Fetch all tickers concurrently (sequential await of 9 feeds blew the 8s UI budget).
    labels = list(assets.keys())
    results = await asyncio.gather(*[_fetch_dated_closes_literal(assets[lbl]) for lbl in labels])
    dated = {lbl: d for lbl, d in zip(labels, results) if d}    # drop empty fetches
    if len(dated) < 2:
        return {"available": False, "reason": "Insufficient market data.", "labels": [], "matrix": []}

    # Align every asset to the common set of dates, then compute returns on that grid.
    common = None
    for d in dated.values():
        keys = set(d.keys())
        common = keys if common is None else (common & keys)
    common = sorted(common or [])
    if len(common) < 22:
        return {"available": False, "reason": "Insufficient overlapping history.", "labels": [], "matrix": []}

    returns_by_asset = {lbl: returns_from_closes([dated[lbl][dt] for dt in common]) for lbl in dated}
    result = correlation_matrix(returns_by_asset, window)
    return {"available": bool(result["matrix"]), "as_of": datetime.now().isoformat(),
            "source": "yfinance (daily closes)", **result}


@router.get("/api/v1/signal-attribution")
async def signal_attribution_v1():
    """Storytelling layer: for Growth / Inflation / Liquidity / Risk, return the score, its
    largest driver, a one-line plain-English explanation, and ranked input contributions —
    computed from the live dashboard inputs (SPX, CPI, 10Y breakeven, DXY, 10Y, Fed, VIX). Phase 2."""
    from api.calculations.storytelling import (
        explain_growth, explain_inflation, explain_liquidity, explain_risk)
    from api.handlers.market_handler import _fetch_closes_literal
    from api.handlers.dashboard_handler import get_dashboard_data

    # Live, correctly-normalized inputs from a fresh dashboard computation.
    km = None
    try:
        dash = await get_dashboard_data(mode="live")
        km = getattr(dash, "keyMetrics", None)
    except Exception as e:
        logger.debug(f"[signal-attribution] dashboard read failed: {e}")

    def g(attr, default=None):
        v = getattr(km, attr, default) if km is not None else default
        return v if v is not None else default

    # Keep SPX self-consistent: latest close as current, prior closes as history.
    closes = await _fetch_closes_literal("^GSPC")
    spx = g("spxLevel") or (closes[-1] if closes else None)
    spx_hist = closes[:-1] if closes else None   # full daily history (growth needs ~6M)
    from api.handlers.macro_inputs import load_macro_inputs, load_monthly_macro, cpi_release_series
    _cpi_now = cpi_release_series(await asyncio.to_thread(load_monthly_macro)).asof(datetime.now().strftime("%Y-%m-%d"))
    _be_now = (await load_macro_inputs())["breakeven"].latest
    signals = [
        explain_growth(spx, spx_hist),
        explain_inflation(_cpi_now, _be_now),
        explain_liquidity(g("dxy"), g("tenYearYield"), g("fedRate")),
        explain_risk(g("vix")),
    ]
    return {"available": True, "signals": signals,
            "source": "computed from live dashboard inputs (yfinance/FRED)",
            "as_of": datetime.now().isoformat()}


_PROVIDER_REGISTRY = None


def _provider_registry():
    """Lazily build the multi-provider registry (Universal Data Layer)."""
    global _PROVIDER_REGISTRY
    if _PROVIDER_REGISTRY is None:
        from api.providers.adapters import build_default_registry
        _PROVIDER_REGISTRY = build_default_registry()
    return _PROVIDER_REGISTRY


@router.get("/api/v1/system/sources")
async def system_sources_v1():
    """Every free data source the platform parses: does it still parse, how old is its latest observation against
    its normal lag (ok / stale / degraded / failing), since when (api/source_monitor.py, checked every 6 h)."""
    from api import source_monitor
    return source_monitor.status()


@router.post("/api/v1/system/sources/check")
async def system_sources_check_v1(request: Request):
    """Run the source checks now (admin / PM)."""
    from api.core.access import require_roles
    from api import source_monitor
    require_roles(request, {"pm"})
    await asyncio.to_thread(source_monitor.run_checks)
    return source_monitor.status()


@router.get("/api/v1/providers")
async def providers_status_v1():
    """Provider health for the data layer: every configured provider, its priority, the asset
    classes it serves, whether it's currently healthy, how many requests it has served, and how
    many times a fallback to it was triggered (visible degraded reliance on backups)."""
    return {"providers": _provider_registry().status(), "as_of": datetime.now().isoformat()}


@router.get("/api/v1/quote")
async def quote_v1(symbol: str, asset_class: str = "equity"):
    """A single quote routed through the provider registry: the highest-priority healthy
    provider serves it, falling back automatically on failure. The serving provider is
    returned in `source` (feeds the lineage popover). Explicit unavailable if all fail."""
    q = await asyncio.to_thread(_provider_registry().get_quote, symbol.strip().upper(), asset_class)
    if q is None:
        return {"available": False,
                "reason": f"Data unavailable — all providers for {asset_class} are currently unreachable for {symbol}."}
    return {"available": True, "symbol": q.symbol, "price": q.price, "change_pct": q.change_pct,
            "source": q.source, "asset_class": q.asset_class, "currency": q.currency,
            "timestamp": q.timestamp.isoformat()}


@router.get("/api/report/generate")
async def report_generate(type: str = "full", format: str = "pdf"):
    """Downloadable daily brief assembled from LIVE data: current regime, the four signal
    scores + one-line explanations, flagged anomalies. `format=pdf` (reportlab) or
    `format=csv`. Powers the header export button."""
    from fastapi import Response
    from datetime import date as _date
    from api.handlers.dashboard_handler import get_dashboard_data

    regime, confidence = None, None
    try:
        dash = await get_dashboard_data(mode="live")
        reg = getattr(dash, "regime", None)
        regime = getattr(reg, "current", None) if reg is not None else None
        confidence = getattr(reg, "confidenceScore", None) if reg is not None else None
    except Exception as e:
        logger.debug(f"[report] dashboard: {e}")
    try:
        signals = (await signal_attribution_v1()).get("signals", [])
    except Exception:
        signals = []
    try:
        flagged = [m for m in (await anomalies_v1()).get("metrics", []) if m.get("is_anomalous")]
    except Exception:
        flagged = []

    today = _date.today().isoformat()

    if format == "csv":
        import io as _io, csv as _csv
        buf = _io.StringIO()
        w = _csv.writer(buf)
        w.writerow(["Macro Terminal — Daily Brief", today])
        w.writerow([])
        w.writerow(["Regime", regime or "—", f"{round(confidence * 100)}% confidence" if confidence is not None else "confidence n/a"])
        w.writerow([])
        w.writerow(["Signal", "Score", "Trend", "Driver", "Explanation"])
        for s in signals:
            w.writerow([s.get("signal"), s.get("score"), s.get("trend"), s.get("driver"), s.get("explanation_text")])
        w.writerow([])
        w.writerow(["Anomalies (outside 2sigma)", "Value", "z-score"])
        for m in flagged:
            w.writerow([m.get("metric"), m.get("current"), m.get("z_score")])
        return Response(buf.getvalue(), media_type="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="macro_brief_{today}.csv"'})

    import io as _io
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

    buf = _io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, topMargin=0.6 * inch, bottomMargin=0.6 * inch)
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Title"], fontSize=18, textColor=colors.HexColor("#0d1117"))
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=12, textColor=colors.HexColor("#334155"))
    bodyst = styles["BodyText"]
    story = [Paragraph("Macro Terminal — Daily Brief", h1),
             Paragraph(f"{today} · generated {datetime.now(timezone.utc).strftime('%H:%M')} UTC", bodyst),
             Spacer(1, 12),
             Paragraph(f"Regime: <b>{regime or '—'}</b>"
                       + (f" ({round(confidence * 100)}% confidence)" if confidence is not None else ""), h2),
             Spacer(1, 8)]
    if signals:
        story.append(Paragraph("Signals", h2))
        rows = [["Signal", "Score", "Trend", "Explanation"]]
        for s in signals:
            rows.append([s.get("signal", ""), f"{s.get('score', '')}", s.get("trend", ""),
                         Paragraph(s.get("explanation_text", ""), bodyst)])
        t = Table(rows, colWidths=[1.0 * inch, 0.7 * inch, 1.0 * inch, 4.0 * inch])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0d1117")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        story += [t, Spacer(1, 12)]
    story.append(Paragraph(f"Anomalies (outside 2σ): {len(flagged)}", h2))
    if flagged:
        arows = [["Metric", "Value", "z-score"]] + [[m.get("metric", ""), f"{m.get('current', '')}", f"{m.get('z_score', '')}σ"] for m in flagged]
        at = Table(arows, colWidths=[3.0 * inch, 1.5 * inch, 1.0 * inch])
        at.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#92400e")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ]))
        story.append(at)
    else:
        story.append(Paragraph("All tracked metrics within their normal historical range.", bodyst))
    doc.build(story)
    return Response(buf.getvalue(), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="macro_brief_{today}.pdf"'})


@router.get("/api/v1/event-vol")
async def event_vol_v1():
    """Event-driven volatility forecast (Phase 6A): the next high-impact macro release and,
    from real SPX daily closes, how realized volatility has historically behaved in the ±3
    trading-day window around that event type vs the baseline. Historical event dates are
    derived from each event's release cadence (surfaced as a caveat)."""
    from datetime import date, timedelta as _td
    from api.calculations.event_vol import event_window_vol
    from api.handlers.market_handler import _fetch_dated_closes_literal

    # The calendar fetch (FOMC/FRED) is slow (~4s) and changes daily, not per-request — cache
    # the computed result for 10 min so the panel loads instantly and never times out.
    _now = time.time()
    if _EVENT_VOL_CACHE.get("data") is not None and _now - _EVENT_VOL_CACHE.get("ts", 0) < 600:
        return _EVENT_VOL_CACHE["data"]

    def _cache(result):
        _EVENT_VOL_CACHE["data"] = result
        _EVENT_VOL_CACHE["ts"] = _now
        return result

    try:
        raw = await get_economic_calendar()
        cal = json.loads(bytes(raw.body)) if hasattr(raw, "body") else raw
    except Exception as e:
        return {"available": False, "reason": f"calendar unavailable: {str(e)[:100]}"}
    events = sorted([e for e in (cal.get("events") or []) if e.get("impact") == "HIGH"],
                    key=lambda e: e.get("date", ""))
    if not events:
        return {"available": False, "reason": "No upcoming high-impact events."}

    nxt = events[0]
    try:
        nd = date.fromisoformat(nxt["date"])
    except Exception:
        return {"available": False, "reason": "Bad event date."}
    # Real historical dates of this event type (FRED release calendar / federalreserve.gov).
    # Stepping back a fixed 30/46 days drifted off the true release dates within months.
    today_iso = date.today().isoformat()
    if nxt["event"] == "FOMC Decision":
        past_dates = [d for d in await asyncio.to_thread(_fetch_fomc_dates) if d < today_iso][-8:]
    else:
        rid = nxt.get("release_id") or {"CPI Release": 10, "Nonfarm Payrolls": 50}.get(nxt["event"])
        past_dates = (await asyncio.to_thread(_fetch_fred_release_dates, rid, 8, True)) if rid else []
    dates_source = "actual"
    if not past_dates:
        cadence_days = {"CPI Release": 30, "FOMC Decision": 46, "Nonfarm Payrolls": 30}.get(nxt["event"], 30)
        past_dates = [(nd - _td(days=cadence_days * i)).isoformat() for i in range(1, 9)]
        dates_source = "cadence-approximated"

    spx = await _fetch_dated_closes_literal("^GSPC")
    if not spx:
        return {"available": False, "reason": "No SPX price history."}
    stats = event_window_vol(spx, past_dates, window=3)
    today = date.today()
    upcoming = [{**e, "days_away": (date.fromisoformat(e["date"]) - today).days} for e in events[:4]]
    if not stats.get("available"):
        return _cache({"available": False, "reason": stats.get("reason"), "next_event": {**nxt, "days_away": (nd - today).days}, "upcoming": upcoming})
    return _cache({
        "available": True,
        "next_event": {**nxt, "days_away": (nd - today).days},
        "upcoming": upcoming,
        **stats,
        "source": f"SPX realized vol (yfinance) around {dates_source} historical event dates",
        "historical_dates_source": dates_source,
        "note": ("Historical event dates from the FRED release calendar / federalreserve.gov"
                 if dates_source == "actual" else
                 "Historical event dates approximated from the release cadence (calendar source unreachable)")
                + "; windows are ±3 trading days.",
        "as_of": datetime.now().isoformat(),
    })


@router.get("/api/v1/risk-parity-compare")
@ttl_cache(600, offload=True)
async def risk_parity_compare_v1():
    """Honest comparison of allocation methods on REAL asset returns (per 'Risk Parity and its
    Discontents' 2025 + HRP/CVaR-RP research): Traditional RP (inverse-vol), Return-overlay RP,
    HRP (López de Prado), CVaR-RP, vs a 60/40 benchmark. Reports Sharpe / Sortino / max
    drawdown for each — including honestly when a method does NOT beat 60/40."""
    import numpy as _np
    from api.handlers.market_handler import _fetch_dated_closes_literal
    from api.calculations.factor_model import returns_from_closes
    from api.calculations.risk_parity import (
        inverse_vol_weights, cvar_weights, hrp_weights, return_overlay_weights, sixty_forty,
        walk_forward_returns, performance_stats, risk_contribution_bands)

    # Asset universe + simple capital-market expected returns (%) for the overlay.
    assets = {"SPX Equity": "^GSPC", "US Bonds (TLT)": "TLT", "Commodities (DBC)": "DBC",
              "Gold": "GC=F", "HY Credit (HYG)": "HYG"}
    cma = {"SPX Equity": 6.0, "US Bonds (TLT)": 4.5, "Commodities (DBC)": 3.0, "Gold": 2.5, "HY Credit (HYG)": 5.0}
    labels = list(assets.keys())
    dated = await asyncio.gather(*[_fetch_dated_closes_literal(assets[l], period="5y") for l in labels])
    dmap = {l: d for l, d in zip(labels, dated) if d}
    if len(dmap) < 3:
        return {"available": False, "reason": "Insufficient asset history."}
    common = None
    for d in dmap.values():
        common = set(d) if common is None else (common & set(d))
    common = sorted(common or [])
    lookback, rebalance = 252, 21
    if len(common) < lookback + 120:
        return {"available": False, "reason": "Insufficient overlapping history for a walk-forward test."}
    labels = [l for l in labels if l in dmap]
    rets = _np.column_stack([returns_from_closes([dmap[l][dt] for dt in common]) for l in labels])
    exp_ret = [cma[l] for l in labels]

    # Weight functions are re-run on a trailing window at each rebalance (walk-forward),
    # so every reported return is out-of-sample.
    methods = {
        "60/40 Benchmark": lambda r: sixty_forty(labels),
        "Traditional RP (inverse-vol)": inverse_vol_weights,
        "Return-overlay RP (70/30)": lambda r: return_overlay_weights(r, exp_ret, 0.7),
        "HRP (López de Prado)": hrp_weights,
        "CVaR Risk Parity": cvar_weights,
    }
    rows = []
    bench = None
    for name, fn in methods.items():
        oos, w = walk_forward_returns(rets, fn, lookback=lookback, rebalance=rebalance)
        m = performance_stats(oos)
        if bench is None:
            bench = m
        m["method"] = name
        m["weights"] = {labels[i]: round(float(w[i]) * 100, 1) for i in range(len(labels))}
        m["beats_6040_sharpe"] = None if name == "60/40 Benchmark" else bool(m["sharpe"] > bench["sharpe"])
        rows.append(m)

    # Phase 2C — bootstrapped risk-contribution fragility bands on the inverse-vol scheme.
    bands = risk_contribution_bands(rets, n_boot=300)
    if bands.get("available"):
        for a in bands["per_asset"]:
            a["asset"] = labels[a["asset"]]

    return {
        "available": True, "universe": labels, "observations": len(common),
        "out_of_sample_days": len(common) - 1 - lookback,
        "period": {"start": common[lookback + 1] if len(common) > lookback + 1 else None, "end": common[-1]},
        "costs": "before trading costs (monthly rebalancing turnover is not charged)",
        "lookback_days": lookback, "rebalance_days": rebalance,
        "results": rows,
        "risk_contribution_uncertainty": bands,
        "note": f"Walk-forward, out-of-sample {common[lookback + 1] if len(common) > lookback + 1 else ''} → {common[-1]}, "
                f"before trading costs: weights re-estimated every {rebalance} trading days "
                f"from the trailing {lookback} days only; 'weights' are the latest estimate. "
                "Per 'Risk Parity and its Discontents' (2025), pure risk weighting often does not beat 60/40.",
        "citations": ["Risk Parity and its Discontents (SSRN 2025)",
                      "HRP & CVaR-RP comparison (Brazilian Review of Finance 2026)",
                      "López de Prado (2016) — Hierarchical Risk Parity"],
        "as_of": datetime.now().isoformat(),
    }


@router.get("/api/v1/quadrants")
@ttl_cache(300, offload=True)
async def quadrants_v1():
    """Bridgewater Four Quadrants: classify the environment on growth-surprise × inflation-
    surprise axes (release vs its own trend, a consensus proxy), with the per-quadrant asset
    playbook, cross-validated against the app's 6-regime label. Citation: Bridgewater All
    Weather / Four Quadrants."""
    from api.calculations.quadrants import surprise_z, quadrant_view
    from api.handlers.dashboard_handler import get_dashboard_data

    # Contiguous monthly FRED panel (industrial production YoY, CPI YoY). The old CSV
    # source had an 18-month gap and forward-filled daily rows, and fell back to
    # synthetic sample data; surprises computed on it were not month-over-trend.
    from api.handlers.macro_inputs import load_monthly_macro
    panel = await asyncio.to_thread(load_monthly_macro)
    if panel is None or panel.empty:
        return {"available": False, "reason": "Monthly FRED macro data unavailable."}
    g_series = panel["growth_yoy"].dropna().tolist()
    i_series = panel["cpi_yoy"].dropna().tolist()

    g_surprise = surprise_z(g_series)
    i_surprise = surprise_z(i_series)

    regime = None
    try:
        dash = await get_dashboard_data(mode="live")
        reg = getattr(dash, "regime", None)
        regime = getattr(reg, "current", None) if reg is not None else None
    except Exception:
        pass

    view = quadrant_view(g_surprise, i_surprise, regime_6=regime)
    view["source"] = "industrial production YoY & CPI YoY surprise vs trailing 12M (FRED)"
    view["data_as_of"] = panel.dropna(subset=["growth_yoy", "cpi_yoy"]).index[-1].strftime("%Y-%m")
    view["citation"] = "Growth × inflation regime framework (four quadrants)"
    view["as_of"] = datetime.now().isoformat()
    return view


@router.get("/api/v1/stream-agreement")
@ttl_cache(300, offload=True)
async def stream_agreement_v1():
    """Three-stream signal agreement: classify live signals into three
    INDEPENDENT evidence streams — macro drivers, intermarket action, capital flows — reduce
    each to risk-on/off/neutral, and return an agreement score + position-sizing multiplier.
    Conviction scales with the NUMBER of independent streams that agree, not the confidence of
    any single model."""
    from api.calculations.stream_agreement import (
        macro_stream, intermarket_stream, flows_stream, stream_agreement)

    # Inputs are the dashboard's own signals (0-1) and its same-date FRED spreads, so this
    # panel cannot contradict the rest of the terminal. (It used to run a separate legacy
    # pipeline on the old CSV — "growth -1.28" while every other panel showed strong growth —
    # and lost the HY spread to a 4-second fetch timeout.)
    from api.handlers.dashboard_handler import get_dashboard_data
    dash, cot = await asyncio.gather(get_dashboard_data(mode="live"),
                                     asyncio.wait_for(get_cot_data(), timeout=30.0))
    sc, ri = dash.scores, dash.riskIndicators
    g, i, l, rsk = sc.growth / 100, sc.inflation / 100, sc.liquidity / 100, sc.risk / 100
    macro = macro_stream(g, i, l)
    _ri = ri if isinstance(ri, dict) else (ri.model_dump() if ri is not None else {})
    curve_pct = _ri.get("yieldSpread")
    hy_pct = _ri.get("creditSpread")
    hy_bps = round(hy_pct * 100) if hy_pct is not None else None
    intermarket = intermarket_stream(curve_pct, hy_bps, rsk)

    # --- FLOWS stream (COT index extremes; put/call unavailable keyless -> neutral) ---
    long_ext = short_ext = None
    if isinstance(cot, dict) and cot.get("contracts"):
        rows = cot["contracts"]
        long_ext = sum(1 for c in rows if c.get("extreme_long"))
        short_ext = sum(1 for c in rows if c.get("extreme_short"))
    flows = flows_stream(long_ext, short_ext, None)

    result = stream_agreement(macro, intermarket, flows)
    result["available"] = True
    result["inputs"] = {
        "macro": {"growth_signal": round(g, 2), "inflation_signal": round(i, 2), "liquidity_signal": round(l, 2)},
        "intermarket": {"curve_2s10s_pct": curve_pct, "hy_spread_bps": hy_bps, "risk_appetite_signal": round(rsk, 2)},
        "flows": {"cot_extreme_longs": long_ext, "cot_extreme_shorts": short_ext, "put_call": None},
    }
    result["source"] = "Dashboard signals; FRED 2s10s and ICE BofA HY OAS; CFTC COT index"
    result["citation"] = "Independent evidence streams: macro data, intermarket prices, positioning/flows"
    result["as_of"] = datetime.now().isoformat()
    return result


@router.get("/api/v1/central-banks/next")
@ttl_cache(1800, offload=True)
async def central_banks_next_v1():
    """Each major central bank's next decision with the free consensus (survey forecast; fed funds futures for the Fed)."""
    from api.handlers.cb_decisions import next_decisions
    policy, curves = None, None
    try:
        gm = await get_global_macro_v1()
        policy = {r["code"]: (r.get("policy") or {}).get("rate") for r in gm.get("economies") or []}
    except Exception as e:
        logger.info("[cb-next] policy rates unavailable: %s", e)
    try:
        from api.marketdata.curves import curves as _curves
        curves = (await asyncio.to_thread(_curves)).get("curves")
    except Exception as e:
        logger.info("[cb-next] curves unavailable: %s", e)
    return await asyncio.to_thread(next_decisions, policy, curves)


@router.get("/api/v1/signals/composite-history")
async def composite_history_v1(weeks: int = 104):
    """Weekly history of the composite signal and its four inputs, re-evaluated with data as of each date, with the
    S&P 500's forward 1-month return (api/handlers/composite_history.py)."""
    from api.handlers.composite_history import composite_history
    try:
        return await composite_history(max(8, min(int(weeks), 260)))
    except Exception as e:
        logger.warning("[composite-history] %s", e)
        return {"available": False, "reason": f"{type(e).__name__}: {str(e)[:160]}", "points": []}


@router.get("/api/v1/factor-validation")
async def factor_validation_v1():
    """Factor out-of-sample validation (Phase 4, AQR discipline): for each macro factor, fit the
    exposure in-sample, measure R² in- vs out-of-sample, and flag factors whose explanatory power
    does NOT survive out-of-sample (overfitting). Unstable factors are excluded from the factor
    rotation call. Citation: AQR 'Fact, Fiction, and Factor Investing'."""
    from api.handlers.governance import factor_validation
    return await factor_validation()


@router.get("/api/v1/regime-transition")
@ttl_cache(300, offload=True)
async def regime_transition_v1():
    """Forward-looking regime early-warning (Phase 6B): the empirical next-period transition
    probabilities from the CURRENT regime, computed from a monthly regime history that is
    classified from real macro data (the same classifier the dashboard uses)."""
    from api.calculations.regime import empirical_transition_matrix, forward_outlook

    try:
        rd = await asyncio.to_thread(get_regime_data)
    except Exception as e:
        return {"available": False, "reason": f"regime classification failed: {str(e)[:120]}"}

    # Transitions from the FULL contiguous monthly history (since the late 1980s), not just
    # the 24 months shown in the timeline.
    try:
        regimes = list((await asyncio.to_thread(_monthly_regime_frame))["regime"])
    except Exception as e:
        return {"available": False, "reason": f"regime history unavailable: {str(e)[:120]}"}
    if len(regimes) < 6:
        return {"available": False, "reason": f"Insufficient regime history ({len(regimes)} months)."}

    matrix = empirical_transition_matrix(regimes)
    outlook = forward_outlook(matrix, rd.current)

    # The headline macro-cycle regime (the 7-state model shown in the header/playbook/scenario),
    # surfaced here so the panel reads as a complementary lens rather than a competing claim.
    cycle_regime = None
    try:
        from api.handlers.dashboard_handler import get_dashboard_data
        dash = await get_dashboard_data(mode="live")
        cycle_regime = dash.regime.current if getattr(dash, "regime", None) else None
    except Exception:
        pass

    return {
        "available": True,
        "current_regime": rd.current,
        "cycle_regime": cycle_regime,
        "confidence": getattr(rd, "confidenceScore", None),
        "outlook": outlook,
        "matrix": matrix,
        "months_analysed": len(regimes),
        "taxonomy": "growth×inflation quadrant (Goldilocks / Reflation / Slowdown / Stagflation)",
        "source": "monthly quadrant regimes from FRED industrial production YoY & CPI YoY (rolling 36M z-scores)",
        "note": "Probabilities are per monthly step. This panel uses the growth×inflation quadrant "
                "model — a complementary lens to the headline macro-cycle regime, so the current "
                "quadrant need not share the same word as the header regime.",
        "as_of": datetime.now().isoformat(),
    }


@router.get("/api/v1/anomalies")
async def anomalies_v1(window: int = 252):
    """System-wide anomaly scan: for each tracked market metric, z-score the latest value
    against its own trailing `window`-day history and flag |z| > 2 (outside normal range).
    Returns every metric ranked by |z_score| so the UI can pin the extremes. Real yfinance
    closes — traceable via `source`."""
    from api.handlers.market_handler import _fetch_closes_literal
    from api.calculations.altdata import historical_band

    window = max(60, min(int(window), 756))
    # (metric label, literal ticker, unit)
    metrics = [
        ("VIX", "^VIX", "idx"), ("S&P 500", "^GSPC", "idx"), ("Nasdaq 100", "^NDX", "idx"),
        ("US Dollar", "DX-Y.NYB", "idx"), ("Gold", "GC=F", "$"), ("WTI Crude", "CL=F", "$"),
        ("10Y (TLT)", "TLT", "$"), ("HY Credit (HYG)", "HYG", "$"), ("2Y (SHY)", "SHY", "$"),
    ]
    closes_list = await asyncio.gather(*[_fetch_closes_literal(t) for _, t, _ in metrics])

    out = []
    for (label, ticker, unit), closes in zip(metrics, closes_list):
        band = historical_band(closes or [], window=window) if closes else None
        if band is None:
            continue
        out.append({"metric": label, "ticker": ticker, "unit": unit, **band})
    out.sort(key=lambda m: abs(m["z_score"]), reverse=True)
    return {
        "available": bool(out),
        "window": window,
        "anomaly_count": sum(1 for m in out if m["is_anomalous"]),
        "metrics": out,
        "source": "yfinance (daily closes)",
        "as_of": datetime.now().isoformat(),
    }


@router.get("/api/v1/altdata/positioning")
async def altdata_positioning_v1():
    """Alternative-data positioning signals: VIX term structure (contango/backwardation),
    cross-market correlation-breakdown alerts, and credit-spread stress — all from real
    yfinance/FRED data."""
    from api.handlers.market_handler import _fetch_dated_closes_literal, _fetch_closes_literal
    from api.calculations.factor_model import returns_from_closes
    from api.calculations.altdata import term_structure, correlation_breakdown, zscore, percentile_rank

    # 1) VIX term structure
    async def _last(t):
        c = await _fetch_closes_literal(t)
        return c[-1] if c else None
    vix9d, vix, vix3m, vix6m = (await _last("^VIX9D"), await _last("^VIX"),
                                await _last("^VIX3M"), await _last("^VIX6M"))
    vix_term = term_structure(vix9d, vix, vix3m, vix6m)

    # 2) Cross-market correlation breakdowns
    pairs = [("SPY", "TLT", "Equity–Duration"), ("SPY", "DX-Y.NYB", "Equity–USD"),
             ("SPY", "GLD", "Equity–Gold"), ("SPY", "HYG", "Equity–HY Credit")]
    dated = {}
    syms = {s for a, b, _ in pairs for s in (a, b)}
    for s in syms:
        dated[s] = await _fetch_dated_closes_literal(s)
    corr_alerts = []
    for a, b, label in pairs:
        da, db = dated.get(a, {}), dated.get(b, {})
        common = sorted(set(da) & set(db))
        if len(common) < 90:
            corr_alerts.append({"pair": label, "available": False})
            continue
        ra = returns_from_closes([da[d] for d in common])
        rb = returns_from_closes([db[d] for d in common])
        res = correlation_breakdown(ra, rb)
        corr_alerts.append({"pair": label, **res})

    # 3) Credit-spread stress. The LEVEL is judged against all the history FRED serves for
    # the ICE BofA indices (it keeps ~3 years); a 1-year window alone called 310bp "stress"
    # at a time when it was the 3-year median. The 1-year z-score is reported as the CHANGE.
    from api.handlers.macro_inputs import _fetch_fred_history_sync
    hy_hist = await asyncio.to_thread(_fetch_fred_history_sync, "BAMLH0A0HYM2", 365 * 4)
    ig_hist = await asyncio.to_thread(_fetch_fred_history_sync, "BAMLC0A0CM", 365 * 4)
    credit = {"available": False}
    if hy_hist.values and ig_hist.values:
        hy_all = list(reversed(hy_hist.values))          # newest first, as zscore() expects
        hy_1y = hy_all[:252]
        hy_bps, ig_bps = hy_all[0] * 100, ig_hist.values[-1] * 100
        pct_level = percentile_rank(hy_all[0], hy_all)
        z_1y = zscore(hy_all[0], hy_1y)
        credit = {
            "available": True,
            "hy_oas_bps": round(hy_bps, 1),
            "ig_oas_bps": round(ig_bps, 1),
            "hy_ig_spread_bps": round(hy_bps - ig_bps, 1),
            "hy_percentile": pct_level,
            "history_from": hy_hist.dates[0],
            "hy_zscore": z_1y,
            "hy_zscore_window": "1y",
            "as_of": hy_hist.dates[-1],
            "signal": ("stress" if (pct_level or 0) >= 85 else
                       "complacent" if (pct_level or 100) <= 15 else
                       "widening" if (z_1y or 0) > 1.5 else
                       "tightening" if (z_1y or 0) < -1.5 else "neutral"),
        }

    return {
        "available": True,
        "vix_term_structure": vix_term,
        "correlation_alerts": corr_alerts,
        "credit": credit,
        "computed_at": datetime.now().isoformat(),
    }


@router.get("/api/v1/signals/backtest")
async def signals_backtest_v1(horizon: int = 21):
    """Walk-forward backtest of price-reconstructable signals on the S&P 500 (5y daily,
    no look-ahead): momentum (12-1m), trend (200d MA), and VIX vol-regime. Reports hit
    rate, forward return by state, strategy Sharpe/drawdown and a confusion matrix — and,
    per signal, the governance status that sets its ensemble weight."""
    from api.handlers.governance import signal_backtests
    return await signal_backtests(horizon)


@router.get("/api/earnings/revisions")
async def get_earnings_revisions():
    """Sector EPS revisions (free: Yahoo analyst estimates for each SPDR sector ETF's top-10 holdings — see
    api/marketdata/eps_revisions.py), with macro-vs-earnings divergences against the regime sector signals.
    Structured absence (available: false, no sectors) when the estimates can't be fetched — never invented numbers."""
    from api.marketdata.eps_revisions import sector_revisions
    try:
        rev = await asyncio.wait_for(asyncio.to_thread(sector_revisions), timeout=90)
    except Exception as e:
        logger.info("[earnings/revisions] unavailable: %s", e)
        return {"available": False, "reason": f"Sector EPS-revision data unavailable ({type(e).__name__}).",
                "sectors": {}, "divergences": [], "updated_at": datetime.now().isoformat()}
    macro = {}
    try:
        from api.handlers.dashboard_handler import get_dashboard_data
        dash = await asyncio.wait_for(get_dashboard_data(mode="live"), timeout=20)
        sa = dash.sectorAllocation
        sa = sa.model_dump() if hasattr(sa, "model_dump") else (sa or {})
        macro = {s.get("name"): s.get("signal") for s in (sa.get("sectors") or [])}
    except Exception as e:
        logger.debug("[earnings/revisions] sector signals unavailable: %s", e)
    sectors, divs = {}, []
    for name, r in rev["sectors"].items():
        if not r.get("available"):
            continue
        sig = macro.get(name) or ""
        div_type = ("macro overweight, estimates falling" if "Overweight" in sig and r["direction"] == "DOWN"
                    else "macro underweight, estimates rising" if "Underweight" in sig and r["direction"] == "UP" else None)
        sectors[name] = {"eps_revision_pct": r["eps_revision_pct"], "direction": r["direction"], "beats_rate": None,
                         "breadth": r["breadth"], "analysts_up_30d": r["analysts_up_30d"],
                         "analysts_down_30d": r["analysts_down_30d"], "etf": r["etf"],
                         "constituents_used": r["constituents_used"], "macro_signal": sig or None,
                         "companies_up": r.get("companies_up"), "companies_down": r.get("companies_down"),
                         "divergence": div_type is not None, "divergence_type": div_type}
        if div_type:
            divs.append({"sector": name, "type": div_type, "revision_pct": r["eps_revision_pct"], "macro_signal": sig})
    return {"available": bool(sectors), "sectors": sectors, "divergences": divs,
            "strongest_positive_revision": rev.get("strongest_positive_revision"),
            "strongest_negative_revision": rev.get("strongest_negative_revision"),
            "method": rev.get("method"), "basis": rev.get("basis"), "source": rev.get("source"),
            "updated_at": rev.get("computed_at")}


@router.get("/api/cot")
@ttl_cache(3600, offload=True)
async def get_cot_data():
    """CFTC Commitments of Traders: speculative positioning per contract, selected by CFTC
    contract code, with the 3-year COT index for extremes (see api/cot.py)."""
    from api.cot import fetch_cot
    try:
        return {**(await asyncio.to_thread(fetch_cot)), "last_updated": datetime.now().isoformat()}
    except Exception as e:
        logger.error(f"COT data error: {e}")
        return {"error": str(e)[:200], "report_date": None, "contracts": [],
                "last_updated": datetime.now().isoformat()}

@router.get("/api/v1/risk/cycle")
@ttl_cache(3600, offload=True)
async def get_cycle_risk_v1():
    """Cycle & systemic-risk indicators from published research: near-term forward spread
    (Engstrom & Sharpe), excess bond premium (Gilchrist & Zakrajšek), financial turbulence
    (Kritzman & Li), absorption ratio (Kritzman et al.) and environmental balance of the book.
    See api/research_indicators.py."""
    from api.research_indicators import build_cycle_risk
    return await build_cycle_risk()


@router.get("/api/v1/global-macro")
@ttl_cache(900)
async def get_global_macro_v1():
    """Developed-markets monitor (Americas, Europe, Asia-Pacific): policy rates and recent
    central-bank moves, CPI, unemployment, GDP, 10Y/3M yields, equity and FX — each value dated
    and graded against its release calendar. See api/global_macro.py for sources."""
    from api.global_macro import build_global_macro
    return await build_global_macro()


@router.get("/api/regional-macro")
@ttl_cache(900)
async def get_regional_macro():
    """Cross-country comparison (legacy shape) derived from the developed-markets monitor.

    It used FRED's mirror of OECD Main Economic Indicators, which stopped updating in early
    2025 — so UK/Canada CPI from 2025-03 and an August-average US 10Y were shown as current.
    Every value now carries its period."""
    from api.global_macro import build_global_macro
    gm = await build_global_macro()
    regions = []
    for r in gm.get("economies", []):
        if r["code"] not in ("US", "EA", "GB", "JP", "CA", "AU", "CH", "DE", "KR"):
            continue
        ten = r["ten_year_live"] if r.get("ten_year_live") else {"value": r["ten_year"]["value"], "date": r["ten_year"]["period"]}
        regions.append({"region": r["name"], "code": r["code"], "tenYear": ten["value"],
                        "unemployment": r["unemployment"]["value"], "cpiYoY": r["cpi"]["value"],
                        "policyRate": r["policy"].get("rate"),
                        "asOf": {"tenYear": ten.get("date"), "unemployment": r["unemployment"]["period"],
                                 "cpiYoY": r["cpi"]["period"], "policyRate": r["policy"].get("as_of")}})
    return {
        "available": gm.get("available", False),
        "regions": regions,
        "indicators": [
            {"key": "policyRate", "label": "Policy rate", "unit": "%"},
            {"key": "cpiYoY", "label": "CPI YoY", "unit": "%"},
            {"key": "unemployment", "label": "Unemployment", "unit": "%"},
            {"key": "tenYear", "label": "10Y Yield", "unit": "%"},
        ],
        "source": "BIS policy rates; OECD/Eurostat CPI, unemployment, yields; FRED (US) — see /api/v1/global-macro",
        "as_of": datetime.now().isoformat(),
    }


@router.get("/api/global-correlation")
@ttl_cache(600)
async def get_global_correlation(window: int = 90):
    """Cross-market correlation matrix across WORLD equity indices + FX + cross-asset, from real
    aligned daily returns (yfinance). Answers 'how do these global markets move together'."""
    from api.handlers.market_handler import _fetch_dated_closes_literal
    from api.calculations.factor_model import returns_from_closes
    from api.calculations.altdata import correlation_matrix

    window = max(20, min(int(window), 252))
    assets = {
        "S&P500": "^GSPC", "Nasdaq": "^IXIC", "FTSE": "^FTSE", "DAX": "^GDAXI",
        "EuroStoxx": "^STOXX50E", "Nikkei": "^N225", "HangSeng": "^HSI", "Shanghai": "000001.SS",
        "ASX200": "^AXJO", "Nifty": "^NSEI",
        "EURUSD": "EURUSD=X", "USDJPY": "USDJPY=X", "DXY": "DX-Y.NYB",
        "Gold": "GC=F", "WTI": "CL=F", "UST10Y": "TLT",
    }
    labels = list(assets.keys())
    results = await asyncio.gather(*[_fetch_dated_closes_literal(assets[l]) for l in labels],
                                   return_exceptions=True)
    dated = {l: d for l, d in zip(labels, results) if d and not isinstance(d, Exception)}
    if len(dated) < 2:
        return {"available": False, "reason": "Insufficient market data.", "labels": [], "matrix": []}
    common = None
    for d in dated.values():
        common = set(d) if common is None else (common & set(d))
    common = sorted(common or [])
    if len(common) < 22:
        return {"available": False, "reason": "Insufficient overlapping history.", "labels": [], "matrix": []}
    returns_by_asset = {l: returns_from_closes([dated[l][dt] for dt in common]) for l in dated}
    result = correlation_matrix(returns_by_asset, window)
    return {"available": bool(result["matrix"]), "as_of": datetime.now().isoformat(),
            "source": "yfinance (daily closes) — global indices, FX & cross-asset",
            "window": window, **result}


def _realized_vol(closes, n: int = 21):
    """Annualised realised volatility (%) of the last `n` daily log returns."""
    import math
    if len(closes) < n + 1:
        return None
    r = [math.log(closes[i] / closes[i - 1]) for i in range(len(closes) - n, len(closes)) if closes[i - 1] > 0]
    if len(r) < 2:
        return None
    m = sum(r) / len(r)
    return round(math.sqrt(sum((x - m) ** 2 for x in r) / (len(r) - 1)) * math.sqrt(252) * 100, 2)


@router.get("/api/fx-rates")
@ttl_cache(300)
async def get_fx_rates():
    """Broad FX board — many pairs grouped by region (G10 majors, Asia, EMEA, LatAm), each with
    a real live spot + daily % change. Pairs that fail to quote return null, never a fake value."""
    from api.handlers.market_handler import _fetch_dated_closes_literal, _pct_change

    # group -> [(pair label, yfinance ticker, decimals)]
    groups = {
        "g10": [("EUR/USD", "EURUSD=X", 4), ("GBP/USD", "GBPUSD=X", 4), ("USD/JPY", "USDJPY=X", 2),
                ("USD/CHF", "USDCHF=X", 4), ("USD/CAD", "USDCAD=X", 4), ("AUD/USD", "AUDUSD=X", 4),
                ("NZD/USD", "NZDUSD=X", 4), ("EUR/GBP", "EURGBP=X", 4), ("EUR/JPY", "EURJPY=X", 2),
                ("USD/SEK", "USDSEK=X", 3)],
        "asia": [("USD/CNY", "USDCNY=X", 3), ("USD/INR", "USDINR=X", 2), ("USD/KRW", "USDKRW=X", 1),
                 ("USD/SGD", "USDSGD=X", 4), ("USD/HKD", "USDHKD=X", 4), ("USD/TWD", "USDTWD=X", 2)],
        "emea_latam": [("USD/BRL", "USDBRL=X", 3), ("USD/MXN", "USDMXN=X", 3),
                       ("USD/ZAR", "USDZAR=X", 3), ("USD/TRY", "USDTRY=X", 3)],
    }
    # Dated closes, already re-dated to their New York session (api/market_dates.py), so a
    # pair's daily change lines up with DXY's and each row says which session it is.
    flat = [(g, p, t, dp) for g, items in groups.items() for (p, t, dp) in items]
    dated_list = await asyncio.gather(*[_fetch_dated_closes_literal(t) for _, _, t, _ in flat],
                                      return_exceptions=True)
    result = {"g10": [], "asia": [], "emea_latam": []}
    for (g, pair, ticker, dp), dated in zip(flat, dated_list):
        if isinstance(dated, Exception) or not dated:
            result[g].append({"pair": pair, "ticker": ticker, "spot": None, "change1d": None,
                              "as_of": None, "available": False})
        else:
            days = sorted(dated)
            closes = [dated[d] for d in days]
            ch1m = _pct_change(closes, 21)
            result[g].append({"pair": pair, "ticker": ticker, "spot": round(float(closes[-1]), dp),
                              "change1d": _pct_change(closes, 1), "change1w": _pct_change(closes, 5),
                              "change1m": ch1m, "vol1m": _realized_vol(closes, 21),
                              "trend": (None if ch1m is None else "UP" if ch1m > 1 else "DOWN" if ch1m < -1 else "FLAT"),
                              "as_of": days[-1], "available": True})
    # Live spot: the latest 5-minute bar of the session in progress (FX trades around the clock); the daily change is
    # measured from the last completed New York close, and both times are reported.
    def _live(ticker):
        try:
            import yfinance as yf
            h = yf.Ticker(ticker).history(period="1d", interval="5m")
            if h is None or h.empty:
                return None
            ts = h.index[-1]
            return float(h["Close"].iloc[-1]), (ts.tz_convert("UTC") if ts.tzinfo else ts).strftime("%Y-%m-%d %H:%M UTC")
        except Exception:
            return None
    lives = await asyncio.gather(*[asyncio.to_thread(_live, t) for _, _, t, _ in flat], return_exceptions=True)
    for (g, pair, ticker, dp), lv in zip(flat, lives):
        row = next((x for x in result[g] if x["pair"] == pair), None)
        if row is None or not row.get("available") or isinstance(lv, Exception) or not lv:
            continue
        price, when = lv
        close = row["spot"]
        row.update({"close": close, "close_as_of": row["as_of"], "spot": round(price, dp), "live_at": when,
                    "change1d": round((price / close - 1) * 100, 3) if close else row["change1d"]})
    dxy_dated = await _fetch_dated_closes_literal("DX-Y.NYB")
    dxy = None
    if dxy_dated:
        dd = sorted(dxy_dated)
        dxy = {"spot": round(float(dxy_dated[dd[-1]]), 2),
               "change1d": _pct_change([dxy_dated[d] for d in dd], 1), "as_of": dd[-1]}
    n_ok = sum(1 for g in result.values() for x in g if x.get("available"))
    return {
        "available": n_ok > 0,
        "dxy": dxy,
        **result,
        "pair_count": n_ok,
        "source": "Yahoo Finance daily closes; FX re-dated to the New York session they belong to",
        "as_of": datetime.now().isoformat(),
    }


@router.get("/api/market-hours")
@ttl_cache(21600, offload=True)  # 6h — holiday calendars change rarely
async def get_market_hours():
    """Per-exchange trading hours + REAL holiday calendars (not hardcoded).

    Holidays come from the `holidays` library, which is per-region and works for ANY year —
    including lunar-based closures (Hong Kong / Singapore Chinese New Year). The frontend keeps
    a live-ticking clock and just uses these dates to mark weekends/holidays as closed."""
    try:
        import holidays as _hol
    except Exception as e:
        return {"available": False, "reason": f"holidays library unavailable: {e}"}

    from datetime import datetime as _dt
    yr = _dt.now().year
    years = [yr, yr + 1]  # include next year so a year-rollover still resolves

    # (display name, city, tz, open, close, holidays-lib resolver)
    exchanges = [
        ("New York", "NYC", "America/New_York", 9.5, 16.0, lambda y: _hol.financial_holidays("NYSE", years=y)),
        ("London", "LON", "Europe/London", 8.0, 16.5, lambda y: _hol.country_holidays("GB", years=y)),
        ("Frankfurt", "FRA", "Europe/Berlin", 9.0, 17.5, lambda y: _hol.country_holidays("DE", years=y)),
        ("Tokyo", "TKY", "Asia/Tokyo", 9.0, 15.0, lambda y: _hol.country_holidays("JP", years=y)),
        ("Hong Kong", "HKG", "Asia/Hong_Kong", 9.5, 16.0, lambda y: _hol.country_holidays("HK", years=y)),
        ("Sydney", "SYD", "Australia/Sydney", 10.0, 16.0, lambda y: _hol.country_holidays("AU", years=y)),
    ]
    out = []
    for name, city, tz, open_h, close_h, resolver in exchanges:
        dates = {}
        try:
            for y in years:
                for d, label in resolver(y).items():
                    dates[d.isoformat()] = label
        except Exception as e:
            logger.warning(f"[market-hours] holiday calc failed for {name}: {e}")
        out.append({
            "name": name, "city": city, "tz": tz,
            "open": open_h, "close": close_h,
            "holidays": sorted(dates.keys()),
            "holidayNames": dates,
        })
    return {
        "available": True,
        "exchanges": out,
        "years": years,
        "source": "python-holidays library (per-region, any-year; incl. lunar calendars)",
        "as_of": _dt.now().isoformat(),
    }


@router.get("/api/global-markets")
@ttl_cache(300)
async def get_global_markets():
    """Major world equity indices with real level + daily % change (not just US).

    Uses live yfinance closes per index; any index that fails to fetch is returned with a null
    level + reason rather than a fabricated value."""
    from api.handlers.market_handler import _fetch_closes_literal, _pct_change

    # (display name, region, yfinance ticker)
    indices = [
        ("S&P 500", "US", "^GSPC"),
        ("Nasdaq", "US", "^IXIC"),
        ("FTSE 100", "UK", "^FTSE"),
        ("DAX", "Germany", "^GDAXI"),
        ("Euro Stoxx 50", "Europe", "^STOXX50E"),
        ("Nikkei 225", "Japan", "^N225"),
        ("Hang Seng", "Hong Kong", "^HSI"),
        ("Shanghai Composite", "China", "000001.SS"),
        ("ASX 200", "Australia", "^AXJO"),
        ("Nifty 50", "India", "^NSEI"),
    ]
    closes_list = await asyncio.gather(*[_fetch_closes_literal(t) for _, _, t in indices],
                                       return_exceptions=True)
    # Valuation from a tracking ETF (index P/E is not free): trailing P/E and dividend yield, cached a day.
    proxy = {"^GSPC": "SPY", "^IXIC": "QQQ", "^FTSE": "EWU", "^GDAXI": "EWG", "^STOXX50E": "FEZ", "^N225": "EWJ",
             "^HSI": "EWH", "000001.SS": "MCHI", "^AXJO": "EWA", "^NSEI": "INDA"}

    def _val(etf):
        from api.marketdata.core import _cached

        def fetch():
            import yfinance as yf
            i = yf.Ticker(etf).info or {}
            pe, dy = i.get("trailingPE"), i.get("yield") or i.get("dividendYield")
            return {"etf": etf, "pe": round(float(pe), 1) if pe else None,
                    "earnings_yield_pct": round(100 / float(pe), 2) if pe else None,
                    "dividend_yield_pct": round(float(dy) * (100 if dy < 1 else 1), 2) if dy else None}
        try:
            return _cached(f"wei:val:{etf}", 86400, fetch)
        except Exception:
            return {"etf": etf, "pe": None, "earnings_yield_pct": None, "dividend_yield_pct": None}
    vals = await asyncio.gather(*[asyncio.to_thread(_val, proxy[t]) for _, _, t in indices])
    markets = []
    for (name, region, ticker), closes in zip(indices, closes_list):
        if isinstance(closes, Exception) or not closes:
            markets.append({"name": name, "region": region, "ticker": ticker,
                            "level": None, "change1d": None, "available": False,
                            "reason": "quote unavailable"})
            continue
        markets.append({
            "name": name, "region": region, "ticker": ticker,
            "level": round(float(closes[-1]), 2),
            "change1d": _pct_change(closes, 1),
            "change1m": _pct_change(closes, 21),
            "spark": [round(float(c), 2) for c in closes[-63:]],          # ~3 months of closes
            "valuation": vals[indices.index((name, region, ticker))],
            "available": True,
        })
    ok = [m for m in markets if m.get("available")]
    return {
        "markets": markets,
        "available": len(ok) > 0,
        "regions_covered": sorted({m["region"] for m in ok}),
        "source": "Yahoo Finance (yfinance) — live index closes; valuation from a tracking ETF (trailing P/E, yield)",
        "as_of": datetime.now().isoformat(),
    }


@router.get("/api/horizon")
async def get_horizon_risks():
    """
    Returns geopolitical and macro horizon risk events for the next 90 days.
    """
    try:
        import requests
        from datetime import datetime, timedelta

        today = datetime.now().date()
        horizon_end = today + timedelta(days=90)

        events = []

        # Try Finnhub economic calendar
        finnhub_key = os.getenv("FINNHUB_API_KEY", "")
        if finnhub_key:
            try:
                url = f"https://finnhub.io/api/v1/calendar/economic?from={today.isoformat()}&to={horizon_end.isoformat()}&token={finnhub_key}"
                response = await asyncio.to_thread(lambda: requests.get(url, timeout=10))    # off the event loop
                if response.status_code == 200:
                    data = response.json()
                    economic_events = data.get("economicCalendar", [])
                    for event in economic_events[:20]:
                        impact = event.get("impact", "")
                        if impact in ["high", "1", "2"]:
                            event_date = event.get("date", "")
                            if event_date:
                                try:
                                    event_dt = datetime.fromisoformat(event_date.replace("Z", "+00:00")).date()
                                    days_away = (event_dt - today).days
                                    events.append({
                                        "date": event_date[:10],
                                        "event": event.get("event", "Unknown"),
                                        "impact": "HIGH" if impact in ["high", "1"] else "MEDIUM",
                                        "category": "MONETARY_POLICY" if "FOMC" in event.get("event", "") else "GROWTH",
                                        "days_away": days_away,
                                    })
                                except Exception:
                                    pass
            except Exception as e:
                logger.warning(f"Finnhub calendar fetch failed: {e}")

        # FOMC decisions from federalreserve.gov (the old hardcoded 2026 list had the
        # wrong months for half the meetings).
        fomc_upcoming = [datetime.fromisoformat(d).date() for d in _fetch_fomc_dates()]

        for fomc_date in fomc_upcoming:
            if today <= fomc_date <= horizon_end:
                days_away = (fomc_date - today).days
                events.append({
                    "date": fomc_date.isoformat(),
                    "event": "FOMC Decision",
                    "impact": "HIGH",
                    "category": "MONETARY_POLICY",
                    "days_away": days_away,
                })

        # CPI releases — SAME source as /api/calendar (FRED release id 10), with the identical
        # ~12th-of-month fallback. Previously horizon used a "second Tuesday" heuristic while the
        # calendar used the 12th, so the two panels showed the same CPI release on different dates
        # (e.g. 07-14 vs 07-12). Now both derive from one source and stay consistent.
        cpi_dates = _calendar_release_dates(10, today, horizon_end)
        if cpi_dates:
            for ds in cpi_dates:
                try:
                    cd = datetime.fromisoformat(ds).date()
                except Exception:
                    continue
                if today <= cd <= horizon_end:
                    events.append({"date": cd.isoformat(), "event": "CPI Release", "impact": "HIGH",
                                   "category": "INFLATION", "days_away": (cd - today).days})
        else:
            for k in range(0, 4):
                y, mth = divmod(today.month - 1 + k, 12)
                cd = datetime(today.year + y, mth + 1, 12).date()
                if today <= cd <= horizon_end:
                    events.append({"date": cd.isoformat(), "event": "CPI Release", "impact": "HIGH",
                                   "category": "INFLATION", "days_away": (cd - today).days})

        # NFP releases — SAME source as /api/calendar (FRED release id 50), fallback to the first
        # Friday of the month, and the same "Nonfarm Payrolls" label the calendar/event-vol use.
        nfp_dates = _calendar_release_dates(50, today, horizon_end)
        if nfp_dates:
            for ds in nfp_dates:
                try:
                    nd = datetime.fromisoformat(ds).date()
                except Exception:
                    continue
                if today <= nd <= horizon_end:
                    events.append({"date": nd.isoformat(), "event": "Nonfarm Payrolls", "impact": "HIGH",
                                   "category": "LABOR", "days_away": (nd - today).days})
        else:
            for k in range(0, 4):
                y, mth = divmod(today.month - 1 + k, 12)
                first_day = datetime(today.year + y, mth + 1, 1)
                first_friday = first_day + timedelta(days=(4 - first_day.weekday()) % 7)
                nd = first_friday.date()
                if today <= nd <= horizon_end:
                    events.append({"date": nd.isoformat(), "event": "Nonfarm Payrolls", "impact": "HIGH",
                                   "category": "LABOR", "days_away": (nd - today).days})

        # The other releases the Economic Calendar rates HIGH (GDP, core PCE): same official
        # dates and names, so the two panels list the same high-impact events.
        from api.econ_calendar import RELEASES as _RELEASES
        for rid, (name, imp, *_rest) in _RELEASES.items():
            if imp != "HIGH" or rid in (10, 50):
                continue
            for ds in _calendar_release_dates(rid, today, horizon_end):
                d_ = datetime.fromisoformat(ds).date()
                events.append({"date": d_.isoformat(), "event": name, "impact": "HIGH",
                               "category": "GROWTH" if rid == 53 else "INFLATION", "days_away": (d_ - today).days})

        # Deduplicate by date + event
        seen = set()
        unique_events = []
        for event in events:
            key = (event["date"], event["event"])
            if key not in seen:
                seen.add(key)
                unique_events.append(event)

        # Sort by date
        unique_events.sort(key=lambda x: x["date"])

        # Find next high impact event
        next_high_impact = None
        for event in unique_events:
            if event["impact"] == "HIGH":
                next_high_impact = {
                    "date": event["date"],
                    "event": event["event"],
                    "days_away": event["days_away"],
                }
                break

        # Calculate risk density
        high_impact_next_14 = sum(1 for e in unique_events if e["impact"] == "HIGH" and e["days_away"] <= 14)
        risk_density = "HIGH" if high_impact_next_14 > 3 else "MEDIUM" if high_impact_next_14 > 1 else "LOW"

        # FIXED: Return format matches frontend HorizonData interface
        return {
            "horizon_events": unique_events[:30],  # Limit to 30 events
            "next_high_impact": next_high_impact,
            "risk_density": risk_density,
            "overallRiskDensity": risk_density,  # For compatibility
            "last_updated": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"Horizon risks error: {e}", exc_info=True)
        return {
            "error": str(e),
            "horizon_events": [],
            "next_high_impact": None,
            "risk_density": "UNKNOWN",
            "last_updated": datetime.now().isoformat(),
        }


# FIXED: Missing endpoints (BUG 15)
@router.get("/api/calendar")
async def get_economic_calendar():
    """US economic calendar: official release dates (FRED release calendar) for the main
    releases and FOMC decisions, with each release's latest print. See api/econ_calendar.py."""
    from api.econ_calendar import get_calendar
    try:
        return JSONResponse(content=scrub_nans(await asyncio.to_thread(get_calendar)))
    except Exception as e:
        logger.error(f"Calendar error: {e}")
        return JSONResponse(content={"upcoming": [], "this_week": [], "events": [], "error": str(e)[:200]})


# FIXED (PART 1): Market Stream endpoint for live topbar data
@router.get("/api/market-stream")
async def get_market_stream():
    """Market snapshot for the live-price tiles (REST fallback for the WebSocket).

    Uses the shared dated-close fetch (FX re-dated to its NY session, api/market_dates.py) and
    FRED for rates. Unavailable values are null. (It previously read rates from the legacy CSV
    — fed funds came back 0.0 — and fell back to invented 4.2 / 3.8 / 4.5 levels.)"""
    from api.handlers.market_handler import _fetch_dated_closes_literal
    from api.handlers.macro_inputs import load_macro_inputs
    tickers = {"spx": "^GSPC", "ndx": "^NDX", "vix": "^VIX", "gold": "GC=F", "wti": "CL=F",
               "dxy": "DX-Y.NYB", "eurusd": "EURUSD=X"}
    closes = await asyncio.gather(*[_fetch_dated_closes_literal(t) for t in tickers.values()])
    result: Dict[str, Any] = {}
    for key, dated in zip(tickers, closes):
        days = sorted(dated or {})
        result[key] = round(dated[days[-1]], 4 if key == "eurusd" else 2) if days else None
        result[f"{key}Chg"] = (round((dated[days[-1]] / dated[days[-2]] - 1) * 100, 3)
                               if len(days) >= 2 else None)
        result[f"{key}AsOf"] = days[-1] if days else None
    result["gld"], result["gldChg"] = result["gold"], result["goldChg"]   # legacy key (gold futures)
    try:
        inp = await load_macro_inputs()
        result["tenYear"], result["twoYear"], result["fed"] = inp["dgs10"].latest, inp["dgs2"].latest, inp["dff"].latest
    except Exception as e:
        logger.debug(f"Market stream rates failed: {e}")
        result["tenYear"] = result["twoYear"] = result["fed"] = None
    return scrub_nans(result)
