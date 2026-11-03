"""Recession ensemble: probit estimation, the pseudo-out-of-sample evaluation (no look-ahead) and the headline wiring.
Synthetic data only — offline."""
import numpy as np

from api.calculations.metrics import calculate_recession_probability
from api.models_ml import recession_ensemble as re_


def _synthetic(n_years=45, seed=0):
    """Monthly rows where a low spread and a high EBP precede 'recessions' (with noise)."""
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n_years * 12):
        y, m = divmod(i, 12)
        ts = 1.5 + np.sin(i / 30) * 1.6 + rng.normal(0, 0.3)
        ebp = -np.sin(i / 30) * 0.6 + rng.normal(0, 0.2)
        rows.append({"month": f"{1973 + y}-{m + 1:02d}", "ts": ts, "ntfs": ts * 0.8 + rng.normal(0, 0.2), "ebp": ebp})
    latent = np.array([-0.9 * r["ts"] + 1.2 * r["ebp"] for r in rows])
    rec = latent > np.quantile(latent, 0.85)
    for i, r in enumerate(rows):
        window = rec[i + 1:i + 13]
        r["y"] = int(window.any()) if i + 12 < len(rows) else None
    return rows


def test_probit_recovers_direction_and_probabilities_are_bounded():
    rows = [r for r in _synthetic() if r["y"] is not None]
    X = re_._design(rows, ["ts", "ebp"])
    beta = re_.probit_fit(X, np.array([r["y"] for r in rows], float))
    assert beta is not None and beta[1] < 0 and beta[2] > 0           # low spread, high EBP → recession ahead
    p = re_.probit_prob(beta, [-1.0, 1.0])
    q = re_.probit_prob(beta, [3.0, -0.5])
    assert 0 < q < p < 1


def test_evaluation_is_out_of_sample_and_beats_the_base_rate_on_informative_data():
    rows = _synthetic()
    ev = re_.evaluate(rows, start_year=1990)
    assert ev and ev["forecasts"] > 100 and ev["from"] >= "1990-01"
    ens, base = ev["models"]["ensemble"], ev["models"]["base_rate"]
    assert ens["auroc"] > 0.7 and ens["brier_skill_vs_base_rate"] > 0 and base["brier_skill_vs_base_rate"] == 0
    assert sum(c["forecasts"] for c in ev["calibration"]) == ev["forecasts"]


def test_evaluation_never_trains_on_unknown_labels(monkeypatch):
    """Every fit sees only months before origin − (12-month window + announcement lag)."""
    rows = _synthetic()
    seen = []
    real = re_.probit_fit

    def spy(X, y):
        seen.append(len(y))
        return real(X, y)
    monkeypatch.setattr(re_, "probit_fit", spy)
    re_.evaluate(rows, start_year=1990, announce_lag=12)
    # first origin Jan 1990 → training months strictly before Jan 1988 = 1973-01 … 1987-12 = 180
    assert seen[0] == 180


def test_headline_prefers_the_ensemble_and_keeps_the_others():
    ens = {"available": True, "probability": 0.056, "model": "Term spread + credit ensemble", "target": "within 12 months",
           "inputs": {"near_term_forward_spread_pp": 0.7, "excess_bond_premium_pp": -0.39}, "evaluation": {"forecasts": 489}}
    d = calculate_recession_probability(0.8, 3.9, 0.1, fitted_probit_prob=0.08, ensemble=ens)
    assert d["probability"] == 0.056 and d["ensembleProb"] == 0.056 and d["logisticProb"] == 0.08
    assert d["model"].startswith("Term spread") and d["evaluation"]["forecasts"] == 489
    assert any(c["name"] == "Excess bond premium" for c in d["components"])
    # unavailable ensemble → previous behaviour
    d2 = calculate_recession_probability(0.8, 3.9, 0.1, fitted_probit_prob=0.08, ensemble={"available": False})
    assert d2["probability"] == 0.08 and d2["ensembleProb"] is None and d2["model"] == "Fitted probit (FRED)"


# ── regime confirmation (api/calculations/regime.py) ──────────────────────────
from api.calculations.regime import confirmed_regime  # noqa: E402


def test_regime_switches_only_after_the_confirmation_window():
    raw = ["reflation"] * 30 + ["stagflation"] * 2
    c = confirmed_regime(raw, confirm=5)
    assert c["current"] == "reflation" and c["pending"] == "stagflation" and c["pending_days"] == 2
    c = confirmed_regime(raw + ["stagflation"] * 3, confirm=5)
    assert c["current"] == "stagflation" and c["pending"] is None


def test_a_brief_wobble_does_not_relabel_and_a_different_candidate_restarts_the_count():
    raw = ["reflation"] * 10 + ["recovery", "stagflation", "stagflation", "reflation", "stagflation"]
    c = confirmed_regime(raw, confirm=5)
    assert c["current"] == "reflation" and c["pending"] == "stagflation" and c["pending_days"] == 1
    assert confirmed_regime([None, "slowdown"], confirm=5)["current"] == "slowdown"


# ── recalibration, inflation direction and the commodity call ────────────────
from api.calculations.idea_generation import desired_tilts  # noqa: E402
from api.calculations.rebalance import regime_budgets  # noqa: E402
from api.calculations.regime import commodity_tilt  # noqa: E402
from api.calculations.signals import calculate_inflation_direction  # noqa: E402


def test_platt_recalibration_learns_overconfidence_and_needs_history():
    assert re_.learned_platt([0.9] * 50, [1] * 50) is None                      # too little history
    rng = np.random.default_rng(1)
    raw = rng.uniform(0.01, 0.99, 600)
    y = (rng.uniform(size=600) < 0.5 * raw).astype(int)                         # outcomes at half the stated rate
    coef = re_.learned_platt(list(raw), list(y))
    assert coef is not None and re_.platt_apply(coef, 0.9) < 0.75               # high readings pulled down
    assert re_.platt_apply(coef, 0.2) < re_.platt_apply(coef, 0.6)              # order kept
    assert re_.platt_apply(None, 0.3) == 0.3


def test_evaluation_reports_the_recalibrated_headline():
    ev = re_.evaluate(_synthetic(), start_year=1990)
    assert "ensemble_calibrated" in ev["models"] and "calibration_now" in ev


def test_inflation_direction_and_commodity_call():
    assert calculate_inflation_direction(2.5, 2.0, 110, 100) > 0.7               # breakevens and commodities up
    assert calculate_inflation_direction(2.0, 2.5, 90, 100) < 0.3
    assert calculate_inflation_direction(None, None, None, None) is None
    assert calculate_inflation_direction(2.3, 2.3, None, None) == 0.5
    assert commodity_tilt("stagflation", 0.30) == "underweight"                 # direction overrides the regime
    assert commodity_tilt("slowdown", 0.70) == "overweight"
    assert commodity_tilt("stagflation", None) == "overweight"                  # no direction → regime's bias
    assert desired_tilts("reflation", 0.30)["commodity"] == -1 and desired_tilts("reflation")["commodity"] == 1
    assert regime_budgets("reflation", 0.30)["DBC"] < regime_budgets("reflation")["DBC"]
