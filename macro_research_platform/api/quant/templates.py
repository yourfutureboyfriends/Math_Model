"""
Research-backed strategy templates for the Quant Lab. Each is an ordinary spec — open it,
change it, save it as your own. `evidence` says what the literature found and what to
watch for, so expectations are set before the backtest is run.
"""
from __future__ import annotations

from typing import Any, Dict, List

TEMPLATES: List[Dict[str, Any]] = [
    {
        "id": "house_multi_trend",
        "name": "House algo — multi-horizon trend, risk-balanced",
        "family": "Trend",
        "description": "The Quant Lab's flagship: time-series momentum on 13 liquid cross-asset ETFs, "
                       "1/3/12-month trend blend, inverse-volatility sized, 10% volatility target, monthly.",
        "evidence": "Trend following earned positive returns in every decade since 1880 across 67 markets, with "
                    "its best results in equity bear markets (Hurst, Ooi & Pedersen 2017). Blending horizons is more "
                    "robust than any single lookback. Weak stretches happen — 2010s CTAs lagged after 2008.",
        "citation": "Moskowitz, Ooi & Pedersen (2012); Hurst, Ooi & Pedersen (2017)",
        "spec": {"universe": {"preset": "cross_asset"},
                 "signal": "sign(mom(21)) + sign(mom(63)) + sign(mom(252))",
                 "selection": {"mode": "sign", "long_only": False},
                 "weighting": "inverse_vol",
                 "risk": {"vol_target": 0.10, "max_weight": 0.35, "max_gross": 2.0},
                 "rebalance": "monthly", "execution": "next_open", "costs": {"bps": 5, "borrow_bps": 50}},
    },
    {
        "id": "tsmom_long_only",
        "name": "Trend, long-only (stay in cash when falling)",
        "family": "Trend",
        "description": "Hold each cross-asset ETF only while its 12-month return is positive; equal slots, cash otherwise.",
        "evidence": "Absolute momentum cuts drawdowns sharply with a modest cost in bull markets; most of the "
                    "benefit comes from avoiding prolonged bear markets (Antonacci 2013; Faber 2007).",
        "citation": "Antonacci (2013); Faber (2007)",
        "spec": {"universe": {"preset": "cross_asset"}, "signal": "mom(252)",
                 "selection": {"mode": "threshold", "min_score": 0},
                 "weighting": "equal_universe", "rebalance": "monthly", "costs": {"bps": 5}},
    },
    {
        "id": "faber_gtaa5",
        "name": "Faber GTAA-5 — 10-month moving average timing",
        "family": "Trend",
        "description": "Five asset classes, 20% each, held only when above their 10-month (≈210-day) average.",
        "evidence": "Published in 2007 and re-tested out of sample 10 years later: Sharpe improved from 0.45 (buy & hold) "
                    "to about 0.80 with equity-like returns at bond-like drawdowns (Faber 2018 update).",
        "citation": "Faber (2007, 2018)",
        "spec": {"universe": {"preset": "gtaa5"}, "signal": "close / sma(close, 210) - 1",
                 "selection": {"mode": "threshold", "min_score": 0},
                 "weighting": "equal_universe", "rebalance": "monthly", "costs": {"bps": 5}},
    },
    {
        "id": "dual_momentum_gem",
        "name": "Dual momentum (Global Equity Momentum)",
        "family": "Momentum",
        "description": "Hold the stronger of US or international equities over 12 months — but only if its return is "
                       "positive; otherwise hold Treasuries (IEF).",
        "evidence": "Combining relative and absolute momentum kept equity-like returns while avoiding most of the "
                    "2000–02 and 2008 bear markets (Antonacci 2013). One switch a year on average; very low turnover.",
        "citation": "Antonacci (2013)",
        "spec": {"universe": {"preset": "gem"}, "signal": "mom(252)",
                 "selection": {"mode": "top_n", "n": 1, "min_score": 0}, "weighting": "equal",
                 "fallback": "IEF", "rebalance": "monthly", "costs": {"bps": 5}},
    },
    {
        "id": "sector_rotation",
        "name": "Sector momentum with market filter",
        "family": "Momentum",
        "description": "Top 3 US sectors by 12-1-month momentum, equal weight; to cash when SPY is below its 200-day average.",
        "evidence": "Industry momentum explains much of stock momentum (Moskowitz & Grinblatt 1999). The market filter "
                    "avoids momentum crashes, which cluster after bear-market rebounds (Daniel & Moskowitz 2016).",
        "citation": "Moskowitz & Grinblatt (1999); Daniel & Moskowitz (2016)",
        "spec": {"universe": {"preset": "us_sectors"}, "signal": "mom(252, 21)", "filter": "mkt > sma(mkt, 200)",
                 "selection": {"mode": "top_n", "n": 3}, "weighting": "equal", "rebalance": "monthly", "costs": {"bps": 5}},
    },
    {
        "id": "country_momentum",
        "name": "Country rotation — momentum",
        "family": "Momentum",
        "description": "Top 5 of 20 country ETFs by 12-1-month momentum, inverse-volatility weighted.",
        "evidence": "Country-index momentum is documented across decades (Richards 1997; Asness, Moskowitz & Pedersen 2013 "
                    "'Value and Momentum Everywhere'). Expect higher volatility than a world index.",
        "citation": "Asness, Moskowitz & Pedersen (2013)",
        "spec": {"universe": {"preset": "country_etfs"}, "signal": "mom(252, 21)",
                 "selection": {"mode": "top_n", "n": 5}, "weighting": "inverse_vol", "rebalance": "monthly", "costs": {"bps": 10}},
    },
    {
        "id": "xs_momentum_stocks",
        "name": "Stock momentum (12-1), top 10",
        "family": "Momentum",
        "description": "The 10 US large caps with the strongest 12-1-month momentum, equal weight, monthly.",
        "evidence": "The original momentum anomaly (Jegadeesh & Titman 1993), one of the most replicated. It suffers rare "
                    "but severe crashes (2009). On a survivorship-biased large-cap list, results are flattered.",
        "citation": "Jegadeesh & Titman (1993)",
        "spec": {"universe": {"preset": "us_megacaps"}, "signal": "mom(252, 21)",
                 "selection": {"mode": "top_n", "n": 10}, "weighting": "equal", "rebalance": "monthly", "costs": {"bps": 5}},
    },
    {
        "id": "low_vol_stocks",
        "name": "Low volatility stocks",
        "family": "Defensive",
        "description": "The least volatile 30% of the large-cap list (1-year), inverse-volatility weighted.",
        "evidence": "Low-risk stocks have earned similar or better returns than high-risk ones with much less risk "
                    "(Ang et al. 2006; Frazzini & Pedersen 2014 'Betting Against Beta'). Lags in strong bull markets.",
        "citation": "Ang, Hodrick, Xing & Zhang (2006); Frazzini & Pedersen (2014)",
        "spec": {"universe": {"preset": "us_megacaps"}, "signal": "-vol(252)",
                 "selection": {"mode": "top_pct", "pct": 0.3}, "weighting": "inverse_vol", "rebalance": "monthly", "costs": {"bps": 5}},
    },
    {
        "id": "momentum_low_vol_combo",
        "name": "Multi-factor: momentum + low volatility",
        "family": "Multi-factor",
        "description": "Rank stocks on momentum and on low volatility, add the ranks, hold the top 20%.",
        "evidence": "Combining lowly correlated factors raises the Sharpe of the mix above either alone "
                    "(Asness, Moskowitz & Pedersen 2013; Blitz & van Vliet 2018 'Conservative Formula').",
        "citation": "Blitz & van Vliet (2018)",
        "spec": {"universe": {"preset": "us_megacaps"}, "signal": "rank(mom(252, 21)) + rank(-vol(252))",
                 "selection": {"mode": "top_pct", "pct": 0.2}, "weighting": "equal", "rebalance": "monthly", "costs": {"bps": 5}},
    },
    {
        "id": "donchian_breakout",
        "name": "Donchian channel trend (Turtle-style)",
        "family": "Trend",
        "description": "Position by where price sits in its 100-day high–low channel: long in the top half, short in the bottom.",
        "evidence": "Breakout systems are another form of time-series momentum; results are close to moving-average "
                    "trend rules and share their crisis-alpha profile (Hurst et al. 2017).",
        "citation": "Donchian; Hurst, Ooi & Pedersen (2017)",
        "spec": {"universe": {"preset": "cross_asset"},
                 "signal": "(close - (highest(close, 100) + lowest(close, 100)) / 2) / (highest(close, 100) - lowest(close, 100))",
                 "selection": {"mode": "sign", "long_only": False}, "weighting": "inverse_vol",
                 "risk": {"vol_target": 0.10, "max_weight": 0.35, "max_gross": 2.0},
                 "rebalance": "weekly", "costs": {"bps": 5, "borrow_bps": 50}},
    },
    {
        "id": "rsi2_dip_buying",
        "name": "Short-term dip buying (RSI-2) in up-trends",
        "family": "Mean reversion",
        "description": "Buy sector ETFs that are deeply oversold (2-day RSI < 15) while above their 200-day average; "
                       "re-checked daily.",
        "evidence": "Short-term reversal is real before costs, but many studies find profits largely vanish after "
                    "trading costs; it survives mainly in liquid large caps and ETFs. Use the cost-sensitivity test.",
        "citation": "Connors & Alvarez (2009); de Groot, Huij & Zhou (2012)",
        "spec": {"universe": {"preset": "us_sectors"}, "signal": "where((rsi(2) < 15) & (close > sma(close, 200)), 15 - rsi(2), nan)",
                 "selection": {"mode": "threshold", "min_score": 0}, "weighting": "equal_universe",
                 "rebalance": "daily", "execution": "next_close", "costs": {"bps": 3}},
    },
    {
        "id": "vol_managed_spy",
        "name": "Volatility-managed S&P 500",
        "family": "Defensive",
        "description": "Hold SPY, scaled to a 12% volatility target (up to 1.5× leverage).",
        "evidence": "Moreira & Muir (2017) found volatility timing raises the Sharpe of equity factors, but Cederburg et al. "
                    "(2020) show real-time versions underperform in 72 of 103 strategies. The report compares with and "
                    "without the target so you can see which holds here.",
        "citation": "Moreira & Muir (2017); Cederburg, O'Doherty, Wang & Yan (2020)",
        "spec": {"universe": {"symbols": ["SPY"]}, "signal": "close / close",
                 "selection": {"mode": "threshold", "min_score": 0}, "weighting": "equal",
                 "risk": {"vol_target": 0.12, "max_weight": 1.0, "max_gross": 1.5, "vol_lookback": 21},
                 "rebalance": "weekly", "costs": {"bps": 2}},
    },
    {
        "id": "risk_parity_all_weather",
        "name": "Risk parity (inverse volatility), all-weather mix",
        "family": "Defensive",
        "description": "Stocks, long bonds, TIPS, gold and commodities, each sized to contribute similar risk; monthly.",
        "evidence": "Balancing risk instead of capital produced higher risk-adjusted returns than 60/40 historically "
                    "(Asness, Frazzini & Pedersen 2012), with the big caveat of the 2022 stock–bond sell-off.",
        "citation": "Asness, Frazzini & Pedersen (2012); Maillard, Roncalli & Teiletche (2010)",
        "spec": {"universe": {"symbols": ["SPY", "TLT", "TIP", "GLD", "DBC"]}, "signal": "close / close",
                 "selection": {"mode": "threshold", "min_score": 0}, "weighting": "inverse_vol",
                 "rebalance": "monthly", "costs": {"bps": 5}},
    },
]

