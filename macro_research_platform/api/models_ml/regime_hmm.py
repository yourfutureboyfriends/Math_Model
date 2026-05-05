"""
Markov Regime Switching classifier for macro regimes.

Academic basis:
  Hamilton, J.D. (1989). A New Approach to the Economic
  Analysis of Nonstationary Time Series and the Business
  Cycle. Econometrica, 57(2), 357-384.

  Ang, A. & Bekaert, G. (2002). Regime Switches in
  Interest Rates. Journal of Business & Economic
  Statistics, 20(2), 163-182.

Key improvement over threshold rules:
  - Regime is a latent variable learned from data
  - Transition probabilities are estimated, not assumed
  - Provides full probability distribution over regimes
  - Uses forward algorithm for real-time state inference
  - Handles fuzzy/overlapping regimes naturally
"""

import numpy as np
import pandas as pd
import sqlite3
import logging
import os
import glob
from datetime import datetime
from hmmlearn import hmm
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger(__name__)


class MacroRegimeHMM:
    """
    4-state Gaussian Hidden Markov Model for macro regime
    classification. States are labelled post-fit by their
    growth/inflation characteristics.

    Features used:
      - Growth z-score (GDP momentum proxy)
      - Inflation z-score (CPI YoY z-score)
      - Yield curve slope (10Y-2Y spread)
      - Credit conditions proxy

    State labelling convention (quadrant):
      High growth + Low inflation  = Goldilocks
      High growth + High inflation = Reflation
      Low growth  + Low inflation  = Slowdown
      Low growth  + High inflation = Stagflation
    """

    def __init__(self, n_states: int = 4):
        self.n_states = n_states
        self.model = hmm.GaussianHMM(
            n_components=n_states,
            covariance_type='full',
            n_iter=300,
            tol=1e-5,
            random_state=42,
            init_params='stmc',
        )
        self.scaler = StandardScaler()
        self.state_labels: dict = {}
        self.feature_cols: list = []
        self.fitted = False
        self.fit_stats: dict = {}
        self.last_trained: str | None = None

    # ── Feature preparation ───────────────────────────────

    def _find_csv(self) -> str | None:
        """Find the macro data CSV file."""
        candidates = (
            glob.glob('data/*.csv') +
            glob.glob('*.csv') +
            glob.glob('api/data/*.csv') +
            glob.glob('../data/*.csv')
        )
        # Prefer files with 'macro' or 'fred' in name
        for c in candidates:
            if any(k in c.lower()
                   for k in ['macro', 'fred', 'data']):
                return c
        return candidates[0] if candidates else None

    def prepare_features(self) -> pd.DataFrame:
        """
        Build feature matrix from available data sources.
        Priority: CSV data file → SQLite regime_history.
        Minimum 24 months of data required for reliable fit.
        """
        # Try CSV first
        csv_path = self._find_csv()
        if csv_path:
            try:
                df = pd.read_csv(csv_path)
                return self._extract_features_from_csv(df)
            except Exception as e:
                logger.warning(
                    f'[HMM] CSV feature build failed: {e}'
                )

        # Fallback: derive from regime_history
        return self._features_from_regime_history()

    def _extract_features_from_csv(
        self, df: pd.DataFrame
    ) -> pd.DataFrame:
        """Extract and z-score macro features from CSV."""
        result = pd.DataFrame()

        # Date column
        for col in ['date', 'Date', 'DATE', 'timestamp']:
            if col in df.columns:
                result['date'] = pd.to_datetime(df[col])
                break
        if 'date' not in result.columns:
            result['date'] = pd.date_range(
                end=datetime.today(), periods=len(df), freq='ME'
            )

        # Growth z-score
        for col in ['gdp_growth', 'real_gdp', 'lei_composite',
                    'payrolls_mom', 'ism_manufacturing']:
            if col in df.columns:
                s = pd.to_numeric(df[col], errors='coerce')
                result['growth_z'] = (
                    (s - s.rolling(36, min_periods=12).mean()) /
                    s.rolling(36, min_periods=12).std()
                )
                break

        # Inflation z-score
        for col in ['us_cpi', 'cpi_yoy', 'core_cpi_yoy',
                    'inflation']:
            if col in df.columns:
                s = pd.to_numeric(df[col], errors='coerce')
                result['inflation_z'] = (
                    (s - s.rolling(36, min_periods=12).mean()) /
                    s.rolling(36, min_periods=12).std()
                )
                break

        # Yield curve
        for col in ['yield_spread', 'treasury_spread',
                    'yield_curve', 'term_spread', 'yield_curve_spread']:
            if col in df.columns:
                s = pd.to_numeric(df[col], errors='coerce')
                result['yield_curve'] = s
                break

        # Credit conditions
        for col in ['hy_spreads', 'credit_spread',
                    'hy_spread', 'credit_impulse', 'credit_spreads']:
            if col in df.columns:
                s = pd.to_numeric(df[col], errors='coerce')
                result['credit_z'] = (
                    (s - s.rolling(36, min_periods=12).mean()) /
                    s.rolling(36, min_periods=12).std()
                )
                break

        # Keep only rows where we have at least 2 features
        feature_cols = [c for c in result.columns
                        if c != 'date']
        if len(feature_cols) < 2:
            raise ValueError(
                f'Only {len(feature_cols)} features found '
                f'in CSV. Need at least 2.'
            )

        result = result.dropna(subset=feature_cols[:2])
        logger.info(
            f'[HMM] Features: {feature_cols}, '
            f'rows: {len(result)}'
        )
        return result.reset_index(drop=True)

    def _features_from_regime_history(self) -> pd.DataFrame:
        """
        Last-resort feature derivation from regime_history.
        Converts regime labels to numeric growth/inflation
        scores for HMM fitting.
        """
        conn = sqlite3.connect('macro_terminal.db')
        rows = conn.execute(
            'SELECT date, regime, confidence '
            'FROM regime_history ORDER BY date'
        ).fetchall()
        conn.close()

        if len(rows) < 8:
            raise ValueError(
                f'Only {len(rows)} regime history rows. '
                f'Need at least 8.'
            )

        regime_to_features = {
            'Goldilocks':  ( 0.8, -0.5,  0.8, -0.3),
            'Reflation':   ( 0.5,  0.8,  0.3,  0.1),
            'Slowdown':    (-0.7, -0.4, -0.5,  0.4),
            'Stagflation': (-0.4,  0.9, -0.6,  0.8),
        }
        data = []
        for date, regime, conf in rows:
            feats = regime_to_features.get(
                regime, (0.0, 0.0, 0.0, 0.0)
            )
            # Add small noise to avoid degenerate covariance
            noise = np.random.normal(0, 0.1, 4)
            data.append({
                'date':        date,
                'growth_z':    feats[0] + noise[0],
                'inflation_z': feats[1] + noise[1],
                'yield_curve': feats[2] + noise[2],
                'credit_z':    feats[3] + noise[3],
            })

        return pd.DataFrame(data)

    # ── Model fitting ─────────────────────────────────────

    def fit(self, df: pd.DataFrame) -> dict:
        """
        Fit HMM on macro features.
        Labels states by economic quadrant.
        Returns fit statistics.
        """
        self.feature_cols = [c for c in df.columns
                             if c != 'date']
        X = df[self.feature_cols].values.astype(float)

        if np.any(np.isnan(X)):
            X = np.nan_to_num(X, nan=0.0)

        X_scaled = self.scaler.fit_transform(X)
        lengths = [len(X_scaled)]

        self.model.fit(X_scaled, lengths)

        # Label states by growth/inflation quadrant
        self._label_states()

        self.fitted = True
        self.last_trained = datetime.utcnow().isoformat()

        log_prob = self.model.score(X_scaled, lengths)
        self.fit_stats = {
            'log_likelihood': round(log_prob, 4),
            'n_samples':      len(X_scaled),
            'n_features':     len(self.feature_cols),
            'state_labels':   self.state_labels,
            'trained_at':     self.last_trained,
            'paper': 'Hamilton (1989) Econometrica 57(2)',
        }
        logger.info(
            f'[HMM] Fit complete: '
            f'logL={log_prob:.2f} '
            f'states={self.state_labels}'
        )
        return self.fit_stats

    def _label_states(self):
        """
        Label HMM states by economic quadrant.
        Uses mean values of growth and inflation features.
        """
        means = self.model.means_  # shape: (n_states, n_features)

        g_idx = self._feature_index('growth_z')
        i_idx = self._feature_index('inflation_z')

        labels = {}
        used_labels = {}

        for state in range(self.n_states):
            g = means[state, g_idx]
            i = means[state, i_idx]

            if g >= 0 and i < 0:
                label = 'Goldilocks'
            elif g >= 0 and i >= 0:
                label = 'Reflation'
            elif g < 0 and i < 0:
                label = 'Slowdown'
            else:
                label = 'Stagflation'

            # Handle duplicate labels
            if label in used_labels:
                label = label + '_2'
            used_labels[label] = state
            labels[state] = label

        self.state_labels = labels

    def _feature_index(self, name: str) -> int:
        """Return index of feature, default 0 if not found."""
        try:
            return self.feature_cols.index(name)
        except ValueError:
            return 0

    # ── Prediction ────────────────────────────────────────

    def predict_current(
        self, current_features: dict
    ) -> dict:
        """
        Predict current regime using forward algorithm.

        Args:
          current_features: dict with keys matching
                            self.feature_cols

        Returns:
          regime, confidence, probabilities, transition_probs
        """
        if not self.fitted:
            raise RuntimeError(
                'HMM not fitted. Call fit() first.'
            )

        X = np.array([[
            current_features.get('growth_z', 0.0),
            current_features.get('inflation_z', 0.0),
            current_features.get('yield_curve', 0.5),
            current_features.get('credit_z', 0.0),
        ]])
        # Trim to n_features used in training
        n = len(self.feature_cols)
        X = X[:, :n]

        X_scaled = self.scaler.transform(X)

        # Forward algorithm: posterior state probabilities
        _, posteriors = self.model.score_samples(
            X_scaled, lengths=[1]
        )
        state_probs = posteriors[0]

        # Map to regime labels
        regime_probs = {}
        for state, prob in enumerate(state_probs):
            label = self.state_labels.get(
                state, f'State_{state}'
            )
            # Merge _2 labels back to base
            base = label.replace('_2', '')
            regime_probs[base] = (
                regime_probs.get(base, 0.0) + float(prob)
            )

        # Most likely regime
        best_state = int(np.argmax(state_probs))
        best_label = self.state_labels.get(
            best_state, 'Unknown'
        )
        best_regime = best_label.replace('_2', '')
        confidence = float(state_probs[best_state])

        # Next-period transition probabilities
        transmat = self.model.transmat_
        next_probs_raw = {}
        for next_state in range(self.n_states):
            label = self.state_labels.get(
                next_state, f'State_{next_state}'
            ).replace('_2', '')
            p = float(transmat[best_state, next_state])
            next_probs_raw[label] = (
                next_probs_raw.get(label, 0.0) + p
            )

        return {
            'regime':               best_regime,
            'confidence':           round(confidence, 4),
            'regime_probabilities': {
                k: round(v, 4)
                for k, v in regime_probs.items()
            },
            'transition_probs':     {
                k: round(v, 4)
                for k, v in next_probs_raw.items()
            },
            'method':   'HMM_Forward_Algorithm',
            'paper':    'Hamilton (1989) Econometrica',
            'trained_at': self.last_trained,
        }

    def get_historical_sequence(
        self, df: pd.DataFrame
    ) -> list[dict]:
        """
        Viterbi decoding: most likely historical regime
        sequence. Used to backfill regime_history table.
        """
        if not self.fitted:
            return []

        X = df[self.feature_cols].values.astype(float)
        X = np.nan_to_num(X, nan=0.0)
        X_scaled = self.scaler.transform(X)
        states = self.model.predict(X_scaled)

        return [
            {
                'date':   str(df['date'].iloc[i])[:10],
                'regime': self.state_labels.get(
                              int(states[i]), 'Unknown'
                          ).replace('_2', ''),
                'state':  int(states[i]),
            }
            for i in range(len(states))
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
        if len(df) < 24:
            logger.warning(
                f'[HMM] Only {len(df)} samples available. '
                f'Need 24 minimum. Using fallback classifier.'
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
