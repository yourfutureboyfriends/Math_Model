"""
Known-answer unit tests for portfolio position math (Phase 1).
Run: pytest api/tests/test_portfolio.py
"""
import math
import pytest

from api.calculations.portfolio import (
    market_value,
    unrealized_pnl,
    unrealized_pnl_pct,
    enrich_position,
    add_weights,
    portfolio_summary,
    books_breakdown,
)


# ── Basic position math (known answers) ──────────────────────────────────────
def test_market_value():
    assert market_value(100, 310.66) == 31066.0
    assert market_value(-50, 747.71) == -37385.5  # short


def test_unrealized_pnl_long_gain():
    assert unrealized_pnl(100, 180, 310.66) == pytest.approx(13066.0)


def test_unrealized_pnl_short_loss_when_price_rises():
    # Short 50 @ 700, price rises to 747.71 -> short loses.
    assert unrealized_pnl(-50, 700, 747.71) == pytest.approx(-2385.5)


def test_unrealized_pnl_short_gain_when_price_falls():
    assert unrealized_pnl(-50, 700, 650) == pytest.approx(2500.0)


def test_unrealized_pnl_pct():
    assert unrealized_pnl_pct(180, 198) == pytest.approx(0.1)
    assert unrealized_pnl_pct(0, 100) is None


# ── Enrichment ───────────────────────────────────────────────────────────────
def test_enrich_position_with_price():
    e = enrich_position({"symbol": "AAPL", "quantity": 100, "avg_cost": 180}, 310.66)
    assert e["price_available"] is True
    assert e["market_value"] == 31066.0
    assert e["unrealized_pnl"] == pytest.approx(13066.0)


def test_enrich_position_no_price_never_fakes():
    e = enrich_position({"symbol": "XYZ", "quantity": 10, "avg_cost": 5}, None)
    assert e["price_available"] is False
    assert e["market_value"] is None and e["unrealized_pnl"] is None


# ── Weights (gross basis) ────────────────────────────────────────────────────
def test_weights_sum_to_one_gross():
    positions = [
        enrich_position({"symbol": "A", "quantity": 100, "avg_cost": 10}, 100),   # mv 10000
        enrich_position({"symbol": "B", "quantity": -100, "avg_cost": 50}, 30),   # mv -3000
    ]
    add_weights(positions)
    total = sum(p["weight_pct"] for p in positions)
    assert math.isclose(total, 1.0, abs_tol=1e-6)
    assert positions[0]["weight_pct"] == pytest.approx(10000 / 13000, abs=1e-4)


# ── Summary aggregation (known answers) ──────────────────────────────────────
def test_portfolio_summary_long_short():
    positions = [
        enrich_position({"symbol": "AAPL", "quantity": 100, "avg_cost": 180}, 310.66),  # +13066, mv 31066
        enrich_position({"symbol": "SPY", "quantity": -50, "avg_cost": 700}, 747.71),   # -2385.5, mv -37385.5
    ]
    s = portfolio_summary(positions)
    assert s["long_market_value"] == pytest.approx(31066.0)
    assert s["short_market_value"] == pytest.approx(-37385.5)
    assert s["gross_exposure"] == pytest.approx(68451.5)   # long + |short|
    assert s["net_exposure"] == pytest.approx(-6319.5)
    assert s["total_unrealized_pnl"] == pytest.approx(10680.5)
    assert s["priced_count"] == 2 and s["unpriced_count"] == 0


def test_books_breakdown_groups_by_book():
    positions = [
        enrich_position({"symbol": "AAPL", "quantity": 100, "avg_cost": 180, "book": "Equity"}, 310.66),
        enrich_position({"symbol": "SPY", "quantity": -50, "avg_cost": 700, "book": "Macro"}, 747.71),
    ]
    rows = books_breakdown(positions)
    books = {r["book"]: r for r in rows}
    assert set(books) == {"Equity", "Macro"}
    assert books["Equity"]["total_unrealized_pnl"] == pytest.approx(13066.0)
    assert books["Macro"]["net_exposure"] == pytest.approx(-37385.5)
