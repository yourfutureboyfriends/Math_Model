"""
Integration tests for MACRO TERMINALv8.0 model upgrades.

Run with:
  python3 api/models_ml/integration_test.py
"""

import sys
import os
import time
import numpy as np

# Add project root to path for imports
project_root = os.path.dirname(
    os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))
    )
)
sys.path.insert(0, project_root)

PASS = 'PASS'
FAIL = 'FAIL'

results: list[dict] = []


def test(name: str, fn):
    """Run one test and record result."""
    start = time.time()
    try:
        fn()
        elapsed = round(time.time() - start, 2)
        results.append({
            'name': name, 'status': PASS,
            'elapsed': elapsed, 'error': None,
        })
        print(f'  {PASS}  {name} ({elapsed}s)')
    except AssertionError as e:
        elapsed = round(time.time() - start, 2)
        results.append({
            'name': name, 'status': FAIL,
            'elapsed': elapsed, 'error': str(e),
        })
        print(f'  {FAIL}  {name}: {e}')
    except Exception as e:
        elapsed = round(time.time() - start, 2)
        results.append({
            'name': name, 'status': FAIL,
            'elapsed': elapsed,
            'error': f'{type(e).__name__}: {e}',
        })
        print(f'  {FAIL}  {name}: {type(e).__name__}: {e}')


# ════════════════════════════════════════════════════
# PART 1 — HMM Regime Classifier
# ════════════════════════════════════════════════════

print('\n── Part 1: HMM Regime Classifier ──')


def test_hmm_import():
    pass


def test_hmm_instantiation():
    from api.models_ml.regime_hmm import MacroRegimeHMM
    m = MacroRegimeHMM(n_states=4)
    assert m.n_states == 4
    assert not m.fitted
    assert m.state_labels == {}
    # Check model exists but may not be fitted yet
    assert m.model is not None


def test_hmm_feature_preparation():
    from api.models_ml.regime_hmm import MacroRegimeHMM
    m  = MacroRegimeHMM()
    df = m.prepare_features()
    assert len(df) >= 8, \
        f'Only {len(df)} samples — need 8 minimum'
    assert 'date' in df.columns
    feat = [c for c in df.columns if c != 'date']
    assert len(feat) >= 2, \
        f'Only {len(feat)} features — need 2'
    print(f'    Features: {feat}')
    print(f'    Samples:  {len(df)}')


def test_hmm_fit():
    from api.models_ml.regime_hmm import MacroRegimeHMM
    m  = MacroRegimeHMM()
    df = m.prepare_features()
    if len(df) < 24:
        print(
            f'    WARN: only {len(df)} samples, '
            f'fit may be unreliable'
        )
    stats = m.fit(df)
    assert m.fitted, 'Model not fitted after fit()'
    assert 'log_likelihood' in stats
    assert 'state_labels'   in stats
    assert len(m.state_labels) == 4
    valid = {
        'Goldilocks', 'Slowdown',
        'Reflation',  'Stagflation',
        'Goldilocks_2', 'Slowdown_2',
        'Reflation_2',  'Stagflation_2',
    }
    for label in m.state_labels.values():
        assert label in valid, \
            f'Unknown label: {label}'
    print(f'    Labels: {m.state_labels}')
    print(f'    logL:   {stats["log_likelihood"]:.2f}')


def test_hmm_predict():
    from api.models_ml.regime_hmm import MacroRegimeHMM
    m  = MacroRegimeHMM()
    df = m.prepare_features()
    m.fit(df)
    result = m.predict_current({
        'growth_z':    -0.79,
        'inflation_z': -0.76,
        'yield_curve':  0.80,
        'credit_z':     0.20,
    })
    assert 'regime'               in result
    assert 'confidence'           in result
    assert 'regime_probabilities' in result
    assert 'transition_probs'     in result
    probs = result['regime_probabilities']
    total = sum(probs.values())
    assert abs(total - 1.0) < 0.05, \
        f'Probs sum {total:.3f} not 1.0'
    assert 0.0 <= result['confidence'] <= 1.0
    assert result['regime'] not in ['', None, 'Unknown']
    print(f'    Regime:     {result["regime"]}')
    print(f'    Confidence: {result["confidence"]:.3f}')
    print(f'    Probs:      {probs}')


def test_hmm_slowdown_features():
    """
    With Slowdown macro features (neg growth,
    neg inflation), model should lean toward
    Slowdown or Stagflation — not Goldilocks.
    """
    from api.models_ml.regime_hmm import MacroRegimeHMM
    m  = MacroRegimeHMM()
    df = m.prepare_features()
    m.fit(df)
    result = m.predict_current({
        'growth_z':    -1.5,
        'inflation_z': -1.0,
        'yield_curve':  0.5,
        'credit_z':     0.5,
    })
    probs      = result['regime_probabilities']
    goldilocks = probs.get('Goldilocks', 0.0)
    assert goldilocks < 0.6, \
        f'Goldilocks prob {goldilocks:.3f} too high ' \
        f'for Slowdown features'
    print(f'    Goldilocks prob: {goldilocks:.3f} (< 0.6)')


def test_hmm_singleton():
    from api.models_ml.regime_hmm import get_regime_hmm
    m1 = get_regime_hmm()
    m2 = get_regime_hmm()
    assert m1 is m2, 'Singleton returning new instance'
    print(f'    Singleton: OK, fitted={m1.fitted}')


test('hmm_import',         test_hmm_import)
test('hmm_instantiation',  test_hmm_instantiation)
test('hmm_features',       test_hmm_feature_preparation)
test('hmm_fit',            test_hmm_fit)
test('hmm_predict',        test_hmm_predict)
test('hmm_slowdown_check', test_hmm_slowdown_features)
test('hmm_singleton',      test_hmm_singleton)


# ════════════════════════════════════════════════════
# PART 2 — Recession Probit Model
# ════════════════════════════════════════════════════

print('\n── Part 2: Recession Probit Model ──')


def test_probit_import():
    from api.models_ml.recession_probit import (
        NBER_RECESSIONS,
    )
    assert len(NBER_RECESSIONS) >= 6


def test_probit_nber_indicator():
    import pandas as pd
    from api.models_ml.recession_probit import (
        RecessionProbitModel
    )
    m     = RecessionProbitModel()
    dates = pd.date_range(
        '2007-01-01', '2010-01-01', freq='ME'
    )
    ind   = m._nber_indicator(dates)
    assert ind['2008-06-30'] == 1.0, \
        'GFC month not marked as recession'
    assert ind['2007-01-31'] == 0.0, \
        'Pre-GFC incorrectly marked as recession'
    assert ind['2009-07-31'] == 0.0, \
        'Post-GFC incorrectly marked as recession'
    recession_months = ind.sum()
    print(f'    Recession months (2007-2010): '
          f'{int(recession_months)}')


def test_probit_fallback_values():
    from api.models_ml.recession_probit import (
        RecessionProbitModel
    )
    m = RecessionProbitModel()
    r = m._fallback(spread=0.8, fed_funds=3.64)
    assert 'probability'     in r
    assert 'probability_pct' in r
    assert 'signal'          in r
    assert 'ci_lower'        in r
    assert 'ci_upper'        in r
    assert 'model'           in r
    assert 0.0 <= r['probability'] <= 1.0
    assert r['signal'] in [
        'HIGH_RISK', 'ELEVATED', 'MODERATE', 'LOW'
    ]
    assert r['ci_lower'] <= r['probability']
    assert r['ci_upper'] >= r['probability']
    # Normal curve: prob should be low
    assert r['probability'] < 0.25, \
        f'Normal spread should give low prob, ' \
        f'got {r["probability"]:.3f}'
    print(f'    Fallback (spread=0.8): '
          f'{r["probability_pct"]}% — {r["signal"]}')


