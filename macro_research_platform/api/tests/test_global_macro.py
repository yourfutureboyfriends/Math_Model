"""Developed-markets monitor: policy-rate history, currency-adjusted returns, latest-period
selection with source preference, macro quadrants."""
from datetime import date

from api.calculations.global_macro import (
    currency_return, in_usd, latest_by_area, macro_quadrant, period_date, period_return,
    policy_stats, recent_moves)

TODAY = date(2026, 10, 4)


def test_policy_stats_last_move_stance_and_12m_change():
    pts = [("2025-09-01", 0.5), ("2025-12-22", 0.75), ("2026-06-17", 1.0), ("2026-09-24", 1.25), ("2026-10-02", 1.25)]
    s = policy_stats(pts, TODAY)
    assert s["rate"] == 1.25 and s["as_of"] == "2026-10-02"
    assert s["last_move"] == {"date": "2026-09-24", "from": 1.0, "to": 1.25, "bp": 25}
    assert s["stance"] == "hiking" and s["change_12m_bp"] == 75


def test_policy_stats_on_hold_and_nan_tolerant():
    s = policy_stats([("2025-06-20", 0.25), ("2025-06-21", 0.0), ("2026-10-01", float("nan")), ("2026-10-02", 0.0)], TODAY)
    assert s["stance"] == "on hold" and s["rate"] == 0.0 and s["last_move"]["bp"] == -25
    assert policy_stats([], TODAY) == {"available": False}


def test_recent_moves_sorted_newest_first():
    m = recent_moves({"BoJ": [("2026-09-23", 1.0), ("2026-09-24", 1.25)],
                      "ECB": [("2026-09-15", 2.25), ("2026-09-16", 2.5)],
                      "SNB": [("2025-06-20", 0.25), ("2025-06-21", 0.0)]}, since="2026-06-06")
    assert [x["economy"] for x in m] == ["BoJ", "ECB"]


def test_currency_and_usd_returns():
    usdjpy = {"2025-12-31": 150.0, "2026-10-01": 157.5}       # USD/JPY up 5% → yen down ~4.76%
    r = currency_return(usdjpy, "2025-12-31", usd_base=True)
    assert round(r, 4) == round(150 / 157.5 - 1, 4)
    eurusd = {"2025-12-31": 1.10, "2026-10-01": 1.21}          # EUR up 10%
    assert round(currency_return(eurusd, "2025-12-31", usd_base=False), 4) == 0.1
    assert round(in_usd(0.10, -0.05), 4) == 0.045
    assert in_usd(0.1, None) is None and period_return({}, "2025-12-31") is None


def test_latest_by_area_prefers_national_cpi_then_newest_period():
    rows = [{"REF_AREA": "EA", "TIME_PERIOD": "2026-08", "OBS_VALUE": "3.2", "METHODOLOGY": "HICP"},
            {"REF_AREA": "EA", "TIME_PERIOD": "2026-07", "OBS_VALUE": "3.0", "METHODOLOGY": "N"},
            {"REF_AREA": "EA", "TIME_PERIOD": "2026-08", "OBS_VALUE": "3.1", "METHODOLOGY": "N"},
            {"REF_AREA": "NZL", "TIME_PERIOD": "2026-Q2", "OBS_VALUE": "4.1"},
            {"REF_AREA": "NZL", "TIME_PERIOD": "2026-Q1", "OBS_VALUE": "NaN-ish"}]
    out = latest_by_area(rows, prefer={"EA": [("METHODOLOGY", "N"), ("METHODOLOGY", "HICP")]})
    assert out["EA"] == ("2026-08", 3.1) and out["NZL"] == ("2026-Q2", 4.1)
    assert period_date("2026-Q2") == "2026-04-01" and period_date("2026-08") == "2026-08-01"


def test_macro_quadrant():
    assert macro_quadrant(2.6, 4.3, 1.7, 2.0) == "reflation"
    assert macro_quadrant(0.5, 2.4, 1.1, 2.0) == "slowdown"
    assert macro_quadrant(0.7, 1.9, 0.6, 2.0) == "goldilocks"
    assert macro_quadrant(0.5, 3.3, 1.0, 2.0) == "stagflation"
    assert macro_quadrant(None, 3.0, 1.0, 2.0) is None


def test_desk_routes_recent_cb_moves():
    from api.calculations.desk import build_queue
    moves = [{"economy": "BoJ", "date": "2026-09-24", "from": 1.0, "to": 1.25, "bp": 25},
             {"economy": "SNB", "date": "2025-06-20", "from": 0.25, "to": 0.0, "bp": -25}]
    q = build_queue("analyst", "a", orders=[], cb_moves=moves, today=TODAY)
    item = next(i for i in q if i["kind"] == "cb_move")
    assert "BoJ +25bp" in item["detail"] and "SNB" not in item["detail"]
