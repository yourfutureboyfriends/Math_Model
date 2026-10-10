"""
Markov Regime Switching classifier for macro regimes.

Academic basis:
  Hamilton, J.D. (1989). A New Approach to the Economic
  Analysis of Nonstationary Time Series and the Business
  Cycle. Econometrica, 57(2), 357-384.

  Ang, A. & Bekaert, G. (2002). Regime Switches in
  Interest Rates. Journal of Business & Economic
  Statistics, 20(2), 163-182.

Design:
  Two independent 2-state Gaussian HMMs, one per quadrant axis:
    - growth axis:    industrial-production YoY z-score (+ credit-spread z-score)
    - inflation axis: CPI YoY z-score
  Each axis's states are labelled "rising"/"falling" by their mean, and the quadrant
  is the combination (Goldilocks = growth rising + inflation falling, etc.).

  A single 4-state joint HMM was used before. Its states don't line up with quadrants
  (it learns e.g. a "crisis" state with collapsing growth and neutral inflation), so
  forcing quadrant names onto them mislabelled 2008/2020 and could leave some
  quadrants unreachable. Per-axis states always have an unambiguous direction.

Key improvement over threshold rules:
  - Regime is a latent variable learned from data
  - Transition probabilities are estimated, not assumed
  - Provides full probability distribution over regimes
  - Uses forward filtering for real-time state inference
"""

from __future__ import annotations

import logging
from datetime import datetime

import numpy as np
import pandas as pd
from hmmlearn import hmm
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger(__name__)

_Z_WINDOW, _Z_MIN = 36, 24
_N_RESTARTS = 5

# (growth rising?, inflation rising?) -> quadrant
_QUADRANT = {
    (True, False): 'Goldilocks',
    (True, True): 'Reflation',
    (False, False): 'Slowdown',
    (False, True): 'Stagflation',
}


class _AxisHMM:
    """2-state Gaussian HMM on one axis; state 'up' has the higher mean of `key`."""

    def __init__(self, name: str, cols: list[str], key: str):
        self.name, self.cols, self.key = name, cols, key
        self.scaler = StandardScaler()
        self.model: hmm.GaussianHMM | None = None
        self.up_state = 0

    def fit(self, df: pd.DataFrame) -> float:
        X = self.scaler.fit_transform(df[self.cols].values.astype(float))
        best, best_ll = None, -np.inf
        for seed in range(_N_RESTARTS):  # EM finds local optima; keep the best fit
            m = hmm.GaussianHMM(n_components=2, covariance_type='full', n_iter=300,
                                tol=1e-5, random_state=seed, init_params='stmc')
            m.fit(X)
            ll = m.score(X)
            if ll > best_ll:
                best, best_ll = m, ll
        self.model = best
        k = self.cols.index(self.key)
        self.up_state = int(np.argmax(best.means_[:, k]))
        return float(best_ll)

    def _X(self, df: pd.DataFrame) -> np.ndarray:
        return self.scaler.transform(df[self.cols].values.astype(float))

    def p_up_filtered(self, df: pd.DataFrame) -> float:
        """P(up at last row | all rows): the last smoothed posterior equals the filter."""
        return float(self.model.predict_proba(self._X(df))[-1, self.up_state])

    def p_up_next(self, p_up: float) -> float:
        p = np.zeros(2)
        p[self.up_state], p[1 - self.up_state] = p_up, 1 - p_up
        return float((p @ self.model.transmat_)[self.up_state])

    def viterbi_up(self, df: pd.DataFrame) -> np.ndarray:
        return self.model.predict(self._X(df)) == self.up_state

    def summary(self) -> dict:
        means = self.scaler.inverse_transform(self.model.means_)
        k = self.cols.index(self.key)
        up, down = self.up_state, 1 - self.up_state
        return {
            'features': self.cols,
            'rising_mean': round(float(means[up, k]), 3),
            'falling_mean': round(float(means[down, k]), 3),
            'p_stay_rising': round(float(self.model.transmat_[up, up]), 4),
            'p_stay_falling': round(float(self.model.transmat_[down, down]), 4),
        }


