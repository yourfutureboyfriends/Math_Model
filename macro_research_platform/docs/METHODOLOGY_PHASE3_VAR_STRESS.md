# Methodology — Phase 3: Value at Risk & Stress Testing

_For a PM to read before trusting the numbers._

## What it does
Answers "how much could this book lose?" three independent ways, decomposes that risk to
the position level, and stress-tests the book against historical crises and custom shocks.
All VaR figures are reported as a **positive dollar loss** (the amount at risk).

## VaR — three methods (on actual positions, 1y daily returns)
Portfolio daily P&L is `Σ_i market_value_i × return_i,t` (shorts negative), date-aligned.
- **Historical VaR** — the empirical (1−c) percentile of that P&L distribution. No
  distributional assumption; captures fat tails actually observed.
- **Parametric (variance-covariance) VaR** — `z(c) × σ(P&L)`, where σ already embeds
  position covariances (z95=1.645, z99=2.326). Assumes normality.
- **Monte Carlo VaR** — estimate the position return covariance, simulate 20,000
  correlated draws, take the percentile of simulated P&L.
Reported at **95% and 99%**, **1-day and 10-day** (10-day = 1-day × √10, square-root-of-time).

## VaR contribution
Euler/marginal allocation of the **parametric** 95% 1-day VaR (variance-based, so the
decomposition is internally consistent): `component_i = VaR × mv_i·cov(r_i, P&L) / var(P&L)`.
Components sum to total VaR; a hedging short shows a **negative** contribution.

## Stress testing
- **Predefined scenarios** (2008 GFC, 2020 COVID, 2013 Taper, 2022 rate shock, 1994 bond):
  representative factor returns for the crisis applied to the book's **dollar factor
  exposures** `DExp_f = gross × portfolio_loading_f`; scenario P&L = `Σ_f DExp_f × shock_f`.
- **Custom scenario** — shock any combination of factors and see estimated P&L.
- **Reverse stress** — for a target loss, the single-factor move that alone causes it
  (`shock_f = −loss / DExp_f`); the factor needing the smallest move is the most dangerous.

## Concentration & liquidity
- **Concentration** — largest single-name and top-5 gross weights, Herfindahl index,
  and breaches of a single-name limit (default 20%).
- **Liquidity** — days-to-liquidate = `|shares| / (participation × ADV)` (default 20% of
  average daily volume); positions above a threshold are flagged illiquid.

## Assumptions & limitations
- **Constant current weights** — historical VaR holds today's market values fixed across
  the lookback; it does not re-weight for past prices (standard current-weights HS).
- **Parametric/MC assume normal returns** — they will understate tail risk relative to
  historical VaR in crises; that is exactly why all three are shown side by side.
- **Stress scenarios are representative, not exact replays**, and depend on the factor
  loadings (which carry the Phase 2 collinearity caveat) — the *net dollar* factor
  exposure is more reliable than any single style loading.
- **Vol/covariance are 1y trailing** — a just-turned regime is under-weighted.
- Positions without ≥61 aligned observations are excluded (contribute 0), never guessed.

## Verification
12 known-answer unit tests (`api/tests/test_var_model.py`): parametric VaR of N(0,1000)
≈ 1.645×1000; 99% > 95%; 10-day = 1-day×√10; Monte Carlo ≈ parametric for a single normal
asset; component VaR sums to total; scenario/reverse-stress arithmetic; concentration
weights and days-to-liquidate. Verified live on a real 4-position book: 95% 1-day VaR
≈ $0.9k–$1.2k across the three methods, AAPL drives 87% of VaR, the SPY short hedges
(−10%), 2008 GFC scenario ≈ −$21k. 65 backend calc tests pass in total.
