# Machine learning in the forecasting models — research and implementation (3 November 2026)

## What the leading firms and researchers do

| Who | Practice | Applied here |
|---|---|---|
| Federal Reserve Board — Puglia & Tucker, *Machine Learning, the Treasury Yield Curve and Recession Forecasting* (FEDS 2020-038) | Neural networks and tree ensembles beat probit under ordinary k-fold cross-validation, but the ranking **reversed** under a more conservative, time-respecting validation. | Every model is scored walk-forward: refit each January only on months whose 12-month outcome window and a 12-month NBER announcement lag had closed (the equivalent of López de Prado's purge + embargo). |
| Vrontos, Galakis & Vrontos, *Int. J. Forecasting* 2021 | Tree ensembles (random forests, boosting) beat probit/logit out of sample on 1979–2019 US data. | Random forest and LightGBM tested; on this protocol they scored worse than the headline (AUROC 0.77–0.84). |
| Man AHL — *Overfitting and its impact on the investor*; CIO Russell Korgaonkar | Overfitting worsens with low signal-to-noise, non-stationarity and feedback; machine-found signals are compared with what random noise would produce; never too much faith in one model. | The challenger's gain is bootstrapped (3-year blocks) and the variants tried are counted (Bonferroni bar 0.05 / 10). |
| Bailey & López de Prado — Deflated Sharpe ratio; *Advances in Financial ML* (purged CV, embargo, CPCV) | Correct performance for the number of trials, non-normality and sample length; purge overlapping labels. | Variants counted; overlapping 12-month labels never straddle the training/test boundary. |
| Gu, Kelly & Xiu, *Empirical Asset Pricing via ML* (RFS 2020) | Trees and neural networks capture non-linear interactions; ensembles of networks are more stable than single ones. | The challenger is a bag of ten small networks (different seeds), averaged. |
| AQR — Israel, Kelly & Moskowitz, *Can Machines "Learn" Finance?* (2020); *Can Machines Time Markets?* (2024) | Finance has small samples, low signal-to-noise and changing regimes; economic theory and human judgement still matter; ML gains in timing are "evolutionary, not revolutionary". | Inputs are economically motivated (curve, credit, labour, equity momentum); expectations set accordingly. |
| Two Sigma (published regime-modelling work; reported interview practice) | Walk-forward validation; a neural network must justify itself against a regularised linear baseline. | Headline probit ensemble is the baseline every challenger must beat. |
| Bridgewater AIA Labs | The machine makes investment decisions; humans keep control of risk, data and execution, with a manual kill switch. | Promotion is never automatic — a person approves it; the platform's kill switch is unchanged. |
| Federal Reserve SR 11-7 model-risk guidance; Citadel / Millennium research roles | Champion / challenger before production; ongoing monitoring of live models for decay and data drift; full retraining lifecycle. | The challenger runs in shadow mode, retrains monthly, logs one forecast a month that can never be rewritten, and is scored as outcomes arrive. |
| Bank of England — Buckmann & Joseph, *An interpretable ML workflow* (SWP 984, 2022) | Model comparison, feature importance and Shapley decompositions to explain ML forecasts. | Each forecast shows how much every input moved it (occlusion approximation of a Shapley attribution). |
| Raftery et al.; Guérin & Leiva-Leon (dynamic model averaging of recession probabilities) | Re-weight models over time by recent predictive performance. | Tested; it chased whichever model had just done well and scored worse (Brier skill +0.14 vs +0.26). Not used. |

## Results on this platform (walk-forward 1985–2025, 1974+ features)

| Model | AUROC | Brier skill vs base rate | Since 2005 | 2013–25 |
|---|---|---|---|---|
| Headline probit ensemble (champion) | 0.867 | +0.26 | +0.09 | −0.57 |
| Bagged neural network (rich inputs) | 0.886 | +0.22 | −0.12 | −1.58 |
| Regularised logistic (rich inputs) | 0.898 | +0.18 | −0.12 | −1.58 |
| LightGBM | 0.765 | 0.00 | −0.20 | −1.38 |
| Random forest | 0.844 | +0.09 | −0.34 | −1.57 |
| Dynamic model averaging (all five) | 0.872 | +0.14 | −0.19 | −1.59 |
| **Headline + neural network, half and half** | **0.901** | **+0.36** | **+0.11** | −0.82 |

(Scores differ slightly from the live headline's record because the extra inputs start in 1974.)

The blend's Brier improvement: +0.038 (1985–99), +0.028 (2000–12), **−0.022 (2013–now)**; overall not
significant — year-block bootstrap P(no gain) ≈ 0.10, against a bar of 0.005 once ~10 variants are allowed for.

## What was implemented

`api/models_ml/recession_challenger.py` — the bagged neural network as a **shadow challenger**:

- retrains every month on the newest labelled data (fixed hyperparameters; nothing tuned on the test period);
- logs one forecast per month to `model_shadow_forecasts` (first value kept; a live record is not revisable) and
  scores it against the headline as each 12-month window closes;
- shows what moved each forecast;
- **promotion rule**: eligible only when the walk-forward gain is significant after the allowance for variants
  tried **and** it has beaten the headline on at least 24 live-scored months — then a person approves it.

Shown in Macro → Cycle & Systemic Risk; `GET /api/v1/models/recession/challenger`; scheduled daily at 06:30 UTC
(`recession_challenger`).

## Sources

- Puglia & Tucker (2020): https://www.federalreserve.gov/econres/feds/files/2020038pap.pdf
- Vrontos, Galakis & Vrontos (2021): https://econpapers.repec.org/RePEc:eee:intfor:v:37:y:2021:i:2:p:647-671
- Man AHL, Overfitting and its impact on the investor: https://www.man.com/insights/overfitting-and-its-impact-on-the-investor
- Man AHL on ML signals vs noise: https://www.wealthmanagement.com/financial-technology/machine-learning-separating-the-signal-from-noise-in-investing
- Israel, Kelly & Moskowitz (2020): https://www.aqr.com/Insights/Research/Journal-Article/Can-Machines-Learn-Finance
- AQR, Can Machines Time Markets? (2024): https://www.aqr.com/Insights/Research/Alternative-Thinking/Can-Machines-Time-Markets-The-Virtue-of-Complexity-in-Return-Prediction
- Gu, Kelly & Xiu (2020): https://www.nber.org/papers/w25398
- Two Sigma, A Machine Learning Approach to Regime Modeling: https://www.twosigma.com/wp-content/uploads/2021/10/Machine-Learning-Approach-to-Regime-Modeling_.pdf
- Bridgewater AI: https://www.bridgewater.com/research-and-insights/artificial-intelligence
- Bank of England SWP 984: https://www.bankofengland.co.uk/-/media/boe/files/working-paper/2022/an-interpretable-machine-learning-workflow-with-an-application-to-economic-forecasting.pdf
- Guérin & Leiva-Leon (model averaging of recession probabilities): https://mpra.ub.uni-muenchen.de/59361
- Purged cross-validation (López de Prado): https://en.wikipedia.org/wiki/Purged_cross-validation