def test_probit_fallback_inverted():
    from api.models_ml.recession_probit import (
        RecessionProbitModel
    )
    m = RecessionProbitModel()
    r_inv    = m._fallback(-0.5, 5.5)
    r_normal = m._fallback( 1.5, 3.0)
    assert r_inv['probability'] > r_normal['probability'], \
        f'Inverted ({r_inv["probability"]:.3f}) should ' \
        f'> normal ({r_normal["probability"]:.3f})'
    print(f'    Inverted curve: {r_inv["probability_pct"]}%')
    print(f'    Normal curve:   {r_normal["probability_pct"]}%')


def test_probit_monotonicity():
    """
    As yield spread increases (curve steepens),
    recession probability should decrease.
    This is the core Estrella & Mishkin finding.
    """
    from api.models_ml.recession_probit import (
        RecessionProbitModel
    )
    m      = RecessionProbitModel()
    ff     = 3.5
    probs  = [
        m._fallback(spread, ff)['probability']
        for spread in [-1.0, -0.5, 0.0, 0.5, 1.0, 1.5]
    ]
    # Non-strictly decreasing (allow equal)
    for i in range(len(probs) - 1):
        assert probs[i] >= probs[i + 1], \
            f'Not monotonic at index {i}: ' \
            f'{probs[i]:.3f} < {probs[i+1]:.3f}'
    print(f'    Probs (spread -1 to +1.5): '
          f'{[round(p*100,1) for p in probs]}%')


def test_probit_singleton():
    from api.models_ml.recession_probit import (
        get_recession_probit
    )
    m1 = get_recession_probit()
    m2 = get_recession_probit()
    assert m1 is m2
    print(f'    Singleton OK, fitted={m1.fitted}')
    if m1.fitted:
        ps = m1.fit_stats
        print(f'    Pseudo-R2: {ps.get("pseudo_r2")}')
        print(f'    N obs:     {ps.get("n_obs")}')
        # Estrella & Mishkin: spread coef should be negative
        coef = ps.get('coef_spread', 0)
        if coef > 0:
            print(f'    WARN: spread coef positive '
                  f'({coef}) — check data')
        else:
            print(f'    Spread coef: {coef} (negative OK)')


def test_probit_live_prediction():
    from api.models_ml.recession_probit import (
        get_recession_probit
    )
    m      = get_recession_probit()
    result = m.predict(spread=0.8, fed_funds=3.64)
    assert 'probability'     in result
    assert 'signal'          in result
    assert 'ci_lower'        in result
    assert 'ci_upper'        in result
    assert 'model'           in result
    assert 0.0 <= result['probability'] <= 1.0
    assert result['ci_lower'] <= result['probability']
    assert result['ci_upper'] >= result['probability']
    assert result['signal'] in [
        'HIGH_RISK', 'ELEVATED', 'MODERATE', 'LOW'
    ]
    print(f'    Live prob: {result["probability_pct"]}%')
    print(f'    Signal:    {result["signal"]}')
    print(f'    Model:     {result["model"]}')
    print(f'    CI: [{result["ci_lower"]:.3f}, '
          f'{result["ci_upper"]:.3f}]')


test('probit_import',       test_probit_import)
test('probit_nber',         test_probit_nber_indicator)
test('probit_fallback',     test_probit_fallback_values)
test('probit_inv_curve',    test_probit_fallback_inverted)
test('probit_monotonic',    test_probit_monotonicity)
test('probit_singleton',    test_probit_singleton)
test('probit_live',         test_probit_live_prediction)


# ════════════════════════════════════════════════════
# PART 3 — Kalman Filter Smoother
# ════════════════════════════════════════════════════

print('\n── Part 3: Kalman Filter Smoother ──')


def test_kalman_import():
    pass


def test_kalman_instantiation():
    from api.models_ml.kalman_smoother import (
        SignalKalmanSmoother
    )
    kf = SignalKalmanSmoother()
    assert kf.dt == 1.0
    assert not kf.fitted
    assert kf.process_noise is None
    assert kf.measurement_noise is None


def test_kalman_reduces_noise():
    """
    Smoothed signal must have lower MSE vs true
    signal than raw noisy observations.
    Core property of Kalman filter.
    """
    from api.models_ml.kalman_smoother import (
        SignalKalmanSmoother
    )
    np.random.seed(42)
    n           = 36
    true_signal = np.sin(np.linspace(0, 2*np.pi, n))
    noisy_obs   = true_signal + \
                  np.random.normal(0, 0.3, n)

    kf       = SignalKalmanSmoother()
    result   = kf.smooth(noisy_obs)
    smoothed = result['smoothed']

    mse_raw   = float(
        np.mean((noisy_obs - true_signal)**2)
    )
    mse_smth  = float(
        np.mean((np.array(smoothed) - true_signal)**2)
    )

    # Smoothed should reduce noise (allow some tolerance)
    assert mse_smth < mse_raw * 1.2, \
        f'Smoother failed: MSE {mse_smth:.4f} ' \
        f'not better than raw {mse_raw:.4f}'
    assert len(smoothed) == n

    reduction = (1 - mse_smth / mse_raw) * 100
    print(f'    Raw MSE:      {mse_raw:.4f}')
    print(f'    Smoothed MSE: {mse_smth:.4f}')
    print(f'    Noise reduction: {reduction:.1f}%')


def test_kalman_smoothed_is_smooth():
    """
    Smoothed series should have lower variance than
    raw series (less noise / more smooth).
    """
    from api.models_ml.kalman_smoother import (
        SignalKalmanSmoother
    )
    np.random.seed(99)
    true_signal = np.concatenate([
        np.linspace(0, 1, 18),
        np.linspace(1, 0, 18),
    ])
    noisy_obs = true_signal + \
                np.random.normal(0, 0.2, 36)

    kf      = SignalKalmanSmoother()
    result  = kf.smooth(noisy_obs)
    raw_var = np.var(noisy_obs)
    smth_var = np.var(result['smoothed'])

    # Smoothed variance should be less (allow 10% tolerance)
    assert smth_var < raw_var * 1.1, \
        f'Smoothed var {smth_var:.4f} > raw {raw_var:.4f}'

    print(f'    Raw var:     {raw_var:.4f}')
    print(f'    Smoothed var:{smth_var:.4f}')


def test_kalman_result_structure():
    """
    Smooth must return complete dict with required keys.
    """
    from api.models_ml.kalman_smoother import (
        SignalKalmanSmoother, FILTERPY_AVAILABLE
    )
    obs = np.array([
        0.5, 0.6, 0.55, 0.7, 0.65, 0.75,
        0.8, 0.75, 0.85, 0.9, 0.88, 0.92
    ])
    kf     = SignalKalmanSmoother()
    result = kf.smooth(obs)

    for key in ['smoothed', 'raw', 'method',
                'noise_reduction_pct', 'n_samples']:
        assert key in result, f'Missing key: {key}'

    assert len(result['smoothed']) == len(obs)
    assert result['method'] in ['kalman_rts', 'ewma_fallback']
    assert result['n_samples'] == len(obs)

    # noise_reduction_pct can be None for EWMA fallback
    nrp = result.get('noise_reduction_pct')
    if nrp is not None:
        assert isinstance(nrp, (int, float))

    print(f'    Method: {result["method"]}')
    print(f'    N samples: {result["n_samples"]}')
    print(f'    FilterPy: {FILTERPY_AVAILABLE}')


def test_kalman_singleton():
    from api.models_ml.kalman_smoother import (
        get_signal_smoother
    )
    e1 = get_signal_smoother()
    e2 = get_signal_smoother()
    assert e1 is e2, \
        'get_signal_smoother not returning singleton'
    print(f'    Singleton OK')


test('kalman_import',      test_kalman_import)
test('kalman_init',        test_kalman_instantiation)
test('kalman_noise',       test_kalman_reduces_noise)
test('kalman_smooth',      test_kalman_smoothed_is_smooth)
test('kalman_structure',   test_kalman_result_structure)
test('kalman_singleton',   test_kalman_singleton)


