"""Blotter store against a temporary SQLite DB: fills update positions atomically."""
import pytest

from api import portfolio_store, blotter_store


@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    path = str(tmp_path / "t.db")
    monkeypatch.setattr(portfolio_store, "_db_path", lambda: path)
    blotter_store.init_db()
    return path


def test_fills_update_positions_and_blotter(tmp_db):
    # Two legacy rows for the same name are consolidated on the first fill.
    portfolio_store.add_position({"symbol": "SPY", "quantity": 10, "avg_cost": 400, "book": "Macro"})
    portfolio_store.add_position({"symbol": "spy", "quantity": 10, "avg_cost": 500, "book": "Macro"})
    t1 = blotter_store.book_fill("Macro", "SPY", 20, 600.0, 6.0, "pm")
    assert t1["side"] == "BUY" and t1["position_after"] == 40
    assert t1["avg_cost_after"] == pytest.approx((10 * 400 + 10 * 500 + 20 * 600) / 40)
    rows = [p for p in portfolio_store.list_positions("Macro") if p["symbol"] == "SPY"]
    assert len(rows) == 1 and rows[0]["quantity"] == 40

    t2 = blotter_store.book_fill("Macro", "SPY", -50, 550.0, 5.0, "pm")      # close 40, short 10
    assert t2["realized_pnl"] == pytest.approx((550 - 525) * 40)
    assert t2["position_after"] == -10 and t2["avg_cost_after"] == 550.0

    t3 = blotter_store.book_fill("Macro", "SPY", 10, 540.0, 1.0, "pm")       # cover
    assert t3["position_after"] == 0
    assert not [p for p in portfolio_store.list_positions("Macro") if p["symbol"] == "SPY"]
    assert len(blotter_store.list_trades()) == 3


def test_order_fields_migrate_and_persist(tmp_db):
    idea = portfolio_store.add_trade_idea({"symbol": "TLT", "direction": "LONG"}, "pm")
    blotter_store.set_order_fields(idea["id"], side="BUY", quantity=100, approved_by="risk", bogus=1)
    o = blotter_store.get_idea(idea["id"])
    assert o["side"] == "BUY" and o["quantity"] == 100 and o["approved_by"] == "risk"
