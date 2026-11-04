# Backend performance — 30 October 2026

## Implemented

- Read-only Markets requests share one blocking computation per function, arguments and fund while it is running. Client timeouts/disconnects do not cancel work that other callers need or start replacement copies while the original worker is still running.
- At most 16 distinct Markets computations are active/queued per event loop through this adapter. New distinct work beyond this limit receives HTTP 503 with Retry-After: 2. Existing callers can still join a running computation. This limit does not apply to order-submission paths.
- The async TTL decorator now coalesces misses in both inline and offloaded modes, isolates cancelled waiters, starts expiry at completion, uses a monotonic clock, and bounds completed cache entries to 2,048. Cross-loop cache mutation is protected by a lock. Fund identity remains part of the key.
- The threaded market cache retains its per-key lock until the owner and all waiting callers leave. This closes a window where a second lock could appear before the first computation published its result.
- Background market refreshes use four workers and a maximum of 16 outstanding refreshes instead of starting an unbounded daemon thread per key. Refreshes retain caller context. Stale-while-revalidate responses explicitly report stale status and age.
- Exchange calendars cache static holiday dates by calendar and year (128 entries), while recalculating open/closed status, countdowns and local time on each request. Market session status is never cached as static data.

## Measurements

The reproducible synthetic benchmark (`scripts/benchmark_backend_concurrency.py`) uses 64 simultaneous identical requests and an 80ms blocking provider. It does not call live vendors or alter portfolio data.

| Measurement | Previous adapter | Shared adapter |
|---|---:|---:|
| Provider calls | 64 | 1 |
| Total burst time | 336.78 ms | 90.21 ms |
| Unrelated worker probe | 242.34 ms | 0.22 ms |

Raw results: [benchmark JSON](benchmarks/backend_concurrency_2026-10-30.json). These numbers demonstrate reduced duplicated work and worker contention; they are not a prediction of end-to-end live-feed speed.

After the initial API restart, the exchange calendar returned HTTP 200 in 17.52 seconds cold, 21 ms warm and 19 ms through the frontend proxy. Model-parameter metadata returned through the proxy in 16 ms. These are smoke timings, not controlled before/after comparisons. Cold calendar initialization and startup contention remain separate costs.

## Validation and limits

Tests cover duplicate bursts, timeout/cancellation isolation, fund separation, bounded capacity, cache expiry and eviction, threaded lock cleanup, bounded background refreshes, error status contracts, stale metadata and holiday-cache keys. Existing dashboard, model, market-data and fund tests are included.

The initial broad run had one live-network failure: the cross-listing test could not resolve Yahoo's FX lookup. Offline tests are run separately; that failed live-network check is not claimed as passed. Existing Pydantic and UTC deprecation warnings remain.

Concurrency coordination is process-local. Multiple API workers would still need shared coordination for expensive provider requests. A Python thread cannot be forcibly stopped: slots remain occupied until underlying work completes, and provider-level timeouts remain necessary. No financial formulas, trading permissions or order workflows were changed in this pass.

Final regression result: **104 passed, 1 live-network test deselected**. Python compilation and `git diff --check` passed. The local API was restarted with the changes.

After the final restart, smoke checks again returned HTTP 200: exchange calendar through the app proxy in 66 ms, and model metadata directly in 69 ms. These reflect that particular startup/load state, not a guaranteed latency target.