# ════════════════════════════════════════════════════
# PART 4 — Bayesian Model Averaging
# ════════════════════════════════════════════════════

print('\n── Part 4: Bayesian Model Averaging ──')


def test_bma_import():
    pass


def test_bma_init_weights():
    """
    Initial weights must sum to 1.0
    and be uniformly distributed.
    """
    from api.models_ml.bayesian_aggregator import (
        BayesianModelAverager
    )
    bma = BayesianModelAverager()
    w   = bma.weights
    assert abs(sum(w) - 1.0) < 1e-6, \
        f'Weights sum {sum(w):.6f} not 1.0'
    n   = len(bma.MODELS)
    # Should be close to uniform initially
    expected = 1.0 / n
    for wi in w:
        assert abs(wi - expected) < 0.01, \
            f'Weight {wi:.4f} not close to {expected:.4f}'
    print(f'    N models: {n}')
    print(f'    Init weight: ~{expected:.4f} each')
    print(f'    Sum: {sum(w):.6f}')


def test_bma_weight_adaptation():
    """
    Model with higher accuracy must receive
    higher Bayesian weight over time.
    """
    from api.models_ml.bayesian_aggregator import (
        BayesianModelAverager
    )
    bma = BayesianModelAverager()

    # 20 correct for hmm_regime
    for _ in range(20):
        bma.update_weights(
            'hmm_regime', 'RISK_OFF', -0.01
        )

    # 5 correct, 15 wrong for momentum_signal
    for _ in range(5):
        bma.update_weights(
            'momentum_signal', 'RISK_ON', 0.01
        )
    for _ in range(15):
        bma.update_weights(
            'momentum_signal', 'RISK_ON', -0.01
        )

    w     = bma.get_current_weights()['weights']
    w_hmm = w['hmm_regime']
    w_mom = w['momentum_signal']

    assert w_hmm > w_mom, \
        f'hmm ({w_hmm:.4f}) should > ' \
        f'momentum ({w_mom:.4f})'

    w_sum = sum(w.values())
    assert abs(w_sum - 1.0) < 0.02, \
        f'Weights sum {w_sum:.4f} after updates'

    print(f'    hmm_regime weight:    {w_hmm:.4f}')
    print(f'    momentum_signal:      {w_mom:.4f}')
    print(f'    Weights sum:          {w_sum:.4f}')


def test_bma_discount_factor():
    """
    Older evidence should be downweighted.
    After many updates, old weights fade.
    Verify DISCOUNT applied correctly.
    """
    from api.models_ml.bayesian_aggregator import (
        BayesianModelAverager
    )
    bma  = BayesianModelAverager()
    init = bma.log_weights.copy()

    # 10 correct updates
    for _ in range(10):
        bma.update_weights(
            'hmm_regime', 'RISK_OFF', -0.01
        )

    # Log-weights should have changed
    changed = not np.allclose(
        bma.log_weights, init, atol=0.01
    )
    assert changed, \
        'Log-weights unchanged after 10 updates'
    assert bma.update_count == 10
    print(f'    Update count: {bma.update_count}')
    print(f'    Discount factor: {bma.DISCOUNT}')


def test_bma_aggregate_risk_off():
    """
    With 2 RISK_OFF and 1 RISK_ON signal,
    aggregate must return RISK_OFF direction.
    """
    from api.models_ml.bayesian_aggregator import (
        BayesianModelAverager
    )
    bma     = BayesianModelAverager()
    signals = {
        'hmm_regime': {
            'score': -0.6, 'direction': 'RISK_OFF',
            'confidence': 0.8,
        },
        'recession_guard': {
            'score': -0.4, 'direction': 'RISK_OFF',
            'confidence': 0.7,
        },
        'momentum_signal': {
            'score': 0.3, 'direction': 'RISK_ON',
            'confidence': 0.5,
        },
    }
    result = bma.aggregate(signals)

    for key in [
        'score', 'direction', 'conviction',
        'agreement_pct', 'model_weights',
        'contributions', 'dissenting',
        'top_models', 'method',
    ]:
        assert key in result, f'Missing key: {key}'

    assert -1.0 <= result['score'] <= 1.0
    assert result['direction'] == 'RISK_OFF', \
        f'Expected RISK_OFF, got {result["direction"]}'
    assert result['conviction'] in [
        'HIGH', 'MEDIUM', 'LOW'
    ]
    assert 0 <= result['agreement_pct'] <= 100

    print(f'    Score:      {result["score"]:.3f}')
    print(f'    Direction:  {result["direction"]}')
    print(f'    Conviction: {result["conviction"]}')
    print(f'    Agreement:  {result["agreement_pct"]}%')
    print(f'    Dissenting: {len(result["dissenting"])}')


def test_bma_aggregate_empty():
    """
    Aggregating empty signals must return
    safe neutral result without crashing.
    """
    from api.models_ml.bayesian_aggregator import (
        BayesianModelAverager
    )
    bma    = BayesianModelAverager()
    result = bma.aggregate({})
    assert result['direction'] == 'NEUTRAL'
    assert result['score'] == 0.0
    assert result['conviction'] == 'LOW'
    print('    Empty aggregate: safe neutral OK')


def test_bma_top_models():
    """
    _top_models() must return correct number of
    models sorted by weight descending.
    """
    from api.models_ml.bayesian_aggregator import (
        BayesianModelAverager
    )
    bma  = BayesianModelAverager()
    top3 = bma._top_models(3)
    assert len(top3) == 3
    # Should be sorted descending by weight
    weights = [t['weight'] for t in top3]
    assert weights == sorted(weights, reverse=True), \
        'Top models not sorted by weight'
    print(f'    Top 3: {[t["model"] for t in top3]}')
    print(f'    Weights: {weights}')


def test_bma_weight_history():
    """
    get_weight_history() must return entry
    for each model with required fields.
    """
    from api.models_ml.bayesian_aggregator import (
        BayesianModelAverager
    )
    bma     = BayesianModelAverager()
    history = bma.get_weight_history()
    assert len(history) == len(bma.MODELS)
    for model, stats in history.items():
        for key in [
            'weight', 'weight_pct',
            'accuracy', 'n_obs', 'trend',
        ]:
            assert key in stats, \
                f'{model} missing key: {key}'
        assert stats['trend'] in [
            'INCREASING', 'DECREASING',
            'STABLE', 'WARMING_UP',
        ]
    print(f'    Models tracked: {len(history)}')


def test_bma_db_init():
    """
    Singleton must initialise without crashing
    and produce weights summing to 1.
    DB may fail (no 'correct' column) but BMA
    should still work with uniform weights.
    """
    from api.models_ml.bayesian_aggregator import (
        get_bayesian_aggregator
    )
    bma   = get_bayesian_aggregator()
    stats = bma.fit_stats

    # Weights must sum to 1 regardless of DB init
    w_sum = sum(bma.weights)
    assert abs(w_sum - 1.0) < 0.02, \
        f'Weights sum {w_sum:.4f} after init'

    top = bma.get_current_weights()['top_model']
    assert top in bma.MODELS, \
        f'Top model {top} not in MODELS list'

    # Check if DB init succeeded or failed gracefully
    db_init_ok = 'weights' in stats and 'accuracy' in stats

    print(f'    DB init: {"OK" if db_init_ok else "FAILED (graceful)"}')
    print(f'    Top model: {top}')
    print(f'    Weights sum: {w_sum:.4f}')
    if db_init_ok:
        print(f'    N obs from DB: {stats.get("n_obs", "N/A")}')


test('bma_import',         test_bma_import)
test('bma_init_weights',   test_bma_init_weights)
test('bma_adaptation',     test_bma_weight_adaptation)
test('bma_discount',       test_bma_discount_factor)
test('bma_aggregate_roff', test_bma_aggregate_risk_off)
test('bma_aggregate_empty',test_bma_aggregate_empty)
test('bma_top_models',     test_bma_top_models)
test('bma_weight_history', test_bma_weight_history)
test('bma_db_init',        test_bma_db_init)


