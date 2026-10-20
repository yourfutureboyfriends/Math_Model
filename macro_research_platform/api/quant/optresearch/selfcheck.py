"""
Stage 1 — correctness checks on synthetic and textbook cases (also run by api/tests/test_optresearch.py). Each check
returns {name, passed, detail}; a stage-1 experiment fails if any check fails.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List

import numpy as np


def _check(name: str, ok: bool, detail: Any) -> Dict[str, Any]:
    return {"name": name, "passed": bool(ok), "detail": detail}


def run_all() -> List[Dict[str, Any]]:
    from api.quant.optresearch import market, portfolio as pf, pricing, simulate as sim, strategies as st, validate, vol
    out = []
    # 1 BSM: textbook value (S=100, K=100, T=1, r=5%, σ=20%: call 10.4506, put 5.5735) and put–call parity
    g_c = pricing.bsm(100, 100, 1.0, 0.05, 0.0, 0.2, True)
    g_p = pricing.bsm(100, 100, 1.0, 0.05, 0.0, 0.2, False)
    parity = g_c["value"] - g_p["value"] - (100 - 100 * math.exp(-0.05))
    out.append(_check("BSM textbook values and put–call parity", abs(g_c["value"] - 10.4506) < 1e-3 and
                      abs(g_p["value"] - 5.5735) < 1e-3 and abs(parity) < 1e-9,
                      {"call": round(float(g_c["value"]), 4), "put": round(float(g_p["value"]), 4), "parity_error": float(parity)}))
    # 2 Greeks against finite differences
    h = 1e-3
    up = pricing.bsm(100 + h, 95, 0.25, 0.03, 0.01, 0.25, False)["value"]
    dn = pricing.bsm(100 - h, 95, 0.25, 0.03, 0.01, 0.25, False)["value"]
    g = pricing.bsm(100, 95, 0.25, 0.03, 0.01, 0.25, False)
    fd_delta = (up - dn) / (2 * h)
    fd_gamma = (up - 2 * g["value"] + dn) / h ** 2
    vu = pricing.bsm(100, 95, 0.25, 0.03, 0.01, 0.26, False)["value"]
    tu = pricing.bsm(100, 95, 0.25 - 1 / 365, 0.03, 0.01, 0.25, False)["value"]
    ok = (abs(fd_delta - g["delta"]) < 1e-5 and abs(fd_gamma - g["gamma"]) < 1e-3 and abs((vu - g["value"]) - g["vega"]) < 2e-3
          and abs((tu - g["value"]) - g["theta"]) < 2e-3)
    out.append(_check("Greeks match finite differences", ok, {"delta": [round(float(g["delta"]), 6), round(float(fd_delta), 6)],
                                                              "gamma": [round(float(g["gamma"]), 6), round(float(fd_gamma), 6)]}))
    # 3 strike by delta: the rounded-off strike's delta is close to the target
    K = pricing.strike_for_delta(np.array([100.0]), np.array([45 / 365]), np.array([0.03]), np.array([0.0]), np.array([0.2]),
                                 0.25, False, "index")
    v = pricing.smile_vol(0.2, 100.0, K, 45 / 365, "index")
    d = pricing.bsm(100.0, K, 45 / 365, 0.03, 0.0, v, False)["delta"]
    out.append(_check("Strike for a 25-delta put has delta −0.25", abs(float(d[0]) + 0.25) < 0.005, {"K": float(K[0]), "delta": float(d[0])}))
    # 4–7 simulation on a synthetic market: bounded payoffs, reconciliation, fair-value null
    p = market.synthetic(1500, ["SPY", "AAA", "BBB", "CCC", "DDD", "EEE"])
    surf = vol.synthetic_surface(p)
    f = st.features(p, surf)
    days = st.decision_days(p.dates, "2015-06-01")
    day = p.dates.values.astype("datetime64[D]").astype(np.int64)
    books, bounds, nulls = [], [], {}
    for name in st.STRATEGIES:
        par = st.loosest(name)
        cand = {"t": np.repeat(days, 6), "j": np.tile(np.arange(6), len(days)), "score": np.ones(len(days) * 6, np.float32),
                "feat": {k: np.ones(len(days) * 6, np.float32) for k in ("iv_rv", "iv_pct", "mom_rank", "adx", "range_z",
                                                                         "mom6", "spy_ret20")}}
        ts = sim.simulate(p, surf, name, par, cand, greeks=True)
        ex = sim.apply_exits(ts, None, None, 0, day)
        done = ex["reason"] == 4
        worst = float(((ex["pnl"][done] + ts["comm"][ex["sel"]][done] * 2) / ts["max_loss"][ex["sel"]][done]).min()) if done.any() else 0
        best = float((ex["pnl"][done] / ts["max_profit"][ex["sel"]][done]).max()) if done.any() else 0
        bounds.append((name, round(worst, 4), round(best, 4)))
        nulls[name] = round(float(ex["r"].mean()), 4)
        d0 = st.DEFAULTS[name]
        books.append({"strategy": name, "ts": ts, "ex": sim.apply_exits(ts, d0["profit_take"], d0["stop_loss"], d0["exit_dte"], day)})
    out.append(_check("Held to expiry, no spread loses more than its maximum loss (beyond assignment cost) or gains more than "
                      "its maximum profit", all(w >= -1.0 - 0.02 and b <= 1.0 + 1e-6 for _, w, b in bounds), bounds))
    res = pf.run(books, p, {"max_positions": 10, "max_per_sector": 10}, greeks=True)
    tp = sum(t["pnl"] for t in res["trades"])
    gap = (res["nav"][-1] - 1e6) - (tp + res["interest"])
    out.append(_check("Portfolio NAV reconciles to trade P&L plus interest", abs(gap) < 1.0, {"gap_dollars": round(float(gap), 4),
                                                                                          "trades": len(res["trades"])}))
    out.append(_check("Fair-value market (IV = realised vol): no strategy shows a positive edge before it is earned",
                      all(v < 0.05 for v in nulls.values()), {"mean_R_held_to_expiry": nulls}))
    # 8 exit logic: a profit-take must trigger no later than holding, and never on the entry day
    ts = books[0]["ts"]
    a = sim.apply_exits(ts, 0.5, None, 0, day)
    out.append(_check("Exits trigger after entry and no later than expiry", bool((a["exit_d"] >= 1).all() and
                      (a["exit_d"] <= ts["H"][a["sel"]]).all()), {"min_exit_day": int(a["exit_d"].min())}))
    # 9 leakage: features on truncated data equal the full-data features up to the cut
    chk = validate.prefix_invariance(p, lambda q: vol.synthetic_surface(q), st.features)
    out.append(_check("No look-ahead in features (prefix invariance)", chk["passed"], chk))
    # 10 costs are monotone: wider spreads never improve a trade
    par = st.loosest("bull_put")
    cand = {"t": days[:40], "j": np.zeros(40, int), "score": np.ones(40, np.float32),
            "feat": {k: np.ones(40, np.float32) for k in ("iv_rv", "iv_pct", "mom_rank", "adx", "range_z", "mom6", "spy_ret20")}}
    lo = sim.apply_exits(sim.simulate(p, surf, "bull_put", par, cand), 0.5, 2.0, 21, day)
    hi = sim.apply_exits(sim.simulate(p, surf, "bull_put", par, cand, costs={"spread_mult": 2.0}), 0.5, 2.0, 21, day)
    out.append(_check("Wider spreads lower P&L", float(hi["pnl"].sum()) < float(lo["pnl"].sum()),
                      {"pnl_1x": round(float(lo["pnl"].sum()), 3), "pnl_2x": round(float(hi["pnl"].sum()), 3)}))
    return out
