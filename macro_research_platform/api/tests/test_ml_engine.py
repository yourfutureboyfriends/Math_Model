"""ML engine: time-correct datasets, walk-forward that trains only on known answers, data checks, the live record,
evidence only from skilful models, and promotion that the gate (not the caller) decides. Synthetic data — offline."""
import numpy as np
import pytest

from api.ml import engine as E
from api.ml.tasks import Task


def _feats(n=480, seed=0):
    rng = np.random.default_rng(seed)
    months = [f"{1975 + i // 12}-{i % 12 + 1:02d}" for i in range(n)]
    a = np.sin(np.arange(n) / 20) + rng.normal(0, .3, n)
    b = rng.normal(0, 1, n)
    y = (a + rng.normal(0, .5, n) > 0.8).astype(int)
    return months, {"a": dict(zip(months, a)), "b": dict(zip(months, b))}, dict(zip(months, y.tolist()))


def _panel(months, n_series=12, seed=1):
    rng = np.random.default_rng(seed)
    return {f"p_S{i}": dict(zip(months, rng.normal(0, 1, len(months)))) for i in range(n_series)}


def _task(target, known_after=6):
    return Task("synthetic", "Synthetic", "?", "tests", ["a", "b"], known_after=known_after, target=lambda: target)


def test_cutoff_trains_only_on_answers_known_by_january():
    assert E.cutoff(1990, 24) == "1988-01" and E.cutoff(1990, 4) == "1989-09" and E.cutoff(2000, 12) == "1999-01"


def test_dataset_lists_missing_inputs_and_keeps_the_unlabelled_latest_month():
    months, feats, target = _feats()
    target = {m: v for m, v in target.items() if m < months[-6]}                # the last six answers unknown
    assert E.dataset(_task(target), {"a": feats["a"]}, _panel(months))["missing"] == ["b"]
    ds = E.dataset(_task(target), feats, _panel(months))
    rows = ds["rows"]
    assert rows[-1]["y"] is None and rows[0]["c"] == [feats["a"][months[0]], feats["b"][months[0]]] and len(rows[0]["p"]) == 12


def test_ragged_release_edge_carries_the_last_value_three_months_at_most():
    months = [f"2026-{m:02d}" for m in range(1, 13)]
    out = E._carry({"2026-01": 1.0, "2026-06": 2.0}, months)
    assert out["2026-09"] == 2.0 and "2026-10" not in out and out["2026-01"] == 1.0


def test_factors_are_fitted_on_the_training_window_only():
    rng = np.random.default_rng(0)
    P = rng.normal(0, 1, (200, 10))
    f = E.Factors().fit(P[:150], k=3)
    assert f.transform(P[150:]).shape == (50, 3) and 0 < sum(f.share) <= 1
    assert np.allclose(f.mu, P[:150].mean(0))                                  # nothing from the test rows


def test_walk_forward_scores_both_models_out_of_sample():
    months, feats, target = _feats()
    task = _task(target)
    bt = E.walk_forward(task, E.dataset(task, feats, _panel(months))["rows"], roster=["champion", "factor_logit", "boosting"])
    assert bt and bt["forecasts"] >= 60 and bt["from"] >= "1987-01"           # first refit after 12 years of history
    assert bt["overall"]["champion"]["auroc"] > 0.7                            # the signal in `a` is learned
    assert set(bt["gains"]) == {"factor_logit", "boosting", "average"} and 0 <= bt["gains"]["boosting"]["p_no_gain"] <= 1


def test_data_checks_flag_extrapolation_and_drift():
    rng = np.random.default_rng(0)
    X = rng.normal(0, 1, (300, 2))
    ok = E.data_checks(X, rng.normal(0, 1, (12, 2)), np.array([0.1, -0.2]), ["a", "b"])
    assert ok["ok"]
    bad = E.data_checks(X, rng.normal(4, 1, (12, 2)), np.array([9.0, 0.0]), ["a", "b"])
    assert not bad["ok"] and any("outside" in f for f in bad["flags"]) and any("shifted" in f for f in bad["flags"])


