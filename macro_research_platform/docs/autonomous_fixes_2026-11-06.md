# Autonomous learning fixes and replay integration — 6 November 2026

## Corrected behavior

- Daily ingestion now captures actual per-source query alternatives with a frozen observation snapshot, preprocessing and neural checkpoint. Independent graph copies prevent one source's fetched events from leaking into another source's alternative. All alternatives use the same evaluation clock, so elapsed decay alone cannot create a query benefit. The originally captured checkpoint identity is preserved even if the daily learner creates a newer challenger afterward.
- Source records include actual receipt/inference times, source event IDs, request/document counts, graph snapshots, safe tensor files and SHA256 identities. Successful empty source checks remain valid observations. Failed or skipped sources cannot form a complete episode.
- Using exactly the document budget no longer produces a false failure. Remaining source feeds are still checked; only actually unprocessed eligible documents produce a budget warning.
- Clock-only graph age/edge decay changes no longer trigger another weight update. Observations/schema/event identity determine new-information eligibility. Inference still uses current age/decay.
- Causal scenarios now include a paired unchanged-mechanism control with identical model weights and time-expanded graph topology. Reported differences remain model-conditional research sensitivities, not identified economic effects.
- Debate score selection no longer lets an earlier abstention suppress the first eligible forecast for an entire month. Cached debate outputs with future availability are rejected.
- Learning completion and deployment waiting are displayed separately. Source collection days, verified episodes and outcome-labelled monthly origins are distinct UI counts.

## Replay and automatic research-policy training

`source_replay.py` verifies saved tensor digests, source/inference availability, aligned query contexts and forecast/embedding schemas. It joins only first-observed outcomes available by the training cutoff and masks labels already known at the query origin or not yet available. Corrupt, future and incompatible records are counted separately.

The frozen replay environment uses probabilities and embeddings actually recorded at collection time. It does not rerun old queries through a later forecast model or make provider requests during PPO training. One source action ends an episode, preventing arbitrary combinations of independently measured alternatives. Repeated manual/daily runs do not become independent monthly target origins.

After at least 24 eligible monthly origins with sufficient observed target cells, the daily worker automatically fits a bounded offline research PPO candidate, writes its weights/manifest, and deduplicates subsequent fits by dataset identity. The policy uses masked mean/variance of GAT embeddings, avoiding accidental node ordering or padding effects. Request costs are normalized compute/request units, not monetary costs.

Research-policy training does not activate live source selection. Prospective utility/cost evidence is still required. Forecast deployment independently retains its existing paired-sample, calibration, class-count and statistical gates. These evidence requirements cannot be replaced with synthetic outcomes.

## Verification

- 47 backend tests passed, including source isolation, captured checkpoint identity, exact-budget handling, clock-only learning deduplication, null-intervention parity, source-record corruption/future-label masking, one-query replay, graph permutation/padding invariance and idempotent research-policy publication.
- TypeScript checking and the production frontend build passed. Status-panel tests cover collection/outcome counts and deployment waiting.
- Real ingestion/learning completed without a worker failure. Five query episodes were integrity-verified across Fed press, speeches and data-announcement feeds, correctly representing one observed collection day. No records were rejected. Outcome-labelled monthly origins remain zero.
- A repeated live refresh with unchanged observations skipped retraining and preserved the same shadow model ID, while continuing source collection.

Existing limitations remain explicit: historical foundation inputs are revised research history; causal/stress outputs are research-only; source-query outcomes need time to mature. No production model or live PPO policy was force-promoted.
