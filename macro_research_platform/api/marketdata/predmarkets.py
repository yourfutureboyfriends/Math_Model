"""
Prediction markets — Kalshi (CFTC-regulated exchange) and Polymarket — read-only market data:

  catalog()                 every open event on both venues (top by activity), normalised: outcomes
                            with probability, bid/ask, 24h change, volume, liquidity, close date
  history(venue, id)        probability history for one outcome (Polymarket CLOB / Kalshi candles)
  orderbook(venue, id)      the live order book for one outcome
  movers()                  biggest 24-hour moves with real volume
  cross_venue()             the same question on both venues, side by side, with the price gap
  macro()                   Fed, inflation, recession, growth and markets questions, plus the Fed
                            decision as priced by each venue vs fed funds futures

Prices are probabilities (0–1). Kalshi volume is in contracts (each pays $1), Polymarket's in USDC.
No trading: data only.
"""
from __future__ import annotations

import json
import math
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from api.marketdata.core import NotFound, Upstream, _cached

logger = logging.getLogger(__name__)
UA = {"User-Agent": "Mozilla/5.0 (macro research terminal)"}
GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"
KALSHI = "https://api.elections.kalshi.com/trade-api/v2"


def _get(url: str, **kw):
    import requests
    r = requests.get(url, headers=UA, timeout=kw.pop("timeout", 30), **kw)
    if r.status_code == 429:
        raise Upstream("The prediction-market API is rate-limiting — try again in a minute.")
    r.raise_for_status()
    return r.json()


def _f(x) -> Optional[float]:
    try:
        v = float(x)
        return v if v == v else None
    except (TypeError, ValueError):
        return None


# ── Categories ──────────────────────────────────────────────────────────────
CATS = [("Fed & rates", r"\bfed\b|fomc|rate (cut|hike)|interest rate|powell|treasury yield|10-year|basis points|bps"),
        ("Inflation", r"\bcpi\b|inflation|\bpce\b|prices? index"),
        ("Economy", r"recession|\bgdp\b|unemployment|payroll|jobs report|jobless|economy|retail sales|tariff|trade deal|debt ceiling|shutdown"),
        ("Markets", r"s&p|nasdaq|\bdow\b|stock|ipo|oil|gold|brent|wti|dollar|euro|yen|treasur|earnings|market cap|largest company"),
        ("Crypto", r"bitcoin|\bbtc\b|ethereum|\beth\b|solana|crypto|xrp|dogecoin|stablecoin"),
        ("Geopolitics", r"war|ceasefire|iran|israel|russia|ukraine|china|taiwan|nato|airstrikes?|strikes? on|invade|military|hormuz|sanction|missile|nuclear|gaza|houthi"),
        ("Politics", r"election|president|senate|house|congress|trump|governor|mayor|prime minister|parliament|vote|nominee|approval|cabinet|supreme court"),
        ("Tech & AI", r"\bai\b|openai|gpt|apple|google|nvidia|tesla|spacex|launch|model|chatgpt|anthropic|meta|microsoft"),
        ("Climate & weather", r"temperature|hurricane|weather|climate|snow|rain|heat"),
        ("Sports", r" vs\.? |nfl|nba|mlb|nhl|premier league|champions league|world cup|grand prix|f1|ufc|tennis|open|super bowl|playoffs|match|game \d|series"),
        ("Culture", r"movie|box office|album|grammy|oscar|emmy|song|spotify|youtube|tiktok|celebrity|taylor swift|netflix")]
SPORT_TAGS = {"sports", "esports", "soccer", "football", "nfl", "nba", "mlb", "nhl", "tennis", "golf", "f1", "ufc", "cricket", "games", "basketball", "baseball", "hockey", "mma", "boxing", "chess"}
KALSHI_CAT = {"Economics": "Economy", "Financials": "Markets", "Politics": "Politics", "Elections": "Politics", "Sports": "Sports",
              "Science and Technology": "Tech & AI", "Climate and Weather": "Climate & weather", "Entertainment": "Culture", "World": "Geopolitics",
              "Crypto": "Crypto", "Companies": "Markets", "Health": "Other", "Social": "Culture", "Transportation": "Other"}


