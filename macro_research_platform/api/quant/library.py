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
from typing import Any, Dict, List

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
    {
        "id": "rentech_statarb",
        "name": "Short-horizon statistical arbitrage (Medallion-style)",
        "source": "Renaissance Technologies as described in Zuckerman (2019) 'The Man Who Solved the Market'; "
                  "Avellaneda & Lee (2010); Blitz, Huij, Lansdorp & Verbeek (2013) 'Short-Term Residual Reversal'",
        "family": "Stat arb",
        "summary": "Market-neutral bets that each stock's market-hedged move of the last few days partly reverses: long the "
                   "biggest residual losers, short the biggest residual winners, scaled by each stock's residual volatility.",
        "evidence": "Medallion's core, by every public account, is thousands of small, short-holding, market-neutral "
                    "statistical bets — right only slightly more often than wrong, levered and diversified. Residual "
                    "reversal is the best-documented public version. Renaissance does it intraday across thousands of "
                    "instruments with its own execution; on 50 large caps with daily bars and full costs the edge is a "
                    "small fraction of that — the cost line shows why speed and execution are the real moat.",
        "code": f"""UNIVERSE = {MEGACAPS}
START = "2008-01-01"
PARAMS = {{"horizon": [3, 5, 10], "n": [8, 12]}}


def strategy(data, horizon=5, n=10):
    px = data.close
    r = px.pct_change()
    mkt = r.mean(axis=1)
    beta = r.rolling(126, min_periods=100).cov(mkt).div(mkt.rolling(126, min_periods=100).var(), axis=0).shift(1)
    resid = r - beta.mul(mkt, axis=0)                              # market-hedged daily return
    score = -resid.rolling(horizon).sum() / resid.rolling(63, min_periods=40).std()
    rk = score.rank(axis=1)
    k = rk.count(axis=1)
    longs = rk.gt(k - n, axis=0).astype(float)
    shorts = (rk <= n).astype(float)
    w = 0.5 * longs.div(longs.sum(axis=1), axis=0) - 0.5 * shorts.div(shorts.sum(axis=1), axis=0)
    return hold_weekly(w.fillna(0))
""",
    },
    {
        "id": "janestreet_etf_rv",
        "name": "ETF relative value (Jane Street-style)",
        "source": "Jane Street — ETF market making and arbitrage (public descriptions of its business); Gatev, Goetzmann & "
                  "Rouwenhorst (2006) 'Pairs Trading'; Engle & Granger (1987)",
        "family": "Stat arb",
        "summary": "Pairs of economically linked ETFs (resource-exporter countries, gold vs miners, energy majors vs "
                   "producers, Asian chip exporters, two high-yield trackers): trade the spread back to its rolling "
                   "equilibrium when it stretches, exit when it closes.",
        "evidence": "Jane Street's best-known business is keeping ETFs in line with their baskets and with each other. The "
                    "intraday NAV arbitrage needs authorised-participant status and real-time data; the daily, public "
                    "version is relative value between closely linked ETFs. Pairs profits are well documented but have "
                    "decayed as the trade became crowded (Do & Faff 2010).",
        "code": """UNIVERSE = ["EWA", "EWC", "EWT", "EWY", "GDX", "GLD", "XLE", "XOP", "HYG", "JNK"]
START = "2008-01-01"
PAIRS = [("EWA", "EWC"), ("EWT", "EWY"), ("GDX", "GLD"), ("XLE", "XOP"), ("HYG", "JNK")]
PARAMS = {"entry": [1.5, 2.0], "lookback": [126, 252]}


def strategy(data, entry=2.0, lookback=252):
    lp = np.log(data.close)
    w = pd.DataFrame(0.0, index=lp.index, columns=lp.columns)
    for a, b in PAIRS:
        y, x = lp[a], lp[b]
        beta = y.rolling(lookback).cov(x) / x.rolling(lookback).var()
        spread = y - beta * x
        z = (spread - spread.rolling(lookback).mean()) / spread.rolling(lookback).std()
        pos = np.zeros(len(z))
        state = 0.0
        for i, zi in enumerate(z.to_numpy()):
            if np.isnan(zi):
                state = 0.0
            elif state == 0 and abs(zi) > entry:
                state = -np.sign(zi)                              # short a stretched spread, long a compressed one
            elif state != 0 and (abs(zi) < 0.5 or abs(zi) > 4):
                state = 0.0                                       # converged, or the pair broke: get out
            pos[i] = state
        bet = pd.Series(pos, index=z.index)
        gross = 1 + beta.abs()
        w[a] += bet / gross / len(PAIRS)
        w[b] -= bet * beta / gross / len(PAIRS)
    return w.fillna(0)
""",
    },
    {
        "id": "cboe_putwrite",
        "name": "Cash-secured put writing (CBOE PutWrite)",
        "source": "CBOE S&P 500 PutWrite Index (PUT); Ungar & Moran (2009) 'The Cash-Secured PutWrite Strategy'",
        "family": "Options",
        "summary": "Each monthly expiry, sell one-month at-the-money S&P 500 (SPY) puts on 100% of NAV; the cash stays "
                   "in T-bills as collateral.",
        "evidence": "Index options are priced above the volatility that follows (the volatility risk premium): PUT has "
                    "matched the S&P 500's return since 1986 with about two-thirds of its volatility, but loses like the "
                    "market in crashes. Synthetic options (Black–Scholes on the VIX term structure) — the model tracks "
                    "CBOE's real PUT index with a 0.96 monthly correlation.",
        "code": '''UNIVERSE = ["SPY"]
START = "2008-01-02"
OPTIONS = [{"underlying": "SPY", "type": "put", "moneyness": 1.0}]
# Option weights are underlying notional: -1.0 = write puts on 100% of NAV.


def strategy(data):
    w = data.close * 0
    w["SPY_P100_1M"] = -1.0
    return on_rolls(w, data, "SPY_P100_1M")
''',
    },
    {
        "id": "cboe_buywrite",
        "name": "Covered calls (CBOE BuyWrite)",
        "source": "CBOE S&P 500 BuyWrite Index (BXM); Whaley (2002); Israelov & Nielsen (AQR, 2014) 'Covered Call "
                  "Strategies: One Fact and Eight Myths'",
        "family": "Options",
        "summary": "Hold the S&P 500 (SPY) and sell one-month at-the-money calls on it at each monthly expiry.",
        "evidence": "Trades the upside for the call premium: lower volatility than the index, similar long-run return "
                    "over 1986–2020. AQR shows the return is the equity premium plus a short-volatility premium — and "
                    "an unintended short on equity momentum.",
        "code": '''UNIVERSE = ["SPY"]
START = "2008-01-02"
OPTIONS = [{"underlying": "SPY", "type": "call", "moneyness": 1.0}]


def strategy(data):
    w = data.close * 0
    w["SPY"] = 1.0
    w["SPY_C100_1M"] = -1.0
    return on_rolls(w, data, "SPY_C100_1M")
''',
    },
    {
        "id": "cboe_collar",
        "name": "Protective collar (CBOE CLL)",
        "source": "CBOE S&P 500 95-110 Collar Index (CLL); Szado & Schneeweis (2010) 'Loosening Your Collar'",
        "family": "Options",
        "summary": "Hold the S&P 500, buy three-month 5% out-of-the-money puts each quarter and finance them by selling "
                   "one-month 10% out-of-the-money calls each month.",
        "evidence": "The textbook hedge: the puts cap crash losses (2008, 2020), the calls pay for most of them. Costs "
                    "show what insurance takes from long-run return.",
        "code": '''UNIVERSE = ["SPY"]
START = "2008-01-02"
OPTIONS = [{"underlying": "SPY", "type": "put", "moneyness": 0.95, "expiry": "quarterly"},
           {"underlying": "SPY", "type": "call", "moneyness": 1.10}]


def strategy(data):
    w = data.close * 0
    w["SPY"] = 1.0
    w["SPY_P95_Q"] = 1.0
    w["SPY_C110_1M"] = -1.0
    roll = data.opt["roll"].any(axis=1)
    return w.where(roll, np.nan, axis=0)
''',
    },
    {
        "id": "index_put_spreads",
        "name": "Index put credit spreads",
        "source": "AQR (2018) 'Understanding the Volatility Risk Premium'; Israelov & Nielsen (2014); OCC bull put spread",
        "family": "Options",
        "summary": "On S&P 500, Nasdaq-100 and Dow ETFs, sell a 20-delta put and buy a 7-delta put at each monthly expiry "
                   "when implied volatility is at least 1.15× realised; risk 0.5% of NAV per spread (5% in total), take "
                   "profit at half the credit, stop at twice it, close 10 days before expiry.",
        "evidence": "Defined-risk harvesting of the index volatility premium: the long wing caps the crash loss that sinks "
                    "naked put writers. Credit and maximum loss come from modelled (VIX-family) option prices, so results "
                    "are indicative; real fills at quoted bid/ask matter more for spreads than for single options.",
        "code": '''UNIVERSE = ["SPY", "QQQ", "DIA"]
START = "2010-01-04"
# Bull put (credit) spreads on index ETFs whose implied volatility comes from a CBOE index (VIX, VXN, VXD):
# short a 20-delta put, long a 7-delta put, monthly expiry. Option weights are underlying notional.
OPTIONS = [
    {"underlying": "SPY", "type": "put", "delta": 0.2, "name": "SPY_PSHORT"}, {"underlying": "SPY", "type": "put", "delta": 0.07, "name": "SPY_PWING"}, {"underlying": "SPY", "type": "put", "delta": 0.5, "name": "SPY_PATM"},
    {"underlying": "QQQ", "type": "put", "delta": 0.2, "name": "QQQ_PSHORT"}, {"underlying": "QQQ", "type": "put", "delta": 0.07, "name": "QQQ_PWING"}, {"underlying": "QQQ", "type": "put", "delta": 0.5, "name": "QQQ_PATM"},
    {"underlying": "DIA", "type": "put", "delta": 0.2, "name": "DIA_PSHORT"}, {"underlying": "DIA", "type": "put", "delta": 0.07, "name": "DIA_PWING"}, {"underlying": "DIA", "type": "put", "delta": 0.5, "name": "DIA_PATM"},
]


def strategy(data, risk_per_trade=0.005, portfolio_risk_cap=0.05, profit_take=0.50, stop_multiple=2.0,
             close_dte=10, iv_rv_hurdle=1.15, max_notional=1.0):
    idx = data.close.index
    names = [u for u in ("SPY", "QQQ", "DIA") if f"{u}_PSHORT" in data.close.columns]
    px, opt = data.close, data.opt
    rv = data.close[names].pct_change().rolling(21, min_periods=15).std() * np.sqrt(252)
    w = pd.DataFrame(np.nan, index=idx, columns=data.close.columns)
    cur = pd.Series(0.0, index=data.close.columns)
    state = {u: None for u in names}                  # open spread: notional and entry credit (per unit of spot)
    for t in range(len(idx)):
        changed = False
        for u in names:
            s, l, a = f"{u}_PSHORT", f"{u}_PWING", f"{u}_PATM"
            spot = opt["spot"][s].iloc[t]
            if not np.isfinite(spot):
                continue
            value = (px[s].iloc[t] - px[l].iloc[t]) / spot          # spread value per unit of spot
            st = state[u]
            if st is not None:                                        # manage: take profit, stop, or close early
                if (value <= (1 - profit_take) * st["credit"] or value >= stop_multiple * st["credit"]
                        or opt["dte"][s].iloc[t] <= close_dte or opt["roll"][s].iloc[t]):
                    cur[[s, l]] = 0.0
                    state[u] = None
                    changed = True
            if state[u] is None and opt["roll"][s].iloc[t]:           # a new contract was struck at this close
                iv, r = opt["iv"][a].iloc[t], rv[u].iloc[t]
                width = (opt["strike"][s].iloc[t] - opt["strike"][l].iloc[t]) / spot     # USD-listed: strike and spot in USD
                if np.isfinite(iv) and np.isfinite(r) and r > 0 and iv / r >= iv_rv_hurdle and value > 0 and width > value:
                    open_risk = sum(v["risk"] for v in state.values() if v)
                    risk = min(risk_per_trade, portfolio_risk_cap - open_risk)
                    if risk > 0:
                        n = min(risk / (width - value), max_notional)      # max loss = notional × (width − credit)
                        cur[s], cur[l] = -n, n
                        state[u] = {"credit": value, "risk": n * (width - value)}
                        changed = True
        if changed:
            w.iloc[t] = cur.values
    return w
''',
    },
    {
        "id": "delta_hedged_straddle",
        "name": "Delta-hedged short straddle (volatility risk premium)",
        "source": "Coval & Shumway (2001) 'Expected Option Returns'; Carr & Wu (2009) 'Variance Risk Premiums'; "
                  "Israelov & Nielsen (AQR, 2015)",
        "family": "Options",
        "summary": "Sell one-month at-the-money S&P 500 straddles on 50% of NAV at each expiry and hedge their delta "
                   "with SPY every day, so what remains is implied minus realised volatility.",
        "evidence": "Index implied volatility has exceeded subsequent realised volatility in most months since 1990 "
                    "(VIX ≈ 19 vs realised ≈ 15 on average); delta-hedged option sellers earn the gap and lose sharply "
                    "in volatility spikes. Daily hedging costs are charged.",
        "code": '''UNIVERSE = ["SPY"]
START = "2008-01-02"
OPTIONS = [{"underlying": "SPY", "type": "put", "moneyness": 1.0}, {"underlying": "SPY", "type": "call", "moneyness": 1.0}]
PARAMS = {"notional": [0.5]}


def strategy(data, notional=0.5):
    d = data.opt["delta"].fillna(0.0)
    w = pd.DataFrame(0.0, index=data.close.index, columns=data.close.columns)
    w["SPY_P100_1M"] = -notional
    w["SPY_C100_1M"] = -notional
    # short options have delta -notional × (Δput + Δcall); holding that much SPY neutralises it
    w["SPY"] = notional * (d["SPY_P100_1M"] + d["SPY_C100_1M"])
    return w
''',
    },
]

