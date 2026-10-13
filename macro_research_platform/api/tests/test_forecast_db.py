"""Lazy schema creation and the forecast log.

Tables are created on the first connection to any database file — a fresh install or a
test DB must serve empty reads, not "no such table" (13 diagnostics routes 500'd that way)."""
import pytest


@pytest.fixture
def db(tmp_path, monkeypatch):
    import database.db as d
    monkeypatch.setattr(d, "DB_PATH", tmp_path / "fresh.db")
    yield d


def test_fresh_db_has_every_table_and_reads_are_empty(db):
    from api.services.expected_returns_validation import expected_returns_validator
    df = expected_returns_validator.get_forecast_history()
    assert df.empty and {"expected_return", "realized_return"} <= set(df.columns)
    with db.get_db() as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"forecast_history", "regime_history", "conviction_history", "production_predictions",
            "recession_forecast_history", "signal_stack_history", "nowcast_history"} <= tables


def test_tracker_round_trip_on_fresh_db(db):
    from api.services.forecast_tracker import ForecastTracker
    t = ForecastTracker()
    assert t.get_unrealized() == [] and t.get_history() == []
    fid = t.log_regime_forecast("Reflation", 0.6, 0.9, 0.5)
    assert fid > 0
    t.log_regime_forecast("Reflation", 0.7, 0.9, 0.5)
    assert len(t.get_history(model_name=t.REGIME_THRESHOLD)) == 1, "one forecast per model per day"
    assert t.backfill_regime_realized(t.get_history()[0]["forecast_date"], "Reflation") == 1
    assert t.get_regime_comparison() is not None
    pid = t.log_forecast("recession_probit", "2026-01-01", "12M", predicted_value=0.3)
    assert t.update_realized(pid, realized_value=0.0)
    assert t.get_model_accuracy("recession_probit").evaluated == 1


def test_registered_schema_applies_to_new_db(db, tmp_path, monkeypatch):
    monkeypatch.setattr(db, "_SCHEMAS", list(db._SCHEMAS))       # keep the probe out of the real registry
    monkeypatch.setattr(db, "_ENSURED", set())
    db.register_schema("CREATE TABLE IF NOT EXISTS probe_table (id INTEGER PRIMARY KEY);")
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "second.db")
    with db.get_db() as conn:
        assert conn.execute("SELECT count(*) FROM probe_table").fetchone()[0] == 0
