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
        "id": "week52_high_stocks",
        "name": "52-week-high momentum",
        "family": "Momentum",
        "description": "Hold the 10 large caps trading closest to their 52-week high, equal weight, monthly.",
        "evidence": "Nearness to the 52-week high predicts returns and explains much of momentum's profit, with "
                    "fewer reversals than classic 12-1 momentum (George & Hwang 2004) — investors anchor on the high.",
        "citation": "George & Hwang (2004)",
        "spec": {"universe": {"preset": "us_megacaps"}, "signal": "drawdown(252)",
                 "selection": {"mode": "top_n", "n": 10}, "weighting": "equal", "rebalance": "monthly", "costs": {"bps": 5}},
    },
    {
        "id": "short_term_reversal_stocks",
        "name": "Short-term reversal (1-month losers)",
        "family": "Mean reversion",
        "description": "Buy the 20% of large caps that fell most over the last month, rebalanced weekly.",
        "evidence": "Last month's losers tend to bounce (Jegadeesh 1990; Lehmann 1990) — a liquidity-provision premium. "
                    "Strong before costs, much weaker after: check the cost-sensitivity test before trusting it.",
        "citation": "Jegadeesh (1990); Lehmann (1990)",
        "spec": {"universe": {"preset": "us_megacaps"}, "signal": "-mom(21)",
                 "selection": {"mode": "top_pct", "pct": 0.2}, "weighting": "equal", "rebalance": "weekly", "costs": {"bps": 5}},
    },
    {
        "id": "rsi2_pullback_stocks",
        "name": "Stock pullbacks in up-trends (RSI-2)",
        "family": "Mean reversion",
        "description": "Buy large caps that are deeply oversold over two days (RSI-2 < 10) while above their 200-day average; daily.",
        "evidence": "Buying short, sharp pullbacks inside long-term up-trends exploits short-term reversal while the trend "
                    "filter avoids falling knives (Connors & Alvarez 2009). Turnover is high — costs decide the result.",
        "citation": "Connors & Alvarez (2009)",
        "spec": {"universe": {"preset": "us_megacaps"}, "signal": "where((rsi(2) < 10) & (close > sma(close, 200)), 10 - rsi(2), nan)",
                 "selection": {"mode": "threshold", "min_score": 0}, "weighting": "equal_universe",
                 "rebalance": "daily", "execution": "next_close", "costs": {"bps": 5}},
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
        "id": "value_earnings_yield",
        "name": "Value — cheapest by earnings yield (point-in-time)",
        "family": "Value & quality",
        "description": "The 20% of large caps with the highest earnings yield (EPS ÷ price), from SEC filings as first "
                       "filed — each figure is used only from the day after it became public.",
        "evidence": "Cheap stocks have out-earned expensive ones over the long run (Basu 1977; Fama & French 1992), but "
                    "value had a long drought after 2007. Point-in-time data avoids the look-ahead that flatters most "
                    "value backtests (using earnings before they were reported).",
        "citation": "Basu (1977); Fama & French (1992)",
        "spec": {"universe": {"preset": "us_megacaps"}, "signal": "earnings_yield",
                 "selection": {"mode": "top_pct", "pct": 0.2}, "weighting": "equal", "rebalance": "monthly",
                 "costs": {"bps": 5}, "start": "2011-01-01"},
    },
    {
        "id": "quality_gross_profitability",
        "name": "Quality — gross profitability (point-in-time)",
        "family": "Value & quality",
        "description": "The 20% of large caps with the highest gross profit ÷ total assets.",
        "evidence": "Gross profitability predicts returns about as well as value, and the two are negatively correlated, "
                    "so they combine well (Novy-Marx 2013 'The Other Side of Value').",
        "citation": "Novy-Marx (2013)",
        "spec": {"universe": {"preset": "us_megacaps"}, "signal": "gross_profitability",
                 "selection": {"mode": "top_pct", "pct": 0.2}, "weighting": "equal", "rebalance": "monthly",
                 "costs": {"bps": 5}, "start": "2011-01-01"},
    },
    {
        "id": "quality_value_combo",
        "name": "Quality + value (point-in-time)",
        "family": "Value & quality",
        "description": "Rank on earnings yield and on gross profitability, add the ranks, hold the top 20%.",
        "evidence": "Buying cheap AND profitable firms beats either alone because each screen removes the other's traps "
                    "(Novy-Marx 2013; Asness, Frazzini & Pedersen 2019 'Quality Minus Junk').",
        "citation": "Novy-Marx (2013); Asness, Frazzini & Pedersen (2019)",
        "spec": {"universe": {"preset": "us_megacaps"}, "signal": "rank(earnings_yield) + rank(gross_profitability)",
                 "selection": {"mode": "top_pct", "pct": 0.2}, "weighting": "equal", "rebalance": "monthly",
                 "costs": {"bps": 5}, "start": "2011-01-01"},
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
    {
        "id": "statarb_sscore",
        "name": "Stat arb — residual mean reversion (Avellaneda–Lee s-score)",
        "family": "Stat arb & market-neutral",
        "description": "Each day, buy the 8 large caps whose market-hedged price has fallen furthest below its own "
                       "mean-reverting equilibrium and short the 8 furthest above; dollar-neutral, daily.",
        "evidence": "The textbook equity stat-arb model run by quant market-neutral desks: model each stock's residual "
                    "(after removing market beta) as an Ornstein–Uhlenbeck process and trade its s-score. Sharpe ≈1.4 "
                    "1997–2007 on US stocks, then much weaker as the trade got crowded — the Aug-2007 quant crash hit it "
                    "hardest (Avellaneda & Lee 2010; Khandani & Lo 2007). Daily turnover: costs decide it. Hedging each "
                    "stock with its sector ETF instead (signal -sscore(60, 1)) scores about the same on this universe.",
        "citation": "Avellaneda & Lee (2010); Khandani & Lo (2007)",
        "spec": {"universe": {"preset": "us_megacaps"}, "signal": "-sscore(60)",
                 "selection": {"mode": "long_short", "n": 8}, "weighting": "inverse_vol",
                 "rebalance": "daily", "execution": "next_close", "costs": {"bps": 2, "borrow_bps": 50}},
    },
    {
        "id": "residual_reversal",
        "name": "Residual short-term reversal, market-neutral",
        "family": "Stat arb & market-neutral",
        "description": "Long the 10 large caps with the worst market-hedged week (scaled by their own residual volatility), "
                       "short the 10 best; weekly, dollar-neutral.",
        "evidence": "Reversal measured on residual returns roughly doubles the risk-adjusted return of plain reversal "
                    "and survives costs better because it is not a hidden market or industry bet (Blitz, Huij, Lansdorp "
                    "& Verbeek 2013). Economically it is paid for supplying liquidity — the market maker's edge "
                    "(Nagel 2012), and it earns most when volatility is high.",
        "citation": "Blitz et al. (2013); Nagel (2012)",
        "spec": {"universe": {"preset": "us_megacaps"}, "signal": "-sum(resid(252), 5) / std(resid(252), 63)",
                 "selection": {"mode": "long_short", "n": 10}, "weighting": "inverse_vol",
                 "rebalance": "weekly", "costs": {"bps": 3, "borrow_bps": 50}},
    },
    {
        "id": "residual_momentum",
        "name": "Residual momentum, market-neutral",
        "family": "Stat arb & market-neutral",
        "description": "Rank large caps on their market-hedged 12-1-month return per unit of residual risk; long the top 10, "
                       "short the bottom 10, monthly.",
        "evidence": "Momentum built from residual returns has about half the volatility of classic momentum and avoids "
                    "most of its crashes, which come from hidden beta after market rebounds (Blitz, Huij & Martens 2011; "
                    "Daniel & Moskowitz 2016).",
        "citation": "Blitz, Huij & Martens (2011)",
        "spec": {"universe": {"preset": "us_megacaps"},
                 "signal": "(sum(resid(252), 252) - sum(resid(252), 21)) / std(resid(252), 252)",
                 "selection": {"mode": "long_short", "n": 10}, "weighting": "inverse_vol",
                 "rebalance": "monthly", "costs": {"bps": 3, "borrow_bps": 50}},
    },
    {
        "id": "market_neutral_multifactor",
        "name": "Market-neutral multi-factor book (quant equity pod)",
        "family": "Stat arb & market-neutral",
        "description": "Equal blend of value (earnings yield), quality (gross profitability), momentum (12-1) and low beta, "
                       "long the top 10 and short the bottom 10, 8% volatility target, monthly.",
        "evidence": "How multi-manager quant equity books are built: several weakly correlated factors, dollar-neutral, "
                    "risk-targeted, so returns come from stock selection rather than the market (Asness, Moskowitz & "
                    "Pedersen 2013; Frazzini & Pedersen 2014; Novy-Marx 2013). Value and momentum hedge each other. Expect long "
                    "dry spells: the 2018–20 'quant winter' hit value-tilted books hard.",
        "citation": "Asness, Moskowitz & Pedersen (2013); Frazzini & Pedersen (2014)",
        "spec": {"universe": {"preset": "us_megacaps"},
                 "signal": "rank(earnings_yield) + rank(gross_profitability) + rank(mom(252, 21)) + rank(-beta(252))",
                 "selection": {"mode": "long_short", "n": 10}, "weighting": "inverse_vol",
                 "risk": {"vol_target": 0.08, "max_weight": 0.15, "max_gross": 2.0},
                 "rebalance": "monthly", "costs": {"bps": 3, "borrow_bps": 50}},
    },
    {
        "id": "vrp_timed_spy",
        "name": "Volatility risk premium timing (S&P 500)",
        "family": "Volatility",
        "description": "Hold SPY while implied volatility (VIX) is above the S&P's realised 1-month volatility; switch to "
                       "Treasuries (IEF) when realised volatility overtakes implied — the market is in stress. Weekly.",
        "evidence": "Implied volatility is usually above realised: option sellers are paid a risk premium. The premium "
                    "predicts equity returns (Bollerslev, Tauchen & Zhou 2009), and when it turns negative the market is "
                    "in a high-volatility regime where drawdowns cluster. Over 2005–26 here: Sharpe ≈0.74 vs 0.64 "
                    "buy-and-hold, max drawdown ≈−39% vs −55%. Lags sharp V-shaped rebounds.",
        "citation": "Bollerslev, Tauchen & Zhou (2009); Carr & Wu (2009)",
        "spec": {"universe": {"symbols": ["SPY"]}, "signal": "vix - 100 * sqrt(252) * std(mkt / delay(mkt, 1) - 1, 21)",
                 "selection": {"mode": "threshold", "min_score": 0}, "weighting": "equal_universe", "fallback": "IEF",
                 "rebalance": "weekly", "costs": {"bps": 2}},
    },
    {
        "id": "short_vol_term_structure",
        "name": "Short volatility with a term-structure filter (SVXY)",
        "family": "Volatility",
        "description": "Hold the short-VIX-futures ETF SVXY only while the VIX curve is in contango (3-month VIX above "
                       "spot VIX) and implied volatility exceeds realised; otherwise short Treasuries (SHY). Daily.",
        "evidence": "Selling VIX futures in contango harvests the roll-down and the volatility premium (Simon & "
                    "Campasano 2014) — the trade behind most option-market-making P&L. It is short a crash: on 5 Feb "
                    "2018 inverse-VIX funds lost ~90% in a day (XIV was liquidated). The filter cut the worst drawdown "
                    "here from −95% to about −59%, but a one-day gap can still exceed any filter. SVXY is −0.5× since 2018.",
        "citation": "Simon & Campasano (2014); Whaley (2013)",
        "spec": {"universe": {"symbols": ["SVXY"]},
                 "signal": "where(vix3m > vix, vix - 100 * sqrt(252) * std(mkt / delay(mkt, 1) - 1, 21), nan)",
                 "selection": {"mode": "threshold", "min_score": 0}, "weighting": "equal_universe", "fallback": "SHY",
                 "rebalance": "daily", "execution": "next_close", "costs": {"bps": 5}},
    },
]

RESEARCH_NOTES: List[Dict[str, str]] = [
    {"title": "What Jane Street and Citadel actually do (the public part)",
     "text": "Their models are secret; their businesses are not. Electronic market makers (Citadel Securities, Jane "
             "Street, Virtu) earn the bid-ask spread and manage inventory risk — see Arb & market making → Market making "
             "(Avellaneda–Stoikov). Jane Street is best known for ETF market making and arbitrage: keeping ETFs in line "
             "with their baskets and related ETFs. Quant market-neutral funds (Citadel's GQS, Renaissance, D. E. Shaw) "
             "run statistical arbitrage: many small, hedged, short-horizon mean-reversion bets (the s-score and pairs "
             "templates) plus multi-factor equity books. Their edge is mostly speed, data, execution and cost control, "
             "which a daily-bar backtest cannot reproduce — so expect these to look far weaker here than in the real firms."},
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
