"""Tests for api/calculations/market_stats.py and the dashboard section builders."""
from datetime import date, datetime, timedelta

import numpy as np
import pytest

from api.calculations import market_stats as ms
from api.handlers import dashboard_sections as ds
from api.handlers.macro_inputs import DatedSeries


def _dated(closes, start="2024-01-01"):
    d0 = date.fromisoformat(start)
    return {(d0 + timedelta(days=i)).isoformat(): float(c) for i, c in enumerate(closes)}


def _walk(n, seed, drift=0.0, vol=0.01, start=100.0):
    rng = np.random.default_rng(seed)
    return list(start * np.cumprod(1 + drift + vol * rng.standard_normal(n)))


# ── pure stats ───────────────────────────────────────────────────────────────────

def test_period_return_and_12_1_momentum():
    closes = list(range(1, 301))            # strictly rising
    assert ms.period_return(closes, 1) == pytest.approx(300 / 299 - 1)
    m = ms.momentum_12_1(closes)
    assert m["return12m"] == pytest.approx(300 / 48 - 1)
    assert m["return1m"] == pytest.approx(300 / 279 - 1)
    assert m["momentum12_1"] == pytest.approx(279 / 48 - 1)


def test_momentum_needs_a_full_year():
    assert ms.momentum_12_1(list(range(1, 200))) is None
    assert ms.period_return([1, 2], 5) is None


def test_trailing_correlation_signs():
    a = _walk(200, 1)
    ra = ms.daily_returns(a)
    mirror = [100.0]
    for r in ra:
        mirror.append(mirror[-1] * (1 - r))
    assert ms.trailing_correlation(a, a, 60) == pytest.approx(1.0)
    assert ms.trailing_correlation(a, mirror, 60) == pytest.approx(-1.0)
    assert ms.trailing_correlation(a[:30], a[:30], 60) is None


def test_align_dated_uses_common_dates_only():
    dates, out = ms.align_dated({"a": {"d1": 1, "d2": 2, "d3": 3}, "b": {"d2": 20, "d3": 30, "d4": 40}})
    assert dates == ["d2", "d3"]
    assert out == {"a": [2.0, 3.0], "b": [20.0, 30.0]}


def test_ols_recovers_known_betas_and_r2_split():
    rng = np.random.default_rng(0)
    x1, x2 = rng.standard_normal(500), rng.standard_normal(500)
    y = 1.5 * x1 - 0.5 * x2 + 0.1 * rng.standard_normal(500)
    fit = ms.ols_decomposition(y, {"x1": x1, "x2": x2})
    betas = {f["factor"]: f["beta"] for f in fit["factors"]}
    assert betas["x1"] == pytest.approx(1.5, abs=0.02)
    assert betas["x2"] == pytest.approx(-0.5, abs=0.02)
    assert sum(f["varianceShare"] for f in fit["factors"]) == pytest.approx(fit["rSquared"], abs=1e-9)
    assert all(abs(f["tStat"]) > 10 for f in fit["factors"])


def test_inverse_vol_weights_favor_low_vol():
    w = ms.inverse_vol_weights({"lo": _walk(100, 1, vol=0.005), "hi": _walk(100, 2, vol=0.02)}, 60)
    assert w["lo"] > w["hi"]
    assert sum(w.values()) == pytest.approx(1.0)


def test_credit_impulse_from_weekly_levels():
    d0 = date(2023, 1, 4)
    dates = [(d0 + timedelta(weeks=i)).isoformat() for i in range(110)]
    # Flow of 1/week for the first year, 2/week afterwards → impulse > 0.
    credit, c = [], 1000.0
    for i in range(110):
        c += 1 if i < 57 else 2
        credit.append(c)
    ci = ms.credit_impulse(dates, credit, nominal_gdp=1000.0)
    assert ci is not None and ci > 0
    assert ms.credit_impulse(dates[:40], credit[:40], 1000.0) is None
    assert ms.credit_impulse(dates, credit, None) is None


def test_relative_strength_score_range():
    bench = _walk(400, 3)
    strong = [b * (1 + 0.001 * i) for i, b in enumerate(bench)]   # steadily outperforms
    s = ms.relative_strength_score(strong, bench)
    assert 0 <= s["percentile"] <= 1
    assert s["relativeReturn"] > 0


# ── section builders: real inputs → values, missing inputs → None ───────────────

NOW = datetime(2026, 10, 1)


