"""Event dataset (point-in-time vintages, surprise proxy, reaction timing), governed shadow trading, two-factor
sign-in, data-licence register, stress tests, position snapshots and the pitch benchmark kill criterion."""
import time

import pandas as pd
import pytest


# ── event dataset ────────────────────────────────────────────────────────────
def test_release_events_use_values_as_published(monkeypatch):
    from api import event_dataset as ed
    # month m: first printed 100+m on release day r_m, then revised to 200+m a month later
    vint = []
    for m in range(1, 30):
        mon = f"{2014 + (m - 1) // 12}-{(m - 1) % 12 + 1:02d}-01"
        rel = (pd.Timestamp(mon) + pd.offsets.MonthBegin(1) + pd.Timedelta(days=4)).strftime("%Y-%m-%d")
        rev = (pd.Timestamp(rel) + pd.Timedelta(days=30)).strftime("%Y-%m-%d")
        vint.append({"date": mon, "value": 100.0 * m, "rs": rel, "re": (pd.Timestamp(rev) - pd.Timedelta(days=1)).strftime("%Y-%m-%d")})
        vint.append({"date": mon, "value": 100.0 * m + 1000, "rs": rev, "re": "9999-12-31"})
    monkeypatch.setattr(ed, "_vintages", lambda s: vint)
    monkeypatch.setattr(ed, "START", "2015-01-01")
    rows = ed.release_events("us_payrolls")
    r = rows[0]
    # actual = first print of month m − the value of m−1 AS KNOWN on that day (already revised once)
    m = int(pd.Timestamp(r["period"] + "-01").strftime("%m")) + (int(r["period"][:4]) - 2014) * 12
    assert r["actual"] == pytest.approx(100.0 * m - (100.0 * (m - 1) + 1000))
    assert all(x["expectation_proxy"] is None or isinstance(x["expectation_proxy"], float) for x in rows)
    assert any(x["surprise_z"] is not None for x in rows)                      # z only once 12 past surprises exist


def test_reaction_window_respects_the_release_time():
    from api import event_dataset as ed
    closes = {"2026-10-01": 100.0, "2026-10-02": 101.0, "2026-10-05": 102.0, "2026-10-06": 103.0,
              "2026-10-07": 104.0, "2026-10-08": 105.0, "2026-10-09": 106.0, "2026-10-12": 107.0}
    days = sorted(closes)
    # 08:30 release on 10-02: a London close (11:30) on 10-02 is after it → pre = 10-01 close
    assert ed._reaction(closes, days, "2026-10-02", "08:30", "11:30", "%")[0] == pytest.approx(1.0)
    # 14:00 FOMC on 10-02: the London close came before → pre = 10-02, first close after = 10-05
    assert ed._reaction(closes, days, "2026-10-02", "14:00", "11:30", "%")[0] == pytest.approx((102 / 101 - 1) * 100, abs=1e-3)
    h0, h5 = ed._reaction(closes, days, "2026-10-02", "08:30", "16:00", "bp")
    assert h0 == pytest.approx(100.0) and h5 == pytest.approx(600.0)


def test_event_summary_flags_the_mechanical_fomc_series():
    from api import event_dataset as ed
    evs = [{"event": "fomc", "surprise_z": z, "reactions": {"DGS2": {"h0": z * 9}, "CSPX.L": {"h0": -z}}}
           for z in [x / 10 for x in range(-15, 15)]]
    s = ed.summary({"events": evs, "assets": {"DGS2": {"unit": "bp"}, "CSPX.L": {"unit": "%"}}}, "fomc")
    assert s["by_asset"]["DGS2"]["mechanical"] and s["by_asset"]["CSPX.L"]["beta_per_1sd"] == pytest.approx(-1.0)


# ── governed shadow trading ──────────────────────────────────────────────────
@pytest.fixture()
def fund(tmp_path, monkeypatch):
    from api import funds
    monkeypatch.setattr(funds, "db_path", lambda fund_id=None: str(tmp_path / "fund.db"))
    monkeypatch.setattr(funds, "get", lambda fid: {"id": fid, "name": "x", "members": []})
    monkeypatch.setattr(funds, "update", lambda *a, **k: None)
    from api import moriah
    moriah.setup("main", "admin")
    return tmp_path


