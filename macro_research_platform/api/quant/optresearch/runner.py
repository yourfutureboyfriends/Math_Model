"""
Staged options-research experiments — run as server jobs, checkpointed section by section, with runtime and peak
memory recorded.

  Stage 1  correctness: textbook pricing, Greeks, payoff bounds, accounting, look-ahead, cost monotonicity (synthetic)
  Stage 2  small universe: the four index ETFs (SPY, QQQ, IWM, DIA) — all with OBSERVED at-the-money IV
  Stage 3  intermediate: the 17 ETFs plus the 100 most liquid S&P 500 members (liquidity measured at the end of 2015,
           membership point in time)
  Stage 4  full: every point-in-time S&P 500 member with free price history (including later-removed names) and the
           optionable ETFs, plus a survivorship comparison against today's US list

A smaller stage never stands in for stage 4: results carry their stage, and a configuration exported from stage < 4
is marked "not validated on the full universe" (deploy.py).

Each strategy: successive search on the development segment only (structure grid → exit rules on the best three →
entry filters on the best three), the development choice evaluated on validation, a walk-forward over the pre-declared
structure grid (2018–2023), cost stress, bootstrap, PBO and the deflated Sharpe ratio, then the survival decision.
Then: seven systems compared under identical accounting, regime models, portfolio construction, survivorship, and the
registry updated. The holdout (2024 →) is computed into a sealed file, revealed only on request (and logged).
"""
from __future__ import annotations

import itertools
import json
import math
import resource
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import numpy as np
import pandas as pd

from api.quant.optresearch import (analytics, market, portfolio as pf, regimes, registry, simulate as sim,
                                   strategies as st, validate as va, vol)

ROOT = Path(__file__).resolve().parents[3] / "data" / "processed" / "quant" / "research" / "experiments"
BASELINES = Path(__file__).resolve().parents[3] / "data" / "processed" / "quant" / "research" / "baselines"
INDEX4 = ["SPY", "QQQ", "IWM", "DIA"]
PORT = {"capital": 1_000_000.0, "max_positions": 10, "max_per_underlying": 1, "max_per_sector": 3, "risk_per_trade": 0.02,
        "max_total_risk": 0.30, "dd_soft": 0.10, "dd_hard": 0.25, "max_adv_frac": 0.01, "corr_max": 1.0}
PORT_STAGE2 = {**PORT, "max_per_underlying": 3, "max_per_sector": 99}
MIN_TRADES = 30
LIMITATIONS = [
    "No historical option quotes: option prices are Black–Scholes–Merton values with observed ATM IV (CBOE indices) where "
    "available and modelled IV elsewhere; the smile, term structure (beyond SPY) and bid/ask are modelled.",
    "Listed strikes and expiries are approximated (standard increments; monthly expiries, Friday weeklies for SPY/QQQ/IWM/"
    "DIA); actual listing, open interest and liquidity per contract are not verified.",
    "Single-stock IV omits earnings-event term structure (the pre-earnings IV bump); underlying earnings gaps are real.",
    "American exercise is approximated by early-assignment rules (dividends, deep in-the-money puts); pin risk beyond a "
    "stock-closing cost is not modelled.",
    "Universe: point-in-time S&P 500 membership; removed members without free price history are missing (counted).",
    "Fills at the modelled natural price at the close; no intraday stops (a stop fills at the close that breaches it).",
]


def _rss_mb() -> float:
    r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return round(r / (1 << 20) if sys.platform == "darwin" else r / 1024, 1)


def _key(p: Dict[str, Any]) -> str:
    return json.dumps({k: p[k] for k in sorted(p)}, sort_keys=True, default=str)


