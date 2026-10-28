"""
Cross-venue prediction-market arbitrage — Polymarket vs Kalshi.

If the *same* yes/no question trades on both venues, buying YES on one and NO on the other pays
exactly $1 whichever way it resolves. When the two asks cost less than $1 after fees, the
difference is locked in (provided both venues resolve the question the same way).

    cost  = YES ask on venue A + NO ask on venue B + fees
    NO ask = 1 − YES bid           (both venues run a single book per question)
    Kalshi taker fee = ⌈0.07 × contracts × P × (1 − P)⌉ to the cent (P = price paid)
    Polymarket: no trading fee on most markets (configurable)

Matching is per question, not per event: titles differ between venues, so questions are compared
on rare words (IDF-weighted), and must agree on every number (thresholds, bps, years), person
names and months. Fed decisions are decoded to (meeting, change in bps) on both venues. Every
match is a *candidate*: the resolution rules, sources and cut-off times must be read on both
sides before treating a gap as risk-free — that is where "arbitrage" usually breaks.

Read-only: nothing here places orders.
"""
from __future__ import annotations

import math
import re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from api.marketdata import predmarkets as pm
from api.marketdata.core import NotFound, _cached

KALSHI_FEE = 0.07
MONTHS = ("january february march april may june july august september october november december").split()
_MON = {m[:3]: i + 1 for i, m in enumerate(MONTHS)}
STOP = pm.STOP | set("price close above below between at least than on in yes no market win wins winner who".split())
_NUM = re.compile(r"(?<![\w.])[-+]?\d[\d,]*(?:\.\d+)?")


def _years(t: str) -> frozenset:
    return frozenset(re.findall(r"\b20[2-3]\d\b", t or ""))


def _nums(t: str) -> frozenset:
    """Numbers in the question other than years (thresholds, bps, counts)."""
    out = set()
    for x in _NUM.findall(t or ""):
        v = x.replace(",", "")
        try:
            f = float(v)
        except ValueError:
            continue
        if not (x.isdigit() and len(x) == 4 and 2020 <= f <= 2039):
            out.add(f"{f:g}")
    return frozenset(out)


def _months(t: str) -> frozenset:
    return frozenset(_MON[w[:3]] for w in re.findall(r"[a-z]+", (t or "").lower()) if w[:3] in _MON and (w in MONTHS or len(w) == 3))


def _tokens(t: str) -> List[str]:
    t = re.sub(r"(\w)\.(\w)\.", r"\1\2", t or "")                  # J.D. → JD
    return [w for w in re.findall(r"[a-z0-9]+", t.lower()) if w not in STOP and len(w) > 1 and not w.isdigit()]


def _comparator(t: str) -> str:
    """How the question compares its number: gt (more than / above), ge (or more / at least), lt, le, range, eq."""
    t = (t or "").lower()
    if re.search(r"between|\bto\b \d|-\d|range", t):
        return "range"
    if re.search(r"or more|at least|or higher|or above|\+", t):
        return "ge"
    if re.search(r"or less|at most|or lower|or below", t):
        return "le"
    if re.search(r"more than|above|greater than|over|exceed|higher than|rise more|reach|hit", t):
        return "gt"
    if re.search(r"less than|below|under|lower than|dip|fall", t):
        return "lt"
    return "eq"


def _person_tokens(t: str) -> set:
    """Capitalised words after the first (people, places), normalised like _tokens."""
    words = re.findall(r"[A-Za-z][\w'’.-]*", re.sub(r"(\w)\.(\w)\.", r"\1\2", t or ""))
    return {x for w in words[1:] if w[0].isupper() for x in _tokens(w) if len(x) > 2}


def _covered(names: set, toks: set) -> bool:
    """Every name appears in the other question (allowing one-letter slips such as Hilary/Hillary, and a shared
    7-letter stem for long words such as Presidency/presidential)."""
    for n in names:
        if n in toks:
            continue
        if not any(len(n) > 4 and (_edit1(n, t) or (len(n) >= 8 and t[:7] == n[:7])) for t in toks):
            return False
    return True


def _edit1(a: str, b: str) -> bool:
    """True if a and b differ by at most one insertion, deletion or substitution."""
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) > len(b):
        a, b = b, a
    i = 0
    while i < len(a) and a[i] == b[i]:
        i += 1
    return a[i + 1:] == b[i + 1:] if len(a) == len(b) else a[i:] == b[i + 1:]