def test_deployments_need_a_g2_model_and_feed_the_shadow_report(fund, monkeypatch):
    from api import governance as gov
    from api.quant import store
    assert "governed models" in gov.model_for_deployment(None)[1]
    m = gov.create_model("q", {"name": "x", "sleeve": "systematic_trend", "mechanism": "m", "target_variable": "t",
                               "horizon": "h", "dataset": "d", "null_hypothesis": "n"})
    assert "G2" in gov.model_for_deployment(m["id"])[1]
    import sqlite3
    from api import funds
    with sqlite3.connect(funds.db_path()) as c:
        c.execute("UPDATE gov_models SET gate = 'G2' WHERE id = ?", (m["id"],))
    assert gov.model_for_deployment(m["id"])[1] is None
    rets = {f"2026-09-{d:02d}": (0.001 * (-1) ** d, 0.0) for d in range(1, 26)}
    monkeypatch.setattr(store, "list_deployments", lambda active_only=True: [
        {"id": 9, "name": "trend", "model_id": m["id"], "fund": "main", "active": 1, "deployed_at": "2026-08-31",
         "backtest": {"vol": 0.016, "sharpe": 0.5, "cagr": 0.05}}])
    monkeypatch.setattr(store, "live_returns", lambda did: rets)
    sh = gov.shadow_report(m["id"])
    assert sh["sessions"] == 25 and sh["live"]["vol"] == pytest.approx(0.0159, abs=0.001) and sh["drift_flags"] == []
    monkeypatch.setattr(store, "list_deployments", lambda active_only=True: [
        {"id": 9, "name": "trend", "model_id": m["id"], "fund": "main", "active": 1, "deployed_at": "2026-08-31",
         "backtest": {"vol": 0.20, "sharpe": 0.5}}])
    assert gov.shadow_report(m["id"])["drift_flags"] and not gov.shadow_report(m["id"])["ready"]