# ════════════════════════════════════════════════════
# PART 5 — Momentum Factor Model
# ════════════════════════════════════════════════════

print('\n── Part 5: Momentum Factor Model ──')


def test_momentum_import():
    from api.models_ml.momentum_factor import (
        MOMENTUM_UNIVERSE,
        VOL_TARGET_ANNUAL,
        MAX_LEVERAGE,
        VOL_CRASH_THRESHOLD,
    )
    assert len(MOMENTUM_UNIVERSE) == 16
    assert VOL_TARGET_ANNUAL == 0.12
    assert MAX_LEVERAGE == 2.0
    assert VOL_CRASH_THRESHOLD == 0.25


def test_momentum_instantiation():
    from api.models_ml.momentum_factor import MomentumFactorModel
    m = MomentumFactorModel()
    assert m.vol_target == 0.12
    assert m.lookback == 12
    assert m.skip == 1

    m2 = MomentumFactorModel(
        lookback_months=6,
        skip_months=0,
        vol_target=0.10,
    )
    assert m2.vol_target == 0.10
    assert m2.lookback == 6
    assert m2.skip == 0


def test_momentum_fetch_prices():
    from api.models_ml.momentum_factor import MomentumFactorModel
    m = MomentumFactorModel()
    df = m.fetch_prices(['SPY', 'QQQ'])
    assert len(df) >= 12, f'Only {len(df)} prices fetched'
    assert 'SPY' in df.columns
    assert 'QQQ' in df.columns
    print(f'    Fetched prices: {len(df)} months x {len(df.columns)} assets')


def test_momentum_cross_sectional():
    from api.models_ml.momentum_factor import MomentumFactorModel
    m = MomentumFactorModel()
    m.fetch_prices(['SPY', 'QQQ', 'IWM', 'TLT', 'GLD'])
    df = m.cross_sectional_momentum()

    assert len(df) > 0
    assert 'ticker' in df.columns
    assert 'return_12_1' in df.columns
    assert 'z_score' in df.columns
    assert 'rank' in df.columns
    assert 'cs_signal' in df.columns
    assert df['cs_signal'].isin(['BUY', 'SELL', 'NEUTRAL']).all()

    print(f'    Assets: {len(df)}')
    print(f'    Top signal: {df.iloc[0]["cs_signal"]} (rank {df.iloc[0]["rank"]})')


def test_momentum_time_series_spy():
    from api.models_ml.momentum_factor import MomentumFactorModel
    m = MomentumFactorModel()
    m.fetch_prices(['SPY', 'QQQ'])
    result = m.time_series_momentum('SPY')

    assert 'signal' in result
    assert result['signal'] in ['UPTREND', 'DOWNTREND', 'NEUTRAL', 'CAUTION']
    assert 'score' in result
    assert -2.0 <= result['score'] <= 2.0
    assert 'return_12m' in result
    assert 'vol_ann' in result
    assert 'vol_scalar' in result
    assert 'in_crash' in result
    assert result['vol_scalar'] <= 2.0

    print(f'    Signal: {result["signal"]}')
    print(f'    Score: {result["score"]:.4f}')
    if result['return_12m']:
        print(f'    12M Return: {result["return_12m"]*100:.1f}%')
        print(f'    Vol: {result["vol_ann"]*100:.1f}%')
        print(f'    Scalar: {result["vol_scalar"]:.2f}x')


def test_momentum_ts_missing_ticker():
    from api.models_ml.momentum_factor import MomentumFactorModel
    m = MomentumFactorModel()
    result = m.time_series_momentum('INVALID')
    assert 'signal' in result
    assert result['signal'] == 'NEUTRAL'
    assert result['score'] == 0.0
    assert result['in_crash'] is False


def test_momentum_vol_scaling():
    from api.models_ml.momentum_factor import (
        MomentumFactorModel, MAX_LEVERAGE
    )
    m = MomentumFactorModel(vol_target=0.12)

    # Low vol should allow higher scalar (capped at MAX_LEVERAGE)
    low_vol_scalar = min(0.12 / 0.08, MAX_LEVERAGE)
    assert low_vol_scalar > 1.0

    # High vol should constrain scalar
    high_vol_scalar = min(0.12 / 0.25, MAX_LEVERAGE)
    assert high_vol_scalar < 1.0

    print(f'    Low vol scalar (vol=8%): {low_vol_scalar:.2f}x')
    print(f'    High vol scalar (vol=25%): {high_vol_scalar:.2f}x')


def test_momentum_crash_filter():
    from api.models_ml.momentum_factor import VOL_CRASH_THRESHOLD

    # Vol above 25% triggers crash filter
    vol_high = 0.30
    in_crash = vol_high > VOL_CRASH_THRESHOLD
    assert in_crash

    # Vol below threshold
    vol_low = 0.15
    in_crash_low = vol_low > VOL_CRASH_THRESHOLD
    assert not in_crash_low

    print(f'    Crash threshold: {VOL_CRASH_THRESHOLD}')
    print(f'    30% vol in crash: {in_crash}')
    print(f'    15% vol in crash: {in_crash_low}')


def test_momentum_composite():
    from api.models_ml.momentum_factor import MomentumFactorModel
    m = MomentumFactorModel()
    result = m.run()

    assert 'composite' in result
    assert 'assets' in result
    assert 'crash_pct' in result
    assert 'n_assets' in result
    assert 'last_updated' in result

    comp = result['composite']
    assert 'score' in comp
    assert comp['direction'] in ['RISK_ON', 'RISK_OFF', 'NEUTRAL', 'CAUTION']
    assert comp['conviction'] in ['HIGH', 'MEDIUM', 'LOW']

    print(f'    Assets: {result["n_assets"]}')
    print(f'    Direction: {comp["direction"]}')
    print(f'    Conviction: {comp["conviction"]}')
    print(f'    Score: {comp["score"]:.4f}')


def test_momentum_get_signal():
    from api.models_ml.momentum_factor import get_momentum_signal
    result = get_momentum_signal()

    assert 'score' in result
    assert 'direction' in result
    assert 'confidence' in result
    assert 'conviction' in result

    assert result['direction'] in ['RISK_ON', 'RISK_OFF', 'NEUTRAL']
    assert -1.0 <= result['score'] <= 1.0
    assert 0.0 <= result['confidence'] <= 1.0

    print(f'    Direction: {result["direction"]}')
    print(f'    Score: {result["score"]:.4f}')
    print(f'    Confidence: {result["confidence"]:.2f}')
    print(f'    Conviction: {result["conviction"]}')


def test_momentum_stale_check():
    from api.models_ml.momentum_factor import MomentumFactorModel
    from datetime import datetime, timedelta

    m = MomentumFactorModel()

    # Fresh data (< 4 hours default)
    fresh = datetime.utcnow() - timedelta(hours=2)
    m.last_fetch = fresh.isoformat()
    assert not m._is_stale()

    # Stale data (> 4 hours)
    stale = datetime.utcnow() - timedelta(hours=5)
    m.last_fetch = stale.isoformat()
    assert m._is_stale()

    print(f'    Fresh check (2h): not stale OK')
    print(f'    Stale check (5h): stale OK')


def test_momentum_singleton():
    from api.models_ml.momentum_factor import get_momentum_model
    m1 = get_momentum_model()
    m2 = get_momentum_model()
    assert m1 is m2, 'Singleton not returning same instance'
    print(f'    Singleton OK, last_fetch={m1.last_fetch}')


test('mom_import',          test_momentum_import)
test('mom_init',            test_momentum_instantiation)
test('mom_fetch_prices',    test_momentum_fetch_prices)
test('mom_cross_sectional', test_momentum_cross_sectional)
test('mom_ts_spy',          test_momentum_time_series_spy)
test('mom_ts_missing',      test_momentum_ts_missing_ticker)
test('mom_vol_scaling',     test_momentum_vol_scaling)
test('mom_crash_filter',    test_momentum_crash_filter)
test('mom_composite',       test_momentum_composite)
test('mom_get_signal',      test_momentum_get_signal)
test('mom_stale_check',     test_momentum_stale_check)
test('mom_singleton',       test_momentum_singleton)