def _fed_key(text: str) -> Optional[Tuple[int, int, int]]:
    """(year, month, change in bps) for a Fed-decision question, else None."""
    t = (text or "").lower()
    if not re.search(r"\bfed\b|federal reserve|fomc", t):
        return None
    if re.search(r"how many|number of|times|cuts in|by end|by december|rate cuts? in 20", t):
        return None
    yrs = re.findall(r"20\d\d", t)
    mons = [m for m in _months(t)]
    if len(mons) != 1 or not yrs:
        return None
    if re.search(r"hike rates by 0 ?bps|maintains|no change|unchanged|hold", t):
        return int(yrs[0]), mons[0], 0
    for pat, bps in pm.FED_MAP:
        if re.search(pat, t):
            return int(yrs[0]), mons[0], bps
    m = re.search(r"(hike|cut|increase|decrease|raise|lower)\w*(?: \w+){0,3}? by (\d+) ?bps", t)
    if m:
        return int(yrs[0]), mons[0], int(m.group(2)) * (1 if m.group(1)[0] in "hir" else -1)
    return None


def _questions() -> List[Dict[str, Any]]:
    qs = []
    for e in pm.catalog()["events"]:
        if e["category"] == "Sports":
            continue
        for m in e["markets"]:
            if not m.get("binary"):
                continue
            text = f'{e["title"]} {m["label"]} {m.get("question") or ""}'
            qs.append({"venue": e["venue"], "event": e, "m": m, "text": text, "toks": set(_tokens(text)),
                       "years": _years(text),
                       "nums": _nums(f'{m["label"]} {m.get("question") or ""}'), "months": _months(f'{m["label"]} {m.get("question") or ""}'),
                       "names": _person_tokens(m.get("question") or m["label"]),
                       "cmp": _comparator(f'{m["label"]} {m.get("question") or ""}') if _nums(f'{m["label"]} {m.get("question") or ""}') else "-",
                       "fed": _fed_key(f'{m.get("question") or ""} {m["label"]} {e["title"]}'), "end": m.get("end") or e.get("end")})
    return qs


def _days(a: Optional[str], b: Optional[str]) -> Optional[int]:
    try:
        return abs((date.fromisoformat(a) - date.fromisoformat(b)).days)
    except (TypeError, ValueError):
        return None


def match(min_score: float = 0.5) -> List[Dict[str, Any]]:
    """Best Kalshi question for each Polymarket question (one-to-one), with a similarity score."""
    qs = _questions()
    poly = [q for q in qs if q["venue"] == "Polymarket"]
    kal = [q for q in qs if q["venue"] == "Kalshi"]
    df: Dict[str, int] = defaultdict(int)
    for q in qs:
        for w in q["toks"]:
            df[w] += 1
    n = len(qs)
    idf = {w: math.log(n / c) for w, c in df.items()}
    rare_cut = math.log(n / max(3, 0.05 * n)) - 1e-9          # "rare" = in ≤ 5% of questions (at least 3)
    index: Dict[str, List[int]] = defaultdict(list)
    for i, q in enumerate(kal):
        for w in q["toks"]:
            if idf[w] >= rare_cut:                                # rare words only — keeps candidates few
                index[w].append(i)
    fed_index: Dict[Tuple, List[int]] = defaultdict(list)
    for i, q in enumerate(kal):
        if q["fed"]:
            fed_index[q["fed"]].append(i)
    cands: List[Tuple[float, int, int, str]] = []
    for pi, p in enumerate(poly):
        if p["fed"]:
            for ki in fed_index.get(p["fed"], []):
                cands.append((0.99, pi, ki, "fed"))
            continue
        seen = set()
        for w in p["toks"]:
            if idf.get(w, 0) >= rare_cut:
                seen.update(index.get(w, ()))
        for ki in seen:
            k = kal[ki]
            if p["years"] and k["years"] and not p["years"] & k["years"]:
                continue
            if k["fed"] or p["nums"] != k["nums"] or p["months"] != k["months"] or p["cmp"] != k["cmp"]:
                continue
            if not _covered(p["names"], k["toks"]) or not _covered(k["names"], p["toks"]):
                continue
            d = _days(p["end"], k["end"])
            if d is not None and d > 45:
                continue
            inter = sum(idf[w] for w in p["toks"] & k["toks"])
            union = sum(idf[w] for w in p["toks"] | k["toks"])
            s = inter / union if union else 0.0
            if s >= min_score:
                cands.append((s, pi, ki, "text"))
    cands.sort(key=lambda c: -c[0])
    used_p, used_k, out = set(), set(), []
    for s, pi, ki, how in cands:
        if pi in used_p or ki in used_k:
            continue
        used_p.add(pi)
        used_k.add(ki)
        out.append({"poly": poly[pi], "kalshi": kal[ki], "score": round(s, 3), "how": how})
    return out


