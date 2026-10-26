"""
Portfolio analytics on the actual book — pure, tested.

* ``holdings_by_day``: the book's holdings each day, rebuilt from today's positions by undoing later trades (a
  position with no trades is held from its entry date). Attribution therefore follows what was actually held.
* ``brinson_day`` / ``carino_link``: Brinson–Fachler allocation / selection / interaction per sector each day,
  linked over the period with Carino's logarithmic coefficients so the effects add up to the active return.
* ``ex_ante_tracking_error``: sqrt(aᵀΣa) of the active weights versus a benchmark, annualised.
* ``corwin_schultz_spread`` / ``abdi_ranaldo_spread``: bid–ask spread from daily highs, lows (and closes).
* ``liquidity_profile``: days to liquidate at a participation rate of average daily volume, and the exogenous
  liquidity cost (half the spread on each position) added to VaR (Bangia et al. 1999 style LVaR).
* ``fifo_lots``: open tax lots from the fills (oldest sold first).
* ``tca_row``: implementation shortfall of a fill versus the decision (arrival) price, the session's typical price
  (VWAP proxy) and the close.
* ``idea_pnl``: mark-to-market of a trade idea from its entry, with stop / target hits from the path.
"""
from __future__ import annotations

import math
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


# ── Holdings reconstruction ──────────────────────────────────────────────────
def holdings_by_day(positions: Sequence[Dict], trades: Sequence[Dict], days: Sequence[str]) -> Dict[str, Dict[str, float]]:
    """{day: {symbol: quantity at that day's close}}.

    Quantity on day d = today's quantity − Σ signed quantities of trades dated after d. A symbol with no trades at
    all is held from its position's entry_date (0 before it). A trade's optional "split_factor" (shares today per
    share then) puts fills from before a split into today's share units, matching split-adjusted price history."""
    cur: Dict[str, float] = {}
    entry: Dict[str, str] = {}
    for p in positions:
        s = str(p["symbol"]).upper()
        cur[s] = cur.get(s, 0.0) + float(p.get("quantity") or 0)
        e = str(p.get("entry_date") or "")[:10]
        entry[s] = min(entry.get(s, e), e) if entry.get(s) else e
    signed: List[Tuple[str, str, float]] = []
    traded = set()
    for t in trades:
        s = str(t["symbol"]).upper()
        q = float(t.get("quantity") or 0) * (1 if str(t.get("side", "")).upper() in ("BUY", "COVER", "B") else -1)
        q *= float(t.get("split_factor") or 1.0)       # a fill before a split, in today's share units
        signed.append((str(t.get("ts") or t.get("date"))[:10], s, q))
        traded.add(s)
        cur.setdefault(s, 0.0)
    out: Dict[str, Dict[str, float]] = {}
    for d in days:
        h = {}
        for s, q in cur.items():
            later = sum(dq for td, ts, dq in signed if ts == s and td > d)
            qty = q - later
            if s not in traded and entry.get(s) and d < entry[s]:
                qty = 0.0
            if abs(qty) > 1e-9:
                h[s] = qty
        out[d] = h
    return out


# ── Brinson–Fachler with Carino linking ──────────────────────────────────────
def brinson_day(port_w: Dict[str, float], port_r: Dict[str, float],
                bench_w: Dict[str, float], bench_r: Dict[str, float]) -> Dict[str, Dict[str, float]]:
    """One period. Weights are fractions of the portfolio / benchmark (cash is a sector with return 0).
    Returns {sector: {allocation, selection, interaction}}."""
    rb_total = sum(bench_w.get(s, 0) * bench_r.get(s, 0) for s in bench_w)
    out = {}
    for s in set(port_w) | set(bench_w):
        wp, wb = port_w.get(s, 0.0), bench_w.get(s, 0.0)
        rb = bench_r.get(s, 0.0)
        rp = port_r.get(s, rb)          # a sector the portfolio doesn't hold earns nothing in selection
        out[s] = {"allocation": (wp - wb) * (rb - rb_total),
                  "selection": wb * (rp - rb),
                  "interaction": (wp - wb) * (rp - rb)}
    return out


def _carino_k(r: float, b: float) -> float:
    if abs(r - b) < 1e-12:
        return 1.0 / (1.0 + r)
    return (math.log1p(r) - math.log1p(b)) / (r - b)


