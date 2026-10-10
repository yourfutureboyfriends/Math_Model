"""
Cross-panel consistency: the same quantity must agree wherever it is shown, and internal
identities must hold. Each check here encodes a contradiction that was actually shipped
(different numbers for one fact, or a label that disagreed with its own data).
"""
import math

import pytest


@pytest.fixture(scope="module")
def dash(client):
    r = client.get("/api/dashboard?mode=live")
    assert r.status_code == 200
    return r.json()


def _close(a, b, tol):
    return a is not None and b is not None and abs(a - b) <= tol


def test_regime_is_the_same_everywhere(client, dash):
    regime = dash["regime"]["current"]
    assert client.get("/api/regime").json()["current"] == regime
    brief = client.get("/api/morning-brief").json()
    assert (brief.get("regime") or "").lower() == regime.lower()
    desk = client.get("/api/v1/desk").json()
    assert desk["macro"].get("regime") in (regime, None)


def test_recession_probability_agrees(client, dash):
    p = dash["recession"]["probability"]
    r = client.get("/api/recession").json()
    assert _close(r["probability"], p, 1e-9)
    assert 0 <= p <= 1
    # model readings are the dashboard's, not multiples of the headline
    if dash["recession"]["logisticProb"] is None:
        pytest.skip("fitted recession model unavailable (FRED unreachable)")
    assert _close(r["logisticProb"], dash["recession"]["logisticProb"], 1e-9)
    assert _close(r["sahmValue"], dash["recession"]["sahmValue"], 1e-9)


def test_risk_budget_single_number(client, dash):
    rb = dash["ensemble"]["riskBudget"]
    brief = client.get("/api/morning-brief").json()
    assert _close(brief.get("position_modifier"), rb, 1e-9)


def test_ensemble_score_is_mean_of_its_components(dash):
    comps = dash["ensemble"]["components"]
    assert len(comps) == 4 and all(c["weight"] == 0.25 for c in comps)
    assert _close(sum(c["score"] for c in comps) / 4, dash["ensemble"]["score"], 0.011)
    assert dash["ensemble"]["mode"] == "Equal-weight"


def test_hy_spread_agrees(client, dash):
    hy = dash["riskIndicators"]["creditSpread"]
    assert _close(dash["liquidity"]["hyOas"], hy, 0.011)
    rec = client.get("/api/recession").json()["indicators"]["hy_oas_pct"]
    assert _close(rec, hy, 0.011)
    sa = client.get("/api/v1/stream-agreement").json()["inputs"]["intermarket"]["hy_spread_bps"]
    assert sa is not None and _close(sa / 100, hy, 0.011)


def test_signal_agreement_uses_dashboard_signals(client, dash):
    sa = client.get("/api/v1/stream-agreement").json()["inputs"]
    assert _close(sa["macro"]["growth_signal"], dash["scores"]["growth"] / 100, 0.006)
    assert _close(sa["intermarket"]["risk_appetite_signal"], dash["scores"]["risk"] / 100, 0.006)


def test_cpi_agrees_across_panels(client):
    fr = {s["metric"]: s for s in client.get("/api/v1/freshness").json()["series"]}
    cpi = fr["inflation"]["latest_value"]
    if cpi is None:
        pytest.skip("FRED unreachable — CPI not available to compare")
    gm = {e["code"]: e for e in client.get("/api/v1/global-macro").json()["economies"]}
    assert _close(gm["US"]["cpi"]["value"], cpi, 0.02)
    assert gm["US"]["cpi"]["period"] == fr["inflation"]["last_observation_date"][:7]


def test_spreads_same_date(client):
    us = client.get("/api/rates").json()["yieldCurves"]["US"]
    pts = {p["tenor"]: p["yield"] for p in us["points"]}
    # 2s10s from the same-date FRED curve points
    assert _close(us["spread2s10s"] / 100, pts[10.0] - pts[2.0], 0.011)


def test_fed_stance_matches_last_move(dash):
    liq = dash["liquidity"]
    mv = liq.get("fedLastMove")
    if mv:
        assert liq["fedPolicyStance"] in ("Tightening", "Easing", "On hold")
        if liq["fedPolicyStance"] == "Tightening":
            assert mv["bp"] > 0
        if liq["fedPolicyStance"] == "Easing":
            assert mv["bp"] < 0
    # the effective rate sits inside the target range
    if liq.get("fedTargetUpper") is not None:
        assert liq["fedTargetUpper"] - 0.30 <= dash["keyMetrics"]["fedRate"] <= liq["fedTargetUpper"] + 0.01


def test_growth_direction_matches_its_change(dash):
    g = dash["signals"]["growth"]
    if g["direction"] == "improving":
        assert g["threeMonth"] > 0
    if g["direction"] == "deteriorating":
        assert g["threeMonth"] < 0


def test_sector_signal_not_contradicted_by_data(dash):
    for s in dash["sectorAllocation"]["sectors"]:
        z = s.get("z_score")
        if z is None:
            continue
        assert not (s["signal"] == "Overweight" and z < -0.5), s
        assert not (s["signal"] == "Underweight" and z > 0.5), s


def test_cot_identities(client):
    cot = client.get("/api/cot").json()
    for c in cot.get("contracts", []):
        assert c["net_position"] == c["speculator_longs"] - c["speculator_shorts"]
        if c["cot_index"] is not None:
            assert 0 <= c["cot_index"] <= 100
            assert c["extreme_long"] == (c["cot_index"] >= 90)
        assert c["positioning"] == ("NET_LONG" if c["net_position"] > 0 else "NET_SHORT")


def test_global_macro_identities(client):
    for e in client.get("/api/v1/global-macro").json()["economies"]:
        p, c = e["policy"].get("rate"), e["cpi"]["value"]
        if p is not None and c is not None:
            assert _close(e["real_policy_rate"], p - c, 0.011)
        mv = e["policy"].get("last_move")
        if mv and e["policy"]["stance"] == "hiking":
            assert mv["bp"] > 0


def test_fx_changes_dated(dash):
    asof = dash["keyMetrics"].get("changeAsOf") or {}
    for k, d in asof.items():
        assert d is None or len(d) == 10


def test_no_score_printed_as_rate(client):
    brief = client.get("/api/morning-brief").json()
    text = (brief.get("summary") or "") + " ".join(r.get("text", "") for r in brief.get("risks", []))
    assert "growth at" not in text.lower() and "inflation at" not in text.lower()
