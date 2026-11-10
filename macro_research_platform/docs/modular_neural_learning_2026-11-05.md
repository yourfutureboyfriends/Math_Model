# Modular neural learning — 5 November 2026

The expanded and research-XL sequence profiles now use this processing chain:

1. Existing market/macro/news ingestion with source publication lags.
2. Training-only normalization and macro PCA, missing-news flags, 24-month windows.
3. Independent encoders for rates/credit, real economy, market prices, macro factors and news. Unknown core fields have their own encoder rather than being dropped.
4. Learned softmax routing and a fusion layer. All specialist representations also enter fusion directly, so a low routing weight cannot completely silence a module.
5. Stacked GRU memory and optional temporal attention over historical observations.
6. Separate task heads for recession, equity drawdown, yields, inflation, oil and unemployment. A head without both known training classes remains unavailable.

The reference profile retains the shared architecture. Every feature must map to exactly one specialist. Architecture/protocol fingerprints isolate model caches, prospective forecast records and promotion evidence. Exposed routing weights describe internal computation, not causal contributions or asset allocations.

## Automatic learning

While the backend runs, a startup check (after three minutes) and daily 08:15 UTC check use the same ingestion contract as training. This uses the program's existing FRED, price and news feeds rather than arbitrary web content. Required features, panel coverage, finite values, input freshness, sufficient history and matured labels are checked first. The digest includes the model configuration, processed inputs and outcomes actually known at the check date; future outcomes cannot trigger a refit.

A changed digest may queue one isolated research rebuild, no more than once per seven days. Durable state survives restarts, unchanged data is skipped, failures back off for 24 hours and failed worker runs can retry. No network fetch or training occurs when ML_AUTO_LEARN=0. Manual rebuilds retain existing controls. A stale cached worker result is not reported as a successful forced rebuild.

Refits retain chronological validation, target-horizon purging, training-only preprocessing, early stopping, regularization, recency weighting, seed budgets, fold caching and an ensemble. Automatic refitting updates the research candidate; existing walk-forward/live-evidence gates and human approval still control which model serves production. It does not rewrite its own code, invent labels, alter risk limits or place trades.

The ML Overview shows processing stages, automatic-learning state, input coverage and latest learned routing when a completed worker result is available. GET /api/v1/ml/deep/status provides the same status; POST /api/v1/ml/deep/learn requests a normal cooldown-respecting check for PM/quant/admin roles.

## Limits and validation

Larger and more modular networks do not guarantee better forecasts. Unit/integration checks verify routing coverage, gradient flow, finite unseen-row predictions, cooldown persistence, disabled mode, failure recovery, cache rejection and existing model evidence handling. A short real-data fit is an execution check, not a claim of investment alpha. Some history is revised rather than first-release data; the current six tasks remain mainly US macro/market forecasts. Fresh global feeds, additional targets and genuine point-in-time histories need separate validation before being added.

Official implementation references:
- https://docs.pytorch.org/docs/main/generated/torch.nn.GRU.html
- https://docs.pytorch.org/docs/2.15/generated/torch.nn.modules.activation.MultiheadAttention.html
- https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit
- https://sklearn.org/1.9/common_pitfalls.html
