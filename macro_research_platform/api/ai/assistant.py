"""
Markets AI assistant — a research analyst that answers ONLY from the terminal's data.

The model never sees the internet directly: it calls tools that hit the same functions as
the Markets and Research screens (quotes, profiles, SEC financials, earnings, analysts,
holders, news, DCF, peers, movers, the screener, the macro regime) and must cite what it
used. Free by default:

  provider "ollama"  local models via Ollama (no key, nothing leaves the machine) — default
                     when an Ollama server is reachable
  provider "groq"    Groq's free tier (GROQ_API_KEY), OpenAI-compatible
  provider "openai"  any OpenAI-compatible endpoint (AI_BASE_URL + AI_API_KEY)

Settings: AI_PROVIDER, AI_MODEL, OLLAMA_URL (default http://localhost:11434).
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)
MAX_ROUNDS = 6
MAX_TOOL_CHARS = 3500
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
PREFERRED_LOCAL = ["llama3.2:latest", "qwen3.5:latest", "qwen3-coder:30b", "llama3.1:8b", "qwen2.5:7b"]

SYSTEM = """You are the research assistant inside a professional market terminal.
Rules:
- Use the tools for EVERY number, date or fact about a company, market or the economy. Never rely on memory for data.
- If a tool returns an error or nothing, say the data is unavailable — never guess or invent numbers.
- Be concise and structured: short paragraphs or bullets, key numbers in **bold**, units and currencies stated.
- Say how current the data is (dates) and name the source (e.g. "SEC 10-Q", "Yahoo Finance", "FRED").
- Distinguish facts from interpretation. Give balanced views (bull and bear points) when asked for opinions.
- You give general research, not personalised investment advice; don't tell the user to buy or sell.
- Today is {today}. The user is currently looking at: {context}."""


# ── Tools ────────────────────────────────────────────────────────────────────
def _compact(obj: Any, limit: int = MAX_TOOL_CHARS) -> str:
    s = json.dumps(obj, default=str, separators=(",", ":"))
    return s if len(s) <= limit else s[:limit] + '…"(truncated)"'


def _t_search(query: str) -> Any:
    from api.marketdata import core
    return core.search(query, 8)


def _t_quote(symbol: str) -> Any:
    from api.marketdata import core
    q = core.quote(symbol)
    return {k: q[k] for k in ("symbol", "name", "type", "exchange", "currency", "price", "change_pct", "day_low", "day_high",
                              "week52_low", "week52_high", "volume", "market_cap", "market_state")}


def _t_profile(symbol: str) -> Any:
    from api.marketdata import core
    p = core.profile(symbol)
    if p.get("description"):
        p["description"] = p["description"][:700]
    return p


def _t_financials(symbol: str) -> Any:
    from api.marketdata import core
    st = core.statements(symbol)
    if st.get("provider") == "sec":
        return {"name": st["name"], "source": "SEC EDGAR (as filed)", "ttm": st["ttm"], "ratios": st["ratios"],
                "annual": st["annual"][-4:], "currency": "USD"}
    return {"source": st.get("source"), "currency": st.get("currency"),
            "income": {r["item"]: r["values"][:3] for r in st["tables"].get("income", {}).get("rows", [])[:14]},
            "periods": st["tables"].get("income", {}).get("periods", [])[:3]}


def _t_earnings(symbol: str) -> Any:
    from api.marketdata import security
    e = security.earnings(symbol)
    return {"history": e["history"][:6], "upcoming": e["upcoming"], "beat_rate": e["beat_rate"], "avg_surprise_pct": e["avg_surprise_pct"],
            "eps_estimates": e["estimates"].get("eps"), "revenue_estimates": e["estimates"].get("revenue"), "currency": e["currency"]}


def _t_analysts(symbol: str) -> Any:
    from api.marketdata import security
    a = security.analysts(symbol)
    return {"targets": a["targets"], "recommendation": a["recommendation"], "analysts": a["analysts"],
            "rating_mix_now": a["summary"][:1], "recent_changes": a["changes"][:8]}


def _t_holders(symbol: str) -> Any:
    from api.marketdata import security
    h = security.holders(symbol)
    return {"breakdown": h["breakdown"], "top_institutions": h["institutions"][:5], "recent_insiders": h["insiders"][:8]}


def _t_news(symbol: Optional[str] = None, query: Optional[str] = None) -> Any:
    if symbol:
        from api.marketdata import core
        n = core.news(symbol)
        return {"headlines": [{k: x.get(k) for k in ("title", "publisher", "time")} for x in n["news"][:10]],
                "sec_filings": n["filings"][:6]}
    from api.marketdata import monitors
    h = monitors.news_hub(query, 15)
    return [{k: x.get(k) for k in ("title", "source", "time", "sentiment")} for x in h["items"]]


def _t_dcf(symbol: str, growth: Optional[float] = None, terminal_growth: Optional[float] = None) -> Any:
    from api.marketdata import dcf
    inp = dcf.inputs(symbol)
    v = dcf.value(inp, growth=growth, terminal_growth=terminal_growth)
    return {"value_per_share": v["per_share"], "price": v["price"], "upside": v["upside"], "currency": inp["currency"],
            "market_implied_growth": dcf.reverse(inp, terminal_growth=terminal_growth), "wacc": v["wacc"]["wacc"],
            "assumptions": v["assumptions"], "terminal_share": v["terminal_share"], "checks": v["checks"],
            "method": "FCFF at WACC, value-driver terminal value"}


def _t_peers(symbol: str) -> Any:
    from api.marketdata import security
    r = security.comps(symbol)
    keep = ("symbol", "name", "country", "market_cap_usd", "pe", "forward_pe", "ev_ebitda", "operating_margin", "revenue_growth")
    subj = next((x for x in r["rows"] if x.get("subject")), {})
    med = r["peer_median"] or {}
    # Spell out the comparison so the model doesn't have to do arithmetic.
    vs = {}
    for k, label, cheap_is_low in (("pe", "trailing P/E", True), ("forward_pe", "forward P/E", True), ("ev_ebitda", "EV/EBITDA", True),
                                   ("operating_margin", "operating margin", False), ("revenue_growth", "revenue growth", False)):
        a, b = subj.get(k), med.get(k)
        if a is not None and b:
            rel = a / b - 1
            word = "below" if a < b else "above"
            meaning = ("cheaper than peers" if a < b else "more expensive than peers") if cheap_is_low else ("weaker than peers" if a < b else "stronger than peers")
            vs[label] = f"{a:.3g} vs peer median {b:.3g}: {abs(rel):.0%} {word} ({meaning})"
    return {"industry": r["industry"], "subject": subj.get("symbol"), "comparison": vs,
            "rows": [{k: x.get(k) for k in keep} for x in r["rows"][:10]], "peer_median": med}


def _t_movers(region: str = "us", kind: str = "gainers") -> Any:
    from api.marketdata import core
    m = core.movers(region, kind, 10)
    return [{k: x.get(k) for k in ("symbol", "name", "price", "change_pct", "market_cap")} for x in m["rows"]]


def _t_screen(region: str = "us", sector: Optional[str] = None, min_market_cap_bn: Optional[float] = None,
              max_pe: Optional[float] = None, min_dividend_yield_pct: Optional[float] = None) -> Any:
    from api.marketdata import core
    r = core.screen([region], sector, "market_cap", False, 15, 0,
                    market_cap_min=min_market_cap_bn * 1e9 if min_market_cap_bn else None, pe_max=max_pe,
                    dividend_yield_min=min_dividend_yield_pct)
    return {"total": r["total"], "rows": [{k: x.get(k) for k in ("symbol", "name", "market_cap", "pe", "dividend_yield", "currency")} for x in r["rows"]]}


def _t_markets() -> Any:
    from api.marketdata import core
    o = core.overview()
    return {g["group"]: [{k: r.get(k) for k in ("name", "price", "change_1d", "change_ytd", "change_1d_bp")} for r in g["rows"]] for g in o["groups"]}


def _t_macro() -> Any:
    """The Research mode's current macro view, from the latest dashboard snapshot."""
    from pathlib import Path
    p = Path(__file__).resolve().parents[2] / "data" / "processed" / "live" / "dashboard_live.json"
    try:
        snap = json.loads(p.read_text())
    except Exception:
        return {"error": "Macro dashboard snapshot unavailable."}
    d = snap.get("data") or {}
    km = d.get("keyMetrics") or {}
    return {"as_of": datetime.fromtimestamp(snap.get("ts", 0), timezone.utc).isoformat(timespec="minutes"),
            "regime": {k: (d.get("regime") or {}).get(k) for k in ("current", "confidence", "duration")},
            "key_metrics": {k: (v.get("value") if isinstance(v, dict) else v) for k, v in km.items()} if isinstance(km, dict) else km,
            "recession": d.get("recession"), "signals": d.get("signals"),
            "sector_tilts": [{k: s.get(k) for k in ("name", "signal", "score")} for s in (d.get("sectorAllocation") or {}).get("sectors", [])][:11]}


