"""Fund governance for Moriah Capital Partners' plan: set-up, approved instruments, the G0–G5 model gates,
risk-policy order controls, halts and incidents, reconciliation, strategy drawdown, monthly pack and scorecard."""
import pytest


@pytest.fixture()
def fund(tmp_path, monkeypatch):
    from api import funds
    monkeypatch.setattr(funds, "db_path", lambda fund_id=None: str(tmp_path / "fund.db"))
    reg = {"main": {"id": "main", "name": "My Fund", "members": []}}
    monkeypatch.setattr(funds, "get", lambda fid: reg.get(fid))
    monkeypatch.setattr(funds, "update", lambda fid, name=None, members=None: reg[fid].update(name=name or reg[fid]["name"]))
    from api import moriah
    out = moriah.setup("main", "admin")
    return {"setup": out, "registry": reg}


def test_setup_follows_the_plan(fund):
    from api import fund_store, governance as gov, moriah
    st = fund_store.get_settings()
    assert fund["registry"]["main"]["name"] == "Moriah Capital Partners"
    assert st["base_currency"] == "GBP" and st["stage"] == "research" and st["governance"] and st["require_approved_model"]
    assert "not capital" in st["capital_basis"] and st["benchmark"] == "CASH_GBP"
    pol = gov.settings()["risk_policy"]
    assert (pol["max_model_risk_share"], pol["max_theme_risk_share"], pol["max_gross_leverage"], pol["daily_loss_pause"],
            pol["strategy_dd_review"], pol["strategy_dd_suspend"]) == (0.25, 0.35, 1.0, 0.01, 0.05, 0.08)
    ins = gov.instruments()
    assert len(ins) == len(moriah.INSTRUMENTS) and all(i["status"] == "proposed" for i in ins)
    assert not next(i for i in ins if i["symbol"] == "GBPUSD=X")["tradable"]
    assert gov.budget()["total_budget"] == 3000.0                              # the plan's £0–3,000 first year
    assert len(gov.milestones()) == 12
    again = moriah.setup("main", "admin")                                      # idempotent
    assert again["seeded"] == {} and len(gov.instruments()) == len(moriah.INSTRUMENTS)
    assert "simulated" in gov.results_label().lower() and "not a fund track record" in gov.results_label()


def test_instrument_approval_is_four_eyes_and_enforced(fund):
    from api import governance as gov
    gov.propose_instrument("ZZZ.L", "analyst", "Test", "equity index", "UK equity", "GBp")
    with pytest.raises(PermissionError):
        gov.decide_instrument("ZZZ.L", "analyst", True)
    gov.decide_instrument("ZZZ.L", "risk", True)
    assert gov.order_controls("ZZZ.L", 10, 100.0, 25_000, 0.5, None) == []
    rules = {r["rule"] for r in gov.order_controls("CSPX.L", 10, 100.0, 25_000, 0.5, None)}
    assert "approved_instruments" in rules                                     # proposed, not approved
    gov.decide_instrument("GBPUSD=X", "risk", True)
    msgs = [r["message"] for r in gov.order_controls("GBPUSD=X", 1000, 1.3, 25_000, 0.5, None)]
    assert any("research / signal series only" in m for m in msgs)


def test_order_controls_short_leverage_size_stale_and_halt(fund):
    from datetime import date, timedelta
    from api import governance as gov
    gov.decide_instrument("ISF.L", "risk", True)
    r = {x["rule"] for x in gov.order_controls("ISF.L", -5, 8.0, 25_000, 0.5, None)}
    assert "no_short" in r
    assert "no_leverage" in {x["rule"] for x in gov.order_controls("ISF.L", 5, 8.0, 25_000, 1.02, None)}
    assert "order_size" in {x["rule"] for x in gov.order_controls("ISF.L", 1000, 8.0, 25_000, 0.5, None)}   # 32% NAV
    old = (date.today() - timedelta(days=9)).isoformat()
    assert "price_feed" in {x["rule"] for x in gov.order_controls("ISF.L", 5, 8.0, 25_000, 0.5, old)}
    gov.start_halt("manual", "testing the halt", "risk")
    assert "halt" in {x["rule"] for x in gov.order_controls("ISF.L", 5, 8.0, 25_000, 0.5, None)}