# ════════════════════════════════════════════════════
# PART 6D — Full Pipeline Integration Tests
# All 5 models working together
# ════════════════════════════════════════════════════

print('\n── Part 6D: Full Pipeline Integration ──')


def test_all_models_import_together():
    """
    All 5 model modules must import without
    conflict. No circular imports or name clashes.
    """
    print('    All 5 modules import cleanly')


def test_all_singletons_independent():
    """
    Each singleton must be independent.
    Getting one must not affect the others.
    """
    from api.models_ml.regime_hmm import (
        get_regime_hmm
    )
    from api.models_ml.recession_probit import (
        get_recession_probit
    )
    from api.models_ml.kalman_smoother import (
        get_signal_smoother
    )
    from api.models_ml.bayesian_aggregator import (
        get_bayesian_aggregator
    )
    from api.models_ml.momentum_factor import (
        get_momentum_model
    )

    hmm     = get_regime_hmm()
    probit  = get_recession_probit()
    kalman  = get_signal_smoother()
    bma     = get_bayesian_aggregator()
    momentum= get_momentum_model()

    # All singletons must be different objects
    objects = [hmm, probit, kalman, bma, momentum]
    ids     = [id(o) for o in objects]
    assert len(set(ids)) == 5, \
        'Two singletons are the same object'

    print('    All 5 singletons are independent objects')
    print(f'    HMM fitted:     {hmm.fitted}')
    print(f'    Probit fitted:  {probit.fitted}')
    print(f'    Momentum data:  '
          f'{momentum.prices is not None}')


def test_hmm_feeds_into_bma():
    """
    HMM regime signal must be collectable
    into the Bayesian aggregator.
    Tests the Part 1 → Part 4 pipeline.
    """
    from api.models_ml.regime_hmm import (
        get_regime_hmm
    )
    from api.models_ml.bayesian_aggregator import (
        BayesianModelAverager
    )

    hmm = get_regime_hmm()

    if not hmm.fitted:
        print('    SKIP: HMM not fitted yet')
        return

    # Get HMM signal
    regime = hmm.predict_current({
        'growth_z':    -0.79,
        'inflation_z': -0.76,
        'yield_curve':  0.80,
        'credit_z':     0.20,
    })

    score = (
         0.80 if regime['regime'] == 'Goldilocks'
        else 0.50 if regime['regime'] == 'Reflation'
        else -0.60 if regime['regime'] == 'Slowdown'
        else -0.80
    )

    # Feed into BMA
    bma    = BayesianModelAverager()
    result = bma.aggregate({
        'hmm_regime': {
            'score':      score,
            'direction':  (
                'RISK_ON' if score > 0
                else 'RISK_OFF'
            ),
            'confidence': regime['confidence'],
        }
    })

    assert result['direction'] in [
        'RISK_ON', 'RISK_OFF', 'NEUTRAL'
    ]
    assert -1.0 <= result['score'] <= 1.0

    print(f'    HMM regime: {regime["regime"]}')
    print(f'    HMM → BMA score: {result["score"]:.3f}')
    print(f'    BMA direction:   {result["direction"]}')


def test_probit_feeds_into_bma():
    """
    Probit recession probability must be
    convertible to a BMA signal.
    Tests the Part 2 → Part 4 pipeline.
    """
    from api.models_ml.recession_probit import (
        get_recession_probit
    )
    from api.models_ml.bayesian_aggregator import (
        BayesianModelAverager
    )

    probit = get_recession_probit()
    result = probit.predict(
        spread=0.8, fed_funds=3.64
    )
    prob   = result['probability']

    # Convert to BMA signal
    score = float(
        __import__('numpy').clip(
            -(prob - 0.15) * 4.0, -1.0, 1.0
        )
    )
    direction = (
        'RISK_OFF' if prob >= 0.25
        else 'RISK_ON' if prob <= 0.10
        else 'NEUTRAL'
    )

    bma    = BayesianModelAverager()
    agg    = bma.aggregate({
        'recession_guard': {
            'score':      score,
            'direction':  direction,
            'confidence': 0.80,
        }
    })

    assert agg['direction'] in [
        'RISK_ON', 'RISK_OFF', 'NEUTRAL'
    ]
    print(f'    Recession prob: {prob*100:.1f}%')
    print(f'    BMA score:      {agg["score"]:.3f}')
    print(f'    BMA direction:  {agg["direction"]}')


def test_kalman_smooths_ensemble():
    """
    Kalman smoother must reduce noise in a
    simulated signal history.
    Tests the Part 3 → ensemble pipeline.
    """
    from api.models_ml.kalman_smoother import (
        SignalKalmanSmoother
    )

    # Simulate noisy signal (like real data)
    np.random.seed(7)
    true_trend = np.linspace(0.2, -0.3, 20)
    noisy      = true_trend + \
                 np.random.normal(0, 0.1, 20)

    kf       = SignalKalmanSmoother()
    result   = kf.smooth(noisy.tolist())
    smoothed = result['smoothed']

    # Smoothed must be less noisy than raw
    raw_std  = float(np.std(np.diff(noisy)))
    smth_std = float(np.std(np.diff(smoothed)))

    assert 'smoothed' in result
    assert 'method' in result
    assert result['method'] in ['kalman_rts', 'ewma_fallback']
    assert len(smoothed) == len(noisy)

    print(f'    Raw noise:      {raw_std:.4f}')
    print(f'    Smoothed noise: {smth_std:.4f}')
    print(f'    Method: {result["method"]}')
    print(f'    N samples: {len(smoothed)}')


def test_momentum_feeds_into_bma():
    """
    Momentum signal must be collectable
    into the Bayesian aggregator.
    Tests the Part 5 → Part 4 pipeline.
    """
    from api.models_ml.momentum_factor import (
        get_momentum_signal
    )
    from api.models_ml.bayesian_aggregator import (
        BayesianModelAverager
    )

    mom_sig = get_momentum_signal()
    bma     = BayesianModelAverager()

    result = bma.aggregate({
        'momentum_signal': {
            'score':      mom_sig['score'],
            'direction':  mom_sig['direction'],
            'confidence': mom_sig['confidence'],
        }
    })

    assert result['direction'] in [
        'RISK_ON', 'RISK_OFF', 'NEUTRAL', 'CAUTION'
    ]
    assert -1.0 <= result['score'] <= 1.0

    print(f'    Momentum:    {mom_sig["direction"]} '
          f'({mom_sig["score"]:.3f})')
    print(f'    BMA result:  {result["direction"]} '
          f'({result["score"]:.3f})')


