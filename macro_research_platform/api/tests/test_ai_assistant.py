"""AI assistant tool loop, offline: a scripted fake model calls tools; results are fed back,
duplicates reused, unknown tools reported, and the final answer returned."""
import json

import pytest

from api.ai import assistant


class FakeModel:
    def __init__(self, script):
        self.script, self.seen = list(script), []

    def __call__(self, cfg, messages, model):
        self.seen.append([m.copy() for m in messages])
        return self.script.pop(0)


def _call(name, args, cid="c1"):
    return {"id": cid, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}


@pytest.fixture()
def cfg(monkeypatch):
    monkeypatch.setattr(assistant, "config", lambda: {"provider": "fake", "available": True, "model": "m", "models": ["m"],
                                                     "base_url": "x", "key": "k", "note": ""})


def test_tool_loop_feeds_results_and_dedupes(cfg, monkeypatch):
    monkeypatch.setitem(assistant.TOOLS, "get_quote", (lambda symbol: {"symbol": symbol, "price": 123.4}, "q", {"symbol": {"type": "string"}}))
    fake = FakeModel([
        {"content": "", "tool_calls": [_call("get_quote", {"symbol": "AAPL"}, "a"), _call("get_quote", {"symbol": "AAPL"}, "b")]},
        {"content": "AAPL is **123.4** (Yahoo Finance)."},
    ])
    monkeypatch.setattr(assistant, "_complete", fake)
    out = assistant.chat([{"role": "user", "content": "price of apple?"}], context="AAPL")
    assert out["reply"].startswith("AAPL is") and out["tool_calls"] == [{"name": "get_quote", "args": {"symbol": "AAPL"}, "ok": True}]
    tool_msgs = [m for m in fake.seen[1] if m["role"] == "tool"]
    assert len(tool_msgs) == 2 and '"price":123.4' in tool_msgs[0]["content"]
    assert "AAPL" in fake.seen[0][0]["content"]                     # context reaches the system prompt


def test_unknown_tool_and_errors_are_reported(cfg, monkeypatch):
    def boom(symbol):
        raise ValueError("no data")
    monkeypatch.setitem(assistant.TOOLS, "get_quote", (boom, "q", {"symbol": {"type": "string"}}))
    ok, out = assistant.run_tool("nope", {})
    assert not ok and "Unknown tool" in out
    ok, out = assistant.run_tool("get_quote", {"symbol": "X", "evil": "drop"})
    assert not ok and "no data" in out


def test_unavailable_provider_raises(monkeypatch):
    monkeypatch.setattr(assistant, "config", lambda: {"provider": "none", "available": False, "note": "Set up Ollama", "models": []})
    with pytest.raises(RuntimeError, match="Ollama"):
        assistant.chat([{"role": "user", "content": "hi"}])


def test_tool_specs_are_valid_openai_functions():
    specs = assistant.tool_specs()
    assert len(specs) == len(assistant.TOOLS)
    for s in specs:
        f = s["function"]
        assert s["type"] == "function" and f["parameters"]["type"] == "object"
        assert set(f["parameters"]["required"]) <= set(f["parameters"]["properties"])