def test_daily_loss_pause(fund):
    from datetime import date, timedelta
    from api import fund_store, governance as gov
    gov.decide_instrument("ISF.L", "risk", True)
    fund_store.record_nav({"date": (date.today() - timedelta(days=1)).isoformat(), "nav": 25_000})
    assert "daily_loss" in {x["rule"] for x in gov.order_controls("ISF.L", 5, 8.0, 24_740, 0.5, None)}   # −1.04%
    assert "daily_loss" not in {x["rule"] for x in gov.order_controls("ISF.L", 5, 8.0, 24_800, 0.5, None)}


MODEL = {"name": "Fed surprise → USD/JPY", "sleeve": "macro_transmission", "mechanism": "Policy surprise moves rate "
         "differentials before carry positions adjust", "target_variable": "5-day USDJPY return", "horizon": "1-10 days",
         "dataset": "FOMC decisions, ALFRED vintages, daily FX", "null_hypothesis": "No excess return after surprises"}


def _ok(names):
    return {"checks": {n: {"ok": True, "note": "reviewed"} for n in names}}


def test_model_gates_need_evidence_and_independent_signoffs(fund, monkeypatch):
    from api import governance as gov
    with pytest.raises(ValueError):
        gov.create_model("quant1", {"name": "x"})                               # G0 needs every field
    m = gov.create_model("quant1", MODEL)
    assert m["gate"] == "G0" and m["next_gate"] == "G1"
    with pytest.raises(PermissionError):
        gov.signoff(m["id"], "quant1", "pm", _ok(gov.GATE_INFO["G1"]["evidence"]))   # the owner
    with pytest.raises(ValueError):
        gov.signoff(m["id"], "lead", "analyst", {})                             # no evidence
    gov.signoff(m["id"], "lead", "analyst", _ok(gov.GATE_INFO["G1"]["evidence"]))
    assert gov.get_model(m["id"])["gate"] == "G0"                              # needs an independent reviewer too
    with pytest.raises(PermissionError):
        gov.signoff(m["id"], "lead", "analyst", _ok(gov.GATE_INFO["G1"]["evidence"]))
    assert gov.signoff(m["id"], "rev", "risk", _ok(gov.GATE_INFO["G1"]["evidence"]))["gate"] == "G1"
    # G2: the linked backtest is checked by the platform
    from api.quant import store
    good = {"label": "fed-usdjpy", "result": {"costs": {"total_trading": 0.004}, "holdout": {"start": "2024-01-01", "baseline_holdout": {"sharpe": 0.2}},
            "validation": {"causality": {"passed": True}, "pbo": {"pbo": 0.2}}, "metrics": {"sharpe": 0.6},
            "provenance": {"record_type": "walk-forward (selection out-of-sample)"}}}
    bad = {"label": "x", "result": {"costs": {"total_trading": None}, "validation": {}, "provenance": {}}}
    monkeypatch.setattr(store, "get_result", lambda owner, rid: good if rid == 1 else bad)
    with pytest.raises(PermissionError):
        gov.signoff(m["id"], "rev", "risk", {"result": {"owner": "quant1", "id": 1}})   # G2 is the IC (pm)
    with pytest.raises(ValueError) as e:
        gov.signoff(m["id"], "ic", "pm", {"result": {"owner": "quant1", "id": 2}, **_ok(["Regime stress tests"])})
    assert "no trading costs" in str(e.value) and "out-of-sample" in str(e.value)
    m2 = gov.signoff(m["id"], "ic", "pm", {"result": {"owner": "quant1", "id": 1}, **_ok(["Regime stress tests"])})
    assert m2["gate"] == "G2" and m2["result_ref"]
    assert gov.model_for_order(m["id"])[1] and "G3" in gov.model_for_order(m["id"])[1]
    # G3 needs a loss budget, allocation and retirement criterion
    with pytest.raises(ValueError):
        gov.signoff(m["id"], "riskop", "risk", _ok(gov.GATE_INFO["G3"]["evidence"]))
    gov.update_model(m["id"], "ic", {"allocation": 5000, "max_loss_budget": 0.08, "retirement_criterion": "Sharpe < 0 over 6m"})
    with pytest.raises(ValueError) as e:                                       # no shadow trading yet
        gov.signoff(m["id"], "riskop", "risk", _ok(gov.GATE_INFO["G3"]["evidence"]))
    assert "shadow trading" in str(e.value)
    monkeypatch.setattr(gov, "shadow_report", lambda mid, min_sessions=20: {"available": True, "sessions": 25,
                        "min_sessions": 20, "live": {"vol": 0.1}, "backtest": {}, "drift_flags": [], "deployment_id": 7})
    assert gov.signoff(m["id"], "riskop", "risk", _ok(["Realistic tradeability",
                                                        "Maximum loss budget and retirement criterion set"]))["gate"] == "G3"
    assert gov.model_for_order(m["id"])[1] is None                             # paper orders allowed
    # G4 (live capital) is closed in Phase I
    with pytest.raises(ValueError) as e:
        gov.signoff(m["id"], "ic", "pm", _ok(gov.GATE_INFO["G4"]["evidence"]))
    assert "no live capital" in str(e.value)
    # a research change after G2 is a new version, back to G1
    v = gov.update_model(m["id"], "quant1", {"dataset": "add JGB yields"})
    assert v["gate"] == "G1" and v["version"] == 2