class MacroRegimeHMM:
    """
    Quadrant regime classifier from two per-axis 2-state HMMs (growth, inflation).

    Public API (unchanged): prepare_features(), fit(df), predict_current(),
    get_historical_sequence(df), fitted / fit_stats / state_labels.
    """

    def __init__(self, n_states: int = 4):
        # n_states kept for backward compatibility; the model is always 2 axes x 2 states.
        self.n_states = 4
        self.growth = _AxisHMM('growth', ['growth_z'], 'growth_z')
        self.inflation = _AxisHMM('inflation', ['inflation_z'], 'inflation_z')
        self.state_labels: dict = {'growth': {}, 'inflation': {}}
        self.feature_cols: list = []
        self.fitted = False
        self.fit_stats: dict = {}
        self.last_trained: str | None = None
        self._train_df: pd.DataFrame | None = None

    # ── Feature preparation ───────────────────────────────

    @staticmethod
    def _rolling_z(s: pd.Series) -> pd.Series:
        """Backward-looking z-score (no look-ahead): uses the trailing 36 months."""
        r = s.rolling(_Z_WINDOW, min_periods=_Z_MIN)
        return (s - r.mean()) / r.std()

    def prepare_features(self) -> pd.DataFrame:
        """
        Monthly feature matrix from FRED (api.handlers.macro_inputs.load_monthly_macro):
        growth_z (industrial production YoY), inflation_z (CPI YoY), yield_curve
        (10Y-2Y, pp) and credit_z (Baa-10Y spread). Real month dates; rows with any
        missing feature are dropped. Raises if FRED data is unavailable — there is no
        synthetic fallback.
        """
        from api.handlers.macro_inputs import load_monthly_macro

        panel = load_monthly_macro()
        if panel is None or panel.empty:
            raise ValueError('Monthly FRED macro data unavailable')

        result = pd.DataFrame({'date': panel.index})
        result['growth_z'] = self._rolling_z(panel['growth_yoy']).values
        result['inflation_z'] = self._rolling_z(panel['cpi_yoy']).values
        if 'curve' in panel:
            result['yield_curve'] = panel['curve'].values
        if 'credit' in panel:
            result['credit_z'] = self._rolling_z(panel['credit']).values

        feature_cols = [c for c in result.columns if c != 'date']
        result = result.dropna(subset=feature_cols).reset_index(drop=True)
        logger.info(f'[HMM] Features: {feature_cols}, rows: {len(result)}')
        return result

    # ── Model fitting ─────────────────────────────────────

    def fit(self, df: pd.DataFrame) -> dict:
        """Fit both axis HMMs. Requires growth_z and inflation_z; credit_z is used on
        the growth axis when present. Returns fit statistics."""
        for col in ('growth_z', 'inflation_z'):
            if col not in df.columns:
                raise ValueError(f'HMM features need a {col} column')
        growth_cols = ['growth_z'] + (['credit_z'] if 'credit_z' in df.columns else [])
        self.growth = _AxisHMM('growth', growth_cols, 'growth_z')
        self.inflation = _AxisHMM('inflation', ['inflation_z'], 'inflation_z')
        self.feature_cols = growth_cols + ['inflation_z']

        # Drop incomplete rows: zero-filling would inject fake "average" observations.
        df = df.dropna(subset=self.feature_cols).reset_index(drop=True)
        ll = self.growth.fit(df) + self.inflation.fit(df)

        self.state_labels = {
            'growth': {self.growth.up_state: 'rising', 1 - self.growth.up_state: 'falling'},
            'inflation': {self.inflation.up_state: 'rising', 1 - self.inflation.up_state: 'falling'},
        }
        self.fitted = True
        self.last_trained = datetime.utcnow().isoformat()
        self._train_df = df
        self.fit_stats = {
            'log_likelihood': round(ll, 4),
            'n_samples':      len(df),
            'n_features':     len(self.feature_cols),
            'growth_axis':    self.growth.summary(),
            'inflation_axis': self.inflation.summary(),
            'sample_start':   str(df['date'].iloc[0])[:10] if 'date' in df else None,
            'sample_end':     str(df['date'].iloc[-1])[:10] if 'date' in df else None,
            'trained_at':     self.last_trained,
            'paper': 'Hamilton (1989) Econometrica 57(2)',
        }
        logger.info(f'[HMM] Fit complete: logL={ll:.2f} n={len(df)}')
        return self.fit_stats

    # ── Prediction ────────────────────────────────────────

    @staticmethod
    def _quadrant_probs(p_g: float, p_i: float) -> dict:
        return {
            _QUADRANT[(g_up, i_up)]: (p_g if g_up else 1 - p_g) * (p_i if i_up else 1 - p_i)
            for g_up in (True, False) for i_up in (True, False)
        }

    def predict_current(self, features_df: pd.DataFrame | None = None) -> dict:
        """
        Filtered regime probabilities for the latest month.

        Runs each axis HMM over the whole feature history (default: the training frame)
        and takes P(rising at T | obs_1..T). Quadrant probabilities combine the two axes
        (treated as independent). Also returns next-month probabilities via each axis's
        transition matrix.
        """
        if not self.fitted:
            raise RuntimeError('HMM not fitted. Call fit() first.')
        df = features_df if features_df is not None else self._train_df
        df = df.dropna(subset=self.feature_cols)

        p_g = self.growth.p_up_filtered(df)
        p_i = self.inflation.p_up_filtered(df)
        probs = self._quadrant_probs(p_g, p_i)
        nxt = self._quadrant_probs(self.growth.p_up_next(p_g), self.inflation.p_up_next(p_i))
        regime = max(probs, key=probs.get)

        return {
            'regime':               regime,
            'confidence':           round(probs[regime], 4),
            'as_of':                str(df['date'].iloc[-1])[:10] if 'date' in df else None,
            'p_growth_rising':      round(p_g, 4),
            'p_inflation_rising':   round(p_i, 4),
            'regime_probabilities': {k: round(v, 4) for k, v in probs.items()},
            'transition_probs':     {k: round(v, 4) for k, v in nxt.items()},
            'method':   'HMM_Forward_Filtering (per-axis)',
            'paper':    'Hamilton (1989) Econometrica',
            'trained_at': self.last_trained,
        }

    def get_historical_sequence(self, df: pd.DataFrame) -> list[dict]:
        """
        Viterbi decoding per axis, combined into the quadrant sequence. Used to
        backfill regime_history. In-sample: parameters and scaling are fit on the full
        sample, so this describes history rather than an out-of-sample backtest.
        """
        if not self.fitted:
            return []
        df = df.dropna(subset=self.feature_cols).reset_index(drop=True)
        g_up = self.growth.viterbi_up(df)
        i_up = self.inflation.viterbi_up(df)
        return [
            {
                'date':   str(df['date'].iloc[k])[:10],
                'regime': _QUADRANT[(bool(g_up[k]), bool(i_up[k]))],
                'growth': 'rising' if g_up[k] else 'falling',
                'inflation': 'rising' if i_up[k] else 'falling',
            }
            for k in range(len(df))
        ]


