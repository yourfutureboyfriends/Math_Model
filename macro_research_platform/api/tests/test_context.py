"""Security context: the regime playbooks' view of a sector, and a strip that survives any part failing."""
import asyncio

from api import context


def test_stance_follows_each_regime_playbook_whatever_its_spelling():
    assert context._stance("stagflation", "XLP")["stance"] == "overweight"            # dashboard spells it lower-case
    assert context._stance("Goldilocks", "XLE")["stance"] == "underweight"
    assert context._stance("Deflationary slowdown", "XLU")["stance"] == "overweight"   # the macro model's name for Slowdown
    assert context._stance("Reflation", "XLV")["stance"] == "neutral"
    assert context._stance(None, "XLK")["stance"] is None and context._stance("Goldilocks", None)["stance"] is None


def test_a_failing_part_never_sinks_the_strip(monkeypatch):
    import api.marketdata.core as core
    from api import portfolio_store
    monkeypatch.setattr(core, "_info", lambda s: {"sector": "Energy", "country": "United States", "longName": "Test Oil"})
    monkeypatch.setattr(portfolio_store, "list_positions", lambda: [{"symbol": "TST", "quantity": 100, "book": "core"}])

    def boom(*a, **k):
        raise RuntimeError("down")
    from api.marketdata import dcf
    monkeypatch.setattr(dcf, "inputs", boom)
    from api.pe import deals
    monkeypatch.setattr(deals, "list_deals", boom)
    monkeypatch.setattr(core, "_cached", lambda key, ttl, fn: fn())
    from api.providers import futu_provider as fp
    monkeypatch.setattr(fp, "opend_running", lambda: False)
    from api.handlers import dashboard_handler
    from api.model import engine

    async def slow_down(*a, **k):
        raise RuntimeError("regime service down")
    monkeypatch.setattr(dashboard_handler, "get_dashboard_data", slow_down)
    monkeypatch.setattr(engine, "world_summary", slow_down)
    r = asyncio.run(context.build("tst", "pm"))
    assert r["symbol"] == "TST" and r["macro"]["sector_etf"] == "XLE"
    assert r["book"]["fund"][0]["quantity"] == 100 and r["book"]["futu"] == []
    assert "unavailable" in r["valuation"] and "unavailable" in r["pe"]
    assert r["macro"]["signal"]["stance"] is None and r["macro"]["model"]["stance"] is None   # regimes down: no stance