def test_rejected_models_stay_in_the_research_log(fund):
    from api import governance as gov
    m = gov.create_model("quant1", MODEL)
    with pytest.raises(ValueError):
        gov.close_model(m["id"], "ic", "pm", "reject", "")
    r = gov.close_model(m["id"], "ic", "pm", "reject", "publication timing not point-in-time")
    assert r["status"] == "rejected" and any(e["action"] == "reject" for e in r["events"])
    assert gov.model_for_order(m["id"])[1] == f"model #{m['id']} is rejected"


def test_halt_needs_fixed_and_independently_signed_off_incident(fund):
    from api import governance as gov
    h = gov.start_halt("manual", "bad price print", "risk")
    with pytest.raises(ValueError):
        gov.lift_halt("risk", "fixed")
    gov.fix_incident(h["incident_id"], "eng", "filtered the print; reran the feed tests")
    with pytest.raises(PermissionError):
        gov.signoff_incident(h["incident_id"], "eng")
    gov.signoff_incident(h["incident_id"], "risk")
    gov.lift_halt("risk", "feed fixed and tested")
    assert gov.active_halt() is None
    t = gov.start_halt("test", "kill-switch test", "risk", test=True)
    assert t["incident_id"] is None
    gov.lift_halt("risk", "test complete")


def test_reconciliation_break_halts_execution(fund):
    import sqlite3
    from api import blotter_store, funds, governance as gov
    blotter_store.book_fill("Macro transmission", "ISF.L", 100, 800.0, 1.0, "pm")
    assert gov.reconcile("risk")["ok"]
    c = sqlite3.connect(funds.db_path())
    c.execute("UPDATE positions SET quantity = 90")                             # a position that disagrees with fills
    c.commit()
    c.close()
    r = gov.reconcile("risk")
    assert not r["ok"] and r["breaks"][0]["difference"] == -10
    h = gov.active_halt()
    assert h and h["kind"] == "reconciliation" and h["incident_id"]


def test_strategy_drawdown_review_and_suspend(fund, monkeypatch):
    from api import governance as gov
    m = gov.create_model("quant1", MODEL)
    gov.update_model(m["id"], "ic", {"allocation": 10_000})
    seq = iter([300.0, -300.0, -600.0])                                         # HWM 300; then −6%, −9% of 10k
    monkeypatch.setattr(gov, "model_pnl_today", lambda: {m["id"]: next(seq)})
    assert gov.record_model_pnl() == []
    assert gov.record_model_pnl()[0]["action"] == "review"
    assert gov.record_model_pnl()[0]["action"] == "suspended"
    assert gov.get_model(m["id"])["status"] == "suspended"


