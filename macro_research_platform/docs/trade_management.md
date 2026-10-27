# Entries and exits — how the platform tells you when to get in and out of a stock

Code: entries `api/calculations/stock_timing.py` (Stock Entry Signals), exits `api/calculations/trade_management.py`
(Position Manager), orchestration `api/trade_manager.py`, evidence `api/exit_evidence.py`.
API: `GET /api/v1/stock/timing?symbol=`, `POST /api/v1/stock/manage`, `GET /api/v1/stock/positions/manage`,
`GET /api/v1/stock/exit-evidence`. UI: Trading → Stock Entry Signals, Position Manager; exit / trim calls on book
positions also arrive as pop-ups.

## Entry — "should I own it, and is now a good moment?"

| Input | Rule | Research |
|---|---|---|
| Trend | price vs 50/200-day averages | Faber (2007); Hurst, Ooi & Pedersen (2017) |
| Momentum | 12-1 month return / volatility | Moskowitz, Ooi & Pedersen (2012); Barroso & Santa-Clara (2015) |
| 52-week high | proximity | George & Hwang (2004) |
| Earnings | latest surprise, decaying | Bernard & Thomas (1989) |
| Sell-side | consensus, target upside, revisions | Chan, Jegadeesh & Lakonishok (1996) |
| Quality | profitability, leverage | Asness, Frazzini & Pedersen |
| Entry timing | pullback to the 20-day average, RSI | Jegadeesh (1990); Kolanovic & Wei (2015) |
| Market regime | index above 200-day, VIX < 25 | Faber (2007) |
| **News tone (new)** | a BUY waits while ≥ 5 headlines in 14 days average ≤ −0.3 | Tetlock (2007) |
| **Insider buying (new)** | ≥ 2 open-market insider buyers in 6 months shown as support; sales only noted | Cohen, Malloy & Pomorski (2012); Lakonishok & Lee (2001) |

No entry within 5 days of a report; half size within 10.

## Exit — "I'm in: hold, tighten, trim, add or exit?"

| Signal | Action | Research |
|---|---|---|
| Close through the 2.5×ATR initial stop | EXIT | Kaminski & Lo (2014) |
| Close below the 200-day average | EXIT | Faber (2007) — the best exit in the test below |
| 50-day below 200-day | TIGHTEN | Faber (2007) |
| 12-1 momentum turns negative | TRIM | Moskowitz, Ooi & Pedersen (2012) |
| Net downgrades / target cuts in 30 days | TRIM | Chan, Jegadeesh & Lakonishok (1996) |
| Earnings miss in the last 60 days | TIGHTEN | Bernard & Thomas (1989) |
| Negative news tone | TIGHTEN | Tetlock (2007) |
| 20-day vol > 2× its 1-year median | TRIM | Moreira & Muir (2017) |
| Market risk-off (index < 200-day or VIX ≥ 30) | TIGHTEN | Daniel & Moskowitz (2016) |
| Target reached | TIGHTEN (not sell) | the fixed-target exit was the weakest rule tested |
| Report within 5 days on a ≥ 1R gain | TRIM | gap risk |
| Warning active and already through the chandelier level | TRIM | LeBeau chandelier exit |
| Still a BUY, pulled back, in profit, no warnings | ADD | pyramid into strength, never into a loser |

Tightening moves the stop to the chandelier level (highest close since entry − 3×ATR(22)) or 2 ATRs from the price,
whichever is closer while still on the right side of the price; the stop never loosens.

## Evidence for the exit defaults (Oct 2026)

Same entry signals, each exit rule traded independently; 30 large caps, 10 years of daily prices, 0.1% round-trip cost.

| Exit rule | Trades | Win rate | Avg / trade | Profit factor | Worst | Return / yr held | PF 1st / 2nd half |
|---|---|---|---|---|---|---|---|
| Hold 63 sessions (no management) | 777 | 64% | +5.5% | 2.79 | −43% | 22.2% | 3.89 / 2.08 |
| Fixed 2.5×ATR stop + 2R target | 1,115 | 47% | +2.6% | 1.64 | −31% | 17.7% | 1.86 / 1.46 |
| Chandelier 3×ATR(22) | 1,296 | 44% | +2.8% | 1.89 | −31% | 20.7% | 2.19 / 1.65 |
| **200-day trend break + initial stop** | 922 | 26% | +4.1% | **2.73** | **−18%** | **22.6%** | **2.75 / 2.29** |
| Chandelier + trend + 60-session time stop | 1,706 | 34% | +1.9% | 1.76 | −31% | 19.6% | 1.89 / 1.60 |

Wider chandeliers (4–5×ATR) raised the profit factor (2.07, 2.47) but not the return per year held. The trend exit
wins few trades but lets winners run, and its worst loss is the smallest; it led in both halves of the decade.
**Caveat:** today's mega caps over a strong decade (survivorship) flatter any rule that holds longer — compare the
rules with each other, not the absolute numbers. The live table (Position Manager) is recomputed weekly.

## Sources checked for this work

- Kaminski & Lo, "When do stop-loss rules stop losses?", *Journal of Financial Markets* 18 (2014) — stops add value
  when returns have momentum, cost money in a random walk. <https://dspace.mit.edu/handle/1721.1/114876>
- Han, Zhou & Zhu, "Taming momentum crashes: a simple stop-loss strategy" (working paper, SSRN 2407199) — a 10% stop
  on momentum winners cut the worst monthly loss from about −50% to −11%, before costs.
- Cohen, Malloy & Pomorski, "Decoding inside information", *Journal of Finance* (2012) — opportunistic insider trades
  earn ~82 bp/month abnormal (value-weighted); routine trades ~0. <https://www.nber.org/papers/w16454>
- Chan, Jegadeesh & Lakonishok, "Momentum strategies", *Journal of Finance* 51(5) (1996) — earnings surprises and
  analyst revisions predict drift independently of price momentum; analysts respond sluggishly.
  <https://ideas.repec.org/a/bla/jfinan/v51y1996i5p1681-1713.html>
- Also cited from the literature: Faber (2007), Moskowitz, Ooi & Pedersen (2012), Bernard & Thomas (1989),
  Tetlock (2007), Moreira & Muir (2017), Daniel & Moskowitz (2016), Lakonishok & Lee (2001).

Not investment advice; every signal is probabilistic.