class Lab:
    """Data, features and caches for one experiment."""

    def __init__(self, stage: int, say: Callable[[str], None], synthetic: bool = False):
        self.stage, self.say = stage, say
        if synthetic:
            self.panel = market.synthetic(2600, ["SPY", "QQQ", "IWM", "DIA", "AAA", "BBB", "CCC", "DDD"])
            self.surf = vol.synthetic_surface(self.panel)
            self.full = self.panel
        else:
            full = market.build("US+PIT", say=say)
            self.full = full
            names = self._universe(full, stage)
            self.panel = full.subset(names)
            say(f"Implied volatility: observed CBOE indices where available, the fitted model elsewhere ({len(names)} underlyings)…")
            self.surf = vol.surface(self.panel)
        self.port = PORT_STAGE2 if stage == 2 else PORT
        self.dates = self.panel.dates
        self.day = self.dates.values.astype("datetime64[D]").astype(np.int64)
        self.f = st.features(self.panel, self.surf)
        self.days = st.decision_days(self.dates, "2016-01-01")
        self.hold = va.pos(self.dates, va.HOLDOUT_START)                 # first holdout session
        self.val_end = va.pos(self.dates, va.VAL[1]) + 1                  # account runs to the end of validation
        self.eligible = self._eligible()
        self.cands = {n: st.candidates(n, self.f, self.panel, self.days, st.loosest(n), eligible=self.eligible)
                      for n in st.STRATEGIES}
        self._sims: Dict[str, Dict[str, Any]] = {}
        self.smile = None
        self.calibration = None

    @staticmethod
    def _universe(full, stage: int) -> List[str]:
        etfs = [t for t in market.ETFS if t in full.tickers]
        if stage == 2:
            return [t for t in INDEX4 if t in full.tickers]
        if stage == 3:
            k = int(full.dates.searchsorted(pd.Timestamp("2015-12-31")))
            adv = full.a["adv"][k]
            mem = full.a["members"][k]
            stocks = [(adv[i], t) for i, t in enumerate(full.tickers) if mem[i] and t not in market.ETFS and np.isfinite(adv[i])]
            top = [t for _, t in sorted(stocks, reverse=True)[:100]]
            obs = [t for t in vol.OBSERVED_IV if t in full.tickers and t not in market.ETFS]
            return list(dict.fromkeys(etfs + obs + top))
        return list(full.tickers)

    def _eligible(self) -> np.ndarray:
        """Point-in-time eligibility: ETFs always; a stock only while it is an S&P 500 member (stage 3–4)."""
        etf = np.array([self.panel.info[t].get("kind") == "etf" for t in self.panel.tickers])
        if self.stage <= 2:
            return np.ones(self.panel.a["close"].shape, bool)
        return self.panel.a["members"] | etf[None, :]

    def calibrate(self, atm_factor: float, put_slope: float) -> None:
        """Apply the CBOE calibration: observed index-kind ATM vols × atm_factor (the VIX-method → ATM scale fitted on
        PUT, 2011–2017, applied to every index-kind volatility index), and the index put-side smile slope (CNDR)."""
        from api.quant.optresearch import pricing
        idx_cols = np.array([self.surf["kinds"].get(t) == "index" for t in self.panel.tickers])
        obs = self.surf["cls"] == vol.OBSERVED
        self.surf["atm"] = np.where(obs & idx_cols[None, :], self.surf["atm"] * atm_factor, self.surf["atm"]).astype(np.float32)
        self.smile = dict(pricing.SMILE, index=(put_slope, pricing.SMILE["index"][1]))
        self.calibration = {"index_atm_factor": atm_factor, "index_put_slope": put_slope}
        self._sims.clear()
        self.f = st.features(self.panel, self.surf)
        self.cands = {n: st.candidates(n, self.f, self.panel, self.days, st.loosest(n), eligible=self.eligible)
                      for n in st.STRATEGIES}

    # ── simulation and evaluation ──
    def sim(self, name: str, p: Dict[str, Any], costs: Optional[Dict[str, float]] = None, greeks: bool = False,
            cand: Optional[Dict[str, np.ndarray]] = None) -> Dict[str, Any]:
        key = json.dumps([name, [p[k] for k in st.STRUCTURE[name]], costs or {}, greeks, cand is not None], default=str)
        if key not in self._sims:
            if len(self._sims) >= (3 if self.stage >= 4 else 6):          # bounded memory on the full universe
                self._sims.pop(next(iter(self._sims)))
            self._sims[key] = sim.simulate(self.panel, self.surf, name, p, cand or self.cands[name], costs, greeks=greeks,
                                           smile=self.smile)
        return self._sims[key]

    def book(self, name: str, p: Dict[str, Any], costs=None, greeks=False, cand=None) -> Dict[str, Any]:
        ts = self.sim(name, p, costs, greeks, cand)
        mask = st.admits(name, ts["feat"], p)
        if name == "bull_call":
            mask &= ts["E"] <= p["max_debit"] * ts["W"]
        ex = sim.apply_exits(ts, p["profit_take"], p["stop_loss"], int(p["exit_dte"] or 0), self.day, mask)
        return {"strategy": name, "ts": ts, "ex": ex}

    def run(self, books: List[Dict[str, Any]], port: Optional[Dict[str, Any]] = None, end: Optional[int] = None,
            greeks: bool = False, gate=None, trades: bool = True) -> Dict[str, Any]:
        cfg = {**self.port, **(port or {})}
        # trades decided before the holdout only, unless the run deliberately extends past it
        stop = end if end is not None else self.val_end
        res = pf.run(books, self.panel, cfg, start=va.pos(self.dates, "2016-01-01"), end=stop, gate=gate,
                     record_trades=trades, greeks=greeks)
        full = np.zeros(len(self.dates))
        if len(res["t"]):
            full[res["t"]] = res["ret"]
        res["full"] = full
        return res

    def seg(self, r: np.ndarray, a: str, b: Optional[str]) -> Dict[str, Any]:
        return analytics.segment(r, self.dates, self.panel.rf, a, b)


