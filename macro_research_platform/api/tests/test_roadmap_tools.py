"""Roadmap tools (Nov 2026): signal decay monitor and related helpers."""


def _monthly(values):
    return [(2010 + (i + 0.5) / 12, v) for i, v in enumerate(values)]


def test_decay_flags_a_signal_whose_edge_has_gone():
    from api.quant.decay import assess
    a = assess(_monthly([0.04] * 60 + [-0.01] * 36), 12)
    assert a["status"] == "gone" and a["retire"] is True and a["ic_recent"] < 0 < a["ic_early"]


def test_decay_half_life_and_fading():
    from api.quant.decay import assess
    a = assess(_monthly([0.04] * 60 + [0.02] * 36), 12)                 # halved: positive, watched, not retired
    assert a["status"] == "fading" and a["retire"] is False and a["half_life_years"] and a["half_life_years"] > 0


def test_decay_holding_up_emerging_and_short_history():
    from api.quant.decay import assess
    assert assess(_monthly([0.03] * 96), 12)["status"] == "holding up"
    assert assess(_monthly([-0.02] * 60 + [0.02] * 36), 12)["status"] == "emerging"
    assert assess(_monthly([0.03] * 10), 12)["status"] == "insufficient history"
    assert assess(_monthly([-0.01] * 96), 12)["status"] == "never worked"


def test_crisis_behaviour_separates_a_hedge_from_beta():
    import numpy as np
    import pandas as pd
    from api.quant.proof import _crisis
    days = pd.bdate_range("2015-01-01", "2022-12-30")
    rng = np.random.default_rng(1)
    b = rng.normal(0.0004, 0.01, len(days))
    beta = b.copy()                                   # moves with the index
    hedge = -0.3 * b + rng.normal(0.0002, 0.002, len(days))
    dates = [d.strftime("%Y-%m-%d") for d in days]
    hb, hh = _crisis(beta, b, dates), _crisis(hedge, b, dates)
    assert hb["crisis_return"] < 0 and hb["role"] is None and abs(hb["downside_capture"] - 1) < 1e-6
    assert hh["crisis_return"] > 0 and hh["role"] == "crisis diversifier"


def test_ops_monitor_records_feed_state_changes_and_open_incidents(tmp_path, monkeypatch):
    from api import health_sources, ops_monitor
    monkeypatch.setattr(ops_monitor, "DIR", tmp_path)
    state = {"fred": "live", "market_data": "live"}
    monkeypatch.setattr(health_sources, "get_sources_health",
                        lambda force=False: {"sources": {k: {"status": v} for k, v in state.items()}})
    assert ops_monitor.check_feeds() == []                      # first run only records the baseline
    state["fred"] = "down"
    ev = ops_monitor.check_feeds()
    assert len(ev) == 1 and ev[0]["source"] == "fred" and ev[0]["severity"] == "critical"
    s = ops_monitor.summary()
    assert [e["source"] for e in s["open_incidents"]] == ["fred"] and s["feeds"]["fred"] == "down"
    state["fred"] = "live"
    assert ops_monitor.check_feeds()[0]["severity"] == "resolved"
    assert ops_monitor.summary()["open_incidents"] == []


def test_journal_premortem_reward_risk_review_and_calibration(tmp_path, monkeypatch):
    import sqlite3
    from api.marketdata import usertools

    def conn():
        c = sqlite3.connect(tmp_path / "u.db")
        c.row_factory = sqlite3.Row
        return c
    monkeypatch.setattr(usertools, "_conn", conn)
    monkeypatch.setattr(usertools, "_ready", False)
    usertools.create_journal("ann", {"symbol": "AAPL", "side": "long", "entry": 100, "stop": 95, "target": 115,
                                     "confidence": 4, "premortem": "Services growth stalls", "review_date": "2000-01-01"})
    usertools.create_journal("ann", {"symbol": "MSFT", "side": "long", "entry": 100, "exit": 90, "confidence": 4})
    usertools.create_journal("ann", {"symbol": "NVDA", "side": "long", "entry": 100, "exit": 120, "confidence": 2})
    j = usertools.list_journal("ann")
    a = next(r for r in j["entries"] if r["symbol"] == "AAPL")
    assert a["reward_risk"] == 3 and a["review_due"] is True
    assert j["stats"]["reviews_due"] == 1 and j["stats"]["with_premortem"] == 1
    cal = {c["confidence"]: c for c in j["stats"]["calibration"]}
    assert cal[4]["win_rate"] == 0 and cal[2]["win_rate"] == 1
    import pytest
    with pytest.raises(ValueError):
        usertools.create_journal("ann", {"side": "long", "confidence": 9})


def test_mcp_research_server_is_read_only_and_cites_its_source(monkeypatch):
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location("mcp_srv", Path(__file__).resolve().parents[2] / "scripts" / "mcp_research_server.py")
    srv = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(srv)
    init = srv.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert init["result"]["capabilities"] == {"tools": {"listChanged": False}}
    tools = srv.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})["result"]["tools"]
    assert tools and all(t["annotations"]["readOnlyHint"] and not t["annotations"]["destructiveHint"] for t in tools)
    seen = []
    monkeypatch.setattr(srv, "_fetch", lambda path: seen.append(path) or {"source": srv.BASE + path, "fetched_at": "t", "data": {"x": 1}})
    r = srv.handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "country", "arguments": {"iso2": "gb"}}})
    assert seen == ["/api/v1/mkt/country/GB"] and '"source"' in r["result"]["content"][0]["text"] and not r["result"]["isError"]
    bad = srv.handle({"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "quote", "arguments": {"symbol": "../admin"}}})
    assert bad["result"]["isError"] and len(seen) == 1                         # rejected before any request
    assert srv.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    assert all("{" not in p or p.count("{") == len(r_) for p, _, _, r_, _ in srv.TOOLS.values())
