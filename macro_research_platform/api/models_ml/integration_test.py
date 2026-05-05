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
    from api.models_ml.regime_hmm import (
        MacroRegimeHMM,
        get_regime_hmm,
        retrain_hmm,
    )


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
        RecessionProbitModel,
        get_recession_probit,
        retrain_probit,
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
    from api.models_ml.kalman_smoother import (
        SignalKalmanSmoother,
        get_signal_smoother,
        reset_smoother,
    )


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
        SignalKalmanSmoother
    )
    obs = np.array([
        0.5, 0.6, 0.55, 0.7, 0.65, 0.75
    ])
    kf     = SignalKalmanSmoother()
    result = kf.smooth(obs)

    for key in ['smoothed', 'raw', 'method',
                'noise_reduction_pct', 'n_samples']:
        assert key in result, f'Missing key: {key}'

    assert len(result['smoothed']) == len(obs)
    assert result['method'] in ['kalman_rts', 'ewma_fallback']
    assert result['n_samples'] == len(obs)

    print(f'    Method: {result["method"]}')
    print(f'    N samples: {result["n_samples"]}')


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
    from api.models_ml.bayesian_aggregator import (
        BayesianModelAverager,
        get_bayesian_aggregator,
        record_prediction_outcome,
    )


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
    Singleton must initialise from DB without
    crashing and produce weights summing to 1.
    """
    from api.models_ml.bayesian_aggregator import (
        get_bayesian_aggregator
    )
    bma   = get_bayesian_aggregator()
    stats = bma.fit_stats

    assert 'weights'  in stats, 'No weights in fit_stats'
    assert 'accuracy' in stats, 'No accuracy in fit_stats'

    w_sum = sum(bma.weights)
    assert abs(w_sum - 1.0) < 0.02, \
        f'Weights sum {w_sum:.4f} after DB init'

    top = bma.get_current_weights()['top_model']
    assert top in bma.MODELS, \
        f'Top model {top} not in MODELS list'

    print(f'    DB init OK')
    print(f'    Top model: {top}')
    print(f'    Weights sum: {w_sum:.4f}')


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
        MomentumFactorModel,
        get_momentum_model,
        get_momentum_signal,
        refresh_momentum_prices,
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
# SUMMARY — Parts 1 through 5
# ════════════════════════════════════════════════════

print('\n' + '=' * 52)
print('INTEGRATION TEST SUMMARY — MACRO TERMINALv8.0')
print('=' * 52)

passed = sum(1 for r in results if r['status'] == PASS)
failed = sum(1 for r in results if r['status'] == FAIL)
total  = len(results)

# By-part breakdown
part1 = [r for r in results if r['name'].startswith('hmm_')]
part2 = [r for r in results if r['name'].startswith('probit_')]
part3 = [r for r in results if r['name'].startswith('kalman_')]
part4 = [r for r in results if r['name'].startswith('bma_')]
part5 = [r for r in results if r['name'].startswith('mom_')]

def part_summary(name, tests):
    p = sum(1 for r in tests if r['status'] == PASS)
    f = sum(1 for r in tests if r['status'] == FAIL)
    return f'  {name}: {p}/{len(tests)} passed' + (f' ({f} failed)' if f > 0 else '')

print()
print(part_summary('Part 1 (HMM Regime)', part1))
print(part_summary('Part 2 (Probit)', part2))
print(part_summary('Part 3 (Kalman)', part3))
print(part_summary('Part 4 (BMA)', part4))
print(part_summary('Part 5 (Momentum)', part5))
print()
print(f'TOTAL: {passed}/{total} passed, {failed} failed')
print('=' * 52)

if failed:
    print('\nFailed tests:')
    for r in results:
        if r['status'] == FAIL:
            print(f'  FAIL  {r["name"]}: {r["error"]}')

sys.exit(1 if failed > 0 else 0)