# ── per-strategy research ────────────────────────────────────────────────────
def research_strategy(lab: Lab, name: str, say) -> Dict[str, Any]:
    G = st.GRIDS[name]
    base = dict(st.DEFAULTS[name])
    trials: Dict[str, Dict[str, Any]] = {}

    def ev(p: Dict[str, Any], tag: str) -> None:
        k = _key(p)
        if k in trials:
            trials[k]["tags"].add(tag)
            return
        res = lab.run([lab.book(name, p)], trades=True)
        dev = lab.seg(res["full"], *va.DEV)
        n_dev = sum(1 for t in res["trades"] if t["entry"] <= va.DEV[1])
        trials[k] = {"params": dict(p), "ret": res["full"].astype(np.float32), "dev": dev, "n_dev": n_dev, "tags": {tag},
                     "exp_r": float(np.mean([t["r"] for t in res["trades"] if t["entry"] <= va.DEV[1]])) if n_dev else None}

    def rank(cands: List[str]) -> List[str]:
        def sc(k):
            t = trials[k]
            return (t["n_dev"] >= MIN_TRADES, t["dev"].get("sharpe") if t["dev"].get("sharpe") is not None else -9)
        return sorted(cands, key=sc, reverse=True)

    t0 = time.time()
    struct = [dict(base, **dict(zip(st.STRUCTURE[name], combo))) for combo in itertools.product(*[G[k] for k in st.STRUCTURE[name]])]
    for i, p in enumerate(struct):
        if i % 6 == 0:
            say(f"{st.LABEL[name]}: structure {i + 1}/{len(struct)}")
        ev(p, "structure")
    top_s = rank([_key(p) for p in struct])[:3]
    for s_ in top_s:
        sp = trials[s_]["params"]
        for combo in itertools.product(*[G[k] for k in st.EXIT]):
            ev(dict(sp, **dict(zip(st.EXIT, combo))), "exits")
    say(f"{st.LABEL[name]}: exit rules done ({len(trials)} configurations)")
    top_e = rank([k for k, t in trials.items() if "exits" in t["tags"]])[:3]
    for s_ in top_e:
        sp = trials[s_]["params"]
        for combo in itertools.product(*[G[k] for k in st.FILTERS[name]]):
            ev(dict(sp, **dict(zip(st.FILTERS[name], combo))), "filters")
    chosen_k = rank(list(trials))[0]
    chosen = trials[chosen_k]["params"]
    say(f"{st.LABEL[name]}: {len(trials)} configurations searched on 2016–2021; evaluating the choice…")

    # the chosen configuration in full (Greeks, trades) to the end of validation
    bk = lab.book(name, chosen, greeks=True)
    res = lab.run([bk], greeks=True)
    r = res["full"]
    dev, val = lab.seg(r, *va.DEV), lab.seg(r, *va.VAL)
    # walk-forward over the pre-declared structure grid (independent of the search path)
    wf = va.walk_forward({_key(p): trials[_key(p)]["ret"] for p in struct}, lab.dates, lab.panel.rf)
    wf_dates = lab.dates[wf["start"]:wf["end"]]
    wf_m = analytics.returns_metrics(wf["returns"], wf_dates, lab.panel.rf[wf["start"]:wf["end"]])
    wf_m.pop("monthly", None)
    rf_wf = lab.panel.rf[wf["start"]:wf["end"]] / 252
    boot = va.bootstrap(wf["returns"] - rf_wf)                                # excess returns
    # cost stress on the chosen configuration (2016–2023)
    stress = {}
    cash = lab.seg(lab.panel.rf / 252, va.DEV[0], va.VAL[1]).get("cagr") or 0.0          # T-bill return, same window
    for label, costs in (("spreads_1.5x", {"spread_mult": 1.5}), ("spreads_2x", {"spread_mult": 2.0}),
                         ("commission_2x", {"commission": 1.30, "fees": 0.04}), ("slippage_$0.02_per_leg", {"slippage": 0.02}),
                         ("implied_vol_-10pct", {"iv_mult": 0.9}), ("implied_vol_+10pct", {"iv_mult": 1.1})):
        rs = lab.run([lab.book(name, chosen, costs=costs)], trades=False)
        m = lab.seg(rs["full"], va.DEV[0], va.VAL[1])
        stress[label] = {k: m.get(k) for k in ("cagr", "sharpe", "max_drawdown")}
        stress[label]["excess_cagr"] = None if m.get("cagr") is None else round(m["cagr"] - cash, 4)
    # overfitting: every configuration tried, over development + validation
    lo, hi = va.pos(lab.dates, va.DEV[0]), lab.val_end
    keys = [k for k, t in trials.items() if np.abs(t["ret"][lo:hi]).sum() > 0]
    mat = np.column_stack([trials[k]["ret"][lo:hi] for k in keys]) if keys else np.zeros((hi - lo, 0))
    prior = registry.total_trials(f"options:{name}")
    exr = lab.panel.rf[lo:hi] / 252
    of = va.overfitting(mat - exr[:, None], r[lo:hi] - exr, len(trials) + prior, [trials[k]["dev"].get("sharpe") for k in keys])
    of["prior_trials_in_registry"] = prior
    surv = va.survived(val, wf_m, boot, stress["spreads_1.5x"], of, stress["implied_vol_-10pct"])
    tr = res["trades"]
    tr_val = [t for t in tr if t["entry"] >= va.VAL[0]]
    years = (pd.Timestamp(va.VAL[1]) - pd.Timestamp(va.DEV[0])).days / 365.25
    tm = analytics.trade_metrics(tr, PORT["capital"], years, float(np.mean(res["nav"])), res["risk_used"], res["costs"])
    vix_at = {str(d.date()): float(v) for d, v in zip(lab.dates, lab.surf["vix"])}
    sens = sensitivity(trials, chosen, name)
    curve = analytics.thin(lab.dates[lo:hi], np.cumprod(1 + r[lo:hi]), analytics.drawdown_series(r[lo:hi]))
    greek_sum = {g: {"avg": round(float(np.mean(v)), 5), "peak_abs": round(float(np.max(np.abs(v))), 5)}
                 for g, v in (res.get("greeks") or {}).items()}
    obs_share = float(np.mean([t["iv_class"] == "observed" for t in tr])) if tr else None
    out = {"label": st.LABEL[name], "chosen": {"params": chosen, "search_rank_metric": "development Sharpe (≥30 trades)"},
           "data_class": "model_observed_iv" if obs_share == 1.0 else "model_iv" if obs_share == 0 else "mixed",
           "observed_iv_share": obs_share, "trials": len(trials),
           "segments": {"development": dev, "validation": val},
           "walk_forward": {"metrics": wf_m, "choices": wf["choices"], "bootstrap": boot,
                            "note": "pre-declared structure grid, re-chosen each January on prior data only"},
           "trade_bootstrap_validation": va.trade_bootstrap(np.array([t["r"] for t in tr_val])),
           "cost_stress": stress, "overfitting": of, "survival": surv, "trades": tm,
           "breakdowns": analytics.option_breakdowns(tr, vix_at), "sensitivity": sens, "greeks": greek_sum,
           "curve": curve, "seconds": round(time.time() - t0, 1),
           "selection_criteria": {k: chosen[k] for k in st.FILTERS[name]},
           "signal_inputs": {"bull_put": "200/50-day averages, IV/RV", "bull_call": "12-1 & 6-1 momentum, rank, ADX, 50-day",
                             "bear_put": "200/50-day, 6-1 momentum, S&P trend & 20-day return, IV percentile",
                             "iron_condor": "ADX, 20-day move vs realised vol, IV/RV"}[name],
           "limitations": [] if obs_share == 1.0 else ["Uses modelled implied volatility for single stocks."],
           "_ret": r.astype(np.float32), "_trials": trials, "_struct": [_key(p) for p in struct], "_trades": tr}
    return out


def sensitivity(trials: Dict[str, Dict[str, Any]], chosen: Dict[str, Any], name: str) -> Dict[str, Any]:
    """Development Sharpe as each parameter varies with the others at the chosen values (where that configuration was
    evaluated) — a flat profile is robust, a spike is fragile."""
    out = {}
    for k in list(st.STRUCTURE[name]) + list(st.EXIT) + list(st.FILTERS[name]):
        rows = []
        for v in st.GRIDS[name][k]:
            p = dict(chosen, **{k: v})
            t = trials.get(_key(p))
            if t:
                rows.append({"value": v, "dev_sharpe": t["dev"].get("sharpe"), "dev_cagr": t["dev"].get("cagr"),
                             "trades": t["n_dev"], "expectancy_r": None if t["exp_r"] is None else round(t["exp_r"], 4)})
        out[k] = rows
    return out


