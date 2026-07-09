# Methodology — Phase 8: Audit, Compliance & Reporting

_For a PM / compliance officer to read._

## What it does
Provides the audit primitives a regulated desk needs to answer "what did the system say,
and who acted on it, at time T."

## Decision log (append-only)
Every material action is recorded with **user, timestamp, action, target, before/after
state, and a required rationale** (`/api/v1/audit/decisions`). A decision cannot be logged
without a rationale (enforced server-side, HTTP 422 otherwise). Trade-idea lifecycle
transitions (Approved, Executed, …) are **auto-logged** to the same ledger, so approvals
carry a timestamped, attributed trail. The log is append-only (no edit/delete endpoint).

## Point-in-time snapshots ("time machine")
A background task snapshots key state — regime + confidence, ensemble score/agreement/mode,
recession reading, and portfolio gross/net exposure + P&L + position count — every 5
minutes into an immutable table (retained ~2000 snapshots). Endpoints:
- `/api/v1/audit/snapshots` — list,
- `/api/v1/audit/snapshots/{id}` — one snapshot's full state,
- `/api/v1/audit/time-machine?at=<ISO>` — the state at or just before a given time.
This is what lets a post-trade review reconstruct exactly what the system displayed when a
decision was made.

## Assumptions & limitations
- **Snapshot cadence is 5 min** — sub-minute reconstruction isn't captured; a specific
  intraday moment resolves to the most recent prior snapshot.
- **Single-user attribution ("admin")** — the app has role-based auth (admin/PM/risk/
  analyst) but the audit entries are currently stamped with a fixed user; wiring the
  authenticated session identity into every log entry is a small follow-up.
- **Not built (scoped):** the data-lineage "trace any number to its source/calc path"
  button (partially served today by the Phase-7 source/freshness tags), the scheduled
  automated PDF risk/attribution/IC reports (on-demand HTML/print export exists), and
  enforcing read-only vs PM vs admin permission gates on write endpoints.

## Verification
Verified live: a position-sizing override and an auto-logged "Trade idea → Executed" both
appear in the decision log with user/timestamp/rationale; logging without a rationale is
rejected (422); the time machine returns a real captured snapshot (regime expansion 76%,
ensemble 0.76, portfolio gross $110,845 / 4 positions). 179 backend tests pass, zero
console errors.