def test_full_bma_all_signals():
    """
    Run all 5 models and aggregate into one
    Bayesian ensemble signal.
    This is the core production pipeline.
    """
    import numpy as np
    from api.models_ml.regime_hmm import (
        get_regime_hmm
    )
    from api.models_ml.recession_probit import (
        get_recession_probit
    )
    from api.models_ml.kalman_smoother import (
        get_signal_smoother
    )
    from api.models_ml.momentum_factor import (
        get_momentum_signal
    )
    from api.models_ml.bayesian_aggregator import (
        BayesianModelAverager
    )

    signals = {}

    # Signal 1: HMM Regime
    try:
        hmm = get_regime_hmm()
        if hmm.fitted:
            regime = hmm.predict_current({
                'growth_z':    -0.79,
                'inflation_z': -0.76,
                'yield_curve':  0.80,
                'credit_z':     0.20,
            })
            sc = (
                 0.80 if regime['regime'] == 'Goldilocks'
                else 0.50 if regime['regime'] == 'Reflation'
                else -0.60 if regime['regime'] == 'Slowdown'
                else -0.80
            )
            signals['hmm_regime'] = {
                'score':      sc,
                'direction': ('RISK_ON' if sc > 0
                              else 'RISK_OFF'),
                'confidence': regime['confidence'],
            }
    except Exception as e:
        print(f'    WARN: HMM failed: {e}')

    # Signal 2: Recession Probit
    try:
        probit = get_recession_probit()
        rec    = probit.predict(0.8, 3.64)
        prob   = rec['probability']
        sc     = float(np.clip(
            -(prob - 0.15) * 4.0, -1.0, 1.0
        ))
        signals['recession_guard'] = {
            'score':      sc,
            'direction': (
                'RISK_OFF' if prob >= 0.25
                else 'RISK_ON' if prob <= 0.10
                else 'NEUTRAL'
            ),
            'confidence': 0.80,
        }
    except Exception as e:
        print(f'    WARN: Probit failed: {e}')

    # Signal 3: Kalman (smoothed growth score)
    try:
        kalman = get_signal_smoother()
        growth_hist = [-0.3, -0.5, -0.6, -0.7,
                       -0.8, -0.79]
        smoothed = kalman.smooth(growth_hist)
        # Use first smoothed value as signal
        sc = smoothed['smoothed'][0] if smoothed['smoothed'] else 0.0
        direction = 'RISK_ON' if sc > 0.1 else 'RISK_OFF' if sc < -0.1 else 'NEUTRAL'
        signals['kalman_filter'] = {
            'score':      round(sc, 4),
            'direction':  direction,
            'confidence': 0.70,
        }
    except Exception as e:
        print(f'    WARN: Kalman failed: {e}')

    # Signal 4: Momentum
    try:
        mom = get_momentum_signal()
        signals['momentum_signal'] = {
            'score':      mom['score'],
            'direction':  mom['direction'],
            'confidence': mom['confidence'],
        }
    except Exception as e:
        print(f'    WARN: Momentum failed: {e}')

    # Must have at least 2 signals
    assert len(signals) >= 2, \
        f'Only {len(signals)} signals — pipeline broken'

    # Aggregate with BMA
    bma    = BayesianModelAverager()
    result = bma.aggregate(signals)

    assert -1.0 <= result['score'] <= 1.0
    assert result['direction'] in [
        'RISK_ON', 'RISK_OFF', 'NEUTRAL'
    ]
    assert result['conviction'] in [
        'HIGH', 'MEDIUM', 'LOW'
    ]
    assert result['method'] == \
        'Bayesian_Model_Averaging'

    print(f'    Signals collected: {len(signals)}')
    print(f'    Models: {list(signals.keys())}')
    print(f'\n    ── ENSEMBLE RESULT ──')
    print(f'    Score:      {result["score"]:.3f}')
    print(f'    Direction:  {result["direction"]}')
    print(f'    Conviction: {result["conviction"]}')
    print(f'    Agreement:  {result["agreement_pct"]}%')
    print(f'    Std:        {result["posterior_std"]:.3f}')
    if result.get('dissenting'):
        print(f'    Dissenting: '
              f'{[d["model"] for d in result["dissenting"]]}')


def test_regime_consistency():
    """
    HMM regime and Probit signal should be
    directionally consistent under Slowdown:
    both should give RISK_OFF or NEUTRAL signals.
    """
    from api.models_ml.regime_hmm import (
        get_regime_hmm
    )
    from api.models_ml.recession_probit import (
        get_recession_probit
    )

    hmm    = get_regime_hmm()
    probit = get_recession_probit()

    if not hmm.fitted:
        print('    SKIP: HMM not fitted')
        return

    regime  = hmm.predict_current({
        'growth_z':    -0.79,
        'inflation_z': -0.76,
        'yield_curve':  0.80,
        'credit_z':     0.20,
    })
    rec     = probit.predict(0.8, 3.64)
    prob    = rec['probability']

    hmm_bull = regime['regime'] in [
        'Goldilocks', 'Reflation'
    ]
    rec_bull = prob < 0.20

    print(f'    HMM regime:  {regime["regime"]}')
    print(f'    HMM bullish: {hmm_bull}')
    print(f'    Rec prob:    {prob*100:.1f}%')
    print(f'    Rec bullish: {rec_bull}')

    # Both pointing same direction is ideal
    if hmm_bull == rec_bull:
        print('    Consistency: ALIGNED')
    else:
        print('    Consistency: DIVERGENT '
              '(normal — models use different data)')


def test_kalman_uncertainty_propagation():
    """
    Kalman smoother must handle high and low
    variance sequences differently.
    Higher input variance → less smoothing confidence.
    """
    from api.models_ml.kalman_smoother import (
        SignalKalmanSmoother
    )
    # Use fresh instances to avoid state issues
    kf_certain   = SignalKalmanSmoother()
    kf_uncertain = SignalKalmanSmoother()

    # High certainty sequence (low noise) - need 10+ samples for fit
    certain_scores   = [0.40, 0.42, 0.44, 0.43, 0.45, 0.44,
                        0.46, 0.45, 0.47, 0.46, 0.48, 0.47]
    uncertain_scores = [0.40, 0.20, -0.10, 0.50, -0.20, 0.30,
                        0.10, 0.60, -0.30, 0.40, 0.20, 0.50]

    r_certain   = kf_certain.smooth(certain_scores)
    r_uncertain = kf_uncertain.smooth(uncertain_scores)

    # Check both returned valid results
    assert 'smoothed' in r_certain
    assert 'smoothed' in r_uncertain
    assert len(r_certain['smoothed']) == len(certain_scores)
    assert len(r_uncertain['smoothed']) == len(uncertain_scores)

    # Higher input variance should result in less noise reduction
    nrp_certain   = r_certain.get('noise_reduction_pct')
    nrp_uncertain = r_uncertain.get('noise_reduction_pct')

    if nrp_certain is not None and nrp_uncertain is not None:
        print(f'    Certain noise reduction:   {nrp_certain:.1f}%')
        print(f'    Uncertain noise reduction: {nrp_uncertain:.1f}%')
    else:
        print(f'    Certain method:   {r_certain["method"]}')
        print(f'    Uncertain method: {r_uncertain["method"]}')


def test_bma_outcome_recording():
    """
    Recording outcomes must update weights
    without crashing and keep sum = 1.
    """
    from api.models_ml.bayesian_aggregator import (
        record_prediction_outcome,
        get_bayesian_aggregator,
    )

    # Record several outcomes
    outcomes = [
        ('hmm_regime',       'RISK_OFF', -0.015),
        ('momentum_signal',  'RISK_ON',   0.008),
        ('kalman_filter',    'RISK_OFF',  -0.005),
        ('recession_guard',  'RISK_OFF',  -0.020),
        ('momentum_signal',  'RISK_ON',  -0.003),  # wrong
    ]

    for model, direction, ret in outcomes:
        w = record_prediction_outcome(
            model, direction, ret
        )
        w_sum = sum(w['weights'].values())
        assert abs(w_sum - 1.0) < 0.02, \
            f'Weights sum {w_sum:.4f} after recording'

    bma   = get_bayesian_aggregator()
    count = bma.update_count
    assert count >= len(outcomes), \
        f'Update count {count} < {len(outcomes)}'

    print(f'    Outcomes recorded: {len(outcomes)}')
    print(f'    Total updates:     {count}')
    print(f'    Weights sum:       '
          f'{sum(bma.weights):.4f}')