def test_budget_and_milestones(fund):
    from api import governance as gov
    gov.add_expense("pm", "2026-10-20", "Data and infrastructure", 120.0, "GBP", "FRED/ALFRED mirror hosting")
    with pytest.raises(PermissionError):
        gov.approve_expense(1, "pm")
    b = gov.approve_expense(1, "md")
    line = next(l for l in b["lines"] if l["category"] == "Data and infrastructure")
    assert line["spent"] == 120.0 and line["remaining"] == 880.0 and b["variance"] == 2880.0
    ms = gov.milestones()[0]
    with pytest.raises(ValueError):
        gov.update_milestone(ms["id"], "md", "done", "")
    gov.update_milestone(ms["id"], "md", "done", "signed responsibility matrix v1")
    with pytest.raises(PermissionError):
        gov.signoff_milestone(ms["id"], "md")
    assert gov.signoff_milestone(ms["id"], "risk")["signed_off_by"] == "risk"


def test_monthly_pack_and_scorecard(fund):
    from datetime import date
    from api import fund_store, governance_reports as gr
    mo = date.today().strftime("%Y-%m")
    fund_store.record_nav({"date": f"{mo}-01", "nav": 25_000, "regime": "Goldilocks"})
    fund_store.record_nav({"date": f"{mo}-02", "nav": 25_250, "regime": "Reflation"})     # the regime the next day starts in
    fund_store.record_nav({"date": f"{mo}-03", "nav": 25_000, "regime": "Reflation"})
    r = gr.monthly_report(mo)
    assert "not a fund track record" in r["label"]
    assert r["returns"]["month_return"] == pytest.approx(0.0, abs=0.01)
    assert r["risk"]["max_drawdown_to_date"] == pytest.approx(-0.99, abs=0.01)
    assert set(r["attribution"]["by_regime"]) == {"Goldilocks", "Reflation"}
    for k in ("returns", "risk", "attribution", "implementation", "research_changes", "validation"):
        assert k in r
    s = gr.scorecard()
    assert s["organisation"]["milestones"] == 12 and s["organisation"]["budget"]["total"] == 3000.0


def test_break_even_matches_the_plan():
    from api import governance as gov
    r = gov.break_even([250_000], [0.015], [20e6])
    assert r["thresholds"][0]["1.500%"] == pytest.approx(16_666_666.67, abs=1)  # the plan's $16.7m
    assert r["grid"][0]["1.500%"]["surplus"] == 50_000                          # $300k − $250k at $20m


