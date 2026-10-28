# Macro model — United States, Euro area, Rest of the world

One method, three economies. Code: `api/model/core.py` (method), `api/model/economies.py` (what each economy uses),
`api/model/sources.py` (data fetchers), `api/model/engine.py` (runs, snapshots, the world summary).
API: `GET /api/v1/model?economy=us|ea|row`, `GET /api/v1/model/world`, `GET /api/v1/model/economies`.
UI: Research → Macro Model (world strip + economy tabs).

## Method (identical for every economy)

1. **Factors** — growth and inflation diffusion indices (Stock & Watson, 2002): first principal component of each block of
   standardised, stationary series, each shifted by its publication lag (the panel at month *t* holds only what had been
   published by then). Sign: the factor loads positively on an anchor series.
2. **Regimes** — logistic models of next month's 3-month factor direction → P(growth ↑), P(inflation ↑) → four quadrant
   probabilities (treated as independent). Markov-switching contraction probability shown as a diagnostic.
3. **Expected returns** — each asset's excess return by realised regime, shrunk toward its mean, weighted by the regime
   probabilities.
4. **Portfolio** — Black–Litterman (prior = environment-balanced portfolio, views = the regime expectations), mean–variance
   with a volatility target, long-only, per-asset cap. Walk-forward backtest re-estimates everything monthly, net of costs.

## Data

| | United States | Euro area | Rest of the world |
|---|---|---|---|
| Growth | 9 FRED series (IP, payrolls, unemployment, claims, housing, retail, capacity, income, hours) | Eurostat: industrial production, retail volume, construction, unemployment; European Commission surveys: economic sentiment, industry, consumer, services confidence, employment expectations | OECD composite leading indicators (UK, Japan, China, India, Canada, Korea, Australia, Brazil, Mexico); OECD unemployment (six of them) |
| Inflation | 8 FRED series (CPI, core, PCE, core PCE, PPI, wages, oil, expectations) | ECB HICP headline, core, services, goods; producer prices; industry selling-price expectations; Brent in EUR | BIS consumer prices for the nine; Brent; IMF all-commodity index |
| Assets | US equity, developed ex-US, EM, long / intermediate Treasuries, TIPS, IG, HY, gold, commodities | DAX (euro equity proxy), synthetic Bund and BTP 10-year returns from ECB yields, € IG credit, US and EM equity in EUR, gold and commodities in EUR | Japan, UK, China & HK, EM equity; international government bonds; EM USD bonds; gold; commodities |
| Returns | USD over 3-month T-bills | EUR over 3-month Euribor | USD over 3-month T-bills |
| Orders | Model sleeve (book “Macro Model”) — staged with pre-trade checks and four-eyes approval | Research view | Research view |

Every input's coverage, latest month and loading is listed in the panel (“Show the N inputs”). A euro-area or rest-of-world
input more than six months behind the newest month is left out of the factors and flagged *stale*, rather than frozen at its
mean.

## Source notes (checked October 2026)

- **EA21**: Bulgaria joined the euro on 1 January 2026; Eurostat's EA20 aggregates end in December 2025. The model uses EA21.
- **HICP** moved to the ECB's new `HICP` dataflow (ECOICOP 2, data provider `4D0`) in 2026; the old `ICP` flow ends in
  December 2025.
- **DBnomics' copy of Eurostat lags by months**, so Eurostat's own API is called; DBnomics is used for the ECB only.
- **OECD CPI** is stale for Japan (2021) and Mexico (2024), so consumer prices come from the BIS long CPI series.
- Every fetch is cached for 12 hours on disk; a failed refresh serves the last good copy.

## Backtests at build (Oct 2026, default parameters; walk-forward, net of 10 bp costs)

| | Period | Tactical Sharpe | Strategic | 60/40 | Tilt vs strategic | Growth-direction accuracy |
|---|---|---|---|---|---|---|
| Euro area | 2004-01 → 2026-09 | 0.67 | 0.63 | 0.52 | +1.7%/yr, t = 1.62 (not significant) | 78% |
| Rest of world | 2004-06 → 2026-09 | 0.71 | 0.41 | 0.34 | +2.7%/yr, t = 2.62 (significant at 5%) | 88%* |

\* OECD leading indicators are pre-smoothed, so the growth factor's direction is persistent and easier to forecast; read the
rest-of-world skill with that in mind.

## Limitations

Revised data, not first-release vintages (all three). Growth and inflation directions treated as independent. Euro equity
history uses the DAX as a proxy; Bund / BTP returns are rebuilt from yields; euro IG credit starts in 2009 and USD assets in
EUR start in 1999. The rest-of-world model is one cycle across nine economies, not a model of any single country.