# ── experiment ───────────────────────────────────────────────────────────────
def run_experiment(stage: int, owner: str, job=None, strategies: Optional[List[str]] = None,
                   synthetic: bool = False) -> Dict[str, Any]:
    t_start = time.time()
    strategies = strategies or list(st.STRATEGIES)
    say = (job.progress if hasattr(job, "progress") else job.say) if job is not None else (lambda m: None)
    cancelled = (lambda: job.cancelled) if job is not None and hasattr(job, "cancelled") else (lambda: False)
    kind = "options:stage" + str(stage)
    eid = registry.start_experiment(owner, kind, stage, f"Stage {stage}", {"strategies": strategies, "portfolio": PORT},
                                    "unit" if stage == 1 else "model_based_simulation")
    d = ROOT / eid
    d.mkdir(parents=True, exist_ok=True)
    timings: Dict[str, Any] = {}

    def section(nm: str, fn):
        a = time.time()
        res = fn()
        timings[nm] = {"seconds": round(time.time() - a, 1), "peak_rss_mb": _rss_mb()}
        return res

    try:
        if stage == 1:
            from api.quant.optresearch import selfcheck
            checks = section("checks", selfcheck.run_all)
            ok = all(c["passed"] for c in checks)
            result = {"experiment_id": eid, "stage": 1, "checks": checks, "passed": ok, "timings": timings}
            _save(d, result)
            registry.finish_experiment(eid, state="done" if ok else "failed", runtime_s=round(time.time() - t_start, 1),
                                       peak_mb=_rss_mb(), trials=0, summary={"passed": ok, "checks": len(checks)},
                                       result_path=str(d / "result.json"))
            return result
        lab = section("data", lambda: Lab(stage, say, synthetic))
        say("Calibrating the index ATM scale and smile against CBOE PUT and CNDR (2011–2017)…")
        rep = section("cboe_replication", lambda: va.replicate_cboe(lab.panel, lab.surf) if not synthetic and "SPY" in lab.panel.tickers else None)
        if rep and rep.get("atm_scale"):
            lab.calibrate(float(rep["atm_scale_vs_default"]), float(rep["chosen_put_slope"]))
        data_quality = {"panel": {k: v for k, v in lab.panel.meta.items() if not k.startswith("_")},
                        "underlyings": len(lab.panel.tickers), "iv_coverage": lab.surf.get("coverage"),
                        "iv_model": {"fit": lab.surf.get("model"), "accuracy": lab.surf.get("model_report")},
                        "observed_iv_underlyings": [t for t in lab.panel.tickers if t in vol.OBSERVED_IV],
                        "cboe_replication": rep, "candidates": {n: int(len(c["t"])) for n, c in lab.cands.items()},
                        "missing_data": ["historical option quotes (bid/ask, IV by strike, volume, open interest)",
                                         "listed strike / expiry calendars", "earnings dates for IV term structure",
                                         "removed index members without free price history"]}
        strat: Dict[str, Any] = {}
        for nm in strategies:
            if cancelled():
                raise RuntimeError("Cancelled.")
            strat[nm] = section(f"strategy:{nm}", lambda nm=nm: research_strategy(lab, nm, say))
            _checkpoint(d, f"strategy_{nm}", strat[nm])
        say("Comparing systems, regime models and portfolio construction…")
        systems, regime_res, port_res, holdout = section("systems", lambda: compare_systems(lab, strat, say))
        surv_check = section("survivorship", lambda: survivorship(lab, strat) if stage >= 3 else None)
        leak = section("leakage", lambda: va.prefix_invariance(lab.panel.subset([t for t in INDEX4 if t in lab.panel.tickers]),
                                                              vol.surface, st.features) if not synthetic else None)
        hyp = update_registry(eid, stage, lab, strat, systems, regime_res, port_res, data_quality, surv_check)
        trials = sum(s["trials"] for s in strat.values()) + port_res.get("trials", 0)
        result = {"experiment_id": eid, "stage": stage, "universe": {"underlyings": len(lab.panel.tickers),
                  "point_in_time": stage >= 3, "spec": lab.panel.meta.get("spec")},
                  "segments": {"development": va.DEV, "validation": va.VAL, "holdout_start": va.HOLDOUT_START},
                  "criteria": va.CRITERIA, "portfolio_defaults": lab.port, "data_quality": data_quality,
                  "strategies": {k: {kk: vv for kk, vv in v.items() if not kk.startswith("_")} for k, v in strat.items()},
                  "systems": systems, "regimes": regime_res, "portfolio_research": port_res, "survivorship": surv_check,
                  "leakage": leak, "hypotheses": hyp, "limitations": LIMITATIONS, "timings": timings,
                  "runtime_s": round(time.time() - t_start, 1), "peak_rss_mb": _rss_mb(), "trials": trials,
                  "holdout": "sealed"}
        _save(d, result)
        (d / "holdout.sealed.json").write_text(json.dumps(holdout, default=str))
        registry.finish_experiment(eid, state="done", runtime_s=result["runtime_s"], peak_mb=result["peak_rss_mb"],
                                   trials=trials, summary=summary(result), result_path=str(d / "result.json"))
        return result
    except Exception as e:
        registry.finish_experiment(eid, state="failed", runtime_s=round(time.time() - t_start, 1), peak_mb=_rss_mb(),
                                   trials=0, summary={"error": f"{type(e).__name__}: {str(e)[:300]}", "timings": timings},
                                   result_path=None)
        raise


def _save(d: Path, result: Dict[str, Any]) -> None:
    tmp = d / "result.json.tmp"
    tmp.write_text(json.dumps(_clean(result), default=str))
    tmp.replace(d / "result.json")


def _checkpoint(d: Path, name: str, obj: Dict[str, Any]) -> None:
    (d / f"{name}.json").write_text(json.dumps(_clean({k: v for k, v in obj.items() if not k.startswith("_")}), default=str))