def test_orders_need_an_approved_model_and_pass_the_policy_over_http(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import api.core.auth as auth
    from api import funds, governance as gov, moriah
    from api.core import accounts
    path = str(tmp_path / "d.db")
    monkeypatch.setattr(funds, "db_path", lambda fund_id=None: path)
    monkeypatch.setattr(auth, "get_db_path", lambda: path)
    monkeypatch.setattr(funds, "get", lambda fid: {"id": fid, "name": "x", "members": []})
    monkeypatch.setattr(funds, "update", lambda *a, **k: None)
    accounts.invalidate_cache()
    accounts.migrate()
    for u in ("pm", "risk", "analyst", "quant"):
        accounts.set_password(u, f"Gov-{u}-Pass-2026!x")
    moriah.setup("main", "admin")
    from api.handlers import market_handler
    from api.routers import fund as fr
    import api.market_bars as mb
    from datetime import date

    async def closes(sym):
        return [800.0, 802.0]

    async def book_state(raw, settings, include_liquidity=True, include_factors=True):
        mv = sum(float(p["quantity"]) * float(p["avg_cost"]) / 100 for p in raw)
        return {"nav": 25_000.0, "exposures": {"gross": mv / 25_000, "net": mv / 25_000},
                "metrics": {"gross_exposure": mv / 25_000}, "positions": []}
    monkeypatch.setattr(market_handler, "_fetch_closes_literal", closes)
    monkeypatch.setattr(fr, "_book_state", book_state)
    monkeypatch.setattr(mb, "bars", lambda s, i, p: {"bars": [{"t": date.today().isoformat(), "c": 802.0}]})
    import api.handlers.portfolio_analytics as pa
    monkeypatch.setattr(pa, "_usd_per_unit", lambda s: ("GBp", 0.0133))
    from api.main import app
    c = {}
    for u in ("pm", "risk", "analyst", "quant"):
        c[u] = TestClient(app)
        c[u].headers["Authorization"] = f"Bearer {accounts.issue_token(accounts.get_user(u))}"
    r = c["quant"].post("/api/v1/orders", json={"symbol": "ISF.L", "side": "BUY", "quantity": 100})
    assert r.status_code == 409 and "approved model" in r.text
    assert c["analyst"].get("/api/v1/governance").json()["settings"]["stage"] == "research"
    m = c["quant"].post("/api/v1/governance/models", json=MODEL).json()
    for user, gate in (("analyst", "G1"), ("risk", "G1")):
        assert c[user].post(f"/api/v1/governance/models/{m['id']}/signoff",
                            json={"evidence": _ok(gov.GATE_INFO[gate]["evidence"])}).status_code == 200
    from api.quant import store
    monkeypatch.setattr(store, "get_result", lambda o, i: {"label": "x", "result": {
        "costs": {"total_trading": 0.01}, "holdout": {"start": "2024-01-01", "baseline_holdout": {"sharpe": 0.1}},
        "validation": {"causality": {"passed": True}, "pbo": {"pbo": 0.1}}, "provenance": {}}})
    assert c["pm"].post(f"/api/v1/governance/models/{m['id']}/signoff",
                        json={"evidence": {"result": {"owner": "quant", "id": 1}, **_ok(["Regime stress tests"])}}).status_code == 200
    assert c["pm"].put(f"/api/v1/governance/models/{m['id']}", json={"allocation": 5000, "max_loss_budget": 0.08,
                                                                    "retirement_criterion": "6m Sharpe < 0"}).status_code == 200
    monkeypatch.setattr(gov, "shadow_report", lambda mid, min_sessions=20: {"available": True, "sessions": 25,
                        "min_sessions": 20, "live": {"vol": 0.1}, "backtest": {}, "drift_flags": []})
    assert c["risk"].post(f"/api/v1/governance/models/{m['id']}/signoff",
                          json={"evidence": _ok(gov.GATE_INFO["G3"]["evidence"])}).json()["gate"] == "G3"
    r = c["quant"].post("/api/v1/orders", json={"symbol": "ISF.L", "side": "BUY", "quantity": 100, "model_id": m["id"]})
    assert r.status_code == 200, r.text
    pre = r.json()["pretrade"]
    assert pre["decision"] == "BLOCK" and any("approved-instruments" in x for x in pre["reasons"])   # not approved yet
    assert r.json()["order"]["book"] == "Macro transmission"
    assert c["risk"].post("/api/v1/governance/instruments/ISF.L/decision", json={"approve": True}).status_code == 200
    r2 = c["quant"].post("/api/v1/orders", json={"symbol": "ISF.L", "side": "BUY", "quantity": 100, "model_id": m["id"]})
    assert r2.json()["pretrade"]["decision"] in ("PASS", "WARN"), r2.json()["pretrade"]
    assert c["risk"].post("/api/v1/governance/controls/halt", json={"reason": "drill", "test": True}).status_code == 200
    r3 = c["quant"].post("/api/v1/orders", json={"symbol": "ISF.L", "side": "BUY", "quantity": 10, "model_id": m["id"]})
    assert r3.json()["pretrade"]["decision"] == "BLOCK"
    assert c["analyst"].post("/api/v1/governance/controls/resume", json={"text": "drill over"}).status_code == 403
    assert c["risk"].post("/api/v1/governance/controls/resume", json={"text": "drill over"}).status_code == 200
    assert c["pm"].get("/api/v1/governance/report/monthly").status_code == 200
    assert TestClient(app).get("/api/v1/governance").status_code == 401
    accounts.invalidate_cache()


def test_aligned_flows_lines_capital_changes_up_with_the_nav_record(fund, monkeypatch):
    """Regression: the fund overview, My Desk and the drawdown limit import `aligned_flows` (it was missing, so the
    overview returned 500)."""
    from api import governance_reports as gr
    monkeypatch.setattr(gr, "_flows", lambda: {"2026-01-03": 5_000.0, "2026-01-05": -1_000.0, "2026-01-06": 250.0})
    hist = [{"date": "2026-01-02"}, {"date": "2026-01-03"}, {"date": "2026-01-05"}]
    assert gr.aligned_flows(hist) == [0.0, 5_000.0, -1_000.0]
    # a live observation labelled "<today>T" picks up the flows dated today and after the last NAV
    assert gr.aligned_flows(hist, ["2026-01-06T"]) == [0.0, 5_000.0, -1_000.0, 250.0]
    assert gr.aligned_flows([]) == []
