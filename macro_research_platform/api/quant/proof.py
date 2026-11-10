"""
What actually works — one scorecard over everything the platform has tested, judged by alpha rather than return.

A strategy that earns 15% a year with a beta of 1.25 to equities has added nothing a fund can't get from an index
fund for a few basis points. So every tested strategy and signal is scored on:

  * multi-factor alpha and its t-statistic (the Quant Lab's factor lens: equity, credit, rates, EM, dollar, size,
    low risk, inflation …), and CAPM alpha against the strategy's own benchmark as a cross-check;
  * the deflated Sharpe ratio (Bailey & López de Prado 2014) — the probability the Sharpe ratio is above zero after
    allowing for how many strategies were tried, their spread of Sharpe ratios, skew and fat tails;
  * overfitting evidence: probability of backtest overfitting (PBO) and whether combinatorial purged cross-validation
    paths stay positive;
  * for stock signals and the macro model's tactical tilt, their own out-of-sample t-statistics.

Verdicts: "alpha" needs multi-factor t ≥ 2, deflated Sharpe ≥ 0.9 and at least 1% a year; "promising" t ≥ 1.2 and at
least 1% a year;
"beta" when equity beta ≥ 0.6 explains most of the return with no alpha; otherwise "no edge".
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent / "data" / "processed"


def _norm_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _norm_ppf(p: float) -> float:
    from scipy.stats import norm
    return float(norm.ppf(p))


def deflated_sharpe(r: np.ndarray, n_trials: int, sr_var: float) -> Optional[float]:
    """Probability that the true (per-period) Sharpe ratio exceeds the best one expected from n_trials of luck."""
    r = r[np.isfinite(r)]
    if len(r) < 60 or r.std() == 0:
        return None
    sr = r.mean() / r.std()
    from scipy.stats import kurtosis, skew
    g3, g4 = float(skew(r)), float(kurtosis(r, fisher=False))
    emc = 0.5772156649
    n = max(2, n_trials)
    sr0 = math.sqrt(max(sr_var, 1e-12)) * ((1 - emc) * _norm_ppf(1 - 1 / n) + emc * _norm_ppf(1 - 1 / (n * math.e)))
    denom = math.sqrt(max(1e-12, 1 - g3 * sr + (g4 - 1) / 4 * sr * sr))
    return _norm_cdf((sr - sr0) * math.sqrt(len(r) - 1) / denom)


def _capm(r: np.ndarray, b: np.ndarray) -> Dict[str, Optional[float]]:
    m = np.isfinite(r) & np.isfinite(b)
    r, b = r[m], b[m]
    if len(r) < 60 or b.var() == 0:
        return {"alpha": None, "alpha_t": None, "beta": None}
    beta = float(np.cov(r, b)[0, 1] / np.var(b, ddof=1))
    res = r - beta * b
    a = res.mean()
    t = a / (res.std(ddof=1) / math.sqrt(len(res)))
    return {"alpha": float(a * 252), "alpha_t": float(t), "beta": beta}


MIN_ALPHA = 0.01        # an edge under 1% a year is not worth the operational and tail risk of running it


def _verdict(alpha: Optional[float], t: Optional[float], dsr: Optional[float], eq_beta: Optional[float]) -> str:
    if alpha is not None and t is not None and t >= 2 and (dsr or 0) >= 0.9 and alpha >= MIN_ALPHA:
        return "alpha"
    if alpha is not None and t is not None and t >= 1.2 and alpha >= MIN_ALPHA:
        return "promising"
    if eq_beta is not None and eq_beta >= 0.6:
        return "beta"
    return "no edge"


VERDICT_TEXT = {"alpha": "Real alpha after costs and multiple testing.",
                "promising": "Positive alpha but not yet statistically proven — candidate for a small, monitored allocation.",
                "beta": "Mostly market exposure: an index fund delivers the same return far more cheaply.",
                "no edge": "No measurable edge after costs."}


def _crisis(r: np.ndarray, b: np.ndarray, dates: List[str]) -> Dict[str, Any]:
    """How a strategy behaves when equities fall — the job of trend and defensive sleeves, which an alpha test misses.
    Monthly returns; crisis months = the worst tenth of benchmark months."""
    import pandas as pd
    if len(b) != len(r) or len(dates) != len(r) or len(r) < 250:
        return {}
    idx = pd.to_datetime(dates)
    m = pd.DataFrame({"s": r, "b": b}, index=idx).fillna(0).groupby(pd.Grouper(freq="ME")).apply(lambda g: (1 + g).prod() - 1)
    if len(m) < 36:
        return {}
    cut = m["b"].quantile(0.10)
    crisis, down = m[m["b"] <= cut], m[m["b"] < 0]
    dc = float(down["s"].mean() / down["b"].mean()) if len(down) and down["b"].mean() < 0 else None
    out = {"crisis_return": float(crisis["s"].mean()), "crisis_benchmark": float(crisis["b"].mean()), "crisis_months": int(len(crisis)),
           "downside_capture": dc, "down_market_corr": float(down["s"].corr(down["b"])) if len(down) > 5 else None}
    out["role"] = ("crisis diversifier" if out["crisis_return"] > 0 or (dc is not None and dc < 0.25) else
                   "partial hedge" if dc is not None and dc < 0.6 else None)
    return out


def scorecard() -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    lib = sorted((ROOT / "quant" / "library").glob("*.json"))
    loaded = []
    for f in lib:
        try:
            d = json.loads(f.read_text())
        except Exception:                                       # noqa: BLE001 — a corrupt cache file is skipped
            continue
        r = np.array([x if x is not None else np.nan for x in d.get("returns") or []], dtype=float)
        if len(r) < 60:
            continue
        loaded.append((f.stem, d, r))
    srs = [np.nanmean(r) / np.nanstd(r) for _, _, r in loaded if np.nanstd(r) > 0]
    # trials: every library strategy plus every stock signal and composite the Signal Lab scores
    labs = []
    for fname in ("result.json", "result_sp1000.json"):
        try:
            labs.append(json.loads((ROOT / "quant" / "alphalab" / fname).read_text()))
        except Exception:                                       # noqa: BLE001
            pass
    n_trials = len(loaded) + sum(len(a["signals"]) + len(a.get("composites", [])) for a in labs)
    # robust spread of the trials' Sharpe ratios: one near-riskless strategy (an option overlay on cash) has an extreme
    # per-day Sharpe that would otherwise inflate the variance and deflate every other strategy to zero
    if len(srs) > 2:
        med = float(np.median(srs))
        sr_var = float((1.4826 * np.median(np.abs(np.array(srs) - med))) ** 2)
    else:
        sr_var = 0.0
    from api.quant import library
    names = {e["id"]: e for e in library.all_entries()}
    for sid, d, r in loaded:
        fl = d.get("factor_lens") or {}
        val = d.get("validation") or {}
        eq = next((x for x in fl.get("factors", []) if x.get("factor") == "Equity"), {})
        b = np.array([x if x is not None else np.nan for x in d.get("benchmark") or []], dtype=float)
        capm = _capm(r, b) if len(b) == len(r) else {"alpha": None, "alpha_t": None, "beta": None}
        dsr = deflated_sharpe(r, n_trials, sr_var)
        m = d.get("metrics") or {}
        alpha, t = fl.get("alpha"), fl.get("alpha_t")
        v = _verdict(alpha, t, dsr, eq.get("beta"))
        cr = _crisis(r, b, d.get("dates") or [])
        rows.append({**cr, "id": sid, "kind": "strategy", "name": (names.get(sid) or {}).get("name", sid),
                     "family": (names.get(sid) or {}).get("family"), "cagr": m.get("cagr"), "sharpe": m.get("sharpe"),
                     "max_drawdown": m.get("max_drawdown"), "alpha": alpha, "alpha_t": t, "r2": fl.get("r2"),
                     "equity_beta": eq.get("beta"), "capm_alpha": capm["alpha"], "capm_t": capm["alpha_t"], "capm_beta": capm["beta"],
                     "deflated_sharpe": dsr, "pbo": (val.get("pbo") or {}).get("pbo"),
                     "cpcv_positive": (val.get("cpcv") or {}).get("share_positive"),
                     "evaluated_at": d.get("evaluated_at"), "verdict": v, "verdict_text": VERDICT_TEXT[v],
                     "note": ("Statistically clear but economically tiny ({:+.2%} a year) — the kind of steady small gain that "
                              "short-option strategies earn until a rare large loss.".format(alpha)
                              if alpha is not None and (t or 0) >= 2 and 0 < alpha < MIN_ALPHA else
                              "Alpha against equities alone (t = {:.1f}) disappears once credit, rates and other exposures are "
                              "included — it is carry from those risks, not skill.".format(capm["alpha_t"])
                              if (capm["alpha_t"] or 0) >= 2 and (t or 0) < 1.2 else None)})
    for alpha_lab in labs:
        uni = alpha_lab.get("universe_label") or "S&P 500"
        for s in alpha_lab.get("composites", []) + alpha_lab["signals"]:
            ex, t = s.get("excess_vs_universe_ann"), s.get("ic_t")
            v = ("alpha" if (t or 0) >= 2.5 and (ex or 0) >= MIN_ALPHA else
                 "promising" if (t or 0) >= 1.2 and (ex or 0) >= MIN_ALPHA else "no edge")
            rows.append({"id": f"signal:{alpha_lab.get('universe_id', 'sp500')}:{s['id']}", "kind": "stock signal", "name": s["name"],
                         "family": f"Stock Signal Lab · {uni}",
                         "cagr": (s.get("top_quintile_net") or {}).get("ann_return"), "sharpe": (s.get("long_short") or {}).get("sharpe"),
                         "alpha": ex, "alpha_t": t, "alpha_basis": "top fifth vs equal-weight index; t is the rank-IC t-statistic",
                         "verdict": v, "verdict_text": VERDICT_TEXT[v]})
    macro = None
    try:
        snaps = sorted((p for p in (ROOT / "live").glob("model_*.json") if "-" not in p.stem), key=lambda p: p.stat().st_mtime)
        bt = json.loads(snaps[-1].read_text())["result"]["backtest"]
        tv = bt.get("tactical_vs_strategic") or {}
        t = tv.get("t_stat")
        v = "alpha" if (t or 0) >= 2 else "promising" if (t or 0) >= 1.2 and (tv.get("annualised_diff") or 0) > 0 else "no edge"
        macro = {"id": "macro_tactical", "kind": "macro model", "name": "Macro model tactical tilt (vs its strategic portfolio)",
                 "family": "Macro model", "alpha": tv.get("annualised_diff"), "alpha_t": t, "information_ratio": tv.get("information_ratio"),
                 "alpha_basis": "tactical minus strategic, a year, net of costs", "verdict": v, "verdict_text": VERDICT_TEXT[v]}
        rows.append(macro)
    except Exception:                                           # noqa: BLE001
        pass
    order = {"alpha": 0, "promising": 1, "beta": 2, "no edge": 3}
    rows.sort(key=lambda x: (order[x["verdict"]], -(x.get("alpha_t") or -9)))
    counts = {k: sum(1 for x in rows if x["verdict"] == k) for k in order}
    best = [x for x in rows if x["verdict"] in ("alpha", "promising")]
    headline = (f"{counts['alpha']} meeting historical alpha criteria, {counts['promising']} promising, {counts['beta']} mostly market beta and "
                f"{counts['no edge']} without an edge, out of {len(rows)} tested.")
    names_by_id = {x["id"]: x["name"] for x in rows}
    forward = [{**f, "name": names_by_id.get(f["id"], f.get("name"))} for f in forward_record()]
    return {"rows": rows, "counts": counts, "n_trials": n_trials, "headline": headline, "forward": forward,
            "trial_count_basis":"Current loaded strategy/signal catalogue; not the complete historical search ledger. Historical criteria do not prove future alpha.",
            "takeaways": _takeaways(rows, counts),
            "method": __doc__.strip().split("\n\n", 1)[1],
            "stale_note": "Strategy results are re-evaluated when opened in the Quant Lab library; dates are shown per row."}


def _takeaways(rows: List[Dict[str, Any]], counts: Dict[str, int]) -> List[str]:
    out = []
    if counts["alpha"] == 0:
        out.append("Nothing tested so far clears the bar for proven alpha once multiple testing is allowed for — so no strategy "
                   "deserves a large, levered allocation on the evidence alone.")
    prom = [x for x in rows if x["verdict"] == "promising"]
    if prom:
        out.append("Closest to an edge: " + "; ".join(f"{x['name']} ({x['alpha']:+.1%} a year, t = {x['alpha_t']:.1f})" for x in prom[:4])
                   + ". Run these small and track them live before sizing up.")
    beta = [x for x in rows if x["verdict"] == "beta"]
    if beta:
        out.append(f"{len(beta)} strategies mostly repackage equity beta — their returns are available from an index fund at a fraction of "
                   "the cost and turnover.")
    sig = [x for x in rows if x["kind"] == "stock signal"]
    if sig and not any(x["verdict"] in ("alpha", "promising") for x in sig):
        out.append("Classic stock-picking signals (momentum, value, profitability, earnings drift, 52-week high …) show no reliable "
                   "edge in S&P 500 stocks since 2014 — don't pay transaction costs to trade them in large caps.")
    return out


# ── forward tracking: freeze a candidate today, then measure only what happens after ──
WATCH = ROOT / "quant" / "proof" / "watch.json"


def watchlist() -> List[Dict[str, Any]]:
    try:
        return json.loads(WATCH.read_text())
    except Exception:                                           # noqa: BLE001
        return []


def watch_add(sid: str, since: str, reason: str, governed_model: Optional[int] = None, mandate: str = "") -> List[Dict[str, Any]]:
    """Start tracking a strategy out-of-sample from `since` (kept if already tracked)."""
    w = watchlist()
    if not any(x["id"] == sid for x in w):
        w.append({"id": sid, "since": since, "reason": reason, "governed_model": governed_model, "mandate": mandate})
        WATCH.parent.mkdir(parents=True, exist_ok=True)
        WATCH.write_text(json.dumps(w, indent=1))
    return w


def forward_record() -> List[Dict[str, Any]]:
    """Each tracked strategy's return since it was frozen, against its benchmark, from the library's latest re-run
    (its decisions are causal, so days after the freeze are genuinely out-of-sample)."""
    out = []
    for w in watchlist():
        f = ROOT / "quant" / "library" / f"{w['id']}.json"
        rec = {**w, "days": 0, "return": None, "benchmark": None, "excess": None, "evaluated_at": None}
        try:
            d = json.loads(f.read_text())
            dates = d.get("dates") or []
            r = np.array([x if x is not None else np.nan for x in d.get("returns") or []], dtype=float)
            b = np.array([x if x is not None else np.nan for x in d.get("benchmark") or []], dtype=float)
            keep = np.array([str(x)[:10] > w["since"] for x in dates])
            rec["evaluated_at"] = d.get("evaluated_at")
            rec["name"] = d.get("name") or w["id"]
            if keep.any():
                rec["days"] = int(keep.sum())
                rec["return"] = float(np.nanprod(1 + r[keep]) - 1)
                if len(b) == len(r):
                    rec["benchmark"] = float(np.nanprod(1 + b[keep]) - 1)
                    rec["excess"] = rec["return"] - rec["benchmark"]
        except Exception:                                       # noqa: BLE001 — shown as not yet evaluated
            pass
        out.append(rec)
    return out
