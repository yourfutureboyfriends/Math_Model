# Autonomous macro learning: implementation package

The application integration is `application.py`, supervised by `api/ml/autonomous.py` and the existing APScheduler. It uses the app's configured AI provider, an exchange calendar, versioned SQLite/PIT stores and immutable local model bundles. The standalone Prefect adapter remains optional. The new TFT/GAT stays in research until prospective deployment checks pass; integration alone does not replace the incumbent forecast.

Use ML → Overview → Autonomous daily learning for live state and an authorized manual run. `ML_AUTONOMOUS_ENABLED=0` disables scheduling. The backend must remain running. Public source text is sent to the configured extraction provider; the initial live integration used Groq. Licensed news providers require their own configured access.

## 1. Data ingestion

- `ingestion.py`: allowlisted HTTPS RSS discovery, bounded source downloads, recent-publication filtering, HTML text extraction, structured LLM events, evidence-substring checks, source/prompt/model hashes and durable extraction cache. Source text receives no tools or execution privileges.
- `data.py`: append-only bitemporal observations; queries enforce both release and receipt times. Feature specs control mixed-frequency aggregation, staleness and carrying. New records imported today are not retrospectively available in an operational backtest.

```python
import os
from pathlib import Path
from langchain.chat_models import init_chat_model
from api.ml.institutional.ingestion import EventBatch, FinancialIngestionAgent, Source

llm = init_chat_model(os.environ['MACRO_EXTRACTION_MODEL'], temperature=0,
                      max_tokens=4096, timeout=60, max_retries=2)
ingestor = FinancialIngestionAgent(
    llm.with_structured_output(EventBatch),
    extractor_version=os.environ['MACRO_EXTRACTION_VERSION'],
    archive=Path('data/autonomous/documents'),
)
sources = [Source('Fed press', 'https://www.federalreserve.gov/feeds/press_all.xml',
                  ('www.federalreserve.gov',))]
```

Supply a version-pinned provider integration through environment credentials. LangChain and Prefect are optional dependencies and are not installed in the current environment. Add licensed financial-news feeds to the source configuration; the default public sources cover Fed press releases, speeches and release announcements. Speeches are not a replacement for unreleased central-bank deliberation transcripts.

Event timestamps are assigned after extraction. The training cutoff is taken after ingestion, not backdated to the earlier market close. Announced future actions remain explicitly distinguished from observed actions. Sentiment and LLM confidence are uncalibrated extracted attributes; neither is an observed market outcome or a training target. An exact supporting quote is a provenance check, not a guarantee of entailment or factual correctness.

## 2. Graph evolution

`graph.py` persists deduplicated events, creates new entity/event/action nodes and writes content-addressed origin snapshots. Evidence and co-occurrence weights decay; correlations use only days with successful configured-source collection. The derived graph is capped at 256 nodes and pruned without deleting the historical ledger. The neural adapter emits fixed-width 20-dimensional node attributes, including action type, announced/observed status, extraction attributes, weighted degrees, age and an optional PIT-standardized value/missing flag.

```python
from api.ml.institutional.graph import DynamicEventGraph, graph_tensors

graph_store = DynamicEventGraph(Path('data/autonomous/graph'),
                               core_nodes=('feature:oil', 'feature:rates'),
                               half_life_days=30, max_nodes=256)
graph_store.append(events, cutoff=cutoff, sources_complete=True)
graph, graph_digest = graph_store.snapshot(cutoff)
node_features, edge_index, node_ids = graph_tensors(graph, cutoff)
# Keep this order identical to edge_index; supply as the model's edge_weight.
edge_weight = [graph.edges[a, b]['weight'] for a, b in graph.edges]
```

The current provenance graph contains source/model/forecast/paper relationships. Do not label these causal economic dependencies or feed future forecast nodes into the GNN. Supply an approved variable/node whitelist and current PIT attributes through the adapter. Event associations are a separate evidence layer; they do not establish oil→rates→employment causality. `rolling_graph_statistics` exports origin-filtered PageRank, degrees and past-window edge-strength momentum; a missing baseline remains missing.

## 3. Continual training

