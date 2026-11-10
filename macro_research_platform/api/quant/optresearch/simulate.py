"""
Vectorised trade simulation: every candidate spread is priced on every day of its life at once (trades × days × legs
arrays, in memory-bounded chunks), then exit rules are applied to the stored paths — so a grid of exit rules costs no
re-pricing.

Execution (conservative, per leg — no mid fills):
  open      buy each long leg at the ask, sell each short leg at the bid (the "natural" price);
  close     sell longs at the bid, buy shorts back at the ask;
  expiry    cash value at intrinsic; a short leg in the money whose hedge is not (between the strikes) is assigned
            physically — the stock is closed next session at assign_bps of its price (pin and overnight gap risk are
            not modelled beyond that);
  early     American exercise: a short call in the money before an ex-dividend date whose time value is below the
            dividend, or a short put whose time value is below max(K·(1−e^(−rT)), $0.02), is assigned at that close —
            the spread is closed at intrinsic for the short leg, the bid for the longs, plus the stock cost.
  fees      commission + exchange/regulatory fees per contract per leg, on opening and on closing (none at expiry).

Quoted half-spread per leg = max(floor, pct × mid) × (1 + max(0, VIX − 20) / 25) × spread_mult + slippage ($ per leg),
by liquidity tier of the underlying (`TIERS`) — an assumption, not observed quotes; stress-tested in validation.
iv_mult scales every implied volatility (a model-risk stress: CBOE CNDR replication shows the model prices
out-of-the-money index options richer than the market did).
"""
from __future__ import annotations

from typing import Any, Dict, Optional

import numpy as np

from api.quant.optresearch import pricing, vol as volmod

INDEX_ETFS = {"SPY", "QQQ", "IWM", "DIA"}
# tier → (pct of mid, floor in $) for the half-spread
TIERS = {"index": (0.010, 0.005), "etf": (0.020, 0.010), "large": (0.030, 0.010), "stock": (0.050, 0.025),
         "small": (0.080, 0.050)}
TIER_ORDER = ["index", "etf", "large", "stock", "small"]
DEFAULT_COSTS = {"commission": 0.65, "fees": 0.02, "spread_mult": 1.0, "slippage": 0.0, "iv_mult": 1.0, "assign_bps_etf": 2.0,
                 "assign_bps_stock": 5.0, "put_exercise_floor": 0.02}
REASONS = ["profit_take", "stop_loss", "time", "early_assignment", "expiry", "open"]
MAX_H = 140                                                           # sessions: covers 90-DTE trades


def tier_of(sym: str, kind: str, adv: float) -> str:
    """Liquidity tier of an underlying (index, etf, or by average dollar volume) for costs."""
    if sym in INDEX_ETFS:
        return "index"
    if kind == "etf":
        return "etf"
    if adv >= 1e9:
        return "large"
    if adv >= 1e8:
        return "stock"
    return "small"


def _legs(name: str, n: int):
    """(is_call [n,4], qty [n,4]) — leg order: put long-wing, put short/long, call short/long, call long-wing."""
    call = np.zeros((n, 4), bool)
    qty = np.zeros((n, 4), np.int8)
    if name == "bull_put":
        qty[:, 0], qty[:, 1] = 1, -1
    elif name == "bear_put":
        qty[:, 0], qty[:, 1] = -1, 1                                  # leg 0: short (lower) put, leg 1: long put
    elif name == "bull_call":
        call[:, 2:] = True
        qty[:, 2], qty[:, 3] = 1, -1                                  # leg 2: long (lower) call, leg 3: short call
    elif name == "iron_condor":
        call[:, 2:] = True
        qty[:] = [1, -1, -1, 1]
    return call, qty


