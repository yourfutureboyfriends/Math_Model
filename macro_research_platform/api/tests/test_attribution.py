"""
Known-answer tests for performance attribution (Phase 5).
Run: pytest api/tests/test_attribution.py
"""
import pytest
from api.calculations.attribution import (
    position_contributions, book_rollup, factor_attribution, cumulative_return,
)

POS = [
    {"symbol": "AAPL", "book": "Equity", "unrealized_pnl": 13066.0},
    {"symbol": "SPY", "book": "Macro", "unrealized_pnl": -2385.5},
    {"symbol": "MSFT", "book": "Equity", "unrealized_pnl": -446.0},
]


def test_position_contributions_sum_to_total():
    rows = position_contributions(POS)
    assert sum(r["pnl"] for r in rows) == pytest.approx(13066.0 - 2385.5 - 446.0)
    assert rows[0]["symbol"] == "AAPL"          # sorted by pnl desc
    assert sum(r["pct_of_abs_pnl"] for r in rows) == pytest.approx(1.0, abs=1e-3)


def test_book_rollup_sums_and_groups():
    rows = book_rollup(POS)
    books = {r["book"]: r for r in rows}
    assert books["Equity"]["pnl"] == pytest.approx(13066.0 - 446.0)
    assert books["Macro"]["pnl"] == pytest.approx(-2385.5)
    assert books["Equity"]["positions"] == 2
    assert sum(r["pnl"] for r in rows) == pytest.approx(13066.0 - 2385.5 - 446.0)


def test_factor_attribution_reconciles():
    loadings = {"equity": 1.2, "rates": -0.3}
    factor_ret = {"equity": 0.10, "rates": 0.04}
    port_ret = 0.15
    res = factor_attribution(loadings, factor_ret, port_ret)
    # systematic = 1.2*0.10 + -0.3*0.04 = 0.12 - 0.012 = 0.108
    assert res["systematic_return"] == pytest.approx(0.108)
    assert res["idiosyncratic_return"] == pytest.approx(0.15 - 0.108)
    # systematic + idio == portfolio return (reconciliation)
    assert res["systematic_return"] + res["idiosyncratic_return"] == pytest.approx(port_ret, abs=1e-9)
    assert res["by_factor"]["equity"] == pytest.approx(0.12)


def test_cumulative_return():
    assert cumulative_return([0.10, -0.10]) == pytest.approx(-0.01)  # 1.10*0.90 - 1
    assert cumulative_return([0.0, 0.0]) == pytest.approx(0.0)


def test_empty_positions():
    assert position_contributions([]) == []
    assert book_rollup([]) == []