- `model.py`: TFT-style adapter with GRNs, specialist VSN, real sparse expert dispatch, GAT origin covariates, LSTM encoder/decoder, shared-value causal temporal attention and 1/3/6/12-month task heads. GAT is implemented in ordinary PyTorch; no PyG installation is required. The node cap is explicit because attention is dense in N.
- `training.py`: trainable multi-task wrapper and bounded fresh-reset trainer. The learnable task-loss weights are registered model parameters. A fine-tune must freeze preprocessing and schema; full resets refit transforms on training data only and rebuild optimizer/EWC state.
- `continual.py`: durable stratified replay; only eligible observed labels; per-example empirical Fisher; immutable EWC anchor storage; bounded daily fine-tuning on a challenger copy.
- `losses.py`, `validation.py`, `uncertainty.py`: masked focal/uncertainty-weighted objectives, purged and label-aware walk-forward splits, fold-local fitting, and frozen-model conformal wrappers.

```python
from copy import deepcopy
from api.ml.institutional.continual import ReplayBuffer, EWC, daily_fine_tune

replay = ReplayBuffer(Path('data/autonomous/replay.sqlite'), capacity=10_000)
challenger = deepcopy(champion)  # Never mutate the serving instance.
anchors = replay.sample(256, cutoff=cutoff, schema=feature_schema)
ewc = EWC.estimate(champion, anchors, lambda m, t: m.loss(t, fisher_nll=True))
report = daily_fine_tune(
    challenger, newly_matured_examples, replay, lambda m, t: m.loss(t),
    cutoff=cutoff, schema=feature_schema, ewc=ewc,
)
```

Each experience is one forecast origin with its frozen input tensors and observed target mask. Unknown cells are masked, not assigned pseudo-labels. Revisions require new immutable identities. Stratified replay changes sampling prevalence, so probability calibration uses an untouched natural-prevalence cohort. Save the foundational Fisher/anchor with its source-model and schema identity; do not estimate Fisher from the new unlabeled news. Full resets use `fit_from_scratch` without old optimizer/EWC state.

The existing six single-horizon labels cannot simply be broadcast to four horizons. Define and version all 24 target cells, including event windows and actual label-availability dates. Supply only origin-known decoder covariates such as the calendar, never future macro values. Without new matured forecast labels, the application can update the shadow encoder by masked observed-feature reconstruction, with forecasting heads fixed. It never treats extracted news or its own predictions as observed future outcomes.

Conformal binary outputs are label sets, not a confidence interval around a recession probability. Regression intervals require a separate, untouched calibration cohort and frozen model identity. Exchangeability-based coverage is not an unconditional guarantee for macro time series. Insufficient calibration returns full/unbounded sets with an explicit status.

## 4. Autonomous deployment

`pipeline.py` implements the daily controller. `application.py` implements `LearningPorts` using the application feature sources, 24 explicit horizon targets, immutable bundles, a prospective forecast ledger and a serving adapter. Historical foundation inputs are currently revised research history; only newly captured observations are operational PIT evidence.

Sequence: session check → deduplicated ingestion → graph snapshot → data-quality checks → persisted PSI/JSD monitor → fine-tune or scratch reset → register challenger → last-30-day diagnostic plus longer walk-forward/prospective evidence → automatic statistical gate → atomic registry decision. Drift resets have a seven-day cooldown. Provider/label/evidence failures retain the champion without a human approval step.

`registry.py` uses paired cohorts, target-identity deduplication, per-cell class/sample requirements, prospective shadow evidence, a Brier improvement margin, dependent-block bootstrap bounds for Brier/AUC/Sharpe improvements, and a trial alpha budget. A 30-day sample or 2% Brier improvement alone cannot promote. Default 12-origin blocks assume monthly forecast origins and 12-month overlap; configure blocks to the actual target overlap if evaluating daily origins. Returns must be one cost-adjusted portfolio excess return per day, not duplicated across task heads. Low class counts, undefined Sharpe, unstable bootstrap draws or insufficient tail resolution produce a hold decision. Bootstrap evidence under nonstationarity is approximate, not a universal statistical certificate.