TOOLS: Dict[str, Tuple[Callable, str, Dict[str, Any]]] = {
    "search_instrument": (_t_search, "Find tickers by company or instrument name (any exchange, FX, futures, crypto).",
                          {"query": {"type": "string", "description": "Company or instrument name"}}),
    "get_quote": (_t_quote, "Latest price, change, ranges, volume and market cap.", {"symbol": {"type": "string"}}),
    "get_profile": (_t_profile, "Business description, sector, valuation multiples and analyst target summary.", {"symbol": {"type": "string"}}),
    "get_financials": (_t_financials, "Financial statements: TTM figures and ratios (SEC filings for US companies).", {"symbol": {"type": "string"}}),
    "get_earnings": (_t_earnings, "Reported vs estimated EPS history, next report date, consensus estimates.", {"symbol": {"type": "string"}}),
    "get_analyst_ratings": (_t_analysts, "Analyst price targets, rating mix and recent rating changes.", {"symbol": {"type": "string"}}),
    "get_holders": (_t_holders, "Institutional ownership and insider transactions.", {"symbol": {"type": "string"}}),
    "get_news": (_t_news, "Company headlines and SEC filings (with symbol), or market headlines (with query).",
                 {"symbol": {"type": "string"}, "query": {"type": "string"}}),
    "run_dcf": (_t_dcf, "Discounted cash flow valuation and the growth the current price implies.",
                {"symbol": {"type": "string"}, "growth": {"type": "number", "description": "year-1 revenue growth, decimal"},
                 "terminal_growth": {"type": "number", "description": "decimal"}}),
    "get_peers": (_t_peers, "Same-industry companies worldwide with valuation multiples and margins.", {"symbol": {"type": "string"}}),
    "get_movers": (_t_movers, "Today's top gainers, losers or most active stocks in a market.",
                   {"region": {"type": "string", "description": "us, jp, gb, de, fr, cn, hk, in, ca, au, kr, tw …"},
                    "kind": {"type": "string", "enum": ["gainers", "losers", "active"]}}),
    "screen_stocks": (_t_screen, "Screen a market's stocks by sector, size, P/E and dividend yield.",
                      {"region": {"type": "string"}, "sector": {"type": "string"}, "min_market_cap_bn": {"type": "number"},
                       "max_pe": {"type": "number"}, "min_dividend_yield_pct": {"type": "number"}}),
    "get_market_overview": (_t_markets, "World indices, rates, currencies, commodities and crypto today.", {}),
    "get_macro_view": (_t_macro, "The terminal's macro model: regime, growth/inflation/liquidity/risk scores, recession odds, sector tilts.", {}),
}
REQUIRED = {"get_quote": ["symbol"], "get_profile": ["symbol"], "get_financials": ["symbol"], "get_earnings": ["symbol"],
            "get_analyst_ratings": ["symbol"], "get_holders": ["symbol"], "run_dcf": ["symbol"], "get_peers": ["symbol"],
            "search_instrument": ["query"]}