def test_sections_are_none_without_inputs():
    empty = ds.SectionInputs()
    assert ds.build_momentum_veto(empty) is None
    assert ds.build_correlation_regime(empty) is None
    assert ds.build_debt_cycle(empty) is None
    assert ds.build_factor_rotation(empty) is None
    assert ds.build_nowcast(empty, NOW) is None
    assert ds.build_factor_decomposition(empty, NOW) is None
    assert ds.build_trend_signals(empty, NOW) is None
    assert ds.build_valuation(empty, NOW) is None
    assert ds.build_international_macro(empty, "expansion", 0.8, 0.7) is None
    adv = ds.build_advanced_indicators(empty, DatedSeries("sahm"), NOW)
    assert adv["sahmRule"]["value"] is None
    assert adv["creditImpulse"]["value"] is None
    assert adv["lei"]["value"] is None
    assert "riskParity" not in adv


def test_momentum_veto_uses_real_returns():
    falling = list(np.linspace(200, 100, 300))
    inp = ds.SectionInputs(prices={"SPX": _dated(falling)})
    mv = ds.build_momentum_veto(inp)
    spx = mv.assets[0]
    assert mv.vetoActive is True and mv.dampenerApplied == 0.5
    assert spx.return12m == pytest.approx(falling[-1] / falling[-253] - 1, abs=1e-4)
    assert spx.rawSignal == "NEGATIVE"


def test_correlation_regime_from_price_history():
    spy = _walk(120, 5)
    inp = ds.SectionInputs(prices={"SPY": _dated(spy), "TLT": _dated(spy)})   # identical → corr 1
    cr = ds.build_correlation_regime(inp)
    assert cr.equityBondCorrelation == pytest.approx(1.0)
    assert cr.switchTriggered is True and cr.currentRegime == "POSITIVE"
    assert [p.assetPair for p in cr.correlations] == ["SPY-TLT"]


def test_debt_cycle_reads_fred_levels():
    q = ["2024-10-01", "2025-01-01", "2025-04-01", "2025-07-01", "2025-10-01"]
    fred = {"QUSCAM770A": DatedSeries("t", q, [240, 242, 245, 248, 251.2]),
            "QUSPAM770A": DatedSeries("p", q, [135, 136, 138, 139, 140.3]),
            "QUSGAM770A": DatedSeries("g", q, [105, 106, 107, 109, 111.0]),
            "TDSP": DatedSeries("d", q, [11.0, 11.0, 11.1, 11.1, 11.1])}
    dc = ds.build_debt_cycle(ds.SectionInputs(fred=fred))
    assert dc.totalDebtGDP == 251.2 and dc.privateDebtGDP == 140.3 and dc.publicDebtGDP == 111.0
    assert dc.trend == "Rising" and dc.phase == "Expansion"


def test_foreign_curve_drops_stale_points():
    fred = {"IRLTLT01GBM156N": DatedSeries("a", ["2026-08-01"], [4.99]),
            "IR3TIB01GBM156N": DatedSeries("b", ["2026-01-01"], [3.71])}
    c = ds.foreign_curve("UK", fred, today="2026-10-01")
    assert c["points"] == [{"tenor": 10, "yield": 4.99}]
    assert c["spread3m10y"] is None and c["shape"] is None and c["recessionProb"] is None
    fresh = {"IRLTLT01DEM156N": DatedSeries("a", ["2026-08-01"], [3.18]),
             "IR3TIB01DEM156N": DatedSeries("b", ["2026-08-01"], [2.51])}
    de = ds.foreign_curve("DE", fresh, today="2026-10-01")
    assert de["spread3m10y"] == pytest.approx(67.0)


def test_nowcast_is_gdpnow():
    s = DatedSeries("GDPNOW", ["2026-04-01", "2026-07-01"], [2.1, 3.7372])
    nc = ds.build_nowcast(ds.SectionInputs(fred={"GDPNOW": s}), NOW)
    assert nc["nowcastQoQ"] == 3.74 and nc["quarter"] == "2026Q3"
    assert nc["nowcastYoY"] is None and nc["confidenceInterval"] is None


# ── second batch: reflexivity, pure alpha, transitions, conditional returns, RP ──

def test_change_zscore_flags_outsized_move():
    calm = [100 + 0.01 * i for i in range(300)]
    jump = calm + [calm[-1] * 1.2]
    z = ms.change_zscore(jump, 21)
    assert z["z"] > 3 and z["change"] > 0.15 and z["percentile"] == 1.0
    assert ms.change_zscore(calm[:30], 21) is None


