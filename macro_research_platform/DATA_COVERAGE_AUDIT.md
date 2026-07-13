# DATA_COVERAGE_AUDIT — how international is the platform?

Honest audit of data breadth in response to "not all of it is international; separate by
regions / countries / currencies; more everything." This documents what was made global this
round, what is legitimately US-specific, and what remains a larger effort.

## Delivered this round (new breadth)

| Area | Before | Now |
|---|---|---|
| **Market clock holidays** | Hardcoded 2026, few exchanges | **python-holidays** — per-region, **any year**, incl. lunar (HK/SG Chinese NY). `/api/market-hours` |
| **Equity indices** | US only (SPX, NDX) | **10 indices / 9 regions** — S&P, Nasdaq, FTSE, DAX, Euro Stoxx, Nikkei, Hang Seng, Shanghai, ASX 200, Nifty. `/api/global-markets` |
| **FX** | 3 pairs (EUR/GBP/JPY) | **20 pairs, region-grouped** — G10 + Asia (CNY, INR, KRW, SGD, HKD, TWD) + EMEA/LatAm (BRL, MXN, ZAR, TRY). `/api/fx-rates` |
| **Cross-market correlation** | US cross-asset only | **16-market global matrix** — world indices + FX + Gold/WTI/UST. `/api/global-correlation` |

All use real yfinance/library data; anything that fails to quote returns an explicit
null/unavailable, never a fabricated value.

## Already international (pre-existing)

- **International macro** (`internationalMacro`): Euro-area, UK, Japan real GDP + CPI from FRED
  international series, with a global-sync read.
- **FX / Commodities / Market Clock**: already multi-region.

## Legitimately US-specific (by design — NOT gaps)

Some panels model **US-specific** constructs; globalizing them would change their meaning:
- **Recession probability** (Sahm rule, US yield-curve probit) — US indicators.
- **Fed policy / rate path, US yield curve (2s10s), Treasury** — US monetary system.
- **US Key Metrics, Regime Playbook** — anchored to the US macro cycle the strategy trades.

These are correct as US models; a parallel ECB/BoJ/PBoC version would be a *new feature*, not a fix.

## Honest remaining gap (larger effort — NOT done this round)

**Full economic regionalization** of every section is a multi-endpoint data-engineering effort:
- Per-country macro dashboards (growth/inflation/policy-rate/unemployment for US, Eurozone, UK,
  Japan, China, India, EM) — needs a curated FRED/OECD international series map per indicator.
- Regionalizing the derived analytics (regime, nowcast, liquidity, factor rotation) per region —
  each currently computes on US series only.
- A country/region selector to pivot the whole dashboard.

Rough audit of the 74 section components: **~11 already global, ~12 US-specific by design,
~51 macro-signal panels that compute on US series** and would each need a regional data feed to
truly regionalize. That is the honest bulk of the remaining work and should be scoped as its own
project (one region-feed + one panel at a time), not claimed as complete here.

## Recommendation
The market/price/FX/correlation layer is now genuinely global. The **macro-economic** layer is
the real frontier: the highest-value next step is a single **Regional Macro Comparison** panel
(GDP/CPI/policy-rate/unemployment across US, Eurozone, UK, Japan, China from FRED international
series) — a bounded, high-impact addition that extends the existing `internationalMacro` builder.
