"""Recession challenger: inputs known at the time, a bagged network that learns a signal, occlusion attributions,
a live record that is never rewritten, and promotion that is never automatic. Synthetic data only — offline."""
import numpy as np
import pytest

from api.models_ml import recession_challenger as ch


def _rows(n=480, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        y_, m = divmod(i, 12)
        ts = 1.5 + np.sin(i / 30) * 1.6 + rng.normal(0, .3)
        ebp = -np.sin(i / 30) * .6 + rng.normal(0, .2)
        rows.append({"month": f"{1973 + y_}-{m + 1:02d}", "ts": ts, "ntfs": ts * .8, "ebp": ebp, "pay6": 2 - ebp})
    latent = np.array([-.9 * r["ts"] + 1.2 * r["ebp"] for r in rows])
    rec = latent > np.quantile(latent, .85)
    for i, r in enumerate(rows):
        r["y"] = int(rec[i + 1:i + 13].any()) if i + 12 < n else None
    return rows


def test_derived_inputs_use_only_earlier_months():
    rows = ch.build_rows(_rows(), {"1980-01": 5.0})
    assert rows[0]["ts_d6"] is None and rows[6]["ts_d6"] == pytest.approx(rows[6]["ts"] - rows[0]["ts"])
    assert rows[3]["ebp_d3"] == pytest.approx(rows[3]["ebp"] - rows[0]["ebp"])
    assert next(r for r in rows if r["month"] == "1980-01")["spx6"] == 5.0


def test_bagged_network_learns_and_attributes():
    rows = [r for r in ch.build_rows(_rows(), {}) if r["y"] is not None and r["ts_d6"] is not None]
    for r in rows:
        r["spx6"] = 0.0
    X = np.array([[r[k] for k in ch.FEATURES] for r in rows])
    y = np.array([r["y"] for r in rows])
    net = ch.BaggedNet(n=3).fit(X, y)
    stress, calm = X[y == 1].mean(0), X[y == 0].mean(0)
    assert net.predict(stress)[0] > net.predict(calm)[0]
    c = ch.contributions(net, stress.copy(), X.mean(0))
    assert set(c) == set(ch.FEATURES) and c["ebp"] > 0                 # high credit stress pushes the risk up


def test_live_record_keeps_the_first_forecast_and_scores_closed_windows(tmp_path, monkeypatch):
    import api.core.app_db as app_db
    monkeypatch.setattr(app_db, "app_db_path", lambda: str(tmp_path / "a.db"))
    monkeypatch.setattr(ch, "_ready", False)
    ch.log_forecast("m", "2007-01", 0.8, 0.3)
    ch.log_forecast("m", "2007-01", 0.1, 0.3)                          # a later run cannot rewrite the month
    ch.log_forecast("m", "2015-01", 0.1, 0.4)
    r = ch.live_record("m")
    assert r["logged"] == 2 and r["scored"] == 2                       # 2007 → recession ahead; 2015 → none
    assert r["challenger_brier"] == pytest.approx(((0.8 - 1) ** 2 + 0.1 ** 2) / 2, abs=1e-4)
    assert r["beats_headline"] is True


def test_promotion_bar_allows_for_variants_tried():
    assert ch.ALPHA / ch.VARIANTS_TRIED == pytest.approx(0.005) and ch.MIN_LIVE_MONTHS >= 24