def _clean(x):
    if isinstance(x, dict):
        return {str(k): _clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_clean(v) for v in x]
    if isinstance(x, set):
        return sorted(x)
    if isinstance(x, (np.floating,)):
        return None if not np.isfinite(x) else float(x)
    if isinstance(x, float):
        return None if not math.isfinite(x) else x
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, np.bool_):
        return bool(x)
    if isinstance(x, np.ndarray):
        return _clean(x.tolist())
    return x


def summary(result: Dict[str, Any]) -> Dict[str, Any]:
    s = {k: {"survived": v["survival"]["survived"], "val_sharpe": v["segments"]["validation"].get("sharpe"),
             "wf_sharpe": v["walk_forward"]["metrics"].get("sharpe")} for k, v in result["strategies"].items()}
    sysm = {k: v["segments"].get("validation", {}).get("sharpe") for k, v in result["systems"]["systems"].items()}
    return {"stage": result["stage"], "strategies": s, "systems_val_sharpe": sysm, "runtime_s": result["runtime_s"],
            "peak_rss_mb": result["peak_rss_mb"], "underlyings": result["universe"]["underlyings"]}


# ── systems, regimes, portfolio construction ─────────────────────────────────
def _baseline_series(lab: Lab, f: str) -> Optional[np.ndarray]:
    p = BASELINES / f
    if not p.exists():
        return None
    s = pd.read_csv(p, parse_dates=["Date"]).set_index("Date")["return"]
    return s.reindex(lab.dates).fillna(0.0).to_numpy()


def compare_systems(lab: Lab, strat: Dict[str, Any], say):
    names = list(strat)
    chosen = {n: strat[n]["chosen"]["params"] for n in names}
    books = lambda costs=None, greeks=False: [lab.book(n, chosen[n], costs=costs, greeks=greeks) for n in names]
    eq_alloc = {n: 1.0 / len(names) for n in names}
    sysr: Dict[str, Dict[str, Any]] = {}
    spy = lab.panel.frame("close")["SPY"].pct_change().fillna(0.0).to_numpy()
    base = _baseline_series(lab, "previous_options_hybrid.csv")
    base_opt = _baseline_series(lab, "previous_options_only.csv")

    def add(key, label, r, res=None, note=None):
        lo, hi = va.pos(lab.dates, va.DEV[0]), lab.val_end
        e = {"label": label, "segments": {"development": lab.seg(r, *va.DEV), "validation": lab.seg(r, *va.VAL),
                                          "walk_forward_window": lab.seg(r, f"{va.WF_FIRST_YEAR}-01-01", va.VAL[1])},
             "curve": analytics.thin(lab.dates[lo:hi], np.cumprod(1 + r[lo:hi]), analytics.drawdown_series(r[lo:hi])),
             "note": note}
        if res is not None:
            years = (pd.Timestamp(va.VAL[1]) - pd.Timestamp(va.DEV[0])).days / 365.25
            e["trades"] = analytics.trade_metrics(res["trades"], PORT["capital"], years, float(np.mean(res["nav"])),
                                                  res["risk_used"], res["costs"])
            if "greeks" in res:
                e["greeks"] = {g: {"avg": round(float(np.mean(v)), 5), "peak_abs": round(float(np.max(np.abs(v))), 5)}
                               for g, v in res["greeks"].items()}
                e["greeks_curve"] = analytics.thin(lab.dates[res["t"]], *[res["greeks"][g] for g in ("delta", "vega", "theta")],
                                                   max_points=300)
            e["strategy_pnl"] = {s: round(float(np.sum(v)), 2) for s, v in res["strategy_pnl"].items()}
        sysr[key] = e

    if base is not None:
        add("baseline", "Existing options algorithm (recorded)", base, note="Recorded daily returns of the previous options "
            "strategy (walk-forward hybrid, Code Lab engine ledger.5, 2016-01-04 → 2026-10-09). Different engine and cost "
            "model from the systems below — compare with care.")
    if base_opt is not None:
        add("baseline_options_only", "Existing algorithm — options sleeve only (recorded)", base_opt)
    add("spy", "SPY buy-and-hold (total return, no costs)", spy)
    holdout: Dict[str, Any] = {}
    for n in names:
        add(n, f"{st.LABEL[n]} only", strat[n]["_ret"].astype(float))
    say("Combined four-strategy portfolio…")
    comb = lab.run(books(greeks=True), port={"alloc": eq_alloc}, greeks=True)
    add("combined", "Combined four strategies (equal risk budgets)", comb["full"], comb)
    # regimes
    say("Regime models (walk-forward, refitted each January)…")
    rf_ = regimes.features(lab.panel, lab.surf, breadth_panel=lab.full)
    y = regimes.labels(lab.panel, lab.surf)
    preds = {"rules": regimes.rules(rf_)}
    try:
        preds.update(regimes.walk_forward(rf_, y, 2016, lab.dates[lab.val_end - 1]))
    except Exception as e:                                                   # noqa: BLE001 — report, keep the rules
        preds["_error"] = f"{type(e).__name__}: {str(e)[:200]}"
    err = preds.pop("_error", None)
    reg_rows = []
    for k, pr in preds.items():
        g = regimes.gates(pr, len(lab.dates))
        rs = lab.run(books(), port={"alloc": eq_alloc}, gate=g, trades=False)
        dev_m = lab.seg(rs["full"], *va.DEV)
        val_m = lab.seg(rs["full"], *va.VAL)
        msk_dev = (lab.dates >= va.DEV[0]) & (lab.dates <= va.DEV[1])
        msk_val = (lab.dates >= va.VAL[0]) & (lab.dates <= va.VAL[1])
        reg_rows.append({"model": k, "classification_dev": regimes.scores(pr[msk_dev], y[msk_dev]),
                         "classification_val": regimes.scores(pr[msk_val], y[msk_val]),
                         "portfolio_dev": {m: dev_m.get(m) for m in ("cagr", "sharpe", "max_drawdown")},
                         "portfolio_val": {m: val_m.get(m) for m in ("cagr", "sharpe", "max_drawdown")}, "_ret": rs["full"]})
    best = max(reg_rows, key=lambda r: r["portfolio_dev"].get("sharpe") or -9)
    gate_best = regimes.gates(preds[best["model"]], len(lab.dates))
    sw = lab.run(books(greeks=True), port={"alloc": eq_alloc}, gate=gate_best, greeks=True)
    add("regime_switching", f"Regime-switching four strategies ({best['model']}, chosen on 2016–2021)", sw["full"], sw)
    regime_res = {"models": [{k: v for k, v in r.items() if k != "_ret"} for r in reg_rows], "chosen": best["model"],
                  "chosen_by": "development-period Sharpe of the gated combined portfolio", "error": err,
                  "fixed_combined": {"dev": {m: sysr["combined"]["segments"]["development"].get(m) for m in ("cagr", "sharpe", "max_drawdown")},
                                     "val": {m: sysr["combined"]["segments"]["validation"].get(m) for m in ("cagr", "sharpe", "max_drawdown")}},
                  "gates": regimes.GATES, "features": regimes.FEATURES,
                  "current": {k: (str(v.dropna().iloc[-1]) if v.notna().any() else None) for k, v in preds.items()},
                  "mix_dev": {k: v[(lab.dates >= va.DEV[0]) & (lab.dates <= va.DEV[1])].value_counts(normalize=True).round(3).to_dict()
                              for k, v in preds.items()}}
    # portfolio construction research on the combined portfolio (selection on development only)
    say("Portfolio construction research…")
    port_res = portfolio_research(lab, books, eq_alloc)
    # sealed holdout: the development choices run through the holdout (not shown unless revealed)
    say("Sealing the holdout…")
    for key, bks, extra in (("combined", books(), {"alloc": eq_alloc}),):
        hr = lab.run(bks, port=extra, end=len(lab.dates))
        holdout[key] = lab.seg(hr["full"], va.HOLDOUT_START, None)
    # the chosen regime model's predictions through the holdout (same annual refit rule, data before each year only)
    full_pred = preds["rules"] if best["model"] == "rules" else \
        regimes.walk_forward(rf_, y, 2016, None, kinds=(best["model"],))[best["model"]]
    hs = lab.run(books(), port={"alloc": eq_alloc}, gate=regimes.gates(full_pred, len(lab.dates)), end=len(lab.dates))
    holdout["regime_switching"] = lab.seg(hs["full"], va.HOLDOUT_START, None)
    for n in names:
        hr = lab.run([lab.book(n, chosen[n])], end=len(lab.dates))
        holdout[n] = lab.seg(hr["full"], va.HOLDOUT_START, None)
    holdout["spy"] = lab.seg(spy, va.HOLDOUT_START, None)
    if base is not None:
        holdout["baseline"] = lab.seg(base, va.HOLDOUT_START, None)
    systems = {"systems": sysr, "order": [k for k in ("baseline", "baseline_options_only", "spy", *names, "combined",
                                                       "regime_switching") if k in sysr],
               "assumptions": {"capital": PORT["capital"], "portfolio": lab.port, "costs": sim.DEFAULT_COSTS,
                               "tiers": sim.TIERS, "accounting": "one account per system, marked to the model mid, cash at "
                                                                 "the T-bill rate, defined-risk margin = max loss"}}
    return systems, regime_res, port_res, holdout