# ── two-factor sign-in ───────────────────────────────────────────────────────
def test_totp_matches_rfc6238_and_blocks_replay():
    from api.core import mfa
    secret = __import__("base64").b32encode(b"12345678901234567890").decode()
    assert mfa.code_at(secret, 59 // 30) == "287082"                          # RFC 6238 test vector (SHA1, T=59)
    assert mfa.code_at(secret, 1111111109 // 30) == "081804"
    step = mfa._match(secret, "287082", None, now=59)
    assert step == 1 and mfa._match(secret, "287082", step, now=59) is None   # used once only


def test_login_with_two_factor_and_lockout(tmp_path, monkeypatch):
    import api.core.auth as auth
    from api.core import accounts, mfa
    path = str(tmp_path / "u.db")
    monkeypatch.setattr(auth, "get_db_path", lambda: path)
    accounts.invalidate_cache()
    accounts.migrate()
    accounts.set_password("pm", "Mfa-Test-Pass-2026!x")
    s = mfa.begin_setup("pm")
    now_code = mfa.code_at(s["secret"], int(time.time() // 30))
    codes = mfa.confirm_setup("pm", now_code)["recovery_codes"]
    assert len(codes) == 8 and mfa.enabled("pm")
    with pytest.raises(accounts.LoginError) as e:
        accounts.check_login("pm", "Mfa-Test-Pass-2026!x")
    assert e.value.mfa_required
    with pytest.raises(accounts.LoginError):
        accounts.check_login("pm", "Mfa-Test-Pass-2026!x", now_code)          # replayed code
    assert accounts.check_login("pm", "Mfa-Test-Pass-2026!x", codes[0])["username"] == "pm"
    with pytest.raises(accounts.LoginError):
        accounts.check_login("pm", "Mfa-Test-Pass-2026!x", codes[0])          # recovery codes are single-use
    for _ in range(4):                                                         # wrong codes count towards lockout
        try:
            accounts.check_login("pm", "Mfa-Test-Pass-2026!x", "000000")
        except accounts.LoginError as err:
            last = err
    assert last.status == 429
    mfa.set_required(True)
    assert mfa.required()
    accounts.invalidate_cache()


def test_enrolment_required_blocks_other_apis(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import api.core.auth as auth
    from api.core import accounts, mfa
    path = str(tmp_path / "u.db")
    monkeypatch.setattr(auth, "get_db_path", lambda: path)
    accounts.invalidate_cache()
    accounts.migrate()
    accounts.set_password("risk", "Mfa-Risk-Pass-2026!x")
    mfa.set_required(True)
    from api.main import app
    c = TestClient(app)
    c.headers["Authorization"] = f"Bearer {accounts.issue_token(accounts.get_user('risk'))}"
    r = c.get("/api/v1/governance")
    assert r.status_code == 403 and r.json()["code"] == "mfa_enrollment_required"
    assert c.get("/api/auth/mfa").json()["required"] is True
    s = c.post("/api/auth/mfa/setup").json()
    assert c.post("/api/auth/mfa/enable", json={"code": mfa.code_at(s["secret"], int(time.time() // 30))}).status_code == 200
    accounts.invalidate_cache()
    assert c.get("/api/v1/governance").status_code == 200
    mfa.set_required(False)
    accounts.invalidate_cache()


# ── licences, stress, snapshots ──────────────────────────────────────────────
def test_data_sources_start_unreviewed_and_need_a_terms_reference(fund):
    from api import governance as gov
    srcs = gov.data_sources()
    assert len(srcs) == len(gov.DATA_SOURCES) and all(s["status"] == "unreviewed" for s in srcs)
    with pytest.raises(ValueError):
        gov.review_source("FRED (St. Louis Fed)", "risk", "allowed", "")
    r = gov.review_source("Yahoo Finance prices (via yfinance)", "risk", "restricted", "Yahoo terms, read 2026-10-26",
                          "research only; no redistribution")
    assert r["status"] == "restricted" and r["reviewed_by"] == "risk"


def test_stress_tests_replay_history_and_report_coverage(fund, monkeypatch):
    from api import governance_reports as gr
    from api.calculations import benchmark as bm
    import api.handlers.portfolio_analytics as pa
    idx = pd.bdate_range("2016-01-01", "2023-01-01")
    monkeypatch.setattr(bm, "in_base", lambda s, b: pd.Series(100.0, index=idx) if s == "OLD" else
                        pd.Series(100.0, index=idx[idx > "2021-01-01"]))
    monkeypatch.setattr(pa, "_usd_per_unit", lambda s: ("USD", 1.0) if s == "OLD" else ("GBp", 0.013))
    r = gr.stress_tests([{"symbol": "OLD", "market_value": 1000.0}, {"symbol": "NEW", "market_value": 1000.0}], "GBP")
    by = {x["id"]: x for x in r["scenarios"]}
    assert by["equity_crash"]["coverage"] == 0.5 and by["equity_crash"]["excluded"] == ["NEW"]
    assert by["correlations_to_one"]["coverage"] == 1.0
    assert by["fx_gbp_up"]["pnl"] == pytest.approx(1000 * (1 / 1.1 - 1), abs=0.01)   # only the USD holding loses
    assert by["data_outage"]["kind"] == "procedure"


def test_position_snapshots_round_trip(fund):
    from api import fund_store
    fund_store.record_positions("2026-09-30", [{"symbol": "isf.l", "book": "Trend", "quantity": 10, "market_value": 80.0,
                                               "unrealized_pnl": 5.0, "current_price": 8.0}], "GBP")
    snap = fund_store.position_snapshot("2026-10-15", "GBP")
    assert snap["date"] == "2026-09-30" and snap["rows"][0]["symbol"] == "ISF.L" and snap["rows"][0]["unrealized_pnl"] == 5.0
    assert fund_store.position_snapshot("2026-09-01")["date"] is None


def test_relative_since_approval(monkeypatch):
    from api.calculations import benchmark as bm
    idx = pd.bdate_range("2026-01-01", periods=40)
    monkeypatch.setattr(bm, "in_base", lambda s, b: pd.Series([100.0] * 20 + [110.0] * 20, index=idx))
    monkeypatch.setattr(bm, "series", lambda c, b: {"returns": pd.Series([0.0] * 30 + [0.05] + [0.0] * 9, index=idx)})
    rel = bm.relative_since("X", "BIFS", "GBP", str(idx[5].date()))
    assert rel == pytest.approx(1.10 / 1.05 - 1, abs=1e-9)                    # +10% vs benchmark +5%
