# Methodology — Phase 2: Factor Risk Model

_For a PM to read before trusting the numbers._

## What it does
Decomposes the portfolio's risk into sensitivities (betas) to systematic factors —
so a macro regime signal becomes an actual statement about what *your* book is exposed to.

## Factors (proxied by liquid, investable instruments)
| Factor | Proxy | Meaning |
|---|---|---|
| Equity Beta | SPY | broad equity market |
| Size | IWM | small-cap tilt |
| Value | IWD | value tilt |
| Growth | IWF | growth tilt |
| Momentum | MTUM | cross-sectional momentum |
| Rates Duration | TLT | long-Treasury (rate sensitivity) |
| Credit Spread | HYG | high-yield credit |
| Commodity | DBC | broad commodities |
| USD | UUP | US dollar |
| Volatility | ^VIX | equity vol |

## Calculation
- **Per-position loading:** OLS regression of the position's daily returns on the
  factor daily returns (with intercept), over ~1y of date-aligned observations:
  `r_position,t = α + Σ_f β_f · r_factor,f,t + ε_t`. The β_f are the factor loadings.
- **Portfolio loading:** `β_portfolio,f = Σ_i (net_weight_i · β_i,f)`, where net weight =
  position market value / portfolio gross exposure (shorts subtract).
- **Factor volatility:** annualized standard deviation of each factor's daily returns
  (`σ · √252`).
- **Contribution to volatility:** `(β_f · σ_f)²` normalized to sum to 1 — the share of
  portfolio variance attributable to each factor.

## Assumptions & limitations (read these)
- **Collinearity:** the style factors (equity/size/value/growth/momentum) are highly
  correlated, so *individual per-position* betas can be unstable and occasionally
  counter-intuitive (e.g. a large negative style beta offsetting a large positive one).
  The **portfolio-level aggregate** and the equity beta are far more stable. A
  production system would orthogonalize factors or use a pre-estimated factor
  covariance (Barra-style) — that is a future enhancement.
- **Vol contribution ignores factor correlation** (first-order, independent-factor
  approximation). A full covariance treatment is Phase 3 (VaR).
- **Returns are daily closes over ~1y** — loadings are backward-looking averages and
  will lag a regime that has just turned.
- Positions without ≥61 aligned observations (very new listings) are shown as "no fit"
  and contribute 0 to the aggregate rather than a guessed number.

## Verification
- Known-answer unit tests (`api/tests/test_factor_model.py`): a synthetic position equal
  to `1.5×equity` recovers β=1.5; `1.2×equity − 0.4×rates` recovers those betas; a clean
  fit gives R²>0.99; a short position subtracts its loading; vol contributions sum to 1.
- Live sanity check: an **SPY position regresses to R²=1.0 and equity β=1.0** (it *is*
  the equity proxy), confirming the pipeline end-to-end. 53 backend calc tests pass.
