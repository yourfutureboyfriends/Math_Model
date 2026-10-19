"""
Portfolio construction for simulated option trades: one account, marked to the model mid every close, cash earning
the T-bill rate (like CBOE's fully collateralised strategy indices), defined-risk margin = each spread's maximum loss.

Each session: positions are marked; trades reaching their exit close at the simulated exit value; then new
candidates (decided at the previous close) are taken in score order while every limit holds:

  max_positions        concurrent spreads (all strategies)
  max_per_underlying   spreads per underlying (default 1)
  max_per_sector       spreads per sector (ETFs count as one "ETF" sector)
  risk_per_trade       maximum loss of a new spread, as a fraction of NAV (sets the contract count, whole contracts)
  max_total_risk       sum of open maximum losses ÷ NAV (buying-power use)
  alloc                optional {strategy: share of max_total_risk}
  corr_max             skip a candidate whose 63-session return correlation with an open position's underlying is
                       above this (1.0 = off)
  delta_limit          |portfolio dollar delta| ÷ NAV after the trade (None = off); vega_limit: |dollar vega per vol
                       point| ÷ NAV
  dd_soft / dd_hard    NAV drawdown at which new risk is halved / no new trades are opened
  max_adv_frac         contract notional ≤ this fraction of the underlying's traded value (capacity)
  gate                 optional {strategy: [T] risk multiplier} from a regime model, read at the decision close
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional

import numpy as np

DEFAULT = {"capital": 1_000_000.0, "max_positions": 10, "max_per_underlying": 1, "max_per_sector": 3,
           "risk_per_trade": 0.02, "max_total_risk": 0.30, "alloc": None, "corr_max": 1.0, "delta_limit": None,
           "vega_limit": None, "dd_soft": 0.10, "dd_hard": 0.25, "max_adv_frac": 0.01}


def _value_paths(ts: Dict[str, Any], ex: Dict[str, Any]) -> np.ndarray:
    """Per selected trade: the mark each day of its life, with the exit day replaced by the exit value net of the closing
    fee; NaN after the exit."""
    V = ts["M"][ex["sel"]].astype(float)
    n, H1 = V.shape
    d = np.arange(H1)[None, :]
    rows = np.arange(n)
    V[rows, np.minimum(ex["exit_d"], H1 - 1)] = ex["exit_value"] - ex["close_fee"]
    V[d > ex["exit_d"][:, None]] = np.nan
    return V


def run(books: List[Dict[str, Any]], panel, cfg: Optional[Dict[str, Any]] = None, start: Optional[int] = None,
        end: Optional[int] = None, gate: Optional[Dict[str, np.ndarray]] = None, record_trades: bool = True,
        greeks: bool = False) -> Dict[str, Any]:
    """books: [{"strategy": name, "ts": simulate(...), "ex": apply_exits(...)}]. start/end: session positions — only
    trades decided in [start, end) open; the account runs to `end` (or the last session)."""
    c = {**DEFAULT, **(cfg or {})}
    Tn = len(panel.dates)
    end = Tn if end is None else min(end, Tn)
    rf_d = panel.rf / 252.0
    px = panel.a["px"]
    close = panel.a["close"]
    sector = [panel.info[t].get("sector") or "Unknown" for t in panel.tickers]
    # flatten candidates
    tabs = []
    for b, bk in enumerate(books):
        ts, ex = bk["ts"], bk["ex"]
        sel = ex["sel"]
        V = _value_paths(ts, ex)
        bk["_V"] = V
        bk["_G"] = {g: ts["G"][g][sel] for g in ts["G"]} if greeks and "G" in ts else None
        sc = ts["score"][sel].astype(float)
        rank = np.argsort(np.argsort(-sc)) / max(len(sc) - 1, 1)              # within-strategy rank (0 = best)
        tabs.append({"b": np.full(len(sel), b), "row": np.arange(len(sel)), "t0": ts["t0"][sel], "t_dec": ts["t_dec"][sel],
                     "j": ts["j"][sel], "risk": ts["max_loss"][sel] + 2 * ts["comm"][sel], "score": sc,
                     "rank": rank, "exit": ts["t0"][sel] + ex["exit_d"]})
    cat = {k: np.concatenate([t[k] for t in tabs]) if tabs else np.array([]) for k in
           ("b", "row", "t0", "t_dec", "j", "risk", "score", "rank", "exit")}
    lo = 0 if start is None else start
    ok = (cat["t_dec"] >= lo) & (cat["t_dec"] < end - 1) if len(cat["t0"]) else np.array([], bool)
    by_day: Dict[int, List[int]] = defaultdict(list)
    for i in np.nonzero(ok)[0][np.lexsort((cat["rank"][ok],))]:
        by_day[int(cat["t0"][i])].append(int(i))
    names = [bk["strategy"] for bk in books]
    first = min(by_day) if by_day else lo
    t_begin = max(lo, first - 1) if start is None else lo
    nav = c["capital"]
    peak = nav
    held: List[Dict[str, Any]] = []
    dates, navs, npos, risk_used, cash_int = [], [], [], [], []
    strat_pnl = {s: [] for s in set(names)}
    gk = {"delta": [], "gamma": [], "theta": [], "vega": []} if greeks else None
    trades: List[Dict[str, Any]] = []
    costs = {"commissions": 0.0, "spread_entry": 0.0, "spread_exit": 0.0, "assignment": 0.0}
    rets = []
    for t in range(t_begin, end):
        # 1) mark and close
        pnl = 0.0
        sp = defaultdict(float)
        prev_pos_value = sum(h["n"] * 100 * h["v"] for h in held)
        still = []
        for h in held:
            bk = books[h["b"]]
            d = t - h["t0"]
            v = bk["_V"][h["row"], d] if d < bk["_V"].shape[1] else np.nan
            if not np.isfinite(v):
                v = h["v"]
            dp = h["n"] * 100 * (v - h["v"])
            pnl += dp
            sp[bk["strategy"]] += dp
            h["v"] = v
            if t >= h["exit"]:
                _close(h, bk, trades, costs, panel, record_trades)
            else:
                still.append(h)
        held = still
        interest = (nav - prev_pos_value) * rf_d[t]
        nav_new = nav + pnl + interest
        # 2) open new trades (decided at the previous close, filled at this close)
        peak = max(peak, nav_new)
        dd = nav_new / peak - 1
        dd_mult = 0.0 if dd <= -c["dd_hard"] else 0.5 if dd <= -c["dd_soft"] else 1.0
        if dd_mult > 0 and t in by_day:
            risk_now = sum(h["risk$"] for h in held)
            risk_by = defaultdict(float)
            for h in held:
                risk_by[books[h["b"]]["strategy"]] += h["risk$"]
            for i in by_day[t]:
                if len(held) >= c["max_positions"]:
                    break
                b, row, j = int(cat["b"][i]), int(cat["row"][i]), int(cat["j"][i])
                bk = books[b]
                s = bk["strategy"]
                mult = 1.0
                if gate is not None and s in gate:
                    mult = float(gate[s][int(cat["t_dec"][i])])
                    if not mult > 0:
                        continue
                if sum(1 for h in held if h["j"] == j) >= c["max_per_underlying"]:
                    continue
                if sum(1 for h in held if sector[h["j"]] == sector[j]) >= c["max_per_sector"]:
                    continue
                if c["corr_max"] < 1.0 and held and t > 64:
                    rj = np.diff(np.log(close[t - 64:t, j].astype(float)))
                    hs = [np.diff(np.log(close[t - 64:t, h["j"]].astype(float))) for h in held]
                    if np.isfinite(rj).all() and any(np.isfinite(x).all() and np.corrcoef(rj, x)[0, 1] > c["corr_max"] for x in hs):
                        continue
                unit = 100 * float(cat["risk"][i])
                n = int(c["risk_per_trade"] * mult * dd_mult * nav_new // unit)
                adv = float(panel.a["adv"][t, j]) if np.isfinite(panel.a["adv"][t, j]) else 0.0
                S0 = float(px[t, j])
                if S0 > 0:
                    n = min(n, int(c["max_adv_frac"] * adv // (100 * S0)))
                if n < 1:
                    continue
                r_add = n * unit
                if risk_now + r_add > c["max_total_risk"] * nav_new:
                    continue
                if c["alloc"] and risk_by[s] + r_add > c["alloc"].get(s, 0.0) * c["max_total_risk"] * nav_new:
                    continue
                G = bk["_G"]
                if G is not None and (c["delta_limit"] is not None or c["vega_limit"] is not None):
                    dl = n * 100 * G["delta"][row, 0] * S0
                    vg = n * 100 * G["vega"][row, 0]
                    cur_d = sum(h["n"] * 100 * books[h["b"]]["_G"]["delta"][h["row"], t - h["t0"]] * px[t, h["j"]] for h in held
                                if books[h["b"]]["_G"] is not None and np.isfinite(books[h["b"]]["_G"]["delta"][h["row"], t - h["t0"]]))
                    cur_v = sum(h["n"] * 100 * books[h["b"]]["_G"]["vega"][h["row"], t - h["t0"]] for h in held
                                if books[h["b"]]["_G"] is not None and np.isfinite(books[h["b"]]["_G"]["vega"][h["row"], t - h["t0"]]))
                    if c["delta_limit"] is not None and abs(cur_d + dl) > c["delta_limit"] * nav_new:
                        continue
                    if c["vega_limit"] is not None and abs(cur_v + vg) > c["vega_limit"] * nav_new:
                        continue
                ts = bk["ts"]
                sel = bk["ex"]["sel"][row]
                basis = float(ts["E"][sel] + ts["comm"][sel])
                v0 = bk["_V"][row, 0]
                dp = n * 100 * (v0 - basis)                                    # the entry day: fees and half the spread
                pnl_entry = dp
                nav_new += pnl_entry
                sp[s] += pnl_entry
                costs["commissions"] += n * 100 * float(ts["comm"][sel])
                costs["spread_entry"] += n * 100 * float(ts["E"][sel] - ts["M"][sel, 0])
                h = {"b": b, "row": row, "sel": int(sel), "t0": t, "j": j, "n": n, "v": float(v0), "risk$": r_add,
                     "exit": int(cat["exit"][i]), "entry_nav": nav_new}
                held.append(h)
                risk_now += r_add
                risk_by[s] += r_add
                if h["exit"] <= t:
                    _close(h, bk, trades, costs, panel, record_trades)
                    held.remove(h)
        rets.append(nav_new / nav - 1 if nav > 0 else 0.0)
        nav = nav_new
        dates.append(t)
        navs.append(nav)
        npos.append(len(held))
        risk_used.append(sum(h["risk$"] for h in held) / nav if nav > 0 else 0.0)
        cash_int.append(interest)
        for s in strat_pnl:
            strat_pnl[s].append(sp.get(s, 0.0))
        if greeks:
            tot = {"delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0}
            for h in held:
                G = books[h["b"]]["_G"]
                if G is None:
                    continue
                d = t - h["t0"]
                S = float(px[t, h["j"]])
                vals = {g: G[g][h["row"], d] for g in tot}
                if not all(np.isfinite(v) for v in vals.values()):
                    continue
                m = h["n"] * 100
                tot["delta"] += m * vals["delta"] * S
                tot["gamma"] += m * 0.5 * vals["gamma"] * (0.01 * S) ** 2
                tot["theta"] += m * vals["theta"]
                tot["vega"] += m * vals["vega"]
            for g in gk:
                gk[g].append(tot[g] / nav if nav > 0 else 0.0)
    for h in held:                                                         # still open at the end
        _close(h, books[h["b"]], trades, costs, panel, record_trades, still_open=True)
    out = {"t": np.array(dates), "nav": np.array(navs), "ret": np.array(rets), "positions": np.array(npos),
           "risk_used": np.array(risk_used), "interest": float(np.sum(cash_int)),
           "strategy_pnl": {s: np.array(v) for s, v in strat_pnl.items()}, "costs": costs, "trades": trades,
           "config": {k: v for k, v in c.items() if k != "alloc"} | {"alloc": c["alloc"]}}
    if greeks:
        out["greeks"] = {g: np.array(v) for g, v in gk.items()}
    return out


def _close(h, bk, trades, costs, panel, record: bool, still_open: bool = False) -> None:
    ts, ex = bk["ts"], bk["ex"]
    row, sel = h["row"], h["sel"]
    reason = int(ex["reason"][row])
    m = h["n"] * 100
    exit_d = int(ex["exit_d"][row])
    fee = float(ex["close_fee"][row])
    costs["commissions"] += m * fee
    if reason in (0, 1, 2):
        mid_exit = float(ts["M"][sel, exit_d])
        costs["spread_exit"] += m * (mid_exit - float(ex["exit_value"][row]))
    assigned = reason == 3 or (reason == 4 and bool(ts["exp_assigned"][sel]))
    if reason == 3:
        costs["assignment"] += m * float(ts["assign_cost_early"][sel])
    elif reason == 4:
        costs["assignment"] += m * float(ts["assign_cost_exp"][sel])
    if not record:
        return
    t0 = h["t0"]
    pnl = m * float(ex["pnl"][row])
    trades.append({"strategy": bk["strategy"], "ticker": panel.tickers[h["j"]], "sector": panel.info[panel.tickers[h["j"]]].get("sector"),
                   "entry": str(panel.dates[t0].date()), "exit": str(panel.dates[min(t0 + exit_d, len(panel.dates) - 1)].date()),
                   "days": exit_d, "contracts": h["n"], "reason": ["profit_take", "stop_loss", "time", "early_assignment",
                                                                  "expiry", "open"][reason] if not still_open else "open",
                   "pnl": round(pnl, 2), "r": round(float(ex["r"][row]), 4), "ret": round(pnl / h["entry_nav"], 6),
                   "credit": bool(ts["credit"][sel]), "premium": round(float(-ts["E"][sel] if ts["credit"][sel] else ts["E"][sel]), 4),
                   "width": round(float(ts["W"][sel]), 2), "max_loss": round(float(ts["max_loss"][sel]), 4),
                   "premium_to_risk": round(float((-ts["E"][sel] if ts["credit"][sel] else ts["max_profit"][sel]) / ts["max_loss"][sel]), 3),
                   "dte": int(ts["exp_day"][sel] - panel.dates[t0].to_datetime64().astype("datetime64[D]").astype(np.int64)),
                   "spot": round(float(ts["S0"][sel]), 2), "strikes": [round(float(k), 2) for k in ts["K"][sel] if np.isfinite(k)],
                   "iv": round(float(ts["atm0"][sel]), 4), "iv_class": "observed" if ts["iv_cls"][sel] == 1 else "model",
                   "iv_rv": round(float(ts["feat"]["iv_rv"][sel]), 3) if np.isfinite(ts["feat"]["iv_rv"][sel]) else None,
                   "assigned": bool(assigned), "risk": round(h["risk$"], 2)})