RESEARCH_NOTES: List[Dict[str, str]] = [
    {"title": "What makes a systematic strategy work",
     "text": "Durable strategies earn a risk premium or exploit a behavioural bias that persists (trend: slow "
             "reaction to news; momentum: under- then over-reaction; low-vol: leverage constraints). An edge without an "
             "economic reason is usually a data-mining artefact."},
    {"title": "Most backtests are too good",
     "text": "Trying many variants and keeping the best inflates results. Harvey, Liu & Zhu (2016) argue a new "
             "strategy needs t > 3, not t > 2; the Deflated Sharpe Ratio and PBO in every report correct for the number "
             "of variants you tried. Published anomalies lose about half their return after publication (McLean & Pontiff 2016)."},
    {"title": "Costs decide short-horizon strategies",
     "text": "Turnover × cost per trade is subtracted from every return. Fast mean-reversion strategies often look "
             "great gross and break even net — check the cost-sensitivity row and the one-day-delay test."},
    {"title": "Diversify across strategies, not just assets",
     "text": "Trend, momentum, low-volatility and carry have low correlation with each other. Combining them by equal "
             "risk usually beats any single model (see Combine). This is how multi-strategy funds are built."},
    {"title": "Volatility targeting is not free alpha",
     "text": "It reliably stabilises risk, but its Sharpe benefit is fragile out of sample (Cederburg et al. 2020). "
             "Every report shows the result with and without the target."},
    {"title": "From backtest to live",
     "text": "Deploy a strategy to the Quant Trader to paper-trade it from today with no hindsight; its live record is "
             "compared with the range the backtest implies, so you can see early if it is behaving out of character."},
]


def get(template_id: str) -> Dict[str, Any]:
    for t in TEMPLATES:
        if t["id"] == template_id:
            return {**t["spec"], "name": t["name"], "description": t["description"]}
    raise KeyError(template_id)
