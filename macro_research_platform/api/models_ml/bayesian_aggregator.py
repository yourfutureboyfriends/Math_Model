"""
Bayesian Model Averaging for macro signal ensemble.

Academic basis:
  Raftery, A.E., Gneiting, T., Balabdaoui, F. &
  Polakowski, M. (2005). Using Bayesian Model Averaging
  to Calibrate Forecast Ensembles. Monthly Weather
  Review, 133(5), 1155-1174.

  Hoeting, J.A., Madigan, D., Raftery, A.E. &
  Volinsky, C.T. (1999). Bayesian Model Averaging:
  A Tutorial. Statistical Science, 14(4), 382-417.

  Diebold, F.X. & Lopez, J.A. (1996). Forecast
  Evaluation and Combination. Handbook of Statistics,
  14, 241-268.

Key improvements over fixed-weight averaging:
  - Weights update automatically based on accuracy
  - Poor models get downweighted over time
  - Full posterior distribution not just point estimate
  - Explicit model uncertainty quantification
  - Weights converge to best model as data accumulates

Bayes update rule applied here:
  log w_i(t) = discount * log w_i(t-1) + log P(y|model_i)
  weights = softmax(log_weights)
"""

import numpy as np
import sqlite3
import logging
from datetime import datetime
from scipy.special import softmax

logger = logging.getLogger(__name__)