def strikes(name: str, p: Dict[str, Any], S, T, r, q, atm, kind_slopes):
    """Strike grid [n,4] for the strategy at entry (listed increments; short legs rounded away from the money)."""
    ps, cs, pk = kind_slopes
    n = len(S)
    K = np.full((n, 4), np.nan)
    inc = pricing.strike_increment(S)
    wid = lambda w: np.maximum(inc, np.round(w * S / inc) * inc)
    put = lambda d: pricing.strike_for_delta(S, T, r, q, atm, d, False, "index", put_slope=ps, call_slope=cs)
    call = lambda d: pricing.strike_for_delta(S, T, r, q, atm, d, True, "index", put_slope=ps, call_slope=cs)
    if name == "bull_put":
        K[:, 1] = pricing.round_strike(put(p["short_delta"]), S, False)
        K[:, 0] = K[:, 1] - wid(p["width"])
    elif name == "iron_condor":
        K[:, 1] = pricing.round_strike(put(p["short_delta"]), S, False)
        K[:, 0] = K[:, 1] - wid(p["width"])
        K[:, 2] = pricing.round_strike(call(p["short_delta"]), S, True)
        K[:, 3] = K[:, 2] + wid(p["width"])
    elif name == "bull_call":
        K[:, 2] = np.maximum(inc, np.round(call(p["long_delta"]) / inc) * inc)
        K[:, 3] = np.maximum(pricing.round_strike(call(p["short_delta"]), S, True), K[:, 2] + inc)
    elif name == "bear_put":
        K[:, 1] = np.maximum(inc, np.round(put(p["long_delta"]) / inc) * inc)
        K[:, 0] = np.minimum(pricing.round_strike(put(p["short_delta"]), S, False), K[:, 1] - inc)
    K = np.where(K > 0, K, np.nan)
    return K


