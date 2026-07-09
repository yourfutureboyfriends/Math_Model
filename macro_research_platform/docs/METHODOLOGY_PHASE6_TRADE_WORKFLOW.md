# Methodology — Phase 6: Trade-Idea Workflow & What-If Pre-Trade

_For a PM to read before trusting the numbers._

## What it does
Turns a trade from an idea into a risk-checked decision: propose it, see exactly how it
would move the book's risk *before* executing, size it to a VaR budget, and track it
through an auditable lifecycle.

## What-if pre-trade analysis
For a proposed trade (symbol, quantity), the system re-runs the Phase-3 risk engine on
**current positions + the hypothetical trade** (not persisted) and reports BEFORE vs
AFTER vs Δ for:
- **VaR 95% 1-day** (parametric, on the combined return set),
- **Gross and net exposure**,
- **Largest-name concentration**.
The proposed price is the latest close of the literal ticker (entry P&L = 0 by default).

## VaR-budget sizing
Given a VaR budget `L`, the suggested size solves the standalone-VaR constraint:
`notional × z(0.95) × daily_vol ≤ L` → `max_notional = L / (z × daily_vol)`,
`suggested_shares = max_notional / price`. This is a **conservative** vol-target: it uses
the position's *standalone* VaR and ignores diversification benefit with the rest of the
book (so it never *under*-sizes risk).

## Trade-idea lifecycle
Ideas move through **Proposed → Under Review → Approved → Executed → Closed**. Every
transition is recorded with state, timestamp and user in an immutable `state_history`,
giving a basic audit trail (the full point-in-time/decision log is Phase 8).

## Assumptions & limitations
- **Sizing is standalone**, not marginal — it does not credit the diversification of the
  new trade against the existing book, so it is deliberately conservative.
- **What-if VaR is parametric only** (fast) — for a final decision, also check the
  historical/Monte-Carlo VaR on the persisted book after executing.
- **Idea *generation* is manual here.** The auto-generator (regime × factor-gap × signal
  consensus → ranked, pre-sized ideas) is scoped but not built; ideas are entered by the
  PM with a rationale, and the what-if provides the sizing input.
- Prices are end-of-day closes (no intraday / bid-ask).

## Verification
Sizing has known-answer unit tests (`test_var_model.py`: `max_notional = L/(z·vol)`;
higher vol → smaller size). Verified live: adding TSLA ×100 moves 95% 1-day VaR
$1,199 → $2,302 (Δ +$1,103) and, for a $1,500 VaR budget, the system caps the suggestion
at 81 shares (TSLA daily vol 2.8%). Trade-idea lifecycle verified through
Proposed → Under Review → Approved with full state history. 170 backend tests pass.