class BayesianModelAverager:
    """
    Bayesian Model Averaging ensemble for macro signals.

    Maintains posterior weight distribution over models.
    Weights updated via Bayes rule each time a prediction
    outcome is observed.
    """

    MODELS = [
        'hmm_regime',
        'recession_guard',
        'kalman_filter',
        'momentum_signal',
        'sentiment_signal',
        'liquidity_signal',
        'valuation_signal',
        'debt_cycle',
    ]

    # Dirichlet prior concentration
    # Higher = slower weight adaptation
    ALPHA_PRIOR = 2.0

    # Exponential discount on old log-weights
    # 0.97 ≈ 33-month half-life on monthly data
    DISCOUNT = 0.97

    def __init__(self):
        n = len(self.MODELS)
        self.log_weights = np.zeros(n)
        self.weights     = np.ones(n) / n
        self.model_index = {
            m: i for i, m in enumerate(self.MODELS)
        }
        self.accuracy_history: dict[str, list] = {
            m: [] for m in self.MODELS
        }
        self.update_count  = 0
        self.last_updated: str | None = None
        self.fit_stats:    dict       = {}

    # ── Initialisation ────────────────────────────────

    def initialise_from_db(self) -> dict:
        """
        Load historical prediction accuracy from DB
        and set initial posterior weights.
        Called once on server startup.
        """
        conn     = sqlite3.connect('macro_terminal.db')
        accuracy = {}

        for model in self.MODELS:
            rows = conn.execute("""
                SELECT correct, predicted_score
                FROM signal_predictions
                WHERE module = ?
                  AND correct IS NOT NULL
                ORDER BY timestamp ASC
            """, (model,)).fetchall()

            if rows:
                correct = [float(r[0]) for r in rows]
                accuracy[model] = {
                    'n':        len(correct),
                    'accuracy': float(np.mean(correct)),
                }
                # Store in history for live updates
                self.accuracy_history[model] = correct
            else:
                accuracy[model] = {
                    'n': 0, 'accuracy': 0.50
                }

        conn.close()

        # Compute initial log-weights from accuracy
        for model, stats in accuracy.items():
            idx = self.model_index[model]
            acc = stats['accuracy']
            n   = stats['n']

            if n >= 5:
                # Laplace-smoothed accuracy
                acc_s = (
                    (acc * n + self.ALPHA_PRIOR * 0.5) /
                    (n   +     self.ALPHA_PRIOR)
                )
                # Log-odds vs random (0.5) baseline
                self.log_weights[idx] = np.log(
                    acc_s / max(1.0 - acc_s, 1e-8)
                )
            else:
                # Uninformative prior: zero log-weight
                self.log_weights[idx] = 0.0

        self.weights = softmax(self.log_weights)

        self.fit_stats = {
            'weights':        dict(zip(
                self.MODELS,
                [round(float(w), 4) for w in self.weights]
            )),
            'accuracy':       {
                m: round(accuracy[m]['accuracy'], 3)
                for m in self.MODELS
            },
            'n_obs':          {
                m: accuracy[m]['n']
                for m in self.MODELS
            },
            'initialised_at': datetime.utcnow().isoformat(),
            'paper': 'Raftery et al. (2005) MWR 133(5)',
        }

        logger.info(
            '[BAYES] Weights initialised: ' +
            str({
                m: round(float(self.weights[i]), 3)
                for m, i in self.model_index.items()
            })
        )
        return self.fit_stats

    # ── Bayesian weight update ─────────────────────────

    def update_weights(
        self,
        model_name:          str,
        predicted_direction: str,
        actual_return:       float,
    ) -> dict:
        """
        Update one model's weight using Bayes rule.

        Likelihood = P(correct | model) based on
        rolling accuracy over last 60 observations.
        Older observations discounted via DISCOUNT factor.

        Args:
          model_name:          model to update
          predicted_direction: 'RISK_ON' or 'RISK_OFF'
          actual_return:       realised return (decimal)
        """
        if model_name not in self.model_index:
            logger.warning(
                f'[BAYES] Unknown model: {model_name}'
            )
            return self.get_current_weights()

        idx = self.model_index[model_name]

        # Was the prediction correct?
        correct = (
            (predicted_direction == 'RISK_ON'  and
             actual_return > 0.0) or
            (predicted_direction == 'RISK_OFF' and
             actual_return < 0.0)
        )

        # Record outcome
        self.accuracy_history[model_name].append(
            1.0 if correct else 0.0
        )

        # Rolling accuracy over last 60 observations
        hist = self.accuracy_history[model_name]
        tail = hist[-60:]
        n60  = len(tail)
        k    = sum(tail)

        # Laplace-smoothed likelihood
        p_correct = (
            (k + self.ALPHA_PRIOR * 0.5) /
            (n60 + self.ALPHA_PRIOR)
        )
        log_lik = np.log(
            p_correct if correct
            else max(1.0 - p_correct, 1e-8)
        )

        # Discount all log-weights (forget old evidence)
        self.log_weights *= self.DISCOUNT

        # Update this model's log-weight
        self.log_weights[idx] += log_lik

        # Renormalise via softmax
        self.weights = softmax(self.log_weights)

        self.update_count += 1
        self.last_updated  = datetime.utcnow().isoformat()

        logger.debug(
            f'[BAYES] {model_name}: '
            f'correct={correct} '
            f'new_w={self.weights[idx]:.4f}'
        )
        return self.get_current_weights()

    # ── Signal aggregation ────────────────────────────

    def aggregate(
        self,
        model_signals: dict[str, dict],
    ) -> dict:
        """
        Combine model signals into Bayesian ensemble.

        Each signal dict must have:
          score:      float in [-1, +1]
          direction:  'RISK_ON'|'RISK_OFF'|'NEUTRAL'
          confidence: float in [0, 1]

        Returns weighted ensemble with full posterior.
        """
        if not model_signals:
            return self._empty_result()

        weighted_score = 0.0
        total_weight   = 0.0
        votes = {'RISK_ON': 0.0, 'RISK_OFF': 0.0,
                 'NEUTRAL': 0.0}
        contributions: dict = {}

        for model, signal in model_signals.items():
            if model not in self.model_index:
                continue

            idx  = self.model_index[model]
            w    = float(self.weights[idx])
            sc   = float(signal.get('score',      0.0))
            conf = float(signal.get('confidence', 0.5))
            dirn = str(  signal.get('direction','NEUTRAL'))

            # Effective weight = Bayes weight × confidence
            eff_w = w * conf

            weighted_score += eff_w * sc
            total_weight   += eff_w

            votes[dirn] = votes.get(dirn, 0.0) + w

            contributions[model] = {
                'bayes_weight':  round(w,     4),
                'score':         round(sc,    4),
                'direction':     dirn,
                'confidence':    round(conf,  4),
                'contribution':  round(eff_w * sc, 4),
            }

        # Normalised final score
        final_score = float(np.clip(
            weighted_score / total_weight
            if total_weight > 0 else 0.0,
            -1.0, 1.0
        ))

        # Dominant direction by weight-vote
        dominant = max(votes, key=votes.get)

        # Agreement across models
        n_models  = len(model_signals)
        agreement = (
            votes.get(dominant, 0.0) / n_models
            if n_models > 0 else 0.0
        )

        # Conviction from score + agreement
        conviction = self._conviction(
            abs(final_score), agreement
        )

        # Posterior uncertainty = std of scores
        scores = [
            float(s.get('score', 0.0))
            for s in model_signals.values()
        ]
        posterior_std = (
            float(np.std(scores))
            if len(scores) > 1 else 0.0
        )

        return {
            'score':           round(final_score, 4),
            'direction':       dominant,
            'conviction':      conviction,
            'agreement_pct':   round(agreement * 100, 1),
            'posterior_std':   round(posterior_std, 4),
            'model_weights':   dict(zip(
                self.MODELS,
                [round(float(w), 4) for w in self.weights]
            )),
            'contributions':   contributions,
            'top_models':      self._top_models(3),
            'dissenting':      self._dissenting(
                contributions, dominant
            ),
            'n_models_active': len(model_signals),
            'method':          'Bayesian_Model_Averaging',
            'paper':
                'Raftery et al. (2005) MWR 133(5)',
            'update_count':    self.update_count,
            'last_updated':    self.last_updated,
        }

    def _conviction(
        self,
        abs_score: float,
        agreement:  float,
    ) -> str:
        combined = abs_score * 0.6 + agreement * 0.4
        if   combined >= 0.65: return 'HIGH'
        elif combined >= 0.45: return 'MEDIUM'
        else:                  return 'LOW'

    def _top_models(self, n: int) -> list[dict]:
        ranked = sorted(
            zip(self.MODELS, self.weights),
            key=lambda x: x[1],
            reverse=True,
        )
        return [
            {'model': m, 'weight': round(float(w), 4)}
            for m, w in ranked[:n]
        ]

    def _dissenting(
        self,
        contributions: dict,
        dominant:       str,
    ) -> list[dict]:
        return [
            {
                'model':     m,
                'direction': c['direction'],
                'weight':    c['bayes_weight'],
            }
            for m, c in contributions.items()
            if c['direction'] not in (dominant, 'NEUTRAL')
        ]

    def _empty_result(self) -> dict:
        return {
            'score':           0.0,
            'direction':       'NEUTRAL',
            'conviction':      'LOW',
            'agreement_pct':   0.0,
            'posterior_std':   0.0,
            'model_weights':   dict(zip(
                self.MODELS,
                [round(float(w), 4) for w in self.weights]
            )),
            'contributions':   {},
            'top_models':      [],
            'dissenting':      [],
            'n_models_active': 0,
            'method':          'Bayesian_Model_Averaging',
        }

    # ── Accessors ─────────────────────────────────────

    def get_current_weights(self) -> dict:
        return {
            'weights':      dict(zip(
                self.MODELS,
                [round(float(w), 4) for w in self.weights]
            )),
            'top_model':    self.MODELS[
                int(np.argmax(self.weights))
            ],
            'update_count': self.update_count,
            'last_updated': self.last_updated,
        }

    def get_weight_history(self) -> dict:
        """
        Return per-model accuracy and weight trends.
        Used in the Weight Adaptations dashboard panel.
        """
        result = {}
        for model in self.MODELS:
            hist = self.accuracy_history[model]
            idx  = self.model_index[model]
            w    = float(self.weights[idx])

            if len(hist) >= 10:
                recent_acc = float(np.mean(hist[-5:]))
                prior_acc  = float(np.mean(hist[-10:-5]))
                trend = (
                    'INCREASING'   if recent_acc > prior_acc + 0.05
                    else 'DECREASING' if recent_acc < prior_acc - 0.05
                    else 'STABLE'
                )
            else:
                trend = 'WARMING_UP'

            result[model] = {
                'weight':       round(w, 4),
                'weight_pct':   round(w * 100, 1),
                'accuracy':     round(
                    float(np.mean(hist)) if hist else 0.5,
                    3
                ),
                'n_obs':        len(hist),
                'trend':        trend,
            }
        return result


# ── Singleton ─────────────────────────────────────────────

_bma: BayesianModelAverager | None = None


def get_bayesian_aggregator() -> BayesianModelAverager:
    """Return initialised BMA singleton."""
    global _bma
    if _bma is None:
        _bma = BayesianModelAverager()
        try:
            stats = _bma.initialise_from_db()
            logger.info(
                '[BAYES] Ready. Top model: '
                f'{stats["weights"]}'
            )
        except Exception as e:
            logger.error(f'[BAYES] Init failed: {e}')
    return _bma


def record_prediction_outcome(
    model_name:          str,
    predicted_direction: str,
    actual_return:       float,
) -> dict:
    """
    Record outcome and update Bayesian weights.
    Call this whenever a prediction horizon expires
    and the actual return becomes known.
    """
    bma = get_bayesian_aggregator()
    return bma.update_weights(
        model_name,
        predicted_direction,
        actual_return,
    )