def kalshi_fee(contracts: float, price: float, rate: float = KALSHI_FEE) -> float:
    """Kalshi's trading fee for `contracts` at `price` (rate × C × P × (1 − P), rounded up to the cent)."""
    return math.ceil(round(rate * contracts * price * (1 - price) * 100, 6)) / 100


def _ladder_yes_no(book: Dict[str, Any]) -> Tuple[List[Tuple[float, float]], List[Tuple[float, float]]]:
    """YES asks and NO asks (price, size) from a YES order book."""
    yes = [(a["price"], a["size"]) for a in book["asks"]]
    no = sorted((round(1 - b["price"], 4), b["size"]) for b in book["bids"])
    return yes, no


def _walk(a: List[Tuple[float, float]], b: List[Tuple[float, float]], kalshi_leg: str, k_rate: float, p_fee: float,
          max_contracts: float = 1e6) -> Dict[str, Any]:
    """Greedily buy one contract of each leg while the pair still costs < $1 after fees.
    `kalshi_leg` is 'a' or 'b' — which ladder is on Kalshi (pays the taker fee)."""
    i = j = 0
    ra = a[0][1] if a else 0
    rb = b[0][1] if b else 0
    qty = cost_a = cost_b = 0.0
    while i < len(a) and j < len(b) and qty < max_contracts:
        pa, pb = a[i][0], b[j][0]
        fee = k_rate * (pa if kalshi_leg == "a" else pb) * (1 - (pa if kalshi_leg == "a" else pb))
        fee += p_fee * (pb if kalshi_leg == "a" else pa)
        if pa + pb + fee >= 1:
            break
        take = min(ra, rb, max_contracts - qty)
        qty += take
        cost_a += take * pa
        cost_b += take * pb
        ra -= take
        rb -= take
        if ra <= 1e-9:
            i += 1
            ra = a[i][1] if i < len(a) else 0
        if rb <= 1e-9:
            j += 1
            rb = b[j][1] if j < len(b) else 0
    if qty <= 0:
        return {"contracts": 0}
    k_cost = cost_a if kalshi_leg == "a" else cost_b
    p_cost = cost_b if kalshi_leg == "a" else cost_a
    k_avg = k_cost / qty
    fees = kalshi_fee(qty, k_avg, k_rate) + p_fee * p_cost
    outlay = cost_a + cost_b + fees
    return {"contracts": round(qty, 2), "outlay": round(outlay, 2), "fees": round(fees, 2),
            "profit": round(qty - outlay, 2), "edge_per_contract": round((qty - outlay) / qty, 4)}


def _quote_edge(pmk: Dict[str, Any], kmk: Dict[str, Any], k_rate: float, p_fee: float) -> List[Dict[str, Any]]:
    """Top-of-book cost of both directions from the catalog quotes."""
    out = []
    pya, pyb, kya, kyb = pmk.get("ask"), pmk.get("bid"), kmk.get("ask"), kmk.get("bid")
    if pya is not None and kyb is not None:          # YES on Polymarket + NO on Kalshi
        kno = 1 - kyb
        out.append({"dir": "poly_yes_kalshi_no", "yes_venue": "Polymarket", "yes_price": pya, "no_venue": "Kalshi", "no_price": round(kno, 4),
                    "cost": round(pya + kno + k_rate * kno * (1 - kno) + p_fee * pya, 4)})
    if kya is not None and pyb is not None:          # YES on Kalshi + NO on Polymarket
        pno = 1 - pyb
        out.append({"dir": "kalshi_yes_poly_no", "yes_venue": "Kalshi", "yes_price": kya, "no_venue": "Polymarket", "no_price": round(pno, 4),
                    "cost": round(kya + pno + k_rate * kya * (1 - kya) + p_fee * pno, 4)})
    for o in out:
        o["edge"] = round(1 - o["cost"], 4)
    return out


def _depth(row: Dict[str, Any], k_rate: float, p_fee: float) -> Dict[str, Any]:
    pmk, kmk = row["_pm"], row["_km"]
    pb = pm.orderbook("Polymarket", pmk["id"])
    kb = pm.orderbook("Kalshi", kmk["id"])
    p_yes, p_no = _ladder_yes_no(pb)
    k_yes, k_no = _ladder_yes_no(kb)
    if row["dir"] == "poly_yes_kalshi_no":
        return _walk(p_yes, k_no, "b", k_rate, p_fee)
    return _walk(k_yes, p_no, "a", k_rate, p_fee)


