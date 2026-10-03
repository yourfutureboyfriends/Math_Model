"""
Risk limits and pre-trade compliance — pure, tested.

Each limit has a SOFT threshold (warn / needs sign-off) and a HARD threshold (block).
Metrics are fractions of NAV unless noted. `evaluate_limits` reports utilization and status
for the current book; `pretrade_check` compares the book before and after a proposed trade:

    BLOCK — the trade creates or worsens a HARD breach
    WARN  — the trade creates or worsens a SOFT breach (needs risk sign-off)
    PASS  — otherwise (including trades that REDUCE an existing breach)
"""
from __future__ import annotations

from typing import Dict, List, Optional

# metric -> (label, soft, hard, unit). "max" limits: value must stay <= threshold.
DEFAULT_LIMITS: Dict[str, Dict] = {
    "gross_exposure":   {"label": "Gross exposure",          "soft": 1.50, "hard": 2.00, "unit": "% NAV"},
    "net_exposure_abs": {"label": "Net exposure (abs)",      "soft": 0.80, "hard": 1.00, "unit": "% NAV"},
    "single_name":      {"label": "Largest single name",     "soft": 0.10, "hard": 0.15, "unit": "% NAV"},
    "top5":             {"label": "Top-5 concentration",     "soft": 0.40, "hard": 0.55, "unit": "% NAV"},
    "var95_1d":         {"label": "VaR 95% 1-day",           "soft": 0.015, "hard": 0.020, "unit": "% NAV"},
    "drawdown":         {"label": "Drawdown from peak",      "soft": 0.08, "hard": 0.12, "unit": "% NAV"},
    "liquidity_days":   {"label": "Days to liquidate (max)", "soft": 3.0, "hard": 5.0, "unit": "days"},
}

_ORDER = {"OK": 0, "WARN": 1, "BREACH": 2}


def merge_limits(overrides: Optional[Dict[str, Dict]]) -> Dict[str, Dict]:
    """Defaults updated with user overrides (only soft/hard per known metric)."""
    out = {k: dict(v) for k, v in DEFAULT_LIMITS.items()}
    for k, v in (overrides or {}).items():
        if k in out and isinstance(v, dict):
            for f in ("soft", "hard"):
                if isinstance(v.get(f), (int, float)) and v[f] >= 0:
                    out[k][f] = float(v[f])
    for k, v in out.items():
        if v["soft"] > v["hard"]:
            v["soft"] = v["hard"]
    return out


def _status(value: Optional[float], soft: float, hard: float) -> str:
    if value is None:
        return "OK"
    if value > hard:
        return "BREACH"
    if value > soft:
        return "WARN"
    return "OK"


def evaluate_limits(metrics: Dict[str, Optional[float]], limits: Dict[str, Dict]) -> Dict:
    """Utilization (value / hard) and status per limit, plus the overall status."""
    rows: List[Dict] = []
    for key, lim in limits.items():
        val = metrics.get(key)
        rows.append({
            "metric": key, "label": lim["label"], "unit": lim["unit"],
            "value": None if val is None else round(float(val), 4),
            "soft": lim["soft"], "hard": lim["hard"],
            "utilization": None if val is None or not lim["hard"] else round(float(val) / lim["hard"], 3),
            "status": _status(val, lim["soft"], lim["hard"]),
            "available": val is not None,
        })
    worst = max((r["status"] for r in rows), key=_ORDER.get, default="OK")
    return {"overall": worst, "limits": rows,
            "breaches": [r for r in rows if r["status"] == "BREACH"],
            "warnings": [r for r in rows if r["status"] == "WARN"]}


def pretrade_check(before: Dict[str, Optional[float]], after: Dict[str, Optional[float]],
                   limits: Dict[str, Dict]) -> Dict:
    """Compare limit status before vs after a proposed trade (see module docstring)."""
    checks = []
    decision = "PASS"
    for key, lim in limits.items():
        b, a = before.get(key), after.get(key)
        sb, sa = _status(b, lim["soft"], lim["hard"]), _status(a, lim["soft"], lim["hard"])
        worsens = a is not None and (b is None or a > b + 1e-12)
        if sa == "BREACH" and worsens:
            verdict = "BLOCK"
        elif sa in ("WARN", "BREACH") and worsens:
            verdict = "WARN"
        else:
            verdict = "PASS"
        if verdict == "BLOCK" or (verdict == "WARN" and decision == "PASS"):
            decision = verdict
        checks.append({"metric": key, "label": lim["label"], "before": b, "after": a,
                       "status_before": sb, "status_after": sa, "verdict": verdict})
    def _fmt(key, v):
        if v is None:
            return "n/a"
        return f"{v:.1f} days" if limits[key]["unit"] == "days" else f"{v * 100:.1f}% NAV"

    def _reason(c):
        lim = limits[c["metric"]]
        bound = lim["hard"] if c["verdict"] == "BLOCK" else lim["soft"]
        kind = "hard" if c["verdict"] == "BLOCK" else "soft"
        return (f"{c['label']}: {_fmt(c['metric'], c['before'])} → {_fmt(c['metric'], c['after'])} "
                f"(over {kind} limit {_fmt(c['metric'], bound)}) — {c['verdict']}")

    return {"decision": decision, "checks": checks,
            "reasons": [_reason(c) for c in checks if c["verdict"] != "PASS"]}
