"""Point-in-time archive: file vintages kept only when they change, looked up as of a day; curve snapshots per day."""
import pytest

from api import vintage_archive as va


@pytest.fixture()
def db(tmp_path, monkeypatch):
    import api.core.app_db as app_db
    monkeypatch.setattr(app_db, "app_db_path", lambda: str(tmp_path / "a.db"))
    monkeypatch.setattr(va, "_ready", False)
    yield


def test_vintages_are_stored_once_per_distinct_version_and_read_as_of_a_day(db, monkeypatch):
    assert va.archive("ebp_csv", "date,ebp\n2026-08,0.1\n") is True
    assert va.archive("ebp_csv", "date,ebp\n2026-08,0.1\n") is False            # unchanged → not stored again
    assert va.archive("ebp_csv", "date,ebp\n2026-08,0.12\n2026-09,0.2\n") is True # the Fed revised August
    vs = va.vintages("ebp_csv")
    assert len(vs) == 2
    assert va.vintage_as_of("ebp_csv", vs[0]["captured_at"][:10]).endswith("0.2\n")   # latest on that day
    assert va.vintage_as_of("ebp_csv", "2000-01-01") is None
    assert va.status()["file_vintages"][0]["versions"] == 2


def test_curve_snapshot_saves_each_root_and_records_failures(db, monkeypatch):
    import api.marketdata.monitors as mon

    def fake(root):
        if root == "NG":
            raise RuntimeError("no curve")
        return {"front": {"month": "2026-12", "price": 70.0}, "slope": -0.05, "annualised_roll_yield": 0.05,
                "points": [{"month": "2026-12", "price": 70.0}, {"month": "2027-12", "price": 66.5}]}
    monkeypatch.setattr(mon, "futures_curve", fake)
    r = va.snapshot_commodity_curves(["CL", "NG"])
    assert r["saved"] == ["CL"] and "NG" in r["failed"]
    va.snapshot_commodity_curves(["CL"])                                          # same day: replaced, not duplicated
    h = va.carry_history("cl")
    assert len(h) == 1 and h[0]["roll_yield"] == 0.05


def test_a_reverted_file_is_a_new_vintage(db):
    va.archive("x", "a"); va.archive("x", "b"); va.archive("x", "a")
    assert [v["sha256"] for v in va.vintages("x")][0] == [v["sha256"] for v in va.vintages("x")][2]
    assert va.vintage_as_of("x", "2999-01-01") == "a"
