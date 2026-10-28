# Methodology — Phase 9: Reliability Infrastructure (partial)

_For an engineer / ops reviewer._

## What was built: automated data-quality checks
Bad data must be caught **before** it propagates into signals, risk or P&L. The check
scans each key price feed and flags:
- **Bad ticks** — a day-over-day move larger than a per-series threshold (e.g. a price
  50% off the previous close is almost always a data error, not a real move). Thresholds
  are calibrated per instrument (cash equities ~15%, USD ~8%, **VIX ~80%** because it
  legitimately spikes 25%+ intraday).
- **Statistical outliers** — values more than 6σ from the recent distribution.

`/api/v1/data-quality` returns a per-series report with status **PASS / WARN / FAIL**
(FAIL = a hard bad tick likely to corrupt downstream calculations) and an overall roll-up,
surfaced as a status strip in the Audit panel. 6 known-answer unit tests
(`test_data_quality.py`): a 50% drop is flagged FAIL; normal moves pass; a 6σ value is an
outlier; VIX-style large-but-real moves pass under the wider threshold.

## What already exists (from earlier phases)
- **WebSocket push** — `/ws/prices` streams live prices/heartbeats (fixed in the repair
  work); the store consumes it. Not yet extended to push regime/risk deltas.
- **Point-in-time historical storage** — the Phase-8 snapshot table already persists
  regime/ensemble/portfolio state on an interval (a lightweight substitute for a
  dedicated time-series DB, sufficient for the time-machine feature).

## NOT built — requires external services (honest scope)
These need infrastructure that cannot be genuinely stood up and *verified* in this
environment, so they were intentionally not stubbed:
- **TimescaleDB / InfluxDB** time-series store for all signals/prices/risk — the app uses
  SQLite; migrating to a real TSDB is a deployment change, not application code.
- **Message queue** (e.g. Redis/Celery) so a slow upstream never blocks the system — a
  Celery scaffold exists in the repo but is not wired as the primary path here.
- **Staging/production split** for validating model changes against history before going
  live — an ops/deployment concern.
- **Sub-second WebSocket push of regime/risk** — the transport exists; pushing computed
  risk deltas intraday needs the message-queue + TSDB pieces above.

## Summary
The one piece with genuine, verifiable value in this environment — **automated
data-quality / bad-tick detection** — is built, tested, and surfaced. The remainder of
Phase 9 is infrastructure that should be delivered as a deployment workstream with the
actual TSDB / queue / staging services provisioned, rather than mocked.