SMART_MONEY: List[Dict[str, Any]] = [
    {"id": "sm_consensus", "kind": "13f", "param": "consensus", "family": "13F institutions", "code": None,
     "name": "Hedge-fund consensus (Goldman 'VIP'-style)",
     "source": "Goldman Sachs Hedge Fund VIP basket; SEC 13F filings of Berkshire, Viking, Lone Pine, Coatue, Tiger, Baupost, "
               "Appaloosa, Pershing Square, Third Point, Duquesne, Elliott, Soros",
     "summary": "The 20 stocks that appear most often among the top-10 holdings of 12 concentrated fundamental hedge funds, "
                "equal weight, updated monthly using only filings already public (13F arrives up to 45 days after quarter end).",
     "evidence": "Goldman's VIP basket (top-10 holdings of fundamental funds) beat the S&P 500 in ~60% of quarters since 2001, "
                 "by ~52 bp a quarter on average, with higher volatility and crowding risk (it fell hard when crowded "
                 "longs unwound, e.g. 2016 and 2022). Long-only and growth-heavy."},
    {"id": "sm_best_ideas", "kind": "13f", "param": "best_ideas", "family": "13F institutions", "code": None,
     "name": "Best ideas of top fundamental funds",
     "source": "Cohen, Polk & Silli (2010) 'Best Ideas'; SEC 13F filings of 12 concentrated hedge funds",
     "summary": "Each fund's two highest-conviction holdings — the positions it overweights most relative to the other funds — "
                "pooled and equal-weighted, updated as filings become public.",
     "evidence": "Managers' best ideas beat the market by ~2.8–4.5% a year in Cohen, Polk & Silli; the rest of their "
                 "portfolios showed no skill. Concentrated, so expect large tracking error against the S&P 500."},
    {"id": "sm_quant_adds", "kind": "13f", "param": "quant_adds", "family": "13F institutions", "code": None,
     "name": "Follow the quant giants' buying",
     "source": "SEC 13F filings of Renaissance, Two Sigma, D. E. Shaw, AQR, Citadel, Millennium and Point72",
     "summary": "The 20 stocks whose weight rose most across the quant and multi-manager firms' disclosed top holdings last "
                "quarter, equal weight, from the day the filings are public.",
     "evidence": "A test, not a recommendation: these firms hold positions for days to weeks, so a quarter-end snapshot "
                 "published 45 days later mostly describes trades already closed. If this tracks the market with no "
                 "edge, the data are telling you exactly that."},
    {"id": "sm_rentech", "kind": "13f", "param": "rentech", "family": "13F institutions", "code": None,
     "name": "Renaissance disclosed holdings clone",
     "source": "SEC 13F filings of Renaissance Technologies LLC (largely its institutional long funds, RIEF/RIDA — "
               "not Medallion)",
     "summary": "Renaissance's 20 largest disclosed long positions, weighted as it weights them, updated when each filing is public.",
     "evidence": "Renaissance's 13F reflects its long-only and long-biased institutional funds, which hold for months "
                 "rather than days, so the clone is a meaningful test of copying them with a 45-day lag. Medallion's "
                 "book is not observable."},
]