def test_live_record_promotion_and_evidence(tmp_path, monkeypatch):
    import api.core.app_db as app_db
    monkeypatch.setattr(app_db, "app_db_path", lambda: str(tmp_path / "a.db"))
    monkeypatch.setattr(E, "_ready", False)
    task = _task({"2020-01": 1, "2020-02": 0})
    for m, pc, pn in (("2020-01", 0.4, 0.8), ("2020-02", 0.3, 0.1)):
        E.log_forecast("synthetic", "champion", m, pc)
        E.log_forecast("synthetic", "network", m, pn)
    E.log_forecast("synthetic", "network", "2020-01", 0.0)                     # a later run cannot rewrite a month
    r = E.live_record(task)
    assert r["scored_months"] == 2 and r["network_ahead"] is True and r["network_brier"] == pytest.approx((0.04 + 0.01) / 2)
    assert r["models"]["network"]["ahead_of_champion"] is True
    # promotion is refused when the gate says no
    monkeypatch.setattr(E, "run", lambda name, force=False: {"available": True, "promotion": {"eligible": False, "eligible_models": [], "status": "x"}})
    with pytest.raises(ValueError):
        E.promote("synthetic", "pm")
    # evidence appears only for a model with positive out-of-sample skill
    E._mem["t1"] = {"month": "x", "data": {"available": True, "signal": {"probability": 0.3, "model": "champion", "skill_vs_base_rate": 0.1, "useful": True}}}
    E._mem["t2"] = {"month": "x", "data": {"available": True, "signal": {"probability": 0.3, "model": "champion", "skill_vs_base_rate": -0.1, "useful": False}}}
    assert "skill +10%" in E.evidence("t1", "chance") and E.evidence("t2", "chance") is None


def test_regime_switching_finds_the_low_growth_state_in_real_time():
    rng = np.random.default_rng(3)
    state = np.zeros(360, int)
    for a, b in ((100, 115), (220, 240), (310, 322)):
        state[a:b] = 1
    series = np.where(state == 1, rng.normal(-1.5, 0.8, 360), rng.normal(0.3, 0.5, 360))
    prob = E.regime_probabilities(series, 300)
    assert prob is not None and prob.shape == (360,)
    assert prob[state == 1].mean() > 0.6 and prob[state == 0].mean() < 0.2
    F = E.regime_features(prob)
    assert F.shape == (360, 2) and F[2, 1] == 0.0


def test_deep_inputs_use_training_scalers_and_hide_unknown_answers():
    from api.ml import deep as D
    rng = np.random.default_rng(0)
    n = 300
    months = [f"{1980 + i // 12}-{i % 12 + 1:02d}" for i in range(n)]
    fr = {"months": months, "C": rng.normal(0, 1, (n, 3)), "P": rng.normal(0, 1, (n, 12)),
          "T": np.where(np.arange(n)[:, None] < 60, np.nan, rng.normal(0, 1, (n, 2))),
          "Y": rng.integers(0, 2, (n, 2)).astype(float), "tasks": ["a", "b"], "known_after": [4, 24]}
    fr["C"][200:] += 50.0                                                     # a shift after the training window
    X = D._features(fr, 150)
    assert abs(X[:150, :3].mean()) < 1e-6 and X[200:, :3].mean() > 10           # scaled with training months only
    assert X.shape[1] == 3 + D.N_FACTORS + 2 + 2 and np.isfinite(X).all()     # text gaps → 0 plus a missing flag
    Y = D._labels_known(fr, "2000-01")
    assert np.isnan(Y[months.index("1999-09"), 0]) and not np.isnan(Y[months.index("1999-08"), 0])   # 4-month delay
    assert np.isnan(Y[months.index("1998-01"), 1]) and not np.isnan(Y[months.index("1997-12"), 1])   # 24-month delay