def _flags(p: Dict[str, Any], k: Dict[str, Any], score: float, how: str) -> List[str]:
    f = []
    d = _days(p["end"], k["end"])
    if d is None:
        f.append("Close date missing on one venue.")
    elif d > 1:
        f.append(f"Close dates differ by {d} days ({p['end']} vs {k['end']}) — one may resolve before the other.")
    if how == "text" and score < 0.6:
        f.append("Loose wording match — confirm it is the same question.")
    if abs((p["m"]["yes"] or 0) - (k["m"]["yes"] or 0)) > 0.25:
        f.append("Prices differ by more than 25 points — check the questions are not opposites or differently defined.")
    if p["m"].get("thin") or k["m"].get("thin"):
        f.append("Thin book on at least one venue — quotes may be stale.")
    return f


def _rf_curve() -> List[Tuple[float, float]]:
    """US Treasury curve (tenor in years, yield as a fraction) — the hurdle a locked-in edge must beat."""
    try:
        from api.marketdata import curves
        pts = curves.curves()["curves"]["US"]["points"]
        return sorted((float(p["tenor"]), float(p["yield"]) / 100) for p in pts if p.get("yield") is not None)
    except Exception:                                        # noqa: BLE001 — the scan works without it
        return []


def _rf(curve: List[Tuple[float, float]], days: Optional[int]) -> Optional[float]:
    if not curve or not days:
        return None
    t = days / 365
    if t <= curve[0][0]:
        return curve[0][1]
    for (t0, y0), (t1, y1) in zip(curve, curve[1:]):
        if t <= t1:
            return y0 + (y1 - y0) * (t - t0) / (t1 - t0)
    return curve[-1][1]


def scan(k_rate: float = KALSHI_FEE, poly_fee: float = 0.0, min_edge: float = -0.03, depth_checks: int = 20) -> Dict[str, Any]:
    """Cross-venue prediction-market arbitrage: matched Polymarket / Kalshi markets with the edge after fees, depth-
    checked.

    Raises:
        ValueError: fee rates out of range.
    """
    if not 0 <= k_rate <= 0.2 or not 0 <= poly_fee <= 0.1:
        raise ValueError("Kalshi fee rate 0–0.2; Polymarket fee 0–10%.")

    def build():
        pairs = match()
        curve = _rf_curve()
        rows = []
        for mt in pairs:
            p, k = mt["poly"], mt["kalshi"]
            for q in _quote_edge(p["m"], k["m"], k_rate, poly_fee):
                end = max([x for x in (p["end"], k["end"]) if x], default=None)
                days = max(1, (date.fromisoformat(end) - date.today()).days) if end else None
                rows.append({**q, "poly_event": p["event"]["title"], "poly_question": p["m"].get("question") or p["m"]["label"],
                             "poly_slug": p["event"].get("slug"), "poly_token": p["m"]["id"],
                             "kalshi_event": k["event"]["title"], "kalshi_question": k["m"].get("question") or k["m"]["label"],
                             "kalshi_ticker": k["m"]["id"], "kalshi_series": k["event"].get("series"),
                             "poly_yes": p["m"]["yes"], "kalshi_yes": k["m"]["yes"], "gap": round(p["m"]["yes"] - k["m"]["yes"], 4),
                             "match": mt["score"], "match_how": mt["how"], "end": end, "days": days,
                             "annualized": round(q["edge"] / q["cost"] * 365 / days, 4) if days and q["cost"] > 0 and q["edge"] > 0 else None,
                             "treasury_yield": None if _rf(curve, days) is None else round(_rf(curve, days), 4),
                             "flags": _flags(p, k, mt["score"], mt["how"]),
                             "poly_rules": (p["m"].get("rules") or "")[:600], "kalshi_rules": (k["m"].get("rules") or "")[:600],
                             "_pm": p["m"], "_km": k["m"]})
        for r in rows:
            if r["annualized"] is not None and r["treasury_yield"] is not None and r["annualized"] < r["treasury_yield"]:
                r["flags"].insert(0, f"Annualised {r['annualized']:.1%} is below the {r['treasury_yield']:.1%} Treasury yield to the "
                                     "same date — the capital earns more in T-bills.")
        rows.sort(key=lambda r: -r["edge"])
        best: Dict[Tuple, Dict] = {}
        for r in rows:                                   # keep the better direction per question pair
            best.setdefault((r["poly_token"], r["kalshi_ticker"]), r)
        rows = sorted(best.values(), key=lambda r: -r["edge"])
        top = [r for r in rows if r["edge"] > min_edge][:depth_checks]
        with ThreadPoolExecutor(4) as ex:
            depths = list(ex.map(lambda r: _safe_depth(r, k_rate, poly_fee), top))
        for r, d in zip(top, depths):
            r["executable"] = d
        for r in rows:
            r.pop("_pm"), r.pop("_km")
        arbs = [r for r in rows if (r.get("executable") or {}).get("contracts", 0) > 0]
        return {"rows": rows[:150], "matched_questions": len(pairs), "arbs": len(arbs),
                "fees": {"kalshi_rate": k_rate, "poly_fee": poly_fee},
                "as_of": pm.catalog().get("as_of"),
                "note": ("Edge = $1 − (YES ask + NO ask + fees) per contract, from top-of-book quotes; 'executable' walks both "
                         "live order books for the size available at a positive edge. A match is a candidate until the "
                         "resolution rules agree — read both. Polymarket settles in USDC on Polygon, Kalshi in USD: moving "
                         "money between them costs time and fees not counted here. Kalshi pays interest on balances and Polymarket "
                         "pays holding rewards on some long-dated markets, which shifts the comparison with T-bills.")}
    return _cached(f"pred:arb:{k_rate}:{poly_fee}:{min_edge}:{depth_checks}", 120, build)


