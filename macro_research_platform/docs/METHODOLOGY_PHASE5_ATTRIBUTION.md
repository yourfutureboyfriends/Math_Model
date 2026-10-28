# Methodology — Phase 5: Performance Attribution

_For a PM to read before trusting the numbers._

## What it does
Explains *where the book's return came from*, two complementary ways, both reconciling
exactly to a total.

## 1. Contribution attribution (since inception)
Each position's **dollar P&L** = `(current_price − avg_cost) × quantity` (Phase 1).
- **By position** — every holding's P&L and its share of total P&L.
- **By book** — P&L summed within each book.
- These **sum exactly** to the portfolio's total unrealized P&L (no residual).

## 2. Factor attribution (trailing ~1y return)
The portfolio's trailing period return is split into a systematic part and a residual:
- `portfolio_return = Σ_i net_weight_i × position_return_i` over the window.
- `systematic_return = Σ_f portfolio_loading_f × factor_period_return_f` (Phase 2 loadings
  × the realized trailing return of each factor proxy).
- `idiosyncratic (selection) = portfolio_return − systematic_return` — the stock-specific
  return not explained by factor exposure.
By construction **systematic + selection = portfolio return** (exact reconciliation).

## How to read it
A book that made money on **selection** (large positive idiosyncratic) profited from
stock-specific calls, not factor timing; a book with large **systematic** contribution
rode broad factor moves. Example (demo book): +12.7% total = −6.2% systematic + 18.9%
selection — i.e. the gains were stock-specific (AAPL/GLD), while the net factor stance
(short-equity-tilted) detracted.

## Assumptions & limitations
- **Two different bases**: contribution is *since-inception dollar P&L* (uses each
  position's own entry), while factor attribution is a *trailing ~1y return*
  decomposition. They answer different questions and are not expressed on a single
  common period — this is stated on the panel.
- **Factor loadings carry the Phase 2 collinearity caveat** — individual style
  contributions (equity/value/growth) can offset each other; the *systematic vs
  selection* split and the *net* factor stance are the robust takeaways.
- **No benchmark/Brinson allocation-vs-selection** in the classic sense yet — that needs
  benchmark group weights; the factor decomposition is the more rigorous substitute here.
- **Gross of fees/costs.**

## Verification
5 known-answer tests (`api/tests/test_attribution.py`): position and book contributions
sum to total P&L; factor attribution reconciles (systematic + idiosyncratic = portfolio
return); cumulative-return compounding. Verified live on the real book: by-position P&L
sums to $20,497; factor decomposition reconciles to +12.7%. 82 backend calc tests pass.
