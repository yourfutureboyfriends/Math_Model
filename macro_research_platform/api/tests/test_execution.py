"""Execution adapters: simulated fills, paper-only routing (mocked HTTP — nothing is sent)."""
from api import execution


class _Resp:
    def __init__(self, code, payload):
        self.status_code, self._p, self.text = code, payload, str(payload)

    def json(self):
        return self._p


class _Session:
    def __init__(self, post, gets=()):
        self.post_resp, self.gets, self.calls = post, list(gets), []

    def post(self, url, **kw):
        self.calls.append(("POST", url, kw.get("json")))
        return self.post_resp

    def get(self, url, **kw):
        self.calls.append(("GET", url, None))
        return self.gets.pop(0)


def test_mode_defaults_to_simulated(monkeypatch):
    monkeypatch.delenv("BROKER_ROUTING", raising=False)
    assert execution.execution_mode() == "simulated"
    monkeypatch.setenv("BROKER_ROUTING", "alpaca_paper")
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    assert execution.execution_mode() == "simulated"        # no keys -> never routes


def test_simulated_fill():
    f = execution.simulated_fill(-100, 250.5)
    assert f.filled and f.price == 250.5 and f.quantity == -100
    assert not execution.simulated_fill(10, None).filled


def test_paper_routing_only_hits_paper_url_and_books_avg_price():
    s = _Session(_Resp(200, {"id": "o1", "status": "accepted"}),
                 [_Resp(200, {"id": "o1", "status": "filled", "filled_avg_price": "101.25"})])
    f = execution.alpaca_paper_fill("SPY", -5, session=s, poll_seconds=5)
    assert f.filled and f.price == 101.25 and f.broker_order_id == "o1"
    assert all(url.startswith("https://paper-api.alpaca.markets") for _, url, _ in s.calls)
    assert s.calls[0][2] == {"symbol": "SPY", "qty": "5", "side": "sell", "type": "market",
                             "time_in_force": "day"}


def test_paper_rejection_is_not_booked():
    f = execution.alpaca_paper_fill("SPY", 5, session=_Session(_Resp(403, {"message": "no"})))
    assert not f.filled and f.status == "rejected"