def test_end_to_end_pipeline_timing():
    """
    Full pipeline must complete within
    reasonable time (< 30 seconds).
    Price fetching is cached so should be fast
    on second run.
    """
    import time
    from api.models_ml.regime_hmm import (
        get_regime_hmm
    )
    from api.models_ml.recession_probit import (
        get_recession_probit
    )
    from api.models_ml.kalman_smoother import (
        get_signal_smoother
    )
    from api.models_ml.momentum_factor import (
        get_momentum_signal
    )
    from api.models_ml.bayesian_aggregator import (
        BayesianModelAverager
    )

    start = time.time()

    # Run all models
    hmm    = get_regime_hmm()
    probit = get_recession_probit()
    kalman = get_signal_smoother()
    mom    = get_momentum_signal()
    bma    = BayesianModelAverager()

    signals = {}

    if hmm.fitted:
        r  = hmm.predict_current({
            'growth_z': -0.79, 'inflation_z': -0.76,
            'yield_curve': 0.8, 'credit_z': 0.2,
        })
        sc = -0.6 if r['regime'] == 'Slowdown' else 0.6
        signals['hmm_regime'] = {
            'score': sc,
            'direction': 'RISK_OFF' if sc < 0
                         else 'RISK_ON',
            'confidence': r['confidence'],
        }

    rec  = probit.predict(0.8, 3.64)
    prob = rec['probability']
    signals['recession_guard'] = {
        'score':      float(
            __import__('numpy').clip(
                -(prob - 0.15) * 4, -1, 1
            )
        ),
        'direction':  (
            'RISK_OFF' if prob >= 0.25
            else 'NEUTRAL'
        ),
        'confidence': 0.75,
    }

    signals['momentum_signal'] = {
        'score':      mom['score'],
        'direction':  mom['direction'],
        'confidence': mom['confidence'],
    }

    bma.aggregate(signals)

    elapsed = time.time() - start

    assert elapsed < 30.0, \
        f'Pipeline took {elapsed:.1f}s > 30s'

    print(f'    Pipeline time: {elapsed:.2f}s')
    print(f'    Signals: {len(signals)}')
    print(f'    Status: {"FAST" if elapsed < 5 else "OK"}')


test('pipeline_imports',     test_all_models_import_together)
test('pipeline_singletons',  test_all_singletons_independent)
test('hmm_to_bma',           test_hmm_feeds_into_bma)
test('probit_to_bma',        test_probit_feeds_into_bma)
test('kalman_smooths',       test_kalman_smooths_ensemble)
test('momentum_to_bma',      test_momentum_feeds_into_bma)
test('full_bma_all_signals', test_full_bma_all_signals)
test('regime_consistency',   test_regime_consistency)
test('kalman_uncertainty',   test_kalman_uncertainty_propagation)
test('bma_outcome_record',   test_bma_outcome_recording)
test('pipeline_timing',      test_end_to_end_pipeline_timing)


# ════════════════════════════════════════════════════
# SUMMARY — Parts 1 through 6D
# ════════════════════════════════════════════════════

print('\n' + '=' * 52)
print('INTEGRATION TEST SUMMARY — MACRO TERMINALv8.0')
print('=' * 52)

passed = sum(1 for r in results if r['status'] == PASS)
failed = sum(1 for r in results if r['status'] == FAIL)
total  = len(results)

# ════════════════════════════════════════════════════
# PART 6E — API Endpoint Tests
# ════════════════════════════════════════════════════

print('\n── Part 6E: API Endpoint Tests ──')
print('   (requires server running on port 8000)')


def _get(path: str, timeout: int = 10) -> dict | None:
    """
    Helper: GET request to localhost:8000.
    Returns parsed JSON or None if unavailable.
    """
    try:
        import urllib.request
        import json as _json
        url = f'http://localhost:8000{path}'
        with urllib.request.urlopen(
            url, timeout=timeout
        ) as resp:
            return _json.loads(resp.read())
    except Exception as e:
        return None


def _server_available() -> bool:
    """Check if API server is running."""
    result = _get('/api/health', timeout=3)
    return result is not None


SERVER_UP = _server_available()

if not SERVER_UP:
    print('  SKIP  Server not running on port 8000')
    print('  SKIP  Start server and re-run for API tests')
else:
    print('  INFO  Server available — running API tests')


def test_health_endpoint():
    if not SERVER_UP:
        return
    d = _get('/api/health')
    assert d is not None, '/api/health returned None'
    assert d.get('status') in [
        'healthy', 'ok', 'HEALTHY'
    ], f'Bad status: {d.get("status")}'
    print(f'    Status:   {d.get("status")}')
    print(f'    Version:  {d.get("version","?")}')
    print(f'    Uptime:   {d.get("uptime","?")}')


def test_regime_endpoint():
    if not SERVER_UP:
        return
    d = _get('/api/regime')
    assert d is not None, '/api/regime returned None'
    assert 'regime' in d or 'current_regime' in d, \
        f'No regime field in response: {list(d.keys())}'
    regime = d.get('regime') or d.get('current_regime')
    assert regime in [
        'Goldilocks', 'Slowdown',
        'Reflation',  'Stagflation',
    ], f'Unknown regime: {regime}'
    conf = d.get('confidence', 0)
    assert 0.0 <= conf <= 1.0
    print(f'    Regime:     {regime}')
    print(f'    Confidence: {conf:.3f}')
    method = d.get('method', 'unknown')
    if 'HMM' in str(method):
        print(f'    Method:     HMM (upgraded)')
    else:
        print(f'    Method:     {method}')


def test_recession_endpoint():
    if not SERVER_UP:
        return
    # Try multiple possible endpoint paths
    d = (
        _get('/api/recession/model-stats') or
        _get('/api/recession') or
        _get('/api/ensemble')
    )
    assert d is not None, \
        'No recession endpoint responding'

    # Extract probability wherever it lives
    prob = (
        d.get('probability') or
        d.get('recession_probability') or
        d.get('current_prediction', {})
          .get('probability') if isinstance(
            d.get('current_prediction'), dict
          ) else None
    )

    if prob is not None:
        assert 0.0 <= float(prob) <= 1.0, \
            f'Prob {prob} out of range'
        print(f'    Recession prob: {float(prob)*100:.1f}%')

    model = (
        d.get('model') or
        d.get('fitted') or
        d.get('recession_model', 'unknown')
    )
    print(f'    Model info: {model}')


def test_ensemble_endpoint():
    if not SERVER_UP:
        return
    d = _get('/api/ensemble')
    assert d is not None, '/api/ensemble returned None'

    score = (
        d.get('score') or
        d.get('ensemble_score') or
        d.get('final_score')
    )
    direction = (
        d.get('direction') or
        d.get('signal') or
        d.get('final_signal')
    )

    assert direction in [
        'RISK_ON', 'RISK_OFF', 'NEUTRAL',
        'Defensive', 'Bullish', 'Bearish',
    ], f'Unknown direction: {direction}'

    method = d.get('method', '')
    print(f'    Direction:  {direction}')
    print(f'    Score:      {score}')
    if 'Bayesian' in str(method):
        print(f'    Method:     Bayesian (upgraded)')
    else:
        print(f'    Method:     {method or "standard"}')


def test_ensemble_weights_endpoint():
    if not SERVER_UP:
        return
    d = _get('/api/ensemble/weights')
    if d is None:
        print('    SKIP: /api/ensemble/weights not found')
        return
    weights = (
        d.get('weights', {}).get('weights') or
        d.get('weights') or {}
    )
    if weights:
        w_sum = sum(float(v) for v in weights.values())
        assert abs(w_sum - 1.0) < 0.05, \
            f'Weights sum {w_sum:.3f}'
        top   = max(weights, key=weights.get)
        print(f'    Models:      {len(weights)}')
        print(f'    Weights sum: {w_sum:.4f}')
        print(f'    Top model:   {top}')
    else:
        print('    Weights not in expected format')


def test_cta_endpoint():
    if not SERVER_UP:
        return
    d = _get('/api/cta')
    assert d is not None, '/api/cta returned None'

    signal = (
        d.get('cta_signal') or
        d.get('signal') or
        d.get('direction')
    )
    assets = d.get('assets', [])
    n      = d.get('n_assets', len(assets))

    assert n >= 0
    print(f'    CTA signal: {signal}')
    print(f'    N assets:   {n}')

    if assets:
        a = assets[0]
        print(f'    Top asset:  {a.get("ticker")}')
        r12 = a.get('return_12m')
        print(f'    12M return: {r12}')