def carino_link(daily: Sequence[Dict[str, Dict[str, float]]], port_rets: Sequence[float],
                bench_rets: Sequence[float]) -> Dict[str, Dict[str, float]]:
    """Link daily effects so their sum equals the period's active return (geometric R − B)."""
    R = math.prod(1 + r for r in port_rets) - 1
    B = math.prod(1 + b for b in bench_rets) - 1
    K = _carino_k(R, B)
    out: Dict[str, Dict[str, float]] = {}
    for eff, r, b in zip(daily, port_rets, bench_rets):
        k = _carino_k(r, b) / K
        for s, e in eff.items():
            o = out.setdefault(s, {"allocation": 0.0, "selection": 0.0, "interaction": 0.0})
            for key in o:
                o[key] += e[key] * k
    return out


def backed_out_weights(w_today: Dict[str, float], price_then: Dict[str, float], price_now: Dict[str, float]) -> Dict[str, float]:
    """Benchmark sector weights on an earlier day, backed out from today's by each sector's price change since:
    w_then ∝ w_today ÷ (P_now / P_then). Exact for a cap-weighted index without reconstitution between the dates."""
    raw = {}
    for s, w in w_today.items():
        a, b = price_then.get(s), price_now.get(s)
        raw[s] = w / (b / a) if a and b else w
    tot = sum(raw.values())
    return {s: v / tot for s, v in raw.items()} if tot else dict(w_today)


# ── Tracking error ───────────────────────────────────────────────────────────
def ex_ante_tracking_error(active_w: Sequence[float], cov_daily) -> float:
    import numpy as np
    a = np.asarray(active_w, dtype=float)
    return float(math.sqrt(max(a @ np.asarray(cov_daily) @ a, 0.0)) * math.sqrt(252))


def ex_post_tracking_error(port_rets: Sequence[float], bench_rets: Sequence[float]) -> Optional[float]:
    import numpy as np
    d = np.asarray(port_rets, dtype=float) - np.asarray(bench_rets, dtype=float)
    return float(d.std(ddof=1) * math.sqrt(252)) if d.size > 2 else None


# ── Liquidity ────────────────────────────────────────────────────────────────
def corwin_schultz_spread(high: Sequence[float], low: Sequence[float],
                          close: Optional[Sequence[float]] = None) -> Optional[float]:
    """Average proportional spread from consecutive-day high/low ranges (Corwin & Schultz 2012), negative two-day
    estimates set to 0. With closes, the paper's overnight adjustment: when day t+1 trades entirely above (below)
    day t's close, its high and low are shifted down (up) by the gap, so an overnight jump is not read as spread."""
    est = []
    n = min(len(high), len(low))
    for i in range(1, n):
        h1, l1, h2, l2 = high[i - 1], low[i - 1], high[i], low[i]
        if min(h1, l1, h2, l2) <= 0:
            continue
        if close is not None and i - 1 < len(close) and close[i - 1]:
            c = close[i - 1]
            if l2 > c:                                # gap up: shift day t+1 down by the gap
                h2, l2 = h2 - (l2 - c), c
            elif h2 < c:                              # gap down: shift up
                h2, l2 = c, l2 + (c - h2)
        beta = math.log(h1 / l1) ** 2 + math.log(h2 / l2) ** 2
        gamma = math.log(max(h1, h2) / min(l1, l2)) ** 2
        k = 3 - 2 * math.sqrt(2)
        alpha = (math.sqrt(2 * beta) - math.sqrt(beta)) / k - math.sqrt(gamma / k)
        s = 2 * (math.exp(alpha) - 1) / (1 + math.exp(alpha))
        est.append(max(s, 0.0))
    return sum(est) / len(est) if est else None


def abdi_ranaldo_spread(close: Sequence[float], high: Sequence[float], low: Sequence[float]) -> Optional[float]:
    """Proportional spread from close, high and low (Abdi & Ranaldo 2017, RFS): s² = 4·E[(c_t − η_t)(c_t − η_{t+1})]
    with c the log close and η the log mid-range; two-day estimates averaged, a negative mean set to 0. Lower bias
    than Corwin–Schultz on daily data."""
    n = min(len(close), len(high), len(low))
    prods = []
    for t in range(n - 1):
        if min(close[t], high[t], low[t], high[t + 1], low[t + 1]) <= 0:
            continue
        c = math.log(close[t])
        eta_t = (math.log(high[t]) + math.log(low[t])) / 2
        eta_n = (math.log(high[t + 1]) + math.log(low[t + 1])) / 2
        prods.append((c - eta_t) * (c - eta_n))
    if len(prods) < 5:
        return None
    m = 4 * sum(prods) / len(prods)
    return math.sqrt(m) if m > 0 else 0.0


