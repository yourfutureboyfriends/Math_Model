"""
Institutional strategy library for the Code Lab — each entry is ordinary strategy code (open it,
edit it, run it) built from the published construction of a large manager or a landmark paper.

Every strategy is evaluated the same way: net of commissions, spreads, square-root market impact,
SEC fees, borrow and financing (api/quant/codelab.py); parameters (a small grid taken from the
source papers, never a fine search) are chosen walk-forward each January using only past data, so
the record shown is out-of-sample. "Maximum money" is pursued as maximum long-run *growth* (the
Kelly criterion): the Monte Carlo then sizes leverage to the growth-optimal level, capped at
half-Kelly and by a drawdown limit — the most a rational investor can lever without courting ruin.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

CACHE = Path(__file__).resolve().parent.parent.parent / "data" / "processed" / "quant" / "library"
TTL = 20 * 3600

CROSS_ASSET = '["SPY", "QQQ", "IWM", "EFA", "EEM", "IEF", "TLT", "TIP", "LQD", "HYG", "GLD", "DBC", "UUP", "VNQ"]'
MEGACAPS = ('["AAPL", "MSFT", "AMZN", "GOOGL", "META", "NVDA", "BRK-B", "JPM", "JNJ", "V", "PG", "XOM", "UNH", "HD", '
            '"MA", "CVX", "KO", "PEP", "MRK", "ABBV", "PFE", "WMT", "BAC", "CSCO", "ORCL", "INTC", "T", "VZ", "DIS", '
            '"MCD", "NKE", "ADBE", "CRM", "COST", "TMO", "ABT", "LLY", "AVGO", "TXN", "QCOM", "HON", "IBM", "CAT", '
            '"GS", "MS", "AMGN", "LOW", "UPS", "BA", "GE"]')

LIBRARY: List[Dict[str, Any]] = [
    {
        "id": "aqr_trend",
        "name": "Multi-asset trend following",
        "source": "AQR — Hurst, Ooi & Pedersen (2017) 'A Century of Evidence on Trend-Following Investing'; Moskowitz, Ooi & Pedersen (2012)",
        "family": "Trend",
        "summary": "Long assets in up-trends and short those in down-trends across equities, bonds, credit, commodities, "
                   "the dollar and REITs, blending 1-, 3- and 12-month signals; each position sized to equal risk; "
                   "the book scaled to a volatility target; traded monthly.",
        "evidence": "AQR found trend profitable in every decade since 1880 across 67 markets, with its best years in equity "
                    "crises (2008: +20%+). Positions are sized inversely to volatility (40% per asset in MOP 2012). "
                    "Trend lagged in the 2010s; ETFs give fewer, more correlated markets than AQR's futures.",
        "code": f'''UNIVERSE = {CROSS_ASSET}
START = "2007-01-01"
# Literature grid: book volatility target, and whether to include the 1-month signal (fast trends add
# crisis convexity but cost more to trade).
PARAMS = {{"target_vol": [0.10, 0.15], "fast": [1, 0]}}


def strategy(data, target_vol=0.10, fast=1):
    px = data.close
    sig = np.sign(momentum(px, 63)) + np.sign(momentum(px, 252))
    if fast:
        sig = sig + np.sign(momentum(px, 21))
    sig = sig / (3 if fast else 2)
    w = sig * (0.40 / ewma_vol(px, 42)) / px.shape[1]          # 40% vol per asset, equal risk budget
    w = vol_target(w, px, target_vol, lookback=126)           # book-level volatility target
    return hold_monthly(w)                                    # trade once a month (MOP 2012)
''',
    },
    {
        "id": "man_ewmac",
        "name": "Moving-average crossover trend (EWMAC)",
        "source": "Man AHL — 'The Many Facets of Trend' / double EWMA crossover models; Carver (2015) 'Systematic Trading'",
        "family": "Trend",
        "summary": "Exponentially weighted moving-average crossovers at several speeds, each normalised by volatility "
                   "and capped, averaged into a continuous forecast; positions scale with signal strength.",
        "evidence": "Man AHL has run double-EWMA crossover models for about three decades and they still carry its largest "
                    "risk allocation in trend. Continuous, volatility-normalised forecasts trade less and degrade more "
                    "gracefully than on/off signals.",
        "code": f'''UNIVERSE = {CROSS_ASSET}
START = "2007-01-01"
PARAMS = {{"speeds": ["medium", "slow"], "target_vol": [0.10, 0.15]}}

SPEEDS = {{"medium": [(16, 64), (32, 128), (64, 256)], "slow": [(32, 128), (64, 256)]}}


def strategy(data, speeds="medium", target_vol=0.10):
    px = data.close
    daily_vol = px.diff().ewm(span=36, min_periods=30).std()            # price-unit volatility
    fc = 0
    for fast, slow in SPEEDS[speeds]:
        raw = (px.ewm(span=fast).mean() - px.ewm(span=slow).mean()) / daily_vol
        scaled = raw / raw.abs().expanding(min_periods=252).mean()       # average |forecast| ≈ 1
        fc = fc + scaled.clip(-2, 2)
    fc = fc / len(SPEEDS[speeds])
    w = fc * (0.25 / ewma_vol(px, 42)) / px.shape[1]
    w = vol_target(w, px, target_vol, lookback=126)
    return hold_weekly(w)
''',
    },
    {
        "id": "bw_risk_parity",
        "name": "Risk parity (All Weather style), levered",
        "source": "Bridgewater — Dalio 'The All Weather Story'; AQR — Asness, Frazzini & Pedersen (2012) 'Leverage Aversion and Risk Parity'",
        "family": "Risk parity",
        "summary": "Equal risk from equities, nominal bonds, inflation-linked bonds, gold and commodities, levered to a "
                   "volatility target and financed at the T-bill rate plus a spread.",
        "evidence": "Balancing risk rather than capital earned a higher Sharpe than 60/40 across 1926–2010 (AFP 2012) "
                    "because investors who cannot borrow overpay for risky assets. Rising real rates (2022) are its worst case.",
        "code": '''UNIVERSE = ["SPY", "EFA", "TLT", "IEF", "TIP", "GLD", "DBC"]
START = "2007-01-01"
PARAMS = {"target_vol": [0.08, 0.10, 0.12]}


def strategy(data, target_vol=0.10):
    px = data.close
    w = 1 / ewma_vol(px, 63)                         # inverse volatility ≈ equal risk for low correlations
    w = normalize_gross(w)
    w = vol_target(w, px, target_vol, lookback=126, max_leverage=3.0)
    return hold_monthly(w)
''',
    },
    {
        "id": "rp_trend_overlay",
        "name": "Risk parity with a trend overlay",
        "source": "AQR — 'Trend Following and Risk Parity' (2015 research note); Man AHL multi-strategy",
        "family": "Risk parity",
        "summary": "Risk parity where each asset's weight is cut to zero while its 10-month trend is negative.",
        "evidence": "Trend tends to make money exactly when risk parity's bond-equity hedge fails (inflation shocks, 2022), "
                    "so combining them lowers drawdowns more than it costs in return.",
        "code": '''UNIVERSE = ["SPY", "EFA", "EEM", "TLT", "IEF", "TIP", "GLD", "DBC", "VNQ"]
START = "2007-01-01"
PARAMS = {"target_vol": [0.08, 0.10, 0.12], "trend": [210, 252]}


def strategy(data, target_vol=0.10, trend=210):
    px = data.close
    up = (px > px.rolling(trend).mean()).astype(float)
    w = up / ewma_vol(px, 63)
    w = normalize_gross(w)
    w = vol_target(w, px, target_vol, lookback=126, max_leverage=3.0)
    return hold_monthly(w)
''',
    },
    {
        "id": "vol_managed_equity",
        "name": "Volatility-managed equities",
        "source": "Moreira & Muir (2017) 'Volatility-Managed Portfolios', Journal of Finance",
        "family": "Defensive",
        "summary": "Hold the S&P 500 in inverse proportion to its recent variance: more when calm, less when turbulent, "
                   "rest in T-bills; leverage capped.",
        "evidence": "Scaling exposure by 1/variance raised the market's Sharpe ratio (alpha ≈ 4.9% a year) because "
                    "volatility is persistent while expected returns do not rise as fast. Out-of-sample gains are smaller "
                    "and leverage caps matter (Cederburg et al. 2020).",
        "code": '''UNIVERSE = ["SPY"]
START = "2005-01-01"
PARAMS = {"target_vol": [0.12, 0.16], "max_leverage": [1.5, 2.0]}


def strategy(data, target_vol=0.16, max_leverage=1.5):
    px = data.close
    r = px.pct_change()
    rv = r.rolling(21).std() * np.sqrt(252)
    w = (target_vol / rv).clip(upper=max_leverage)
    return hold_monthly(w)
''',
    },
    {
        "id": "vrp_timing",
        "name": "Volatility risk premium timing",
        "source": "Bollerslev, Tauchen & Zhou (2009) 'Expected Stock Returns and Variance Risk Premia'",
        "family": "Defensive",
        "summary": "Hold the S&P 500 while implied volatility (VIX) exceeds realised volatility; move to Treasuries when "
                   "realised overtakes implied (stress).",
        "evidence": "A positive variance premium predicts equity returns; when it turns negative, markets are in the "
                    "high-volatility regime where drawdowns cluster.",
        "code": '''UNIVERSE = ["SPY", "IEF"]
START = "2005-01-01"
PARAMS = {"window": [10, 21]}


def strategy(data, window=21):
    spy = data.close["SPY"]
    rv = spy.pct_change().rolling(window).std() * np.sqrt(252) * 100
    calm = (data.vix > rv).astype(float)
    w = pd.DataFrame({"SPY": calm, "IEF": 1 - calm}, index=data.close.index)
    return hold_weekly(w)
''',
    },
    {
        "id": "robeco_conservative",
        "name": "Conservative formula (low risk + momentum)",
        "source": "Robeco — Blitz & van Vliet (2018) 'The Conservative Formula: Quantitative Investing Made Easy'",
        "family": "Equity factors",
        "summary": "From the large-cap list, keep the half with the lowest 3-year volatility, then hold those with the "
                   "strongest 12-1-month momentum; equal weight, monthly.",
        "evidence": "Low volatility plus momentum (plus payout yield, omitted here) earned ~15% a year vs ~9% for the market "
                    "1929–2016 with lower risk, in US, Europe, Japan and emerging markets. Uses today's large caps, so "
                    "results are flattered by survivorship.",
        "code": f'''UNIVERSE = {MEGACAPS}
START = "2008-01-01"
PARAMS = {{"n": [10, 15]}}


def strategy(data, n=15):
    px = data.close
    vol = px.pct_change().rolling(756, min_periods=500).std()
    mom = momentum(px, 252, 21)
    low_vol = vol.rank(axis=1, pct=True) <= 0.5
    score = mom.where(low_vol)
    pick = score.rank(axis=1, ascending=False) <= n
    w = pick.astype(float)
    return hold_monthly(normalize_gross(w))
''',
    },
    {
        "id": "aqr_bab",
        "name": "Betting against beta",
        "source": "AQR — Frazzini & Pedersen (2014) 'Betting Against Beta', Journal of Financial Economics",
        "family": "Equity factors",
        "summary": "Long low-beta stocks levered to beta 1, short high-beta stocks de-levered to beta 1: market-neutral, "
                   "monthly.",
        "evidence": "Leverage-constrained investors bid up high-beta stocks, so low-beta stocks earn higher risk-adjusted "
                    "returns in 19 of 20 countries (BAB Sharpe ≈ 0.78 in US equities 1926–2012). Shrunk betas reduce "
                    "noise. Expect long flat spells (2016–2020).",
        "code": f'''UNIVERSE = {MEGACAPS}
START = "2008-01-01"
PARAMS = {{"lookback": [252, 504]}}


def strategy(data, lookback=252):
    px = data.close
    r = px.pct_change()
    m = r.mean(axis=1)                                   # equal-weight market of the universe
    beta = r.rolling(lookback, min_periods=200).cov(m).div(m.rolling(lookback, min_periods=200).var(), axis=0)
    beta = 0.6 * beta + 0.4                               # Vasicek shrinkage toward 1 (FP 2014)
    rk = beta.rank(axis=1, pct=True)
    lo = (rk <= 0.3).astype(float)
    hi = (rk >= 0.7).astype(float)
    lo = lo.div(lo.sum(axis=1), axis=0)
    hi = hi.div(hi.sum(axis=1), axis=0)
    blo = (lo * beta).sum(axis=1)
    bhi = (hi * beta).sum(axis=1)
    w = lo.div(blo, axis=0) - hi.div(bhi, axis=0)          # each side scaled to beta 1
    return hold_monthly(w.fillna(0) * 0.5)
''',
    },
    {
        "id": "sector_momentum",
        "name": "Sector momentum with crash protection",
        "source": "Moskowitz & Grinblatt (1999); Daniel & Moskowitz (2016) 'Momentum Crashes'; Barroso & Santa-Clara (2015)",
        "family": "Equity factors",
        "summary": "Hold the 3 US sectors with the best 12-1-month momentum, scaled down when the strategy's own "
                   "volatility is high.",
        "evidence": "Industry momentum explains much of stock momentum. Momentum's crashes follow bear-market rebounds and "
                    "are forecastable from its own volatility — scaling by it nearly doubled momentum's Sharpe "
                    "(Barroso & Santa-Clara 2015).",
        "code": '''UNIVERSE = ["XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY"]
START = "2005-01-01"
PARAMS = {"n": [2, 3, 4]}


def strategy(data, n=3):
    px = data.close
    mom = momentum(px, 252, 21)
    pick = (mom.rank(axis=1, ascending=False) <= n).astype(float)
    w = normalize_gross(pick)
    w = vol_target(w, px, 0.15, lookback=126, max_leverage=1.0)     # crash protection: only scale down
    return hold_monthly(w)
''',
    },
    {
        "id": "turn_of_month",
        "name": "Turn-of-the-month equities",
        "source": "Lakonishok & Smidt (1988); McConnell & Xu (2008) 'Equity Returns at the Turn of the Month'",
        "family": "Calendar",
        "summary": "Hold the S&P 500 from the last trading day of each month through the third trading day of the next; "
                   "T-bills otherwise.",
        "evidence": "Over 1926–2005 essentially all of the US equity premium was earned in the 4-day turn-of-month window "
                    "(McConnell & Xu 2008), linked to month-end pension and payroll flows. In the market ~20% of the "
                    "time, so it trades 24 round trips a year — costs matter.",
        "code": '''UNIVERSE = ["SPY"]
START = "2005-01-01"
PARAMS = {"days_after": [3, 4]}


def strategy(data, days_after=3):
    idx = data.close.index
    s = pd.Series(np.arange(len(idx)), index=idx)
    month = idx.to_period("M")
    first = s.groupby(month).transform("min")
    last = s.groupby(month).transform("max")
    pos_in_month = s - first                              # 0 = first trading day
    # decided at close t, held on t+1: hold from the close before the last day through day `days_after`
    hold_next = (s == last - 1) | (s == last) | (pos_in_month < days_after - 1)
    return pd.DataFrame({"SPY": hold_next.astype(float)}, index=idx)
''',
    },
]


PORTFOLIO = {
    "id": "multi_strategy",
    "name": "Multi-strategy portfolio (the library combined)",
    "source": "How multi-manager and multi-strategy funds allocate — risk budgeting across uncorrelated return streams "
              "(AQR 'Portfolio Construction'; Bridgewater 'Holy Grail' of 15+ uncorrelated streams)",
    "family": "Portfolio",
    "summary": "Each month, allocate across the library's strategies in inverse proportion to their trailing 1-year "
               "volatility, keeping only those with a positive trailing 3-year Sharpe ratio; then size the whole "
               "book with the Monte Carlo's growth-optimal leverage.",
    "evidence": "Combining weakly correlated strategies raises the Sharpe ratio roughly with the square root of the number "
                "of independent bets — the cheapest source of extra return once each strategy is already net of costs. "
                "Uses each strategy's out-of-sample record, so no look-ahead; costs are those of the members (netting "
                "of offsetting trades across strategies, which would lower them, is ignored).",
    "code": None,
}


def _portfolio(members: List[Dict[str, Any]]) -> Dict[str, Any]:
    import numpy as np
    import pandas as pd
    from api.quant import codelab, codeserver
    rets = {}
    for m in members:
        if m.get("returns"):
            rets[m["id"]] = pd.Series(m["returns"], index=pd.to_datetime(m["dates"]))
    R = pd.DataFrame(rets).sort_index()
    vol = R.rolling(252, min_periods=126).std()
    sh = R.rolling(756, min_periods=252).mean() / R.rolling(756, min_periods=252).std()
    w = (1 / vol).where(sh > 0)
    w = w.div(w.sum(axis=1), axis=0)
    w = codelab.hold_monthly(w).shift(1)                      # decided at month-end, applied from the next day
    port = (w * R).sum(axis=1, min_count=1).dropna()
    port = port[w.reindex(port.index).sum(axis=1) > 0]
    dates = [d.strftime("%Y-%m-%d") for d in port.index]
    rf = codeserver.rf_for(dates)
    last = w.dropna(how="all").iloc[-1].dropna() if w.notna().any().any() else pd.Series(dtype=float)
    ev = {"metrics": codelab.metrics(port, rf), "metrics_gross": None, "costs": None,
          "optimisation": {"walk_forward": True, "members": list(R.columns), "oos_start": dates[0] if dates else None},
          "weights_last": {k: round(float(v), 4) for k, v in last.items() if v > 0},
          "dates": dates, "returns": [round(float(x), 7) for x in port.values]}
    spy = codeserver._index_series("SPY", dates[0])
    if spy is not None:
        b = spy.reindex(port.index).pct_change(fill_method=None).fillna(0.0)
        ev["benchmark"] = [round(float(x), 7) for x in b.values]
        ev["benchmark_metrics"] = codelab.metrics(b, rf)
    return ev


def get(sid: str) -> Dict[str, Any]:
    if sid == PORTFOLIO["id"]:
        return PORTFOLIO
    for s in LIBRARY:
        if s["id"] == sid:
            return s
    raise KeyError(sid)


def _path(sid: str) -> Path:
    return CACHE / f"{sid}.json"


def result(sid: str, force: bool = False) -> Dict[str, Any]:
    """Evaluated result (cached ~20h): backtest + optimisation + Monte Carlo + deep analysis."""
    from api.quant import codeserver
    p = _path(sid)
    if not force:
        try:
            if time.time() - p.stat().st_mtime < TTL:
                return json.loads(p.read_text())
        except Exception:
            pass
    s = get(sid)
    if sid == PORTFOLIO["id"]:
        ev = _portfolio([{**result(x["id"]), "id": x["id"]} for x in LIBRARY])
    else:
        ev = codeserver.evaluate_code(s["code"], trusted=True)
    an = codeserver.analyze(ev["dates"], ev["returns"], ev.get("benchmark"), label=s["name"])
    out = {"id": sid, "evaluated_at": time.strftime("%Y-%m-%d %H:%M"), **ev, **an}
    CACHE.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, default=str))
    return out


def summaries() -> List[Dict[str, Any]]:
    """Library cards with headline numbers where a result is cached."""
    out = []
    for s in [PORTFOLIO] + LIBRARY:
        card = {k: s[k] for k in ("id", "name", "source", "family", "summary", "evidence", "code")}
        try:
            r = json.loads(_path(s["id"]).read_text())
            mc = r.get("monte_carlo") or {}
            card["headline"] = {"metrics": r.get("metrics"), "gross": r.get("metrics_gross"), "costs": r.get("costs"),
                                "recommended_leverage": mc.get("recommended_leverage"), "cagr_p50": (mc.get("cagr_pct") or {}).get("50"),
                                "oos_start": (r.get("optimisation") or {}).get("oos_start"), "evaluated_at": r.get("evaluated_at")}
        except Exception:
            card["headline"] = None
        out.append(card)
    return out