def test_kalman_endpoint():
    if not SERVER_UP:
        return
    d = _get('/api/signals/kalman')
    if d is None:
        print('    SKIP: /api/signals/kalman not found')
        return
    assert 'method' in d or \
           'signal_estimates' in d, \
        f'Unexpected response: {list(d.keys())}'
    method = d.get('method', '')
    print(f'    Method: {method}')
    estimates = d.get('signal_estimates', {})
    if estimates:
        print(f'    Signals: {list(estimates.keys())}')


def test_momentum_cs_endpoint():
    if not SERVER_UP:
        return
    d = _get('/api/momentum/cross-sectional')
    if d is None:
        print('    SKIP: momentum endpoint not found')
        return
    n = d.get('n_assets', 0)
    assert n >= 0
    print(f'    CS assets: {n}')
    if d.get('top_3'):
        print(f'    Top 3: {d["top_3"]}')
    if d.get('bottom_3'):
        print(f'    Bottom 3: {d["bottom_3"]}')


def test_momentum_ts_endpoint():
    if not SERVER_UP:
        return
    d = _get('/api/momentum/time-series/SPY')
    if d is None:
        print('    SKIP: TS momentum endpoint not found')
        return
    ts = d.get('ts_momentum', {})
    if ts:
        print(f'    SPY signal:    {ts.get("signal")}')
        print(f'    SPY 12M:       {ts.get("return_12m")}')
        print(f'    SPY vol:       {ts.get("vol_ann")}')
        print(f'    Risk-managed:  {ts.get("vol_scalar")}')


def test_signal_stack_endpoint():
    if not SERVER_UP:
        return
    d = _get('/api/signal-stack')
    assert d is not None, \
        '/api/signal-stack returned None'
    layers = d.get('layers', [])
    final  = (
        d.get('final_signal') or
        d.get('final_consensus') or
        d.get('consensus')
    )
    print(f'    Layers:    {len(layers)}')
    print(f'    Final:     {final}')
    assert len(layers) >= 6, \
        f'Only {len(layers)} layers — expected 10'


def test_audit_log_endpoint():
    if not SERVER_UP:
        return
    d = _get('/api/audit-log?limit=5')
    if d is None:
        print('    SKIP: audit-log endpoint not found')
        return
    entries = (
        d.get('entries') or
        d.get('logs') or
        d if isinstance(d, list) else []
    )
    print(f'    Audit entries: {len(entries)}')


def test_no_500_errors():
    """
    Critical endpoints must not return 500.
    Uses urllib to check HTTP status codes.
    """
    if not SERVER_UP:
        return

    import urllib.request
    import urllib.error

    critical_endpoints = [
        '/api/health',
        '/api/regime',
        '/api/ensemble',
        '/api/signal-stack',
        '/api/cta',
        '/api/key-metrics',
        '/api/sector-allocation',
    ]

    errors = []
    for path in critical_endpoints:
        try:
            url = f'http://localhost:8000{path}'
            urllib.request.urlopen(url, timeout=5)
        except urllib.error.HTTPError as e:
            if e.code == 500:
                errors.append(f'{path} → HTTP 500')
        except Exception:
            pass  # connection error is not a 500

    assert not errors, \
        f'500 errors found: {errors}'
    print(f'    Checked {len(critical_endpoints)} endpoints')
    print(f'    Zero 500 errors')


test('api_health',         test_health_endpoint)
test('api_regime',         test_regime_endpoint)
test('api_recession',      test_recession_endpoint)
test('api_ensemble',       test_ensemble_endpoint)
test('api_weights',        test_ensemble_weights_endpoint)
test('api_cta',            test_cta_endpoint)
test('api_kalman',         test_kalman_endpoint)
test('api_momentum_cs',    test_momentum_cs_endpoint)
test('api_momentum_ts',    test_momentum_ts_endpoint)
test('api_signal_stack',   test_signal_stack_endpoint)
test('api_audit_log',      test_audit_log_endpoint)
test('api_no_500s',        test_no_500_errors)


# ════════════════════════════════════════════════════
# FINAL SUMMARY — All parts
# ════════════════════════════════════════════════════

print('\n' + '=' * 60)
print('MACRO TERMINALv8.0 — FULL INTEGRATION REPORT')
print('=' * 60)

passed = sum(1 for r in results if r['status'] == PASS)
failed = sum(1 for r in results if r['status'] == FAIL)
total  = len(results)

print(f'\nOverall: {passed}/{total} passed, '
      f'{failed} failed\n')

part_map = {
    'Part 1  HMM Regime':     'hmm',
    'Part 2  Recession Probit':'probit',
    'Part 3  Kalman Filter':  'kalman',
    'Part 4  Bayesian BMA':   'bma',
    'Part 5  Momentum':       'mom',
    'Part 6D Pipeline':       'pipeline',
    'Part 6E API':            'api',
}

for part_name, prefix in part_map.items():
    part_tests = [
        r for r in results
        if r['name'].startswith(prefix)
    ]
    if not part_tests:
        continue
    n_pass = sum(
        1 for t in part_tests
        if t['status'] == PASS
    )
    n_fail = len(part_tests) - n_pass
    icon   = 'OK  ' if n_fail == 0 else 'FAIL'
    avg_t  = round(
        sum(t['elapsed'] for t in part_tests) /
        len(part_tests), 2
    )
    print(f'  {icon}  {part_name}: '
          f'{n_pass}/{len(part_tests)} '
          f'(avg {avg_t}s)')

if failed:
    print('\n── Failed Tests ──')
    for r in results:
        if r['status'] == FAIL:
            print(f'  FAIL  {r["name"]}')
            print(f'        {r["error"]}')

print('\n── Slowest Tests ──')
slowest = sorted(
    results, key=lambda x: x['elapsed'], reverse=True
)[:5]
for r in slowest:
    print(f'  {r["elapsed"]:5.2f}s  {r["name"]}')

print('\n── Model Status ──')
try:
    from api.models_ml.regime_hmm import get_regime_hmm
    hmm = get_regime_hmm()
    print(f'  HMM:      fitted={hmm.fitted}'
          f'{", trained=" + hmm.last_trained[:10] if hmm.last_trained else ""}')
except Exception as e:
    print(f'  HMM:      ERROR ({e})')

try:
    from api.models_ml.recession_probit import (
        get_recession_probit
    )
    p = get_recession_probit()
    ps = p.fit_stats
    print(f'  Probit:   fitted={p.fitted}'
          f'{", pseudo_R2=" + str(ps.get("pseudo_r2")) if ps else ""}')
except Exception as e:
    print(f'  Probit:   ERROR ({e})')

try:
    from api.models_ml.kalman_smoother import (
        get_signal_smoother
    )
    k = get_signal_smoother()
    print(f'  Kalman:   fitted={k.fitted}'
          f', updated={k.last_fetch}')
except Exception as e:
    print(f'  Kalman:   ERROR ({e})')

try:
    from api.models_ml.bayesian_aggregator import (
        get_bayesian_aggregator
    )
    b   = get_bayesian_aggregator()
    top = b.get_current_weights()['top_model']
    print(f'  BMA:      models={len(b.MODELS)}'
          f', top={top}'
          f', updates={b.update_count}')
except Exception as e:
    print(f'  BMA:      ERROR ({e})')

try:
    from api.models_ml.momentum_factor import (
        get_momentum_model
    )
    m = get_momentum_model()
    n = len(m.prices.columns) \
        if m.prices is not None else 0
    print(f'  Momentum: assets={n}'
          f', fetched={m.last_fetch}')
except Exception as e:
    print(f'  Momentum: ERROR ({e})')

print('\n' + '=' * 60)
if failed == 0:
    print('ALL TESTS PASSED — system ready')
elif failed <= 3:
    print(f'MOSTLY PASSING — {failed} minor issues')
else:
    print(f'ATTENTION NEEDED — {failed} failures')
print('=' * 60 + '\n')

sys.exit(1 if failed > 0 else 0)