MULTI_MANAGER = {
    "id": "multi_manager",
    "name": "Multi-manager platform (Millennium risk rules, Citadel-style hedging)",
    "source": "Millennium Management's pod model as widely reported (capital halved at a 5% drawdown, pod closed at 7.5%); "
              "Citadel's market-neutral pods targeting pure alpha; Two Sigma/AQR risk budgeting",
    "family": "Portfolio",
    "summary": "Every library strategy is a 'pod': its market beta is hedged out daily with SPY (Citadel-style), it is scaled "
               "to 6% volatility and given an equal risk budget. A pod down 5% from its peak has its capital halved; down 7.5% it is shut and a new pod "
               "running the same strategy is hired six months later (Millennium rules).",
    "evidence": "Multi-managers earn steady returns not from any single pod but from many uncorrelated, beta-neutral books "
                "with hard loss limits that stop small losses becoming large ones; they then lever the low-volatility "
                "whole. The table shows each layer separately — and the hard lesson in it: once market beta is hedged "
                "out, most public strategies have little alpha left, which is why these firms pay so much for "
                "portfolio managers who do. Funding only pods with a good recent record made it worse here: track records "
                "persist weakly (as hedge-fund research finds).",
    "code": None,
}


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
    w = codelab.hold_monthly(w).ffill().shift(1)              # decided on the month's first day, applied from the next
    port = (w * R).sum(axis=1, min_count=1).dropna()
    port = port[w.reindex(port.index).sum(axis=1) > 0]
    dates = [d.strftime("%Y-%m-%d") for d in port.index]
    rf = codeserver.rf_for(dates)
    last = w.dropna(how="all").iloc[-1].dropna() if w.notna().any().any() else pd.Series(dtype=float)
    ev = {"metrics": codelab.metrics(port, rf), "metrics_gross": None, "costs": None,
          "optimisation": {"walk_forward": True, "members": list(R.columns), "oos_start": dates[0] if dates else None},
          "weights_last": {k: round(float(v), 4) for k, v in last.items() if v > 0},
          "provenance": {"engine_version": codelab.ENGINE_VERSION, "record_type": "combination of the members' out-of-sample "
                         "return streams (allocation decided monthly from past data only)"},
          "dates": dates, "returns": [round(float(x), 7) for x in port.values]}
    spy = codeserver._index_series("SPY", dates[0])
    if spy is not None:
        b = spy.reindex(port.index).pct_change(fill_method=None).fillna(0.0)
        ev["benchmark"] = [round(float(x), 7) for x in b.values]
        ev["benchmark_metrics"] = codelab.metrics(b, rf)
    return ev