# ── Module-level singleton ────────────────────────────────

_hmm_instance: MacroRegimeHMM | None = None


def get_regime_hmm() -> MacroRegimeHMM:
    """
    Return the fitted HMM singleton.
    Fits on first call using available data.
    """
    global _hmm_instance
    if _hmm_instance is None:
        _hmm_instance = MacroRegimeHMM()
        _fit_hmm_on_startup(_hmm_instance)
    return _hmm_instance


def _fit_hmm_on_startup(model: MacroRegimeHMM):
    """Attempt to fit HMM on startup. Log but don't crash."""
    try:
        df = model.prepare_features()
        if len(df) < 60:
            logger.warning(
                f'[HMM] Only {len(df)} monthly samples available. '
                f'Need 60 minimum. Using fallback classifier.'
            )
            return
        stats = model.fit(df)
        logger.info(
            f'[HMM] Startup fit: '
            f'logL={stats["log_likelihood"]}, '
            f'n={stats["n_samples"]}'
        )
    except Exception as e:
        logger.error(f'[HMM] Startup fit failed: {e}')


def retrain_hmm() -> dict:
    """Force retrain. Called by weekly Celery task."""
    global _hmm_instance
    _hmm_instance = MacroRegimeHMM()
    df = _hmm_instance.prepare_features()
    return _hmm_instance.fit(df)