def portfolio_research(lab: Lab, books, alloc) -> Dict[str, Any]:
    rows = []
    bk = books(greeks=True)

    def go(label, group, port, gate=None, bks=None):
        rs = lab.run(bks or bk, port={"alloc": alloc, **port}, greeks=True, trades=False, gate=gate)
        d, v = lab.seg(rs["full"], *va.DEV), lab.seg(rs["full"], *va.VAL)
        rows.append({"label": label, "group": group, "config": port,
                     "dev": {k: d.get(k) for k in ("cagr", "sharpe", "max_drawdown", "calmar")},
                     "val": {k: v.get(k) for k in ("cagr", "sharpe", "max_drawdown", "calmar")},
                     "avg_positions": round(float(np.mean(rs["positions"])), 2),
                     "capital_use": round(float(np.mean(rs["risk_used"])), 3),
                     "peak_delta": round(float(np.max(np.abs(rs["greeks"]["delta"]))), 3) if "greeks" in rs else None})
    for mp in (5, 10, 15, 20):
        for rpt in (0.01, 0.02, 0.03):
            go(f"{mp} positions, {rpt:.0%} risk each", "positions_x_risk", {"max_positions": mp, "risk_per_trade": rpt})
    for tr in (0.15, 0.30, 0.50):
        go(f"total risk {tr:.0%}", "portfolio_risk_budget", {"max_total_risk": tr})
    go("sector cap 2", "concentration", {"max_per_sector": 2})
    go("no sector cap", "concentration", {"max_per_sector": 999})
    go("correlation filter 0.7", "correlation", {"corr_max": 0.7})
    go("delta ≤ 50% of NAV", "greeks", {"delta_limit": 0.5})
    go("delta ≤ 25% of NAV", "greeks", {"delta_limit": 0.25})
    go("vega ≤ 0.2% of NAV per vol pt", "greeks", {"vega_limit": 0.002})
    go("no drawdown brake", "drawdown_control", {"dd_soft": 1.0, "dd_hard": 1.0})
    go("tight drawdown brake (5% / 15%)", "drawdown_control", {"dd_soft": 0.05, "dd_hard": 0.15})
    # H15: cross-sectional ranking vs random order among the same candidates
    rng = np.random.default_rng(11)
    rnd = []
    for b in bk:
        ts = dict(b["ts"])
        ts["score"] = rng.random(len(ts["score"])).astype(np.float32)
        rnd.append({**b, "ts": ts})
    go("random candidate order (no ranking)", "ranking", {}, bks=rnd)
    # strategy allocation: inverse development volatility vs equal
    vols = {}
    for b in bk:
        rs = lab.run([b], trades=False)
        vols[b["strategy"]] = float(np.std(rs["full"][va.pos(lab.dates, va.DEV[0]):va.pos(lab.dates, va.DEV[1])])) or 1.0
    iv = {k: (1 / v) for k, v in vols.items()}
    tot = sum(iv.values())
    go("inverse-volatility strategy budgets (development vol)", "allocation", {"alloc": {k: v / tot for k, v in iv.items()}})
    base = next(r for r in rows if r["config"] == {"max_positions": 10, "risk_per_trade": 0.02})
    best = max((r for r in rows if r["group"] == "positions_x_risk"), key=lambda r: r["dev"].get("sharpe") or -9)
    return {"rows": rows, "reference": base["label"], "best_on_development": best["label"], "trials": len(rows),
            "note": "Each row changes one setting of the combined portfolio (equal strategy risk budgets) from the "
                    "reference: 10 positions, 2% risk per trade, 30% total. Choose on development; read validation."}


