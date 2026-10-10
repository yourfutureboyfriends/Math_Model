"""Analytics functions: FX forwards (covered interest parity) and correlation ordering."""
import pandas as pd
import pytest


def test_fx_forward_is_covered_interest_parity(monkeypatch):
    from api.marketdata import analytics, core
    monkeypatch.setattr(analytics, "_short_rate", lambda c: {"rate": {"EUR": 0.02, "USD": 0.05}[c], "date": "2099-01-01", "series": c})
    monkeypatch.setattr(core, "quote", lambda s: {"price": 1.10})
    monkeypatch.setattr(analytics, "_cached", lambda k, ttl, fn: fn())
    f = analytics.fx_forwards("EUR", "USD")
    one_year = next(t for t in f["tenors"] if t["tenor"] == "1Y")
    assert one_year["forward"] == pytest.approx(1.10 * (1 + 0.05 * 365 / 360) / (1 + 0.02 * 365 / 360))
    assert one_year["points"] > 0                       # higher USD rates → EUR trades at a forward premium
    assert f["stale_rates"] == []


def test_correlation_cluster_order_keeps_related_together():
    from api.marketdata.analytics import _cluster_order
    c = pd.DataFrame([[1, .9, .1, .1], [.9, 1, .1, .1], [.1, .1, 1, .8], [.1, .1, .8, 1]],
                     index=list("ABCD"), columns=list("ABCD"))
    order = _cluster_order(c)
    pos = {s: i for i, s in enumerate(order)}
    assert abs(pos["A"] - pos["B"]) == 1 and abs(pos["C"] - pos["D"]) == 1
