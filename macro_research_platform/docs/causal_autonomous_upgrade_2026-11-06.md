# Connected causal and continual-learning upgrade — 6 November 2026

## Execution path

`application.py` remains the isolated daily worker. It captures source observations in `PointInTimeFeatureStore`, updates the existing persistent event/provenance graph, fits or loads `TrainableMacroSystem`, runs replay/EWC-DR or observed-feature reconstruction, and submits the candidate to the existing prospective registry gate. `run_champion_challenger_pipeline` is the common entrypoint. Inferences emit the existing exact artifact manifest plus PROV-JSON entities, activities, usage, derivation and generation records.

The TFT's six heads and four forecast horizons remain authoritative. New components consume its real tensors or feed its graph/static context; no separate mock forecasting model was added. The old served forecast path remains until deployment checks pass.

## Pillar 1 — causal research

`causal.py` implements PCMCI/ParCorr with BH-adjusted MCI tests, train-cutoff filtering, a lagged linear structural mechanism fit and explicit intervention rollout. Economic time feedback is retained in a time-expanded DAG instead of discarding links to force a flattened DAG. `CausalMaskedGATConv` and the main graph encoder support strictly masked directional attention. Local state residuals are distinguished from graph messages. `causal_forecast` sends the fitted, intervened time-expanded graph through the actual TFT heads.

The evidence graph is not itself an identified SCM. Source, document, model and forecast nodes do not possess economic time-series observations and are excluded from discovery. The initial bounded live probe uses eight observed feature nodes, not a fabricated 51-variable panel. The KG now has a dynamic node count; the real run used 67 total graph nodes. Discovered links are hypotheses under PCMCI's assumptions. Interventions are model-conditional research scenarios, not established economic causal effects.

## Pillar 2 — continual training

`advanced_continual.py` provides a Bernoulli-head adaptation of EWC-DR: importance estimation differentiates BCE(-logits, observed_targets), while prediction training uses ordinary logits. Its squared-gradient importance is documented as a surrogate rather than the true likelihood Fisher. Frozen anchors and importance are stored with each immutable bundle.

`StratifiedRegimeReplayBuffer` keeps bounded durable strata while sampling proportional to eligible historical population counts. Regimes are determined by origin-observable inflation/labour conditions, not future recession outcomes. The combined update explicitly weights new supervised loss, replay loss and the EWC penalty. Foundational research examples are retained as training replay; they never become operational historical-PIT evaluation evidence.

## Pillar 3 — debate and world model

`reasoning.py` provides independent drafting, synchronous prior-round critique and consensus weighted by shrinkage Brier scores from previously issued, subsequently matured agent forecasts. Unknown agents begin with equal weights. Evidence IDs are validated. Agent ranges are opinion dispersion, not statistical confidence intervals. The 24 numerical debate inputs enter the TFT static context through a zero-initialized projection; the branch learns only when genuine prospective labelled examples contain those features.

`ML_DEBATE_ENABLED=1` permits up to six configured-provider calls per evidence-bearing day. Provider throttling or schema failure leaves that optional feature unavailable. Public source text, not credentials or private fund information, is supplied to the provider. Model/agent outputs are never converted into observed forecast outcomes.

`MacroVAE` uses recurrent generation and FiLM conditioning on the current main-model GAT embeddings. The application runs a bounded 16-step research fit and four stress-path inferences through the existing task heads. Generated sequences are isolated from replay labels, EWC anchors and promotion evidence. These few paths are a connectivity/robustness probe, not a calibrated tail-risk distribution.

## Pillar 4 — information foraging

`foraging.py` implements a Gymnasium environment, source/STOP actions, finite budgets, duplicate-query protection, belief-update KL, eligible observed Brier gain and compute/provider cost. `model_foraging_environment` evaluates actual origin-frozen source alternatives using the existing model's heads and node embeddings. Stable Baselines3 PPO training is restricted to offline episodes and fixed model identity.

The application has no audited source-alternative replay history yet. Live PPO source selection is explicitly inactive. There is no synthetic substitute for satellite/shipping subscriptions, counterfactual query effects, or matured accuracy rewards. The PPO loop was exercised with test fixtures only; that smoke policy is not a production policy. Collecting an adequate, PIT-audited source-query episode dataset and evaluating its policy prospectively remains necessary before activation.

## Pillar 5 — audit and deployment

`PointInTimeFeatureStore.snapshot_graph` freezes mixed-frequency values, masks missing inputs and preserves source/spec identities. `provenance.py` exports PROV-JSON and supplies `track_provenance`; the actual existing `InferenceAudit` context manager emits equivalent PROV records for serving/research inference. Standard `prov` deserialization is tested.

The purged and embargoed validation implementations remain available in `validation.py`. The daily runner accepts only an attested fold-local validation adapter; it does not relabel the latest revised research history as historical PIT. No such historical-vintage backtest adapter has been supplied. The existing prospective checks are therefore retained, including sample/class requirements, dependent-block uncertainty bounds, origin deduplication, incumbent/reference skill and an atomic registry pointer change. A 2% point improvement alone is insufficient for production promotion.

## Real-data verification

The integrated run on 6 November completed ingestion, graph snapshotting, an eight-step observed-feature reconstruction update and a research forecast. It produced a 67-node graph, an eight-variable PCMCI fit with 35 lagged links, and four VAE stress paths after 16 optimization steps. The deployment gate returned `insufficient_evidence` and retained the incumbent. Drift monitoring correctly reports one observed day rather than inventing a historical drift window. The final rerun also completed the configured-provider debate protocol. All three agents abstained because the available official announcements did not support a macro forecast. That abstention was persisted rather than converted into invented numerical features. The adapter now includes bounded token budgets, supported low reasoning effort for Groq GPT-OSS, and bounded transient rate-limit retries.

Verification: 39 backend tests and 10 frontend tests passed; TypeScript checking and the production build passed. Authenticated ML Overview was visually verified after sign-in: completed run, causal/stress research status, explicit agent abstention, inactive PPO status, the full 24-cell forecast table and raw-cell labels render correctly. The browser reported no captured JavaScript console errors during this check. Visual proof: /private/tmp/ml-overview-verified-2026-11-06.png.

Automated coverage includes directional influence, temporal feedback/intervention mechanics, edge-prior propagation through both attention layers, EWC-DR confident-head importance, replay prevalence, independent debate visibility, zero-initialized debate learning, graph-conditioned VAE/head integration, PROV-JSON parsing, PIT revisions, real PCMCI execution and an offline PPO fit. These checks verify implementation behavior, not investment performance.

## Implementation references

- EWC-DR paper, equations 19–24 and implementation link: https://arxiv.org/html/2603.18596v1
- Tigramite implementation and algorithm assumptions: https://github.com/jakobrunge/tigramite
- Stable Baselines3 PPO implementation/API: https://stable-baselines3.readthedocs.io/en/master/modules/ppo.html
- W3C PROV-JSON Member Submission: https://www.w3.org/submissions/prov-json/

Optional dependency pins are in `api/ml/institutional/requirements-optional.txt`. Local files/SQLite provide auditability, not regulatory WORM retention or distributed high availability.