def _safe_depth(r, k_rate, p_fee):
    try:
        return _depth(r, k_rate, p_fee)
    except Exception as e:                                   # noqa: BLE001 — one bad book must not sink the scan
        return {"contracts": 0, "error": str(e)[:120]}


def check(poly: str, kalshi: str, k_rate: float = KALSHI_FEE, poly_fee: float = 0.0) -> Dict[str, Any]:
    """Both directions for a pair the user chose: a Polymarket market (slug, URL or YES token id) and a Kalshi ticker.
    """
    poly, kalshi = (poly or "").strip(), (kalshi or "").strip().upper()
    if not poly or not kalshi:
        raise ValueError("Give a Polymarket market and a Kalshi market ticker.")
    kalshi = kalshi.rstrip("/").split("/")[-1].upper()
    pm_m = _poly_lookup(poly)
    j = pm._get(f"{pm.KALSHI}/markets/{kalshi}")
    km_raw = (j or {}).get("market")
    if not km_raw:
        raise NotFound(f"Kalshi market {kalshi} not found — use the market ticker, e.g. KXFEDDECISION-26OCT-H0.")
    km = pm._kalshi_market(km_raw, km_raw.get("event_ticker", "").split("-")[0])
    if not km:
        raise NotFound(f"Kalshi market {kalshi} is not open.")
    out = []
    for q in _quote_edge(pm_m, km, k_rate, poly_fee):
        q["executable"] = _safe_depth({**q, "_pm": pm_m, "_km": km}, k_rate, poly_fee)
        out.append(q)
    return {"poly": {k: pm_m.get(k) for k in ("question", "yes", "bid", "ask", "end", "rules")},
            "kalshi": {k: km.get(k) for k in ("question", "yes", "bid", "ask", "end", "rules")},
            "directions": sorted(out, key=lambda r: -r["edge"]), "fees": {"kalshi_rate": k_rate, "poly_fee": poly_fee}}


def _poly_lookup(s: str) -> Dict[str, Any]:
    if re.fullmatch(r"\d{20,}", s):
        rows = pm._get(f"{pm.GAMMA}/markets", params={"clob_token_ids": s})
    else:
        slug = s.rstrip("/").split("?")[0].split("/")[-1]
        rows = pm._get(f"{pm.GAMMA}/markets", params={"slug": slug})
        if not rows:
            ev = pm._get(f"{pm.GAMMA}/events", params={"slug": slug})
            mk = (ev[0].get("markets") if ev else None) or []
            if len(mk) == 1:
                rows = mk
            elif mk:
                names = ", ".join((m.get("groupItemTitle") or m.get("question") or "")[:40] for m in mk[:8])
                raise ValueError(f"That Polymarket event has {len(mk)} questions ({names}…) — paste the URL of one question.")
    m = pm._poly_market(rows[0]) if rows else None
    if not m or not m.get("binary"):
        raise NotFound("Polymarket market not found or not a yes/no question.")
    return m
