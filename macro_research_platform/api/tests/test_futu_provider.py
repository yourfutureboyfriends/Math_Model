"""Futu integration: symbol mapping, the read-only guarantee, and a clear 'not running' state without FutuOpenD."""
import inspect
import re

import pytest

from api.providers import futu_provider as fp


@pytest.mark.parametrize("yahoo,futu", [("0700.HK", "HK.00700"), ("9988.HK", "HK.09988"), ("AAPL", "US.AAPL"), ("BRK-B", "US.BRK.B"),
                                        ("600519.SS", "SH.600519"), ("000001.SZ", "SZ.000001"), ("D05.SI", "SG.D05")])
def test_symbol_mapping_round_trips(yahoo, futu):
    assert fp.to_futu(yahoo) == futu and fp.from_futu(futu) == yahoo


def test_unsupported_markets_are_not_mapped():
    assert fp.to_futu("SAP.DE") is None and fp.to_futu("^GSPC") is None and fp.to_futu("EURUSD=X") is None


def test_module_never_unlocks_trading_or_touches_orders():
    src = inspect.getsource(fp)
    code = "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))
    code = re.sub(r'"""[\s\S]*?"""', "", code)                                  # docstrings may describe the rule
    for call in ("unlock_trade", "place_order", "modify_order", "cancel_order", "cancel_all_order"):
        assert call not in code, call


def test_without_opend_everything_reports_not_running(monkeypatch):
    monkeypatch.setattr(fp, "opend_running", lambda: False)
    assert fp.status()["connected"] is False
    with pytest.raises(fp.FutuUnavailable, match="not running"):
        fp.order_book("0700.HK")
    with pytest.raises(fp.FutuUnavailable, match="not running"):
        fp.positions()


def test_tape_uses_futu_ticks_and_flow_when_available(monkeypatch):
    from api.marketdata import core
    monkeypatch.setattr(fp, "opend_running", lambda: True)
    monkeypatch.setattr(fp, "ticks", lambda s, n=200: {"ticks": [{"time": "2026-10-27 15:59:58.120", "price": 385.2, "volume": 1000, "side": 1}]})
    monkeypatch.setattr(fp, "capital_flow", lambda s: {"by_order_size": {"big": {"in": 300.0, "out": 100.0}, "small": {"in": 100.0, "out": 100.0}}})
    extra = core._futu_tape("0700.HK", {"volume": 1_000_000})
    assert extra["prints"][0] == {"time": "15:59:58", "price": 385.2, "volume": 1000, "side": 1}
    assert extra["buy_share"] == pytest.approx(400 / 600) and extra["up_volume"] == pytest.approx(1_000_000 * 400 / 600)
    monkeypatch.setattr(fp, "opend_running", lambda: False)
    assert core._futu_tape("0700.HK", {"volume": 1}) == {}                 # no OpenD: the bar estimate stands


def test_scheduler_runs_late_jobs_instead_of_skipping_them():
    from api.main import _scheduler
    assert _scheduler._job_defaults["misfire_grace_time"] >= 300 and _scheduler._job_defaults["coalesce"] is True