def _pods(members: List[Dict[str, Any]], hedge: bool, rules: bool, pod_vol: float = 0.06,
          cut: float = 0.05, stop: float = 0.075, rehire_days: int = 126, select: bool = False):
    """Book returns of a multi-manager platform built from strategy return streams (see MULTI_MANAGER)."""
    import numpy as np
    import pandas as pd
    from api.quant import codeserver
    R = pd.DataFrame({m["id"]: pd.Series(m["returns"], index=pd.to_datetime(m["dates"])) for m in members if m.get("returns")}).sort_index()
    spy = codeserver._index_series("SPY", R.index[0].strftime("%Y-%m-%d"))
    rf = codeserver.rf_for([d.strftime("%Y-%m-%d") for d in R.index])
    # Work in returns above T-bills: a futures hedge removes the market's *excess* return, and scaling a pod
    # scales its risk premium, not the cash rate. The cash rate is added back once, at the book level.
    R = R.sub(rf, axis=0)
    s_r = spy.reindex(R.index).pct_change(fill_method=None).fillna(0.0) - rf
    if hedge:
        beta = R.rolling(126, min_periods=63).cov(s_r).div(s_r.rolling(126, min_periods=63).var(), axis=0).shift(1).fillna(0.0)
        hedge_cost = beta.diff().abs().fillna(0.0) * 0.5e-4                 # ~0.5 bp per unit of SPY traded
        R = R - beta.mul(s_r, axis=0) - hedge_cost
    vol = R.rolling(63, min_periods=40).std().shift(1) * np.sqrt(252)
    pods = (R * (pod_vol / vol).clip(upper=4.0)).where(R.notna() & vol.notna())
    if select:
        # capital only for pods with a positive (hedged) track record over the past two years — how platforms
        # allocate to and hire portfolio managers; decided with data up to the previous day
        record = R.rolling(504, min_periods=252).mean().shift(1)
        pods = pods.where(record > 0)
    T, N = pods.shape
    P = pods.to_numpy()
    alloc = np.zeros((T, N))
    state = np.ones(N)                                                      # 1 full, 0.5 halved, 0 closed
    eq, hwm = np.ones(N), np.ones(N)
    closed_at = np.full(N, -10**9)
    events = []
    for t in range(T):
        for j in range(N):
            if not np.isfinite(P[t, j]):
                continue
            if state[j] == 0 and t - closed_at[j] >= rehire_days:
                state[j], eq[j], hwm[j] = 1.0, 1.0, 1.0                      # new PM, fresh high-water mark
                events.append({"date": str(pods.index[t].date()), "pod": pods.columns[j], "event": "re-hired"})
            alloc[t, j] = state[j]
            if state[j] > 0:
                eq[j] *= 1 + state[j] * P[t, j]
                hwm[j] = max(hwm[j], eq[j])
                dd = eq[j] / hwm[j] - 1
                if rules and dd <= -stop:
                    state[j], closed_at[j] = 0.0, t
                    events.append({"date": str(pods.index[t].date()), "pod": pods.columns[j], "event": f"closed at {dd:.1%}"})
                elif rules and dd <= -cut and state[j] == 1.0:
                    state[j] = 0.5
                    events.append({"date": str(pods.index[t].date()), "pod": pods.columns[j], "event": f"capital halved at {dd:.1%}"})
                elif state[j] == 0.5 and dd >= 0:
                    state[j] = 1.0
    A = pd.DataFrame(alloc, index=pods.index, columns=pods.columns).where(pods.notna(), 0.0)
    live = pods.notna().sum(axis=1).replace(0, np.nan)
    book = ((A * pods.fillna(0.0)).sum(axis=1) / live).dropna()            # equal risk budget per live pod
    book = book + rf.reindex(book.index).fillna(0.0)                        # capital earns T-bills
    alive = pods.notna().any() if not select else pods.iloc[-63:].notna().any()
    end_state = pd.Series(state, index=pods.columns).where(alive, 0.0)
    share = end_state / end_state.sum() if end_state.sum() > 0 else end_state
    return book, events, share


