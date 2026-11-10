# Continual financial learning: papers mapped to released implementations

Reviewed 5 November 2026. This review distinguishes a published algorithm, its authors' released research code, and this application's implementation. Released research code is not evidence that a firm uses the same system in production. No external repository was installed or executed during this review.

## 1. Microsoft Qlib: separate research, training and serving

[Paper](https://arxiv.org/abs/2009.11189) · [Pinned online manager](https://github.com/microsoft/qlib/blob/54355232463878d2eebb91fe0ee5fa7fa1f5976c/qlib/workflow/online/manager.py) · [Pinned strategy](https://github.com/microsoft/qlib/blob/54355232463878d2eebb91fe0ee5fa7fa1f5976c/qlib/workflow/online/strategy.py)

Implementation inspected: `OnlineManager.routine`, `OnlineStrategy.prepare_tasks`, `prepare_online_models`, and `RollingStrategy`. Task creation, training, selecting serving models and preparing signals have separate responsibilities. The strategy explicitly discusses training at T and switching at T+1. “Online” here does not imply updating neural weights on every tick.

Application decision: retain separate provider, inference, research and promotion stages. The new provider supervisor follows this separation; it is our implementation, not an integration of Qlib. A successful training job must not itself be treated as approval to replace a served forecast.

## 2. SJTU DoubleAdapt: actual incremental adaptation

[KDD paper, methodology and Appendix C](https://arxiv.org/html/2306.09862v3) · [Pinned training implementation](https://github.com/SJTU-DMTai/DoubleAdapt/blob/e20b6e46ccbd2b6b8180ff3db62f68b16721684c/src/model.py#L280) · [Pinned adapters](https://github.com/SJTU-DMTai/DoubleAdapt/blob/e20b6e46ccbd2b6b8180ff3db62f68b16721684c/src/net.py#L25)

`DoubleAdaptManager._run_task` performs a differentiable inner update using `higher.innerloop_ctx`, produces predictions, then updates its meta-learners. `meta_end` and `mask_y` restrict the labels used by the outer update; it explicitly handles an empty labelled set. `IncrementalManager.fit` also trains on validation tasks after selecting its offline checkpoint.

The released adapters use prototype/cosine gates and affine feature/label transformations. The base objective is MSE and the implementation assumes CUDA. Those details matter: our six binary event heads use masked BCE and run on CPU as well. Applying their continuous label transformation to binary event targets would change the meaning of our probabilities.

Application decision: a feature-only adapter is a plausible experimental challenger. Keep binary targets intact, use matured labels, and compare against both frozen and periodically refitted models. Our new scheduler remains full refitting; it is not DoubleAdapt. The current 85/15 early-stopping fit also warrants a separately tested final-fit protocol: choose training length on validation, then refit using all eligible history, without contaminating reported out-of-sample results.

## 3. Microsoft / UW–Madison DDG-DA: learn historical sample weights

[AAAI paper, sections 3.1–3.2 and Appendix D](https://arxiv.org/html/2201.04038) · [Pinned meta-network](https://github.com/microsoft/qlib/blob/54355232463878d2eebb91fe0ee5fa7fa1f5976c/qlib/contrib/meta/data_selection/net.py#L9) · [Training and time reweighter](https://github.com/microsoft/qlib/blob/54355232463878d2eebb91fe0ee5fa7fa1f5976c/qlib/contrib/meta/data_selection/model.py)

The paper targets predictable distribution drift, rather than assuming every abrupt change can be forecast. In code, `TimeWeightMeta` converts historical performance into constrained weights. `PredNet.forward` fits a differentiable weighted linear proxy through a regularized matrix solve. This concrete implementation reweights historical observations; it does not manufacture unknown future outcomes.

Application decision: compare learned time weights against uniform, fixed recency and rolling-window baselines. Learn weights within chronological meta-training folds only. Our fixed recency weighting is not DDG-DA. Monthly macro data provide far fewer independent observations than a daily stock panel, so increasing parameter count is not automatically justified.

## 4. University of Alberta / Amii: Continual Backpropagation

[Nature paper](https://doi.org/10.1038/s41586-024-07711-7) · [Pinned generate-and-test implementation](https://github.com/shibhansh/loss-of-plasticity/blob/3138c5556859e0e2918d40f113b40699b6575cfa/lop/algos/gnt.py#L111) · [Linear-layer variant](https://github.com/shibhansh/loss-of-plasticity/blob/3138c5556859e0e2918d40f113b40699b6575cfa/lop/algos/cbp_linear.py)

`GnT` tracks unit utility and age, selects eligible low-utility units, reinitializes incoming weights, and zeros outgoing weights. Its optimizer-state reset is conditional on the custom `AdamGnT` optimizer: replacing weights alone is insufficient. The newer `CBPLinear` hook variant should not be assumed to reset an arbitrary optimizer's moments.

Application decision: first measure inactive units, activation diversity and validation deterioration during warm starts. These experiments establish a continual-learning mechanism, not financial trading profitability. Our recurrent GRU is not the feedforward structure assumed by this code; arbitrary replacement of GRU units could disrupt coupled gates. Current full refits already reinitialize weights, so neuron replacement is not an immediate production priority.

## 5. JPMorgan ABIDES-Gym: execution, not a provider-fed forecasting engine

[ICAIF paper, section 4.2](https://arxiv.org/html/2110.14771) · [Pinned execution environment](https://github.com/jpmorganchase/abides-jpmc-public/blob/f9cbe51342b7dedd9587e4e069040d68a5c6477f/abides-gym/abides_gym/envs/markets_execution_environment_v0.py)

Inspected `SubGymMarketsExecutionEnv_v0`: actions map to market orders, limit orders or waiting; state construction includes execution progress, time, order-book imbalance, spread and price movement. Reward uses fills relative to the entry benchmark, with terminal adjustments for incomplete or excessive execution. This is an actual market-interaction simulator, not merely a proposed architecture.

Application decision: useful later for execution and transaction-cost experiments with calibrated order-book data. It does not solve monthly macro forecasting or supply live financial data. The public repository is archived, so dependency compatibility and market calibration would need separate work before integration.

## 6. Oxford–Man Deep Momentum Networks: strategy-level objective

[Paper, sections IV and VI](https://arxiv.org/html/1904.04912)

The implementation described in the paper learns volatility-scaled positions and optimizes a Sharpe-based objective, with turnover regularization to account for trading costs. Its reported experiments use a futures universe. An original author-maintained implementation for this particular paper was not verified in this review; third-party reproductions are not labelled official.

Application decision: relevant to a future portfolio-positioning layer. Keep calibrated event-probability estimation separate from return/cost optimization. The paper's performance should not be transferred to our data or targets as an accuracy claim.

## What changed in this application

The provider supervisor now defines source-specific refresh intervals, bounded subprocesses, schema/coverage/freshness checks, last-good preservation, failure backoff, and content-addressed snapshots. Quote context is separate from monthly training features. Accepted feature changes can trigger inference using frozen preprocessing. Research eligibility is checked every six hours; newly matured outcomes can allow a daily refit, otherwise weekly limits apply. Existing model-promotion gates remain.

Tests also cover labels that become eligible during a refit cooldown: they must remain pending instead of disappearing when the next observation is recorded. These are engineering foundations for continual learning, not a reproduction of the advanced algorithms above.

## Evaluation protocol before adopting an adaptive challenger

1. Build timestamped feature vintages and target-availability records. New snapshots preserve observations from now onward; they cannot reconstruct historical release vintages or remove revision bias in older data.
2. At each forecast origin, issue and persist predictions before any update using newly released outcomes. Train transformations, PCA and adaptation parameters using eligible data only.
3. Compare frozen, periodic full-refit, fixed-recency and adaptive challengers on identical prospective cohorts. Purge overlapping target horizons at validation boundaries.
4. For event probabilities, measure Brier score, log loss, calibration and discrimination by task and regime. For strategies, additionally measure turnover, cost-adjusted returns and drawdowns.
5. Record seeds, source digests, code/configuration identity, runtime and uncertainty. Keep an untouched final interval and a prospective shadow period. Promote only when improvements persist beyond tuning data.

Priority: point-in-time data and prospective evaluation first; learned historical weights second; feature-only incremental adapters third; plasticity intervention only if measured warm-start deterioration warrants it. Larger networks and more frequent training are hypotheses to test, not reliability guarantees.
