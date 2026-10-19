from api.calculations.signal_governance import (
    evidence_status, evidence_weights, independence_agreement, factor_consequences)


def _card(sharpe, total, hit=0.55, p=0.03):
    return {"available": True, "strategy_sharpe": sharpe, "strategy_total_return": total,
            "hit_rate_independent": hit, "hit_rate_p_value": p}


def test_status_fail_weak_pass_unvalidated():
    assert evidence_status(_card(-0.32, -0.27, 0.50, 0.9))[0] == "FAIL"
    assert evidence_status(_card(0.4, 0.2, 0.52, 0.6))[0] == "WEAK"
    assert evidence_status(_card(0.8, 0.5, 0.58, 0.02))[0] == "PASS"
    assert evidence_status(None)[0] == "UNVALIDATED"


def test_failing_input_is_retired_and_weights_renormalise():
    rows = evidence_weights([("a", 0.8), ("b", 0.2), ("c", 0.5)],
                            {"a": _card(0.8, 0.5), "b": _card(-0.3, -0.2)})
    w = {r["name"]: r["weight"] for r in rows}
    assert w["b"] == 0
    assert abs(sum(w.values()) - 1) < 1e-6
    assert w["a"] == round(1 / 1.5, 3) and w["c"] == round(0.5 / 1.5, 3)


def test_all_retired_falls_back_to_equal():
    rows = evidence_weights([("a", 1.0), ("b", 0.0)], {"a": _card(-1, -0.1), "b": _card(-1, -0.1)})
    assert [r["weight"] for r in rows] == [0.5, 0.5]


def test_correlated_votes_count_once():
    votes = {"m1": True, "m2": True, "m3": True, "m4": True, "liq": False, "rec": False}
    drivers = {"m1": "eq", "m2": "eq", "m3": "eq", "m4": "eq", "liq": "rates", "rec": "macro"}
    out = independence_agreement(votes, drivers)
    assert out["raw_agreement"] == 0.67
    assert out["effective_votes"] == 3
    assert out["agreement"] == 0.67 and out["bullish_share"] == 0.33   # 1 of 3 drivers bullish


def test_factor_consequences_short_names():
    v = {"factors": [{"factor": "Momentum (MTUM)", "available": True, "unstable": True},
                     {"factor": "Value (VLUE)", "available": True, "unstable": False},
                     {"factor": "Size (IWM−SPY)", "available": False}]}
    out = factor_consequences(v)
    assert out["momentum"]["unstable"] and not out["value"]["unstable"] and "size" not in out


def test_decision_log_is_append_only():
    import sqlite3
    import pytest
    from api.audit_store import add_decision, init_audit_db
    from api.core.app_db import app_db_path
    init_audit_db()
    row = add_decision("test_action", "append-only check", user="tester")
    conn = sqlite3.connect(app_db_path())
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        conn.execute("UPDATE decision_log SET rationale='x' WHERE id=?", (row["id"],))
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        conn.execute("DELETE FROM decision_log WHERE id=?", (row["id"],))
    conn.close()


def test_quote_staleness_respects_market_hours():
    from datetime import datetime, timezone
    from api.health_sources import quote_staleness
    # Monday 20 Oct 2026 15:00 New York (19:00 UTC): NYSE open
    now = datetime(2026, 10, 20, 19, 0, tzinfo=timezone.utc)
    assert quote_staleness("nyse", datetime(2026, 10, 20, 18, 50, tzinfo=timezone.utc), now)["status"] == "fresh"
    assert quote_staleness("nyse", datetime(2026, 10, 19, 19, 55, tzinfo=timezone.utc), now)["status"] == "stale"
    # Saturday: Friday's last bar is current for equities and FX
    sat = datetime(2026, 10, 24, 15, 0, tzinfo=timezone.utc)
    assert quote_staleness("nyse", datetime(2026, 10, 23, 19, 55, tzinfo=timezone.utc), sat)["status"] == "fresh"
    assert quote_staleness("fx", datetime(2026, 10, 23, 20, 55, tzinfo=timezone.utc), sat)["status"] == "fresh"
    # FX a day behind on a weekday is stale
    assert quote_staleness("fx", datetime(2026, 10, 19, 18, 0, tzinfo=timezone.utc), now)["status"] == "stale"