def simulate(panel, surf: Dict[str, Any], name: str, p: Dict[str, Any], cand: Dict[str, np.ndarray],
             costs: Optional[Dict[str, float]] = None, greeks: bool = False, smile: Optional[Dict[str, tuple]] = None,
             max_cells: int = 6_000_000) -> Dict[str, Any]:
    """Price every candidate trade's legs over its life. Returns per-trade scalars and per-day paths."""
    c = {**DEFAULT_COSTS, **(costs or {})}
    smile = smile or pricing.SMILE
    a = panel.a
    Tn = len(panel.dates)
    day = panel.dates.values.astype("datetime64[D]").astype(np.int64)
    t_dec, j = cand["t"].astype(int), cand["j"].astype(int)
    t0 = t_dec + 1
    ok = t0 < Tn - 1
    t_dec, j, t0 = t_dec[ok], j[ok], t0[ok]
    keep_idx = np.nonzero(ok)[0]
    n = len(t0)
    tick = panel.tickers
    kinds = np.array([surf["kinds"].get(tick[x], "stock") for x in range(len(tick))])
    is_index = np.array([t in INDEX_ETFS for t in tick])
    # expiries: weekly Fridays for the index ETFs, monthly for everything else
    exp_w, pos_w = pricing.expiry_table(panel.dates, True)
    exp_m, pos_m = pricing.expiry_table(panel.dates, False)
    weekly = is_index[j]
    ei_w = pricing.pick_expiry(day[t0], int(p["dte"]), exp_w)
    ei_m = pricing.pick_expiry(day[t0], int(p["dte"]), exp_m)
    exp_day = np.where(weekly, exp_w[ei_w], exp_m[ei_m])
    exp_pos = np.where(weekly, pos_w[ei_w], pos_m[ei_m])            # last session on/before expiry (may be ≥ Tn)
    beyond = exp_day > day[-1]
    exp_pos = np.where(beyond, Tn + (exp_day - day[-1]), exp_pos)    # expiry after the data: open at the end
    H = np.minimum(exp_pos - t0, MAX_H)
    good = H >= 1
    # entry state
    S0 = a["px"][t0, j].astype(float)
    T0 = (exp_day - day[t0]) / 365.0
    r0 = panel.rf[t0]
    qy = _div_yield(panel)
    q0 = qy[t0, j]
    beta = np.where(np.array([k == "stock" for k in kinds])[j], 0.5, 1.0)
    atm30 = surf["atm"][t0, j].astype(float)
    ratio0 = volmod.term_ratio(surf["pillars"], surf["P"], t0, np.maximum(T0, 9 / 365))
    atm0 = atm30 * np.nan_to_num(ratio0, nan=1.0) ** beta * c["iv_mult"]
    ps = np.array([smile.get(k, smile["stock"])[0] for k in kinds])[j]
    cs = np.array([smile.get(k, smile["stock"])[1] for k in kinds])[j]
    K = strikes(name, p, S0, T0, r0, q0, atm0, (ps, cs, None))
    callm, qty = _legs(name, n)
    good &= np.isfinite(S0) & (S0 > 0) & np.isfinite(atm0) & np.all(np.isfinite(K) | (qty == 0), axis=1)
    adv0 = a["adv"][t0, j]
    adv0 = np.nan_to_num(adv0)
    tiers = np.where(is_index[j], 0, np.where(kinds[j] != "stock", 1, np.where(adv0 >= 1e9, 2, np.where(adv0 >= 1e8, 3, 4)))
                     ).astype(np.int8)
    pct = np.array([TIERS[t][0] for t in TIER_ORDER])[tiers]
    floor = np.array([TIERS[t][1] for t in TIER_ORDER])[tiers]
    assign_bps = np.where(np.array([kinds[jj] != "stock" for jj in j]), c["assign_bps_etf"], c["assign_bps_stock"]) / 1e4
    vix = surf["vix"]
    Hmax = int(H[good].max()) if good.any() else 1
    M = np.full((n, Hmax + 1), np.nan, np.float32)
    Lq = np.full((n, Hmax + 1), np.nan, np.float32)
    G = {g: np.full((n, Hmax + 1), np.nan, np.float32) for g in ("delta", "gamma", "theta", "vega")} if greeks else None
    E = np.full(n, np.nan)
    X = np.full(n, np.nan)                                            # value at expiry (after assignment cost)
    exp_assigned = np.zeros(n, bool)
    early_d = np.full(n, -1, np.int32)
    early_v = np.full(n, np.nan)
    acx = np.zeros(n)                                                 # stock cost of an assignment at expiry
    ace = np.zeros(n)                                                 # … of an early assignment
    legs_n = (qty != 0).sum(axis=1)
    idx_all = np.nonzero(good)[0]
    step = max(1, max_cells // ((Hmax + 1) * 4))
    for s in range(0, len(idx_all), step):
        k = idx_all[s:s + step]
        d = np.arange(Hmax + 1)[None, :]
        tt = t0[k, None] + d
        live = (d <= H[k, None]) & (tt < Tn)
        ttc = np.minimum(tt, Tn - 1)
        jj = j[k, None]
        S = a["px"][ttc, jj].astype(float)
        Tcal = np.maximum((exp_day[k, None] - day[ttc]) / 365.0, 0.0)
        at_exp = live & (tt == exp_pos[k, None])
        Tcal = np.where(at_exp, 0.0, Tcal)
        r = panel.rf[ttc]
        q = qy[ttc, jj]
        a30 = surf["atm"][ttc, jj].astype(float)
        rat = volmod.term_ratio(surf["pillars"], surf["P"], ttc, np.maximum(Tcal, 9 / 365))
        atmT = a30 * np.nan_to_num(rat, nan=1.0) ** beta[k, None] * c["iv_mult"]
        vm = (1 + np.maximum(0.0, vix[ttc] * 100 - 20) / 25) * c["spread_mult"]
        mid_sum = np.zeros(S.shape)
        liq = np.zeros(S.shape)
        ent = np.zeros(len(k))
        asg = np.zeros(S.shape)                                        # value if early-assigned this close
        early = np.zeros(S.shape, bool)
        intr_sum = np.zeros(S.shape)
        gs = {g: np.zeros(S.shape) for g in ("delta", "gamma", "theta", "vega")} if greeks else None
        exp_short_itm_unhedged = np.zeros(len(k), bool)
        for L in range(4):
            qL = qty[k, L].astype(float)
            if not np.any(qL):
                continue
            KL = K[k, L][:, None]
            cl = callm[k, L][:, None]
            v = pricing.smile_vol(atmT, S, KL, np.maximum(Tcal, 1 / 365), "index", ps[k, None], cs[k, None])
            g = pricing.bsm(S, KL, Tcal, r, q, v, cl)
            mid = g["value"]
            h = np.maximum(floor[k, None], pct[k, None] * mid) * vm + c["slippage"]
            bid, ask = np.maximum(mid - h, 0.0), mid + h
            intr = np.where(cl, np.maximum(S - KL, 0.0), np.maximum(KL - S, 0.0))
            long_ = qL[:, None] > 0
            mid_sum += qL[:, None] * mid
            liq += np.where(long_, bid, -ask) * np.abs(qL[:, None])
            ent += np.where(qL > 0, ask[:, 0], -bid[:, 0]) * np.abs(qL)
            intr_sum += qL[:, None] * intr
            if greeks:
                for gname in gs:
                    gs[gname] += qL[:, None] * g[gname]
            short = (qL < 0)[:, None]
            ext = mid - intr
            nxt = np.minimum(ttc + 1, Tn - 1)
            divnext = a["exdiv"][nxt, jj].astype(float)
            ec = cl & (S > KL) & (divnext > 0) & (ext < divnext * S)
            ep = ~cl & (KL > S) & (ext < np.maximum(KL * (1 - np.exp(-r * np.maximum(Tcal, 0))), c["put_exercise_floor"]))
            ex_L = short & (ec | ep) & live & (Tcal > 0)
            early |= ex_L
            # if assigned early this close: the assigned short at intrinsic, other shorts bought at the ask, longs sold
            asg += np.where(long_, bid, -np.where(ex_L, intr, ask)) * np.abs(qL[:, None])
        # expiry: a vertical pair with exactly one leg in the money leaves a stock position after exercise or
        # assignment (the other leg expires worthless) — closed next session at assign_bps of the price
        e_rel = np.clip(exp_pos[k] - t0[k], 0, Hmax)
        rowsel = np.arange(len(k))
        S_e = S[rowsel, e_rel]
        for L0, L1 in ((0, 1), (2, 3)):
            if not (np.any(qty[k, L0]) and np.any(qty[k, L1])):
                continue
            i0 = np.where(callm[k, L0], S_e > K[k, L0], S_e < K[k, L0])
            i1 = np.where(callm[k, L1], S_e > K[k, L1], S_e < K[k, L1])
            exp_short_itm_unhedged |= (i0 ^ i1) & (qty[k, L0] != 0) & (qty[k, L1] != 0)
        M[k] = np.where(live, mid_sum, np.nan)
        Lq[k] = np.where(live, np.where(at_exp, intr_sum, liq), np.nan)
        if greeks:
            for gname in gs:
                G[gname][k] = np.where(live & ~at_exp, gs[gname], np.where(live, 0.0, np.nan))
        E[k] = ent
        exp_ok = exp_pos[k] < Tn
        cost_exp = np.where(exp_short_itm_unhedged, assign_bps[k] * S_e, 0.0)
        X[k] = np.where(exp_ok, intr_sum[rowsel, e_rel] - cost_exp, np.nan)
        exp_assigned[k] = exp_ok & exp_short_itm_unhedged
        acx[k] = np.where(exp_ok, cost_exp, 0.0)
        early &= ~at_exp
        has = early.any(axis=1)
        fd = np.where(has, early.argmax(axis=1), -1)
        early_d[k] = fd
        ev = asg[rowsel, np.maximum(fd, 0)] - assign_bps[k] * S[rowsel, np.maximum(fd, 0)]
        early_v[k] = np.where(has, ev, np.nan)
        ace[k] = np.where(has, assign_bps[k] * S[rowsel, np.maximum(fd, 0)], 0.0)
    credit = np.array([bool(name in ("bull_put", "iron_condor"))] * n)
    width = np.where(np.isfinite(K), K, 0)
    w_put = np.abs(width[:, 1] - width[:, 0])
    w_call = np.abs(width[:, 3] - width[:, 2])
    W = np.maximum(w_put, w_call)
    max_loss = np.where(credit, W + E, E)                             # E < 0 for credits
    max_profit = np.where(credit, -E, W - E)
    valid = good & np.isfinite(E) & (max_loss > 0) & (max_profit > 0)
    sel = np.nonzero(valid)[0]
    comm = (c["commission"] + c["fees"]) * legs_n / 100.0              # per share, per side
    out = {"name": name, "params": dict(p), "n": int(len(sel)), "t_dec": t_dec[sel], "t0": t0[sel], "j": j[sel],
           "H": H[sel], "exp_pos": exp_pos[sel], "exp_day": exp_day[sel], "K": K[sel], "qty": qty[sel],
           "call": callm[sel], "E": E[sel], "X": X[sel], "W": W[sel], "max_loss": max_loss[sel],
           "max_profit": max_profit[sel], "credit": credit[sel], "comm": comm[sel], "S0": S0[sel], "atm0": atm0[sel],
           "iv_cls": surf["cls"][t0[sel], j[sel]], "tier": tiers[sel], "exp_assigned": exp_assigned[sel],
           "early_d": early_d[sel], "early_v": early_v[sel], "assign_cost_exp": acx[sel], "assign_cost_early": ace[sel], "M": M[sel], "Lq": Lq[sel],
           "score": cand["score"][keep_idx][sel], "feat": {k2: v[keep_idx][sel] for k2, v in cand["feat"].items()},
           "dropped": int(n - len(sel))}
    if greeks:
        out["G"] = {g: v[sel] for g, v in G.items()}
    return out


def _div_yield(panel) -> np.ndarray:
    """Trailing 12-month dividend yield (continuous approximation) per (session, underlying) — causal."""
    key = "_qy"
    if key in panel.meta:
        return panel.meta[key]
    ex = np.nan_to_num(panel.a["exdiv"].astype(float))
    cs = np.cumsum(ex, axis=0)
    lag = np.vstack([np.zeros((252, ex.shape[1])), cs[:-252]]) if len(cs) > 252 else np.zeros_like(cs)
    q = np.clip(cs - lag, 0, 0.15)
    panel.meta[key] = q
    return q


def apply_exits(ts: Dict[str, Any], profit_take: Optional[float], stop_loss: Optional[float], exit_dte: int,
                day: np.ndarray, mask: Optional[np.ndarray] = None) -> Dict[str, np.ndarray]:
    """Exit day (relative to entry), reason and P&L per share (after fees) for each trade under these rules. Triggers
    are checked at each close from the day after entry: profit-take (fraction of the maximum profit), stop-loss
    (credit: multiple of the credit; debit: fraction of the debit), time (calendar days to expiry ≤ exit_dte),
    early assignment, expiry. A trade still open when the data end is marked at its last value ("open")."""
    sel = np.arange(ts["n"]) if mask is None else np.nonzero(mask)[0]
    Lq = ts["Lq"][sel].astype(float)
    E = ts["E"][sel][:, None]
    n, H1 = Lq.shape
    d = np.arange(H1)[None, :]
    live = np.isfinite(Lq)
    pnl = Lq - E
    credit = ts["credit"][sel]
    mp = ts["max_profit"][sel][:, None]
    base_loss = np.where(credit, -ts["E"][sel], ts["E"][sel])[:, None]     # credit received / debit paid
    reason = np.full(n, 5, np.int8)                                         # 5 = open (data ended)
    H = ts["H"][sel]
    exp_rel = ts["exp_pos"][sel] - ts["t0"][sel]
    first = lambda m: np.where(m.any(axis=1), m.argmax(axis=1), 10 ** 6)
    cands = []
    after = (d >= 1) & live & (d < exp_rel[:, None])
    if profit_take is not None:
        cands.append((first(after & (pnl >= profit_take * mp)), 0))
    if stop_loss is not None:
        cands.append((first(after & (pnl <= -stop_loss * base_loss)), 1))
    if exit_dte and exit_dte > 0:
        t_abs = ts["t0"][sel][:, None] + d
        dte = ts["exp_day"][sel][:, None] - day[np.minimum(t_abs, len(day) - 1)]
        cands.append((first(after & (dte <= exit_dte)), 2))
    ed = ts["early_d"][sel]
    cands.append((np.where(ed >= 1, ed, 10 ** 6), 3))
    exp_in = (exp_rel <= H) & np.isfinite(ts["X"][sel])
    cands.append((np.where(exp_in, exp_rel, 10 ** 6), 4))
    best = np.full(n, 10 ** 6)
    for day_k, code in cands:
        better = day_k < best
        best = np.where(better, day_k, best)
        reason = np.where(better, code, reason).astype(np.int8)
    last_live = np.where(live.any(axis=1), H1 - 1 - np.argmax(live[:, ::-1], axis=1), 0)
    is_open = best >= 10 ** 6
    best = np.where(is_open, last_live, best)
    reason = np.where(is_open, 5, reason)
    rows = np.arange(n)
    val = Lq[rows, np.minimum(best, H1 - 1)]
    val = np.where(reason == 3, ts["early_v"][sel], val)
    val = np.where(reason == 4, ts["X"][sel], val)
    close_fee = np.where((reason == 4) | (reason == 5), 0.0, ts["comm"][sel])
    pnl_x = val - ts["E"][sel] - ts["comm"][sel] - close_fee
    ex = best.astype(np.int32)
    return {"sel": sel, "exit_d": ex, "reason": reason.astype(np.int8), "exit_value": val, "pnl": pnl_x,
            "r": pnl_x / ts["max_loss"][sel], "close_fee": close_fee}