def _multi_manager(members: List[Dict[str, Any]]) -> Dict[str, Any]:
    from api.quant import codelab, codeserver
    labels = {"equal_risk": "Equal-risk pods, no hedge, no stops", "hedged": "+ daily beta hedge (Citadel-style)",
              "hedged_rules": "+ drawdown rules (Millennium) - the record shown",
              "hedged_rules_select": "+ fund only pods with a positive 2-year record (track-record chasing)"}
    variants = {k: _pods(members, h, r, select=sel) for k, h, r, sel in (
        ("equal_risk", False, False, False), ("hedged", True, False, False), ("hedged_rules", True, True, False),
        ("hedged_rules_select", True, True, True))}
    book, events, last = variants["hedged_rules"]
    dates = [d.strftime("%Y-%m-%d") for d in book.index]
    rf = codeserver.rf_for(dates)
    out = {"metrics": codelab.metrics(book, rf), "metrics_gross": None, "costs": None,
           "optimisation": {"walk_forward": True, "members": [m["id"] for m in members], "oos_start": dates[0] if dates else None,
                            "variants": [{"label": labels[k], **codelab.metrics(v[0].reindex(book.index).fillna(0.0), rf)} for k, v in variants.items()],
                            "events": events[-40:], "n_events": len(events)},
           "weights_last": {k: float(v) for k, v in (last.items() if last is not None else []) if v > 0},
           "provenance": {"engine_version": codelab.ENGINE_VERSION, "record_type": "multi-manager simulation over the "
                          "members' out-of-sample return streams (pod rules applied causally)"},
           "dates": dates, "returns": [round(float(x), 7) for x in book.values]}
    spy = codeserver._index_series("SPY", dates[0])
    if spy is not None:
        bm = spy.reindex(book.index).pct_change(fill_method=None).fillna(0.0)
        out["benchmark"] = [round(float(x), 7) for x in bm.values]
        out["benchmark_metrics"] = codelab.metrics(bm, rf)
    return out


def all_entries() -> List[Dict[str, Any]]:
    return [MULTI_MANAGER, PORTFOLIO] + LIBRARY + SMART_MONEY


def get(sid: str) -> Dict[str, Any]:
    for s in [MULTI_MANAGER, PORTFOLIO] + SMART_MONEY:
        if s["id"] == sid:
            return s
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
    elif sid == MULTI_MANAGER["id"]:
        ev = _multi_manager([{**result(x["id"]), "id": x["id"]} for x in LIBRARY + SMART_MONEY])
    elif s.get("kind") == "13f":
        from api.quant import smartmoney
        ev = smartmoney.evaluate(s["param"])
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
    for s in all_entries():
        card = {k: s.get(k) for k in ("id", "name", "source", "family", "summary", "evidence", "code")}
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