def test_conditional_return_stats_uses_lagged_label():
    months = [f"{y}-{m:02d}" for y in range(2000, 2006) for m in range(1, 13)]
    closes, level = {}, 100.0
    labels = {}
    for i, m in enumerate(months):
        labels[m] = "A" if (i // 6) % 2 == 0 else "B"
        level *= 1.02 if labels.get(months[i - 2], "") == "A" else 0.99
        closes[m] = level
    st = ms.conditional_return_stats(closes, labels, "A", label_lag=2)
    assert st["annualReturn"] == pytest.approx(0.02 * 12, rel=1e-6)
    assert ms.conditional_return_stats(closes, labels, "missing") is None


def test_regime_transitions_and_expected_returns_from_monthly_panel():
    import pandas as pd
    idx = pd.date_range("1990-01-01", periods=240, freq="MS")
    rng = np.random.default_rng(7)
    df = pd.DataFrame({"growth_yoy": np.cumsum(rng.standard_normal(240)),
                       "cpi_yoy": np.cumsum(rng.standard_normal(240))}, index=idx)
    months = [ts.strftime("%Y-%m") for ts in idx]
    mpx = {k: dict(zip(months, _walk(240, s, vol=0.04))) for s, k in enumerate(["SPY", "TLT", "GLD", "DBC"])}
    inp = ds.SectionInputs(monthly_macro=df, monthly_prices=mpx)
    rt = ds.build_regime_transitions(inp, "goldilocks", NOW)
    row = rt["transitions"][rt["currentRegime"]]
    assert sum(row.values()) == pytest.approx(1.0, abs=0.01)
    assert rt["mostLikelyNext"] != rt["currentRegime"]
    er = ds.build_expected_returns(inp, rt, NOW)
    assert er.currentQuadrant == rt["currentRegime"]
    assert er.weightedPortfolioReturn is not None and set(er.byAssetClass) <= {n for n, _ in ds._ER_ASSETS}
    assert all(0 < s["probability"] <= 1 for s in er.next12Months)


def test_new_sections_unavailable_without_inputs():
    empty = ds.SectionInputs()
    assert ds.build_reflexivity(empty, "goldilocks", NOW) is None
    assert ds.build_pure_alpha(empty, NOW) is None
    assert ds.build_regime_transitions(empty, "goldilocks", NOW) is None
    assert ds.build_performance_tracking(empty, NOW) is None
    er = ds.build_expected_returns(empty, None, NOW)
    assert er.weightedPortfolioReturn is None and er.sectors == []
    rp = ds.build_risk_parity(empty, NOW)
    assert rp["holdings"] == [] and rp["portfolioVol"] is None and rp["leverage"] is None


def test_risk_parity_weights_and_portfolio_vol():
    prices = {k: _dated(_walk(150, i, vol=v)) for i, (k, v) in
              enumerate([("SPY", 0.012), ("TLT", 0.009), ("GLD", 0.008), ("DBC", 0.011)])}
    rp = ds.build_risk_parity(ds.SectionInputs(prices=prices), NOW)
    w = {h["ticker"]: h["baseWeight"] for h in rp["holdings"]}
    assert sum(w.values()) == pytest.approx(1.0, abs=1e-3)
    assert w["GLD"] > w["SPY"]                     # lower vol → higher weight
    assert rp["diversificationRatio"] > 1.0        # independent walks diversify
    assert rp["leverage"] == pytest.approx(ds.RP_TARGET_VOL / rp["portfolioVol"], rel=0.02)


def test_reflexivity_loop_activates_on_reinforcing_moves():
    calm = list(np.linspace(100, 101, 300))
    spx = _dated(calm[:-21] + [calm[-22] * (1 - 0.01 * k) for k in range(1, 22)])   # sharp fall
    vix = _dated(calm[:-21] + [calm[-22] * (1 + 0.05 * k) for k in range(1, 22)])   # vol spike
    out = ds.build_reflexivity(ds.SectionInputs(prices={"SPX": spx, "VIX": vix}), "slowdown", NOW)
    active = {l["id"] for l in out["activeLoops"]}
    assert "vol-deleveraging" in active and out["reflexivityAlert"] is True


def test_performance_tracking_hides_accuracy_until_enough_evaluated():
    stats = [{"model_name": "regime_threshold", "n": 1840, "evaluated": 3, "hit_rate": 1.0,
              "first": "2026-05-05", "last": "2026-10-01"},
             {"model_name": "regime_hmm", "n": 40, "evaluated": 25, "hit_rate": 0.6,
              "first": "2026-05-05", "last": "2026-09-01"}]
    pt = ds.build_performance_tracking(ds.SectionInputs(forecast_stats=stats), NOW)
    assert pt["regimeAccuracy"] is None                 # only 3 evaluated
    assert pt["modelAccuracies"] == {"regime_hmm": 0.6}
    assert pt["totalPredictions"] == 1880 and pt["trackingPeriod"] == "2026-05-05 → 2026-10-01"