def survivorship(lab: Lab, strat: Dict[str, Any]) -> Dict[str, Any]:
    """The chosen configurations on point-in-time members vs on today's US list (survivor-selected)."""
    out = {}
    today = np.array([lab.panel.info[t].get("today_listed", False) for t in lab.panel.tickers])
    elig_today = np.repeat(today[None, :], len(lab.dates), axis=0)
    for n, s in strat.items():
        p = s["chosen"]["params"]
        cand = st.candidates(n, lab.f, lab.panel, lab.days, st.loosest(n), eligible=elig_today)
        rs = lab.run([lab.book(n, p, cand=cand)], trades=False)
        a = lab.seg(s["_ret"].astype(float), va.DEV[0], va.VAL[1])
        b = lab.seg(rs["full"], va.DEV[0], va.VAL[1])
        out[n] = {"point_in_time": {k: a.get(k) for k in ("cagr", "sharpe", "max_drawdown")},
                  "todays_list": {k: b.get(k) for k in ("cagr", "sharpe", "max_drawdown")},
                  "sharpe_bias": None if a.get("sharpe") is None or b.get("sharpe") is None else round(b["sharpe"] - a["sharpe"], 3)}
    return out


# ── registry update ──────────────────────────────────────────────────────────
def update_registry(eid, stage, lab, strat, systems, regime_res, port_res, dq, surv_check) -> List[Dict[str, Any]]:
    ds = f"stage {stage}: {len(lab.panel.tickers)} underlyings, 2016-01 → 2023-12 (holdout sealed)"
    lim = "; ".join(LIMITATIONS[:2])
    upd = []

    def put(hid, status, method, config, results, limitation=lim):
        registry.update_hypothesis(hid, status=status, method=method, dataset=ds, config=config, results=results,
                                   limitations=limitation, experiment_id=eid)
        upd.append({"id": hid, "status": status})
    small = stage < 4
    # strategy hypotheses: the pre-declared survival tests decide (and stage 4 is required for "survived")
    tag = lambda ok: ("survived" if ok else "rejected") if not small else ("inconclusive" if ok else "rejected")
    # relative hypotheses (A beats B): one validation window without a significance test on the difference cannot
    # establish an effect — a direction that holds in development AND validation is "inconclusive" (supported, untested),
    # anything else "rejected". (Tightened after the first stage-4 run had labelled single-window comparisons "survived".)
    rel = lambda dev_ok, val_ok: "inconclusive" if (dev_ok and val_ok) else "rejected"
    gt = lambda a, b: (a if a is not None else -9) > (b if b is not None else -9)
    for hid, n in (("H01", "bull_put"), ("H03", "bull_call"), ("H04", "bear_put"), ("H05", "iron_condor")):
        if n not in strat:
            continue
        s = strat[n]
        put(hid, tag(s["survival"]["survived"]), "successive search on development; validation; walk-forward; stress; "
            "PBO/DSR", s["chosen"]["params"], {"survival": s["survival"], "validation": s["segments"]["validation"],
                                               "walk_forward": s["walk_forward"]["metrics"]})
    if "bull_put" in strat:
        by = {r["group"]: r for r in strat["bull_put"]["breakdowns"].get("by_iv_class", [])}
        if "observed" in by and "model" in by:
            ok = (by["model"]["expectancy_r"] or 0) < (by["observed"]["expectancy_r"] or 0)
            put("H02", "inconclusive", "bull put trades split by IV class (observed-IV ETFs vs modelled-IV stocks)", None,
                {"observed": by["observed"], "model": by["model"], "direction_consistent": ok},
                "Stock IV is modelled, so a stock-level premium cannot be confirmed from this data.")
        sens = strat["bull_put"]["sensitivity"]
        if sens.get("iv_rv_min"):
            rows = sens["iv_rv_min"]
            ok = len(rows) >= 2 and all((rows[i + 1].get("expectancy_r") or -9) >= (rows[i].get("expectancy_r") or -9) for i in range(len(rows) - 1))
            put("H13", "inconclusive" if ok else "rejected", "IV/RV entry threshold at the chosen configuration", None, rows)
        if sens.get("profit_take") or sens.get("exit_dte"):
            put("H06", "inconclusive", "exit-rule sensitivity at the chosen configuration (development)", None,
                {"profit_take": sens.get("profit_take"), "exit_dte": sens.get("exit_dte"), "stop_loss": sens.get("stop_loss")})
    syss = systems["systems"]
    sh = lambda k, seg: syss[k]["segments"][seg].get("sharpe")
    if "combined" in syss:
        best_dev = max(strat, key=lambda n: sh(n, "development") or -9)
        put("H10", rel(gt(sh("combined", "development"), sh(best_dev, "development")), gt(sh("combined", "validation"), sh(best_dev, "validation"))),
            "Sharpe: combined vs the best single strategy (chosen on development)", None,
            {"combined": {"dev": sh("combined", "development"), "val": sh("combined", "validation")},
             "best_single": best_dev, "single": {"dev": sh(best_dev, "development"), "val": sh(best_dev, "validation")}})
    if "regime_switching" in syss:
        put("H08", rel(gt(sh("regime_switching", "development"), sh("combined", "development")), gt(sh("regime_switching", "validation"), sh("combined", "validation"))),
            "Sharpe: regime-switching vs fixed combined (development and validation)", {"model": regime_res["chosen"]},
            {"regime_switching": {"dev": sh("regime_switching", "development"), "val": sh("regime_switching", "validation")},
             "fixed": {"dev": sh("combined", "development"), "val": sh("combined", "validation")}})
        cb = sh("combined", "validation")
        cbd = sh("combined", "development")
        rules_row = next((r for r in regime_res["models"] if r["model"] == "rules"), None)
        ml = [r for r in regime_res["models"] if r["model"] != "rules"]
        if rules_row and ml:
            rb = rules_row["classification_val"].get("balanced_accuracy") or 0
            best_ml = max(ml, key=lambda r: r["classification_val"].get("balanced_accuracy") or 0)
            put("H09", "inconclusive" if (best_ml["classification_val"].get("balanced_accuracy") or 0) > rb else "rejected",
                "validation balanced accuracy and gated-portfolio Sharpe vs the rules baseline", None,
                {"rules": rules_row, "best_ml": best_ml})
            put("H07", rel(gt(rules_row["portfolio_dev"].get("sharpe"), cbd), gt(rules_row["portfolio_val"].get("sharpe"), cb)),
                "rules gating (incl. stress = no new short volatility) vs ungated, development and validation", None,
                {"rules_gated": {"dev": rules_row["portfolio_dev"], "val": rules_row["portfolio_val"]}, "ungated": {"dev": cbd, "val": cb}})
    rows = port_res["rows"]
    pos = {r["config"].get("max_positions"): r for r in rows if r["group"] == "positions_x_risk" and r["config"].get("risk_per_trade") == 0.02}
    if pos:
        sh_ = {k: v["val"].get("sharpe") for k, v in pos.items()}
        hump = lambda d: (max(d.get(10) or -9, d.get(15) or -9) > (d.get(5) or -9)) and (d.get(20) or -9) <= max(d.get(10) or -9, d.get(15) or -9)
        shd = {k: v["dev"].get("sharpe") for k, v in pos.items()}
        put("H11", rel(hump(shd), hump(sh_)), "max positions 5/10/15/20 at 2% risk per trade (development and validation Sharpe)",
            None, {"dev": shd, "val": sh_})
    g = [r for r in rows if r["group"] == "greeks"]
    ref = next(r for r in rows if r["label"] == port_res["reference"])
    if g:
        better = lambda r, seg: ((r[seg].get("max_drawdown") or -1) > (ref[seg].get("max_drawdown") or -1)
                                 and (r[seg].get("sharpe") or -9) >= (ref[seg].get("sharpe") or -9) - 0.05)
        put("H12", rel(any(better(r, "dev") for r in g), any(better(r, "val") for r in g)),
            "delta/vega caps vs the reference portfolio (smaller drawdown, Sharpe no worse; development and validation)", None,
            {"reference": ref, "caps": g})
    rnd = next((r for r in rows if r["group"] == "ranking"), None)
    if rnd:
        put("H15", rel(gt(ref["dev"].get("sharpe"), rnd["dev"].get("sharpe")), gt(ref["val"].get("sharpe"), rnd["val"].get("sharpe"))),
            "ranked vs random candidate order (development and validation)", None, {"ranked": {"dev": ref["dev"], "val": ref["val"]},
                                                                                     "random": {"dev": rnd["dev"], "val": rnd["val"]}})
    acc = (dq.get("iv_model") or {}).get("accuracy") or {}
    oos = (acc.get("summary") or {}).get("out_of_sample")
    if oos:
        put("H14", "survived" if oos["mae_vol_pts"] < 3 else "rejected", "IV model vs CBOE volatility indices, 2019 onward",
            (dq.get("iv_model") or {}).get("fit"), acc, "Accuracy measured on the 15 observed-IV underlyings only; other "
                                                        "stocks may differ.")
    return upd