The registry verifies artifact hashes at registration and again before promotion. Transactions compare the expected champion pointer, archive the prior artifact and persist an idempotent decision. The serving adapter must verify the new bundle and atomically replace a loaded immutable model; it must never load untrusted pickled model objects. Rollback is a new audited compare-and-swap to an existing verified artifact, not deletion of history.

```python
from api.ml.institutional.pipeline import prefect_flow

# pipeline is AutonomousDailyPipeline with audited LearningPorts and a maintained
# market_close(date) adapter. Calendar returns None on exchange holidays.
flow = prefect_flow(pipeline)
flow.serve(name='macro-daily-learning', cron='*/10 12-17 * * 1-5',
           timezone='America/New_York')
```

This polling window handles regular and early US closes. The calendar, not the cron expression, decides whether a session is valid. DST follows New York time. A persistent process lock and run journal suppress duplicate daily work; a crashed run can retry and a completed promotion is recovered idempotently. A single-host SQLite/file-lock implementation is supplied. For multiple workers/hosts, replace it with a transactional shared registry, advisory lock/outbox and immutable object storage.

## Inference lineage

Use `InferenceAudit` around every inference, after loading and verifying all artifacts. The manifest records data, feature logic, preprocessing, graph, weights, calibration, target schema, source tree, configuration and code revision. Started/completed records are hashed, fsynced and published without clobbering prior files; incomplete records expose crashes. An audit-write failure raises before the request can return a prediction. Local files are not a WORM or cryptographic signing service: use an access-controlled immutable sink in production.

## Validation and deployment status

The core tests run locally with PyTorch, NumPy, Pandas, NetworkX, scikit-learn and Pydantic. External LangChain model calls, Prefect orchestration and live automatic deployment have not been exercised; these integrations are not configured. `config.json` is disabled by default and lists activation prerequisites. The current app's served model and existing promotion policy remain unchanged.

Research/code references: [Google TFT implementation](https://github.com/google-research/google-research/blob/master/tft/libs/tft_model.py), [GAT paper](https://arxiv.org/abs/1710.10903), [sparse MoE](https://arxiv.org/abs/1701.06538), [EWC](https://arxiv.org/abs/1612.00796), [uncertainty-weighted losses](https://arxiv.org/abs/1705.07115), [conformal implementation guidance](https://arxiv.org/abs/2107.07511), [LangChain structured output](https://docs.langchain.com/oss/python/langchain/structured-output), [Prefect schedules](https://github.com/PrefectHQ/prefect/blob/main/docs/v3/concepts/schedules.mdx), [Fed source feeds](https://www.federalreserve.gov/feeds/feeds.htm).

## Running the checks / deployment entry point

From `macro_research_platform`:

```sh
../.venv/bin/python -m pytest api/tests/test_institutional_pipeline.py -q
../.venv/bin/python -m api.ml.institutional.smoke
```

Verified locally: **17 tests passed**. A separate synthetic 51-node, 11-specialist forward/backward run produced finite `[2, 4, 6]` forecasts through a 473,789-parameter model. These checks cover code contracts and execution, not investment accuracy or live provider reliability.

After implementing the required integration adapters, install the optional integrations in an isolated deployment image, resolve a lockfile, point `MACRO_PIPELINE_FACTORY` at the trusted `build_pipeline(config)` factory, and enable a reviewed configuration:

```sh
python -m api.ml.institutional.serve --config deployment_config.json
```

The bundled disabled configuration starts no job. No changes were made to the current app's active scheduler, model pointer or approval policy. The new registry/controller supports unattended promotion after its evidence gates pass; it is not silently substituted for the active application registry.


## Connected causal/continual extensions (6 November 2026)

The application worker now runs the connected PCMCI/scenario and graph-conditioned VAE research probes. It uses the EWC-DR binary adaptation and population-proportional regime replay for supervised updates. Optional provider debate inputs feed the existing TFT through a zero-initialized static projection; agents can explicitly abstain. Every audited inference also emits PROV-JSON. The Gymnasium/SB3 source-selection adapter consumes real frozen query alternatives through the same heads; live PPO selection remains inactive without an audited episode dataset. See `docs/causal_autonomous_upgrade_2026-11-06.md` for integration boundaries and real-run results.