def _category(title: str, tags: List[str], kalshi_cat: Optional[str] = None) -> str:
    text = f"{title} {' '.join(tags)}".lower()
    if {t.lower() for t in tags} & SPORT_TAGS or kalshi_cat == "Sports" or re.search(r"\bvs\.? .*(winner|o/u|spread|exact score|more markets)|counter-strike|dota|esports|valorant|league of legends", text):
        return "Sports"
    for name, rx in CATS[:6]:                 # specific macro / markets topics win over a venue's broad bucket
        if re.search(rx, text):
            return name
    if kalshi_cat and KALSHI_CAT.get(kalshi_cat):
        return KALSHI_CAT[kalshi_cat]
    for name, rx in CATS[6:]:
        if re.search(rx, text):
            return name
    return "Other"


def _quality(bid, ask, vol24, price) -> Dict[str, Any]:
    """How much to trust a price: the spread, and whether anyone actually trades it. A wide or empty book with no
    volume means the 'probability' is just a stale quote."""
    spread = round(ask - bid, 4) if bid is not None and ask is not None and ask >= bid else None
    thin = spread is None or spread > 0.10 or vol24 < 100
    return {"spread": spread, "thin": thin}


# ── Polymarket ──────────────────────────────────────────────────────────────
def _poly_market(m: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if m.get("closed") or not m.get("active", True):
        return None
    try:
        outs = json.loads(m.get("outcomes") or "[]")
        prices = [float(x) for x in json.loads(m.get("outcomePrices") or "[]")]
        tokens = json.loads(m.get("clobTokenIds") or "[]")
    except Exception:
        return None
    if not outs or len(outs) != len(prices):
        return None
    binary = [o.lower() for o in outs] == ["yes", "no"]
    label = (m.get("groupItemTitle") or m.get("question") or "").strip() if binary else " vs ".join(outs)
    return {"id": tokens[0] if tokens else m.get("id"), "label": label, "question": m.get("question"), "yes": prices[0],
            "outcomes": [{"name": o, "price": p, "token": tokens[i] if i < len(tokens) else None} for i, (o, p) in enumerate(zip(outs, prices))],
            "binary": binary, "bid": _f(m.get("bestBid")), "ask": _f(m.get("bestAsk")), "last": _f(m.get("lastTradePrice")),
            "chg_1d": _f(m.get("oneDayPriceChange")), "chg_1w": _f(m.get("oneWeekPriceChange")), "volume_24h": _f(m.get("volume24hr")) or 0,
            "volume": _f(m.get("volume")) or 0, "liquidity": _f(m.get("liquidity")) or 0, "end": (m.get("endDate") or "")[:10] or None,
            "rules": m.get("description"), **_quality(_f(m.get("bestBid")), _f(m.get("bestAsk")), _f(m.get("volume24hr")) or 0, prices[0])}


def _poly_events(pages: int = 8) -> List[Dict[str, Any]]:
    def page(k: int):
        try:
            return _get(f"{GAMMA}/events", params={"closed": "false", "active": "true", "limit": 100, "offset": k * 100,
                                                   "order": "volume24hr", "ascending": "false"})
        except Exception as e:
            logger.info("[pred] polymarket page %s: %s", k, e)
            return []
    with ThreadPoolExecutor(4) as ex:
        raw = [e for p in ex.map(page, range(pages)) for e in (p or [])]
    out, seen = [], set()
    for e in raw:
        if e.get("id") in seen:
            continue
        seen.add(e.get("id"))
        mk = [x for x in (_poly_market(m) for m in e.get("markets") or []) if x]
        if not mk:
            continue
        mk.sort(key=lambda m: -(m["yes"] if m["binary"] else m["volume_24h"]))
        tags = [t.get("label", "") for t in e.get("tags") or [] if isinstance(t, dict)]
        out.append({"venue": "Polymarket", "id": str(e.get("id")), "slug": e.get("slug"), "title": e.get("title"),
                    "category": _category(e.get("title") or "", tags), "tags": tags[:6],
                    "volume_24h": _f(e.get("volume24hr")) or 0, "volume": _f(e.get("volume")) or 0, "liquidity": _f(e.get("liquidity")) or 0,
                    "open_interest": _f(e.get("openInterest")), "end": (e.get("endDate") or "")[:10] or None,
                    "description": e.get("description"), "markets": mk})
    return out


# ── Kalshi ──────────────────────────────────────────────────────────────────
def _kalshi_market(m: Dict[str, Any], series: str) -> Optional[Dict[str, Any]]:
    if m.get("status") not in (None, "active", "open"):
        return None
    last, prev = _f(m.get("last_price_dollars")), _f(m.get("previous_price_dollars"))
    bid, ask = _f(m.get("yes_bid_dollars")), _f(m.get("yes_ask_dollars"))
    if bid is not None and ask and ask - bid <= 0.06:
        yes = round((bid + ask) / 2, 4)            # a tight quote is more current than the last trade
    else:
        yes = last if last else ((bid + ask) / 2 if bid is not None and ask else bid)
    if yes is None:
        return None
    return {"id": m.get("ticker"), "series": series, "label": (m.get("yes_sub_title") or m.get("subtitle") or m.get("title") or "").strip(),
            "question": m.get("title"), "yes": yes, "outcomes": [{"name": "Yes", "price": yes}, {"name": "No", "price": round(1 - yes, 4)}],
            "binary": True, "bid": bid, "ask": ask, "last": last, "chg_1d": (yes - prev) if prev is not None and last else None, "chg_1w": None,
            "volume_24h": _f(m.get("volume_24h_fp")) or 0, "volume": _f(m.get("volume_fp")) or 0,
            "liquidity": _f(m.get("liquidity_dollars")) or 0, "open_interest": _f(m.get("open_interest_fp")),
            "end": (m.get("close_time") or "")[:10] or None, "rules": m.get("rules_primary"), **_quality(bid, ask, _f(m.get("volume_24h_fp")) or 0, yes)}


# Macro / markets series pulled directly — the general listing is dominated by politics and runs past
# the pages we fetch, so these would otherwise be missed.
KALSHI_SERIES = ["KXFED", "KXFEDDECISION", "KXRATECUTCOUNT", "KXCPI", "KXCPIYOY", "KXCPICORE", "KXPCE", "KXGDP", "KXPAYROLLS", "KXU3",
                 "KXRECSSNBER", "KXJOBLESS", "KXINX", "KXINXY", "KXNASDAQ100", "KXNASDAQ100Y", "KXWTI", "KXWTIMAX", "KXGOLD", "KXBTC",
                 "KXBTCMAXY", "KXETH", "KXEURUSD", "KXUSDJPY", "KXTNOTE", "KXGASPRICE", "KXMORTGAGE", "KXSHUTDOWN", "KXDEBTCEILING",
                 "KXTARIFF", "KXECBRATE", "KXBOERATE", "KXBOJRATE"]


def _kalshi_events(pages: int = 10) -> List[Dict[str, Any]]:
    out, cursor = [], None
    raw: List[Dict[str, Any]] = []

    def series(t):
        try:
            return _get(f"{KALSHI}/events", params={"series_ticker": t, "status": "open", "with_nested_markets": "true", "limit": 50}).get("events") or []
        except Exception:
            return []
    with ThreadPoolExecutor(6) as ex:
        for evs in ex.map(series, KALSHI_SERIES):
            raw.extend(evs)
    for _ in range(pages):
        params = {"status": "open", "limit": 200, "with_nested_markets": "true"}
        if cursor:
            params["cursor"] = cursor
        try:
            j = _get(f"{KALSHI}/events", params=params)
        except Exception as e:
            logger.info("[pred] kalshi page: %s", e)
            break
        raw.extend(j.get("events") or [])
        cursor = j.get("cursor")
        if not cursor:
            break
    seen = set()
    for e in raw:
        if e.get("event_ticker") in seen:
            continue
        seen.add(e.get("event_ticker"))
        st = e.get("series_ticker") or ""
        mk = [x for x in (_kalshi_market(m, st) for m in e.get("markets") or []) if x]
        if not mk:
            continue
        mk.sort(key=lambda m: -m["yes"])
        v24 = sum(m["volume_24h"] for m in mk)
        out.append({"venue": "Kalshi", "id": e.get("event_ticker"), "series": st, "title": e.get("title"),
                    "subtitle": e.get("sub_title"), "category": _category(e.get("title") or "", [e.get("category") or ""], e.get("category")),
                    "tags": [e.get("category")] if e.get("category") else [], "volume_24h": v24, "volume": sum(m["volume"] for m in mk),
                    "liquidity": sum(m["liquidity"] for m in mk), "open_interest": sum(m.get("open_interest") or 0 for m in mk),
                    "end": min((m["end"] for m in mk if m["end"]), default=None), "description": mk[0].get("rules"), "markets": mk})
    return out


# ── Catalog ─────────────────────────────────────────────────────────────────
def catalog() -> Dict[str, Any]:
    return _cached("pred:catalog", 300, _build_catalog)


_refresher_started = False


def refresher_start(every: float = 240.0) -> None:
    """Rebuild the catalog in the background before it expires, so PRED and the odds panels around
    the terminal never wait ~15 s for both venues on a cold cache."""
    global _refresher_started
    if _refresher_started:
        return
    _refresher_started = True
    import threading

    def loop():
        from api.marketdata import core
        while True:
            try:
                val = _build_catalog()
                with core._lock:
                    core._cache["pred:catalog"] = (time.time(), val)
                for k in [k for k in list(core._cache) if k.startswith(("pred:cross", "pred:macro", "pred:movers"))]:
                    core._cache.pop(k, None)
                cross_venue()
                macro()
            except Exception as e:
                logger.info("[pred] background refresh: %s", e)
            time.sleep(every)
    threading.Thread(target=loop, name="pred-refresh", daemon=True).start()


def _build_catalog() -> Dict[str, Any]:
    with ThreadPoolExecutor(2) as ex:
        fp, fk = ex.submit(_poly_events), ex.submit(_kalshi_events)
        poly, kal = fp.result(), fk.result()
    if not poly and not kal:
        raise Upstream("Neither Polymarket nor Kalshi answered.")
    events = poly + kal
    events.sort(key=lambda e: -(e["volume_24h"] or 0))
    cats: Dict[str, int] = {}
    for e in events:
        cats[e["category"]] = cats.get(e["category"], 0) + 1
    return {"events": events, "categories": sorted(cats.items(), key=lambda kv: -kv[1]),
            "venues": {"Polymarket": {"events": len(poly), "markets": sum(len(e["markets"]) for e in poly), "volume_24h": sum(e["volume_24h"] for e in poly)},
                       "Kalshi": {"events": len(kal), "markets": sum(len(e["markets"]) for e in kal), "volume_24h": sum(e["volume_24h"] for e in kal)}},
            "as_of": datetime.now(timezone.utc).isoformat(timespec="minutes"),
            "source": "Polymarket (gamma / CLOB APIs) and Kalshi (public trade API)",
            "note": "Prices are probabilities. Polymarket volume in USDC; Kalshi volume in contracts (each settles at $1). "
                    "Read-only market data — no trading."}


# ── One outcome: history and order book ─────────────────────────────────────
def history(venue: str, market_id: str, series: Optional[str] = None, span: str = "1m") -> Dict[str, Any]:
    def build():
        if venue.lower().startswith("poly"):
            interval = {"1d": "1d", "1w": "1w", "1m": "1m", "max": "max"}.get(span, "1m")
            fid = {"1d": 5, "1w": 60, "1m": 240, "max": 1440}.get(span, 240)
            j = _get(f"{CLOB}/prices-history", params={"market": market_id, "interval": interval, "fidelity": fid})
            pts = [{"t": int(p["t"]), "p": float(p["p"])} for p in j.get("history") or []]
        else:
            if not series:
                series_t = market_id.split("-")[0]
            else:
                series_t = series
            now = int(time.time())
            days = {"1d": 1, "1w": 7, "1m": 31, "max": 365}.get(span, 31)
            period = 60 if days <= 7 else 1440 if days > 31 else 60
            j = _get(f"{KALSHI}/series/{series_t}/markets/{market_id}/candlesticks",
                     params={"start_ts": now - days * 86400, "end_ts": now, "period_interval": period})
            pts = []
            for c in j.get("candlesticks") or []:
                pr = (c.get("price") or {})
                p = _f(pr.get("close_dollars")) or _f(pr.get("previous_dollars"))
                if p is None:
                    b, a = _f((c.get("yes_bid") or {}).get("close_dollars")), _f((c.get("yes_ask") or {}).get("close_dollars"))
                    p = (b + a) / 2 if b is not None and a is not None else None
                if p is not None:
                    pts.append({"t": int(c["end_period_ts"]), "p": p})
        if not pts:
            raise NotFound("No price history for this outcome yet.")
        rows = [{"date": datetime.fromtimestamp(p["t"], tz=timezone.utc).strftime("%Y-%m-%d %H:%M"), "p": round(p["p"] * 100, 2)} for p in pts]
        return {"venue": venue, "id": market_id, "span": span, "rows": rows}
    return _cached(f"pred:hist:{venue}:{market_id}:{span}", 300, build)


def orderbook(venue: str, market_id: str) -> Dict[str, Any]:
    def build():
        if venue.lower().startswith("poly"):
            j = _get(f"{CLOB}/book", params={"token_id": market_id})
            bids = sorted(((float(x["price"]), float(x["size"])) for x in j.get("bids") or []), reverse=True)
            asks = sorted((float(x["price"]), float(x["size"])) for x in j.get("asks") or [])
        else:
            j = _get(f"{KALSHI}/markets/{market_id}/orderbook")
            ob = j.get("orderbook_fp") or j.get("orderbook") or {}
            yes = [(float(p), float(s)) for p, s in ob.get("yes_dollars") or []]
            no = [(float(p), float(s)) for p, s in ob.get("no_dollars") or []]
            bids = sorted(yes, reverse=True)
            asks = sorted((round(1 - p, 4), s) for p, s in no)           # a NO bid at p is a YES offer at 1 − p
        return {"venue": venue, "id": market_id, "bids": [{"price": p, "size": s} for p, s in bids[:25]],
                "asks": [{"price": p, "size": s} for p, s in asks[:25]],
                "best_bid": bids[0][0] if bids else None, "best_ask": asks[0][0] if asks else None,
                "unit": "shares (USDC)" if venue.lower().startswith("poly") else "contracts ($1)"}
    return _cached(f"pred:book:{venue}:{market_id}", 20, build)


# ── Movers ──────────────────────────────────────────────────────────────────
def movers(min_volume: float = 5000, sports: bool = False) -> Dict[str, Any]:
    def build():
        rows = []
        for e in catalog()["events"]:
            for m in e["markets"]:
                if m.get("chg_1d") is None or abs(m["chg_1d"]) < 0.02 or (m.get("volume_24h") or 0) < min_volume:
                    continue
                if (not sports and e["category"] == "Sports") or not 0.02 < m["yes"] < 0.98 or m.get("thin"):   # live games / settled outcomes are noise
                    continue
                rows.append({"venue": e["venue"], "event_id": e["id"], "event": e["title"], "category": e["category"], "label": m["label"],
                             "market_id": m["id"], "series": m.get("series"), "yes": m["yes"], "chg_1d": m["chg_1d"], "volume_24h": m["volume_24h"],
                             "end": m.get("end")})
        rows.sort(key=lambda r: -abs(r["chg_1d"]))
        return {"rows": rows[:150], "note": f"Outcomes whose probability moved 2+ points in 24 hours, with at least {min_volume:,.0f} traded"
                         + ("." if sports else " (live sports and settled outcomes hidden).")}
    return _cached(f"pred:movers:{int(sports)}", 300, build)


# ── Same question on both venues ────────────────────────────────────────────
STOP = set("will the a an of in on by to be for at and or is are before after this end than more less who what which how 2025 2026 2027 vs".split())


def _words(t: str) -> set:
    return {w for w in re.findall(r"[a-z0-9]+", (t or "").lower()) if w not in STOP and len(w) > 1}


def _names(t: str) -> set:
    """Capitalised words after the first — the places and people that make two similar titles different questions."""
    w = re.findall(r"[A-Za-z][\w'’.-]*", t or "")
    return {x.lower() for x in w[1:] if x[0].isupper() and x.lower() not in STOP and len(x) > 2}


def cross_venue() -> Dict[str, Any]:
    def build():
        ev = catalog()["events"]
        poly = [e for e in ev if e["venue"] == "Polymarket"]
        kal = [e for e in ev if e["venue"] == "Kalshi"]
        kw = [(_words(e["title"]), e) for e in kal]
        pairs = []
        for p in poly:
            wp = _words(p["title"])
            if len(wp) < 2:
                continue
            best, score = None, 0.0
            yp = set(re.findall(r"20\d\d", p["title"] or ""))
            for wk, k in kw:
                if not wk:
                    continue
                yk = set(re.findall(r"20\d\d", k["title"] or ""))
                if yp and yk and not yp & yk:
                    continue
                np_, nk = _names(p["title"]), _names(k["title"])
                if (np_ - wk) and (nk - wp):          # e.g. 'Prime Minister of Spain' vs '… of Greece'
                    continue
                if p.get("end") and k.get("end") and abs((datetime.fromisoformat(p["end"]) - datetime.fromisoformat(k["end"])).days) > 120:
                    continue
                j = len(wp & wk) / len(wp | wk)
                if j > score:
                    best, score = k, j
            if not best or score < 0.5:
                continue
            # align outcomes by label words
            rows = []
            for pm in p["markets"][:12]:
                lw = _words(pm["label"])
                km = max(best["markets"], key=lambda m: len(lw & _words(m["label"])) / (len(lw | _words(m["label"])) or 1), default=None)
                if km is not None and lw and len(lw & _words(km["label"])) / (len(lw | _words(km["label"])) or 1) >= 0.5:
                    rows.append({"label": pm["label"], "poly": pm["yes"], "kalshi": km["yes"], "gap": round(pm["yes"] - km["yes"], 4),
                                 "kalshi_label": km["label"]})
            if not rows and len(p["markets"]) == 1 and len(best["markets"]) == 1:
                pm, km = p["markets"][0], best["markets"][0]
                rows.append({"label": "Yes", "poly": pm["yes"], "kalshi": km["yes"], "gap": round(pm["yes"] - km["yes"], 4), "kalshi_label": km["label"]})
            if not rows:
                continue
            pairs.append({"poly": {"id": p["id"], "title": p["title"], "volume_24h": p["volume_24h"], "end": p["end"]},
                          "kalshi": {"id": best["id"], "title": best["title"], "volume_24h": best["volume_24h"], "end": best["end"]},
                          "match": round(score, 2), "category": p["category"], "outcomes": rows,
                          "max_gap": max((abs(r["gap"]) for r in rows), default=None)})
        pairs.sort(key=lambda x: (-(x["max_gap"] or 0), -x["match"]))
        return {"pairs": pairs, "note": "Events matched by title; outcomes aligned by label. A gap is the difference in implied "
                                        "probability between venues (fees, rules and settlement sources can differ — read both)."}
    return _cached("pred:cross", 300, build)


# ── Macro view ──────────────────────────────────────────────────────────────
MACRO_CATS = {"Fed & rates", "Inflation", "Economy", "Markets"}
FED_MAP = [(r"no change|hold|unchanged|maintain", 0), (r"25 ?bps? (decrease|cut)|cut 25|decrease 25", -25), (r"50\+? ?bps? (decrease|cut)", -50),
           (r"25 ?bps? (increase|hike)|hike 25|increase 25", 25), (r"50\+? ?bps? (increase|hike)", 50)]


def macro() -> Dict[str, Any]:
    def build():
        ev = catalog()["events"]
        groups: Dict[str, List[Dict[str, Any]]] = {}
        for e in ev:
            if e["category"] in MACRO_CATS:
                groups.setdefault(e["category"], []).append(e)
        for k in groups:
            groups[k] = sorted(groups[k], key=lambda e: -(e["volume_24h"] or 0))[:40]
        # next Fed decision: each venue vs fed funds futures
        fed_rows: Dict[int, Dict[str, Any]] = {}
        poly_fed = next((e for e in sorted(ev, key=lambda e: e.get("end") or "9") if e["venue"] == "Polymarket"
                         and re.search(r"fed decision in", e["title"] or "", re.I)), None)
        if poly_fed:
            for m in poly_fed["markets"]:
                for rx, bp in FED_MAP:
                    if re.search(rx, m["label"], re.I):
                        fed_rows.setdefault(bp, {"move_bp": bp})["polymarket"] = m["yes"]
                        break
        kal_fed, kalshi_note, th = None, None, []
        try:     # Kalshi lists the decision itself (KXFEDDECISION) and the resulting rate as thresholds (KXFED)
            j = _get(f"{KALSHI}/events", params={"series_ticker": "KXFEDDECISION", "status": "open", "with_nested_markets": "true"})
            evs = sorted(j.get("events") or [], key=lambda e: min((m.get("close_time") or "9") for m in e.get("markets") or [{}]))
            if evs:
                kal_fed = evs[0]
                for m in kal_fed.get("markets") or []:
                    km = _kalshi_market(m, "KXFEDDECISION")
                    lab = (km or {}).get("label", "").lower()
                    bp = 0 if "maintain" in lab else (-50 if "cut >" in lab else -25 if "cut" in lab else 50 if "hike >" in lab else 25 if "hike" in lab else None)
                    if km and bp is not None:
                        fed_rows.setdefault(bp, {"move_bp": bp})["kalshi"] = km["yes"]
            j = _get(f"{KALSHI}/events", params={"series_ticker": "KXFED", "status": "open", "with_nested_markets": "true"})
            evs = sorted(j.get("events") or [], key=lambda e: min((m.get("close_time") or "9") for m in e.get("markets") or [{}]))
            if evs:
                for m in evs[0].get("markets") or []:
                    km = _kalshi_market(m, "KXFED")
                    mm = re.search(r"([\d.]+)%", (km or {}).get("label") or "")
                    if km and mm:
                        th.append({"above": float(mm.group(1)), "p": km["yes"]})
                th.sort(key=lambda r: r["above"])
                kalshi_note = evs[0].get("title")
        except Exception as e:
            logger.info("[pred] kalshi fed: %s", e)
        futures = None
        try:
            from api.marketdata import extras
            w = extras.wirp()
            m0 = (w.get("meetings") or [None])[0]
            if m0:
                futures = {"meeting": m0["meeting"], "probabilities": m0.get("probabilities"), "change_bp": m0.get("change_bp"),
                           "target_upper": w.get("target_upper"), "target_lower": w.get("target_lower")}
                for k, v in (m0.get("probabilities") or {}).items():
                    mm = re.match(r"([+-]?\d+)", k)
                    if mm:
                        fed_rows.setdefault(int(mm.group(1)), {"move_bp": int(mm.group(1))})["futures"] = v
        except Exception as e:
            logger.info("[pred] wirp: %s", e)
        table = sorted(fed_rows.values(), key=lambda r: r["move_bp"])
        return {"groups": groups, "fed": {"rows": table, "polymarket_event": poly_fed["title"] if poly_fed else None,
                                          "kalshi_event": kal_fed["title"] if kal_fed else None, "kalshi_thresholds": [r for r in th if 0.02 < r["p"] < 0.98] or th[-6:],
                                          "kalshi_note": kalshi_note, "futures": futures},
                "note": "The next Fed decision as priced by Polymarket, Kalshi and fed funds futures (CME-style, from WIRP). "
                        "Gaps between them are where the crowds disagree with the rates market."}
    return _cached("pred:macro", 300, build)


# ── Browse / one event (slim payloads for the UI) ───────────────────────────
SORTS = {"volume": lambda e: -(e["volume_24h"] or 0), "total": lambda e: -(e["volume"] or 0),
         "liquidity": lambda e: -(e["liquidity"] or 0), "ending": lambda e: e.get("end") or "9999",
         "moving": lambda e: -max((abs(m.get("chg_1d") or 0) for m in e["markets"]), default=0)}


def _slim(e: Dict[str, Any], n: int = 4) -> Dict[str, Any]:
    keep = ("id", "series", "label", "yes", "bid", "ask", "chg_1d", "volume_24h", "end", "binary", "outcomes", "spread", "thin")
    mk = e["markets"]
    live = [m for m in mk if not m["binary"] or m["yes"] >= 0.01] or mk      # sub-1% long shots are noise on a card
    return {**{k: v for k, v in e.items() if k not in ("markets", "description")}, "n_markets": len(mk),
            "markets": [{k: m.get(k) for k in keep} for m in live[:n]]}


def browse(q: str = "", venue: str = "", category: str = "", sort: str = "volume", offset: int = 0, limit: int = 50,
           active: bool = True, sports: bool = False) -> Dict[str, Any]:
    c = catalog()
    ev = c["events"]
    if not category and not q and not sports:   # live games swamp the volume ranking; show them on request
        ev = [e for e in ev if e["category"] != "Sports"]
    if active:      # something must trade: $1k a day on Polymarket, 1k contracts on Kalshi, or a live two-sided quote
        ev = [e for e in ev if (e["volume_24h"] or 0) >= 1000 or any(not m.get("thin") for m in e["markets"])]
    if venue:
        ev = [e for e in ev if e["venue"].lower() == venue.lower()]
    if category:
        ev = [e for e in ev if e["category"] == category]
    if q:
        terms = q.lower().split()
        ev = [e for e in ev if all(t in f"{e['title']} {e.get('subtitle') or ''} {' '.join(m['label'] for m in e['markets'][:30])} {' '.join(e['tags'])}".lower()
                                   for t in terms)]
    ev = sorted(ev, key=SORTS.get(sort, SORTS["volume"]))
    return {"total": len(ev), "offset": offset, "events": [_slim(e) for e in ev[offset:offset + limit]],
            "categories": c["categories"], "venues": c["venues"], "as_of": c["as_of"], "note": c["note"], "source": c["source"]}


def event(venue: str, event_id: str) -> Dict[str, Any]:
    for e in catalog()["events"]:
        if e["venue"].lower() == venue.lower() and str(e["id"]) == str(event_id):
            return e
    raise NotFound("That event is no longer open (or isn't among the most active on its venue).")


NOISE = re.compile(r"# ?tweets|tweet count|say .* during|mention|word .* said|highest temperature|lowest temperature", re.I)


# ── Related markets: odds that bear on whatever screen you're on ────────────
def related(terms: List[str], limit: int = 6, exclude_sports: bool = True) -> Dict[str, Any]:
    """Open events whose title (or outcome labels) mention any of the terms, as whole words, ranked by
    how many terms hit the title and by 24-hour volume. Thin, settled-looking events are dropped."""
    terms = [t.strip().lower() for t in terms if t and len(t.strip()) >= 2][:12]
    if not terms:
        return {"events": []}
    rx = [(t, re.compile(r"(?<![\w$])" + re.escape(t) + r"(?![\w])", re.I)) for t in terms]
    scored = []
    for e in catalog()["events"]:
        if exclude_sports and e["category"] == "Sports":
            continue
        if NOISE.search(e["title"] or ""):
            continue
        title = e["title"] or ""
        hits_t = sum(1 for _, r in rx if r.search(title))
        hits_l = 0 if hits_t else sum(1 for _, r in rx if any(r.search(m["label"] or "") for m in e["markets"][:20]))
        if not hits_t and not hits_l:
            continue
        if (e["volume_24h"] or 0) < 200 and all(m.get("thin") for m in e["markets"][:5]):
            continue
        scored.append((hits_t * 3 + hits_l, math.log1p(e["volume_24h"] or 0), e))
    scored.sort(key=lambda x: (-x[0], -x[1]))
    return {"terms": terms, "events": [_slim(e, 3) for _, _, e in scored[:limit]]}