# ── running as a server job, in its own process ─────────────────────────────
def _child(stage: int, owner: str, strategies, q) -> None:
    class _J:
        cancelled = False

        def progress(self, m):
            q.put(("msg", m))
    try:
        res = run_experiment(stage, owner, job=_J(), strategies=strategies)
        q.put(("done", {"experiment_id": res["experiment_id"], "stage": stage,
                        "summary": summary(res) if stage > 1 else {"passed": res["passed"]}}))
    except Exception as e:                                              # noqa: BLE001 — reported to the job
        q.put(("error", f"{type(e).__name__}: {str(e)[:500]}"))


def run_in_subprocess(stage: int, owner: str, job, strategies: Optional[List[str]] = None) -> Dict[str, Any]:
    """Run an experiment in a separate process (the research holds the CPU for minutes; the web server must stay
    responsive). Progress messages are relayed to the job; cancelling the job stops the process."""
    import multiprocessing as mp
    import queue as _queue
    ctx = mp.get_context("spawn")
    q = ctx.Queue()
    p = ctx.Process(target=_child, args=(stage, owner, strategies, q), daemon=True)
    p.start()
    try:
        while True:
            if getattr(job, "cancelled", False):
                p.terminate()
                raise RuntimeError("Cancelled.")
            try:
                kind, val = q.get(timeout=1.0)
            except _queue.Empty:
                if not p.is_alive():
                    raise RuntimeError("The research process stopped unexpectedly (out of memory?).")
                continue
            if kind == "msg":
                job.progress(val)
            elif kind == "done":
                return val
            else:
                raise RuntimeError(val)
    finally:
        p.join(timeout=5)


def reveal_holdout(eid: str, user: str) -> Dict[str, Any]:
    d = ROOT / eid
    f = d / "holdout.sealed.json"
    if not f.exists():
        raise ValueError("This experiment has no sealed holdout.")
    n = registry.log_holdout(eid, user, "revealed in the Options research dashboard")
    return {"experiment_id": eid, "holdout_start": va.HOLDOUT_START, "results": json.loads(f.read_text()),
            "reveals_total": n, "warning": "Any change made after looking at these numbers is no longer tested out of "
                                           "sample. Every reveal is logged in the registry."}


def load_result(eid: str) -> Optional[Dict[str, Any]]:
    f = ROOT / eid / "result.json"
    try:
        return json.loads(f.read_text())
    except (OSError, ValueError):
        return None
