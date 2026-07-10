# DATA_LAYER_AUDIT — current state (Phase 0)

Map of every external data dependency **before** the multi-provider overhaul.

## External data calls by provider

| Provider | Where | Asset classes | Key | Single point of failure? |
|---|---|---|---|---|
| **yfinance** (Yahoo) | `main.py` (45 `yfinance` + 27 `yf.`), `providers/yahoo_provider.py`, `price_cache.py`, `websocket_manager.py`, `handlers/market_handler.py`, `signalling/*` | equity, index, fx, commodity (all live/historical prices) | none (keyless) | **YES** — the only price source |
| **FRED** (St. Louis Fed) | `providers/fred_provider.py`, `main.py` (7), `data_pipeline.py`, `models_ml/recession_probit.py`, `handlers/market_handler.py` | macro series (GDP, CPI, yields, M2, …) + release dates | `FRED_API_KEY` (configurable) | **YES** — the only macro source |
| **Finnhub** | `main.py` (11), `signalling/universe_builder.py` (7) | news, recommendations, some alt-data | `finnhub_key` | partial (news only) |

Existing provider package: `api/providers/{yahoo_provider,fred_provider,news_provider}.py` —
each already wraps one API with a typed result (`PriceRecord`/`PriceFetchResult`,
`FREDObservation`/`FREDResult`). **No common contract, no registry, no failover** — callers
import a specific provider class directly.

Config already anticipates more providers (unset): `ALPHA_VANTAGE_KEY`, `POLYGON_KEY` in
`api/config.py`; there is no `provider priority` config.

## Hardcoded symbol universes (to make data, not code)

| Location | What |
|---|---|
| `providers/yahoo_provider.py:54` `SYMBOL_MAP` | macro-alias → yfinance ticker (e.g. `GLD→GC=F`, `SPX→^GSPC`) |
| `calculations/factor_model.py` `FACTOR_PROXIES` | fixed 10-factor ETF set (SPY/IWM/IWD/…) |
| `main.py` / endpoints | fixed lists in `/api/v1/correlation-matrix` (9 assets), `/api/v1/anomalies` (9), `data-quality` (8) |
| `signalling/universe_builder.py` | a signal universe |

~84 occurrences of hardcoded tickers (`^GSPC`, `^NDX`, `^VIX`, `DX-Y.NYB`, `GC=F`, `CL=F`, …).

## Gaps this overhaul targets
1. **No abstraction** — the app talks to yfinance/FRED directly in dozens of places.
2. **Single point of failure** — one yfinance outage breaks every price; one FRED outage breaks every macro series.
3. **Static universe** — adding a symbol/asset class requires a code change.
4. **No provider health / rate-limit visibility.**

## Environment constraint (honest)
The recommended paid/keyed multi-asset providers (Twelve Data, Finnhub full, Polygon,
Alpha Vantage) require API keys **not available in this environment**; `pandas_datareader`
is not installed and Stooq's keyless CSV endpoint returns 404 here. So a *live* second
independent price feed can't be exercised without a key. The overhaul therefore delivers the
**provider-agnostic architecture + failover mechanism** (demonstrable with two independent
keyless Yahoo code paths) and wires keyed providers to activate **zero-code** when a key is set.
