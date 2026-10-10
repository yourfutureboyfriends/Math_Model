# Methodology — Phase 1: Position & Portfolio Ingestion

_For a PM to read before trusting the numbers._

## What it does
Lets you record what you actually hold (per position, per book), stores it server-side,
and continuously values it against **live market prices**. Every downstream risk,
attribution, and trade feature is computed against these positions.

## Inputs (what you enter)
Per position: `symbol`, `quantity` (negative = short), `avg_cost`, `book`
(e.g. "Macro", "Equity L/S"), `asset_class`. Entered manually or via CSV upload
(columns: `symbol, quantity, avg_cost, book`).

## Calculations (exact formulas)
- **Current price** — last daily close for the *literal* ticker from Yahoo Finance
  (GLD = the GLD ETF, not gold futures), cached ~10 min.
- **Market value** = `quantity × current_price`. Shorts are negative.
- **Unrealized P&L** = `(current_price − avg_cost) × quantity`. A short gains when the
  price falls and loses when it rises — the sign is handled naturally.
- **Unrealized P&L %** = `current_price / avg_cost − 1`.
- **Weight** = `|market value| / Σ|market value|` (gross basis, so longs and shorts
  both consume risk budget).
- **Gross exposure** = long MV + |short MV|. **Net exposure** = long MV + short MV.
- **Book / firm aggregates** = the above summed within each book and across all books.

## Assumptions & limitations
- Prices are **end-of-day closes**, not intraday ticks — values move once per day, and
  after-hours moves are not reflected until the next close.
- Valuation is **mark-to-market on last close**; no bid/ask, no accrued interest,
  no FX conversion (all values assumed in USD).
- A symbol with **no price** is shown as "no price" with null value — never a fabricated
  number. Illiquid or delisted tickers will read as unpriced.
- `avg_cost` is a single blended entry price; there is no lot-level tax accounting.
- Persistence is a local SQLite table; this is a single-desk store, not a
  firm-of-record book — reconciliation against custodian fills is Phase 8.

## Verification
Unit tests (`api/tests/test_portfolio.py`, 10 known-answer checks) cover market value,
long/short P&L sign, weights summing to 1 on a gross basis, and book/firm aggregation.
Verified live: AAPL/SPY(short)/MSFT/GLD across two books value correctly against live
prices with correct long/short exposure and P&L.