def liquidity_profile(qty: float, price: float, adv_shares: Optional[float], spread: Optional[float],
                      participation: float = 0.20) -> Dict[str, Optional[float]]:
    """Days to exit at `participation` of average daily volume, and the half-spread cost of exiting."""
    mv = abs(qty * price)
    dtl = (abs(qty) / (participation * adv_shares)) if adv_shares else None
    return {"days_to_liquidate": round(dtl, 4) if dtl is not None else None,
            "pct_of_adv": round(abs(qty) / adv_shares * 100, 3) if adv_shares else None,
            "spread_bps": round(spread * 1e4, 1) if spread is not None else None,
            "liquidity_cost": round(0.5 * spread * mv, 2) if spread is not None else None}


# ── Lots ─────────────────────────────────────────────────────────────────────
def fifo_lots(fills: Iterable[Dict]) -> List[Dict]:
    """Open lots after applying fills in time order (each fill: date, side BUY/SELL, quantity, price).
    Sells close the oldest long lots first; buys close the oldest short lots first."""
    lots: List[Dict] = []
    for f in sorted(fills, key=lambda x: str(x.get("date"))):
        q = float(f["quantity"]) * (1 if str(f.get("side", "")).upper() in ("BUY", "COVER", "B") else -1)
        while abs(q) > 1e-9 and lots and (lots[0]["quantity"] > 0) != (q > 0):
            take = min(abs(q), abs(lots[0]["quantity"]))
            lots[0]["quantity"] += take if lots[0]["quantity"] < 0 else -take
            q += -take if q > 0 else take
            if abs(lots[0]["quantity"]) < 1e-9:
                lots.pop(0)
        if abs(q) > 1e-9:
            lots.append({"date": str(f.get("date"))[:10], "quantity": q, "price": float(f["price"]),
                         "source": f.get("source")})
    return lots


# ── TCA ──────────────────────────────────────────────────────────────────────
def tca_row(side_sign: int, shares: float, fill: float, arrival: Optional[float], high: Optional[float],
            low: Optional[float], close: Optional[float]) -> Dict[str, Optional[float]]:
    """Slippage in basis points (positive = cost) versus arrival, the typical price (H+L+C)/3 and the close."""
    def bps(ref):
        return round(side_sign * (fill / ref - 1) * 1e4, 1) if ref else None
    typical = (high + low + close) / 3 if None not in (high, low, close) else None
    shortfall = side_sign * (fill - arrival) * shares if arrival else None
    return {"vs_arrival_bps": bps(arrival), "vs_vwap_proxy_bps": bps(typical), "vs_close_bps": bps(close),
            "shortfall_usd": round(shortfall, 2) if shortfall is not None else None}


# ── Trade-idea P&L ───────────────────────────────────────────────────────────
def idea_pnl(direction: str, entry: float, path: Sequence[Tuple[str, float, float, float]],
             stop: Optional[float] = None, target: Optional[float] = None) -> Dict:
    """path: [(date, high, low, close)] from the idea's creation. Returns the return to the last close (or to the
    stop / target if one was touched first — a stop counts when the path trades through it)."""
    sign = -1 if str(direction).upper() in ("SHORT", "SELL") else 1
    hit, hit_on, exit_px = None, None, None
    for d, hi, lo, cl in path:
        stop_hit = stop is not None and ((sign > 0 and lo <= stop) or (sign < 0 and hi >= stop))
        tgt_hit = target is not None and ((sign > 0 and hi >= target) or (sign < 0 and lo <= target))
        if stop_hit:                                  # same-day stop and target: assume the stop (conservative)
            hit, hit_on, exit_px = "stop", d, stop
            break
        if tgt_hit:
            hit, hit_on, exit_px = "target", d, target
            break
    last = path[-1][3] if path else None
    px = exit_px if exit_px is not None else last
    ret = sign * (px / entry - 1) if px and entry else None
    mfe = max((sign * ((hi if sign > 0 else lo) / entry - 1) for _, hi, lo, _ in path), default=None) if entry else None
    mae = min((sign * ((lo if sign > 0 else hi) / entry - 1) for _, hi, lo, _ in path), default=None) if entry else None
    return {"return": round(ret, 4) if ret is not None else None, "status": hit or "open",
            "closed_on": hit_on, "exit_price": px, "last_close": last,
            "max_favourable": round(mfe, 4) if mfe is not None else None,
            "max_adverse": round(mae, 4) if mae is not None else None}
