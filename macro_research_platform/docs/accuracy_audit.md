# Accuracy audit — 2 November 2026

`scripts/audit_accuracy.py` compares what the platform shows with sources it does not use for that number, and checks
model outputs for internal consistency. Run it against the live backend at any time:

```
../.venv/bin/python scripts/audit_accuracy.py
```

It writes a JSON report to `data/processed/audit/`. Final run: **109 pass, 0 fail, 3 warnings (DCF methodology), 2 info**.

## What is checked

| Area | Checks | Independent reference |
|---|---|---|
| Markets | S&P 500, Dow, Nasdaq, Nikkei, VIX and WTI closes on the same date; EUR/USD and 8 dollar crosses; USD/JPY; 5 stock prices; Bitcoin, Ether and dominance; index movers add up to the index move; 1-day S&P return; ETF premiums; FX forwards | FRED, ECB reference rates, Massive (Polygon) daily bars, CoinGecko, covered interest parity |
| Rates | Treasury curve (3M, 2Y, 10Y, 30Y) on the same date; latest curve shown; 10Y, TIPS, 5Y/10Y breakevens; fed funds and SOFR; Fed, ECB policy rates; WIRP and FOMC target range; IG and HY spreads; swap spreads and 1Y swap vs SOFR | FRED, NY Fed, ECB data portal |
| Macro | Dashboard snapshot age, 10Y, S&P level, VIX; 10Y–2Y and 10Y–3M spreads; HY OAS; NFCI; GDPNow; recession probability; CPI used for real yields; unemployment; dashboard vs macro-model regime | FRED, NY Fed recession model |
| Equities | Trailing EPS, P/E, TTM revenue and market cap for AAPL, MSFT, JPM; option deltas recomputed from their IVs; ATM IV range; probability-lab distribution sums to 1 and percentiles increase; dividend yields; DCF sanity; breadth recomputed | Yahoo (for SEC-based figures), Black–Scholes, Massive closes |

## Errors found and fixed

1. **SEC fundamentals a quarter behind after earnings.** Company facts and point-in-time EPS were cached for 3 days and the freshness check used an old local filing index, so Microsoft's 28 October 10-Q was missing (EPS 17.96 vs 19.16; revenue −4%). Now checked against SEC's live submissions feed every 6 hours and refetched when a newer 10-Q/10-K exists. Affects FA, DCF, GE, EM, CRPR and the Quant Lab's point-in-time data.
2. **ETF premiums false after the close.** Yahoo's NAV moves to the same day once the fund publishes, while `previousClose` stays on the day before, so every big up or down day showed as a large premium (SMH +744bp, SPY +182bp). The NAV is now paired with the close it belongs to.
3. **Dashboard regime flipped on one day's market move.** Growth there is S&P 500 momentum; a −1.8% day moved it from ~0.6 to 0.49 and relabelled the economy from Reflation to Stagflation at "Medium" confidence. A ±0.05 dead band now keeps the previous regime on a coin-flip axis, confidence there is labelled Low, and a note appears when the walk-forward macro model disagrees.
4. **Macro model's time machine ended a month early.** Its last row was September's decision (Goldilocks 56%) while the model's current regime, from October's data, was Reflation 44%. The live decision is now the last row, marked Live.
5. **Single-name CDS grouped different companies together.** Trades on the standard-reference-obligation placeholder ISIN were merged under one name ("Worldline", 164 trades). Entities are now keyed by valid ISIN issuer, the entity name, or the RED code; duplicates are merged; spreads under 5bp (mis-scaled reports) are dropped and a spread needs at least three trades.
6. **GDPNow "as of" date.** FRED dates GDPNow by the quarter it estimates; that date was shown as the update date. Now labelled by quarter.

## Judgement calls, not errors

- **DCF values below market** (AAPL $159 vs $345, MSFT $399 vs $522, KO $43 vs $94). Inputs match the data; the gap comes from deliberate choices: today's 4.93% risk-free rate, a 5% equity risk premium, industry (bottom-up) betas — AAPL 1.34 vs its regression beta of 1.07 — and a 20-year fade of returns on new capital, which leaves 11–18% of value in the terminal period and implies exit multiples of 7–9× EBIT. KO also carries analysts' expected 2027 revenue fall (bottler sales) without the margin uplift that would accompany it. The market-implied growth figure on the DCF screen shows what the price requires.
- **JPM revenue** is 4.6% above Yahoo's: SEC "Revenues" is JPMorgan's total net revenue as reported; Yahoo uses its own definition for banks.
- **WTI** front-month futures (WEI) and the spot price (FRED) differ by a few percent when the curve is steep.

## Still not free

Official agency ratings (S&P, Moody's, Fitch publish 17g-7 histories only behind a login), individual corporate-bond
prices (FINRA TRACE needs a subscription; market breadth works with a free FINRA API key — screen TRACE), and Markit
RED entity names.
