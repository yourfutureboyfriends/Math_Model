# DATA_LAYER_REPORT — multi-provider, failover-capable data layer

Delivers the **provider-agnostic architecture + automatic failover** the overhaul is about.
The rest of the app can now ask a registry for data by symbol + asset class instead of
calling yfinance/FRED directly, and no single provider failure returns a user-visible error
while a fallback exists. See [DATA_LAYER_AUDIT.md](DATA_LAYER_AUDIT.md) for the before-state.

## Providers integrated + fallback chain

| Provider | Role | Asset classes | Priority | Key | Status |
|---|---|---|---|---|---|
| `yahoo_download` | primary prices (existing `YahooFinanceProvider`, yfinance) | equity, index, fx, commodity, crypto | 1 | none | ✅ live |
| `yahoo_chart` | **independent keyless fallback** (direct Yahoo chart JSON — different code path) | equity, index, fx, commodity, crypto | 2 | none | ✅ live |
| `alpha_vantage` | keyed multi-asset fallback | equity, index, fx, crypto | 3 | `ALPHA_VANTAGE_KEY` | ⏸ inactive (no key) — activates zero-code when key is set |
| `fred` | macro series | macro | 1 | `FRED_API_KEY` | ✅ live |

Routing: `ProviderRegistry.get_quote(symbol, asset_class)` tries the highest-priority
**healthy** provider whose `asset_classes` include the request; on exception / empty / rate-limit
it records the error and falls back to the next, logging every fallback. `alpha_vantage`
reports `healthy=False` until its key exists, so it is simply skipped today.

**Common contract** (`api/providers/registry.py`): `Quote`, `TimeSeries`, `MacroSeries`,
and a `DataProvider` Protocol. Adding a provider = implement the Protocol + `register()` —
no change to any calculation. Adapters live in `api/providers/adapters.py`.

## Surfaced
- `GET /api/v1/providers` — every provider's health, priority, asset classes, served/error/**fallback** counters.
- `GET /api/v1/quote?symbol=&asset_class=` — a quote routed through the registry; the serving provider is returned in `source` (feeds the lineage popover). Explicit *"Data unavailable — all providers … unreachable"* if all fail (Phase 6, never a fabricated number).
- **Data Providers** panel (System tab) renders the table live.

## Verification evidence

1. **Failover (unit, deterministic):** `test_provider_registry.py` (6 tests) — primary serves when healthy; on primary **exception** or **empty** result the registry serves from the backup and records the fallback; all-fail → `None` (honest); unhealthy provider skipped; routing by asset class.
2. **Failover (live, organic):** `GET /api/v1/quote?symbol=AAPL` → `yahoo_download` returned empty, the registry **auto-fell-back to `yahoo_chart`** and served price 314.8 — user got a valid quote, and `/api/v1/providers` showed `yahoo_download errors=1, fallbacks_triggered=1`, `yahoo_chart served=1`. `SPX` (index alias) served by `yahoo_download` at 7572. Rendered live: "DATA PROVIDERS 3/4 active".
3. **Graceful degradation:** with no `ALPHA_VANTAGE_KEY`, that provider is `healthy=false` and skipped; a fully-failed class returns the explicit unavailable message.

`182` backend unit tests pass; frontend build passes.

## Remaining single-point-of-failure gaps (honest)

| Gap | What's needed |
|---|---|
| Prices still ultimately depend on Yahoo | `yahoo_download` + `yahoo_chart` are independent code paths but the same origin. A **truly independent** live feed needs a keyed provider (Twelve Data / Finnhub / Polygon / Alpha Vantage) — the adapter + registry slot is built; just set the env key. |
| Macro still only FRED | A second macro source (e.g. DBnomics, keyless) would remove the FRED SPOF — same adapter shape. |
| Crypto depth | No dedicated crypto provider wired (Yahoo covers majors via `-USD`); a CoinGecko adapter (keyless) is the next add. |
| **Phase 2 dynamic universe** (symbols CRUD + search), **Phase 3 macro breadth registry**, **Phase 4 rate-limit tracking**, **Phase 5C priority reorder UI** | Scoped, not built this pass — the registry is the foundation they hang off. The existing `ttl_cache` + background warm loops already cover much of Phase 4's caching intent. |

The architecture is the deliverable: **the app no longer talks to a single API directly, and the failover mechanism is real and demonstrated.** Broadening the provider roster is now configuration/keys, not a rewrite.