def tool_specs() -> List[Dict[str, Any]]:
    return [{"type": "function", "function": {"name": n, "description": d,
                                              "parameters": {"type": "object", "properties": p, "required": REQUIRED.get(n, [])}}}
            for n, (_, d, p) in TOOLS.items()]


def run_tool(name: str, args: Dict[str, Any]) -> Tuple[bool, str]:
    if name not in TOOLS:
        return False, json.dumps({"error": f"Unknown tool {name}"})
    fn = TOOLS[name][0]
    allowed = set(TOOLS[name][2])
    clean = {k: v for k, v in (args or {}).items() if k in allowed and v not in (None, "")}
    try:
        return True, _compact(fn(**clean))
    except Exception as e:
        return False, json.dumps({"error": str(e)[:300]})


# ── Providers ────────────────────────────────────────────────────────────────
def _ollama_models() -> List[str]:
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=2)
        return [m["name"] for m in r.json().get("models", []) if not m["name"].endswith("-cloud")]
    except Exception:
        return []


def config() -> Dict[str, Any]:
    prov = (os.getenv("AI_PROVIDER") or "").lower()
    groq_key = os.getenv("GROQ_API_KEY") or ""
    local = _ollama_models()
    if not prov:
        prov = "ollama" if local else ("groq" if groq_key else "none")
    if prov == "ollama":
        model = os.getenv("AI_MODEL") or next((m for m in PREFERRED_LOCAL if m in local), local[0] if local else None)
        return {"provider": "ollama", "base_url": f"{OLLAMA_URL}/v1", "key": "ollama", "model": model, "available": bool(local and model),
                "models": local, "note": "Runs locally with Ollama — free, nothing leaves your computer."
                if local else "Ollama is not running — open the Ollama app (or run `ollama serve`)."}
    if prov == "groq":
        return {"provider": "groq", "base_url": "https://api.groq.com/openai/v1", "key": groq_key,
                "model": os.getenv("AI_MODEL") or "llama-3.3-70b-versatile", "available": bool(groq_key), "models": [],
                "note": "Groq free tier." if groq_key else "Set GROQ_API_KEY (free at console.groq.com)."}
    if prov == "openai":
        base = os.getenv("AI_BASE_URL") or "https://api.openai.com/v1"
        key = os.getenv("AI_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
        return {"provider": "openai", "base_url": base, "key": key, "model": os.getenv("AI_MODEL") or "gpt-4o-mini",
                "available": bool(key), "models": [], "note": f"OpenAI-compatible endpoint {base}."}
    return {"provider": "none", "available": False, "models": local,
            "note": "No AI model configured. Free options: install and open Ollama (local), or set GROQ_API_KEY."}


def _complete(cfg: Dict[str, Any], messages: List[Dict[str, Any]], model: str) -> Dict[str, Any]:
    body: Dict[str, Any] = {"model": model, "messages": messages, "tools": tool_specs(), "temperature": 0.2, "stream": False}
    if cfg["provider"] == "ollama":
        body["reasoning_effort"] = "none"        # qwen3.x: skip slow 'thinking' (ignored by models without it)
    r = requests.post(f"{cfg['base_url']}/chat/completions", json=body,
                      headers={"Authorization": f"Bearer {cfg['key']}", "Content-Type": "application/json"}, timeout=240)
    if r.status_code >= 400:
        raise RuntimeError(f"{cfg['provider']} error {r.status_code}: {r.text[:300]}")
    return r.json()["choices"][0]["message"]


def chat(history: List[Dict[str, str]], context: Optional[str] = None, model: Optional[str] = None) -> Dict[str, Any]:
    cfg = config()
    if not cfg["available"]:
        raise RuntimeError(cfg["note"])
    use_model = model if model and (cfg["provider"] != "ollama" or model in cfg["models"]) else cfg["model"]
    t0 = time.time()
    msgs: List[Dict[str, Any]] = [{"role": "system", "content": SYSTEM.format(today=datetime.now().strftime("%Y-%m-%d"),
                                                                           context=context or "the Markets home screen")}]
    for m in history[-12:]:
        if m.get("role") in ("user", "assistant") and isinstance(m.get("content"), str):
            msgs.append({"role": m["role"], "content": m["content"][:4000]})
    calls: List[Dict[str, Any]] = []
    seen: Dict[Tuple[str, str], Tuple[bool, str]] = {}
    for _ in range(MAX_ROUNDS):
        reply = _complete(cfg, msgs, use_model)
        tcs = reply.get("tool_calls") or []
        if not tcs:
            return {"reply": (reply.get("content") or "").strip() or "I couldn't produce an answer — try rephrasing.",
                    "tool_calls": calls, "provider": cfg["provider"], "model": use_model, "seconds": round(time.time() - t0, 1)}
        msgs.append({"role": "assistant", "content": reply.get("content") or "", "tool_calls": tcs})
        for tc in tcs[:4]:
            fn = tc.get("function") or {}
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except Exception:
                args = {}
            key = (fn.get("name"), json.dumps(args, sort_keys=True))
            if key in seen:                                   # same call twice: reuse the result
                ok, out = seen[key]
            else:
                ok, out = run_tool(fn.get("name", ""), args)
                seen[key] = (ok, out)
                calls.append({"name": fn.get("name"), "args": args, "ok": ok})
            msgs.append({"role": "tool", "tool_call_id": tc.get("id") or fn.get("name"), "name": fn.get("name"), "content": out})
    # Out of rounds: ask for a final answer without tools.
    msgs.append({"role": "user", "content": "Answer now using the data gathered above."})
    body = {"model": use_model, "messages": msgs, "temperature": 0.2, "stream": False}
    r = requests.post(f"{cfg['base_url']}/chat/completions", json=body, headers={"Authorization": f"Bearer {cfg['key']}"}, timeout=240)
    content = r.json()["choices"][0]["message"].get("content", "") if r.ok else ""
    return {"reply": content.strip() or "I gathered data but couldn't finish the answer.", "tool_calls": calls,
            "provider": cfg["provider"], "model": use_model, "seconds": round(time.time() - t0, 1)}
