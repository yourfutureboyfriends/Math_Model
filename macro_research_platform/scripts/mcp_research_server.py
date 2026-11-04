#!/usr/bin/env python3
"""
Read-only MCP research server for the Macro Terminal: lets Claude (Desktop or Code) answer questions from the
platform's own data — regime, recession odds, nowcast, signals, Fed watch, markets, DCF, country data, data health —
with every answer citing the endpoint it came from and when it was fetched.

  read-only   GET requests only, to a fixed list of research endpoints; no orders, approvals, gate sign-offs,
              settings or anything that writes. There is no tool that can change state.
  grounded    each result is {"source": <url>, "fetched_at": <UTC time>, "data": …}; the instructions ask the model
              to cite the source and to say when a figure is missing rather than estimate it
  no deps     plain Python 3 standard library (MCP over stdio, JSON-RPC 2.0, newline-delimited)

Register it (Claude Code):
    claude mcp add macro-terminal -- /path/to/.venv/bin/python /path/to/scripts/mcp_research_server.py

Environment:
    MACRO_API_BASE    backend URL (default http://127.0.0.1:8000)
    MACRO_API_TOKEN   optional bearer token, for the signed-in tools (signal health, strategy evidence). Paste it
                      yourself; it is sent only to MACRO_API_BASE.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

BASE = os.getenv("MACRO_API_BASE", "http://127.0.0.1:8000").rstrip("/")
TOKEN = os.getenv("MACRO_API_TOKEN")
MAX_CHARS = 24_000
PROTOCOL = "2024-11-05"

INSTRUCTIONS = (
    "Tools read the Macro Terminal's own research data. Cite the `source` and `fetched_at` of every figure you use. "
    "If a field is null, missing or the tool errors, say so — do not estimate or fill in from memory. Paper / simulated "
    "results are not a track record. These tools cannot trade or change anything."
)

SYM = {"type": "string", "description": "Ticker, e.g. AAPL, SPY, VOD.L"}
# name: (path template, description, input properties, required, needs sign-in)
TOOLS: Dict[str, Tuple[str, str, Dict[str, Any], List[str], bool]] = {
    "macro_regime": ("/api/regime", "Current US macro regime (growth × inflation quadrant), its probability and drivers.", {}, [], False),
    "macro_dashboard": ("/api/dashboard", "The full macro dashboard: indicators, regime, recession, signals, asset views.", {}, [], False),
    "recession_probability": ("/api/recession", "US recession probability and the components behind it.", {}, [], False),
    "nowcast": ("/api/nowcast", "Real-time GDP / inflation nowcast.", {}, [], False),
    "macro_signals": ("/api/signals", "Composite macro signals and asset-class tilts.", {}, [], False),
    "yield_curve": ("/api/signals/yield-curve", "US yield curve shape, spreads and what they signal.", {}, [], False),
    "economic_calendar": ("/api/calendar", "Upcoming economic releases and central-bank events.", {}, [], False),
    "cot_positioning": ("/api/cot", "CFTC Commitments of Traders positioning.", {}, [], False),
    "fed_watch": ("/api/v1/mkt/fedwatch", "Latest FOMC statement: redline vs the previous one, tone score, dissents, vote.", {}, [], False),
    "margin_debt": ("/api/v1/mkt/margin-debt", "FINRA margin debt history and its change — a leverage / risk-appetite gauge.", {}, [], False),
    "markets_overview": ("/api/v1/mkt/overview", "Cross-asset market overview: indices, rates, FX, commodities, crypto.", {}, [], False),
    "quote": ("/api/v1/mkt/quote/{symbol}", "Quote and key statistics for one security.", {"symbol": SYM}, ["symbol"], False),
    "dcf_valuation": ("/api/v1/mkt/dcf/{symbol}", "Discounted-cash-flow valuation with its assumptions and sensitivity.", {"symbol": SYM}, ["symbol"], False),
    "company_news": ("/api/v1/mkt/news?symbol={symbol}", "Recent news for a security.", {"symbol": SYM}, ["symbol"], False),
    "country": ("/api/v1/mkt/country/{iso2}", "One country's macro snapshot (growth, inflation, policy rate, yields, FX).",
                {"iso2": {"type": "string", "description": "ISO 3166 alpha-2 code, e.g. GB, US, JP"}}, ["iso2"], False),
    "world_model": ("/api/v1/model/world", "The multi-economy macro model: regimes and views across economies.", {}, [], False),
    "data_health": ("/api/v1/ops/monitor", "Data-feed status, open data incidents and the last accuracy audit — check before relying on figures.", {}, [], False),
    "signal_health": ("/api/v1/quant/decay", "Stock-signal decay monitor: which signals are holding up, fading or gone (needs MACRO_API_TOKEN).", {}, [], True),
    "strategy_evidence": ("/api/v1/quant/proof", "Strategy evidence: out-of-sample results and crisis behaviour (needs MACRO_API_TOKEN).", {}, [], True),
    "ml_signals": ("/api/v1/ml/tasks", "Machine-learning signals for every forecast task (recession, 10% S&P fall, yields, inflation, oil, "
                   "unemployment): the served probability, its out-of-sample skill, the neural network's reading and data checks "
                   "(needs MACRO_API_TOKEN).", {}, [], True),
    "ml_task": ("/api/v1/ml/tasks/{task}", "One ML task in full: champion and network forecasts, what moved them, walk-forward record by "
                "era, live record and promotion status (needs MACRO_API_TOKEN).",
                {"task": {"type": "string", "description": "recession_12m, spx_drawdown_6m, yields_up_3m, inflation_up_3m, oil_up_3m or unemployment_up_6m"}},
                ["task"], True),
}
ARG_RE = {"symbol": re.compile(r"^[A-Za-z0-9.\-=^]{1,15}$"), "iso2": re.compile(r"^[A-Za-z]{2}$"),
          "task": re.compile(r"^[a-z0-9_]{3,40}$")}


def _fetch(path: str) -> Dict[str, Any]:
    url = BASE + path
    req = urllib.request.Request(url, method="GET", headers={"Accept": "application/json"})
    if TOKEN:
        req.add_header("Authorization", f"Bearer {TOKEN}")
    fetched = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        hint = " (sign-in needed: set MACRO_API_TOKEN)" if e.code == 401 else ""
        return {"source": url, "fetched_at": fetched, "error": f"HTTP {e.code}{hint}"}
    except Exception as e:                                                       # noqa: BLE001
        return {"source": url, "fetched_at": fetched, "error": f"backend unreachable: {e}"}
    return {"source": url, "fetched_at": fetched, "data": data}


def call_tool(name: str, args: Dict[str, Any]) -> Tuple[str, bool]:
    if name not in TOOLS:
        return f"Unknown tool {name!r}.", True
    path, _, props, required, _ = TOOLS[name]
    for k in required:
        v = str(args.get(k) or "")
        if not ARG_RE[k].match(v):
            return f"Invalid {k}: {v!r}", True
        path = path.replace("{" + k + "}", urllib.parse.quote(v if k in ("symbol", "task") else v.upper(), safe=".=^-_"))
    out = _fetch(path)
    text = json.dumps(out, default=str, ensure_ascii=False)
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS] + f'… [truncated at {MAX_CHARS} characters; source {out["source"]}]'
    return text, "error" in out


def _tool_list() -> List[Dict[str, Any]]:
    return [{"name": n, "description": d + " Read-only.",
             "inputSchema": {"type": "object", "properties": p, "required": r, "additionalProperties": False},
             "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False}}
            for n, (_, d, p, r, _) in TOOLS.items()]


def handle(msg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    mid, method, params = msg.get("id"), msg.get("method"), msg.get("params") or {}
    if mid is None:                                                              # notification: no reply
        return None
    if method == "initialize":
        result: Any = {"protocolVersion": params.get("protocolVersion") or PROTOCOL,
                       "capabilities": {"tools": {"listChanged": False}},
                       "serverInfo": {"name": "macro-terminal-research", "version": "1.0.0"},
                       "instructions": INSTRUCTIONS}
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": _tool_list()}
    elif method == "tools/call":
        text, err = call_tool(params.get("name", ""), params.get("arguments") or {})
        result = {"content": [{"type": "text", "text": text}], "isError": err}
    else:
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"Method not found: {method}"}}
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            reply: Optional[Dict[str, Any]] = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
        else:
            reply = handle(msg)
        if reply is not None:
            sys.stdout.write(json.dumps(reply) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
