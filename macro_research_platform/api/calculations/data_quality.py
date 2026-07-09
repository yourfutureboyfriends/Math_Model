"""
Data-quality checks — pure, tested (Phase 9).

Flags bad data before it propagates into signals/risk: outlier "ticks" (a value that
jumps implausibly from the previous one) and statistical outliers (values far from the
recent distribution). Returns structured issues, never mutates the data.
"""
from __future__ import annotations

from typing import Dict, List, Sequence, Optional
import numpy as np


def detect_jump_outliers(closes: Sequence[float], jump_threshold: float = 0.25) -> List[Dict]:
    """Flag day-over-day moves larger than `jump_threshold` (e.g. 0.25 = 25%).

    A single tick 50% off the previous close is almost always a data error, not a real
    move. Returns [{index, prev, value, pct_change}].
    """
    c = np.asarray(closes, dtype=float)
    issues = []
    for i in range(1, c.size):
        if c[i - 1] and c[i - 1] > 0:
            chg = c[i] / c[i - 1] - 1.0
            if abs(chg) > jump_threshold:
                issues.append({"index": i, "prev": round(float(c[i - 1]), 4),
                               "value": round(float(c[i]), 4), "pct_change": round(float(chg), 4)})
    return issues


def detect_zscore_outliers(values: Sequence[float], z_threshold: float = 6.0) -> List[Dict]:
    """Flag values more than `z_threshold` std from the series mean (extreme outliers)."""
    v = np.asarray(values, dtype=float)
    v = v[~np.isnan(v)]
    if v.size < 10 or v.std(ddof=1) == 0:
        return []
    mean, std = v.mean(), v.std(ddof=1)
    issues = []
    for i, x in enumerate(values):
        if x is None or (isinstance(x, float) and np.isnan(x)):
            continue
        z = (x - mean) / std
        if abs(z) > z_threshold:
            issues.append({"index": i, "value": round(float(x), 4), "zscore": round(float(z), 2)})
    return issues


def quality_report(name: str, closes: Sequence[float],
                   jump_threshold: float = 0.25, z_threshold: float = 6.0) -> Dict:
    """Per-series quality report: jump + z-score outliers, and an overall status.

    status: PASS (no issues), WARN (z-score outliers only), FAIL (jump outliers — a
    hard data error likely to corrupt downstream calculations).
    """
    c = [x for x in closes if isinstance(x, (int, float)) and x == x]
    if len(c) < 10:
        return {"series": name, "status": "UNKNOWN", "reason": "insufficient data",
                "observations": len(c), "jump_outliers": [], "zscore_outliers": []}
    jumps = detect_jump_outliers(c, jump_threshold)
    zs = detect_zscore_outliers(c, z_threshold)
    status = "FAIL" if jumps else "WARN" if zs else "PASS"
    return {
        "series": name, "status": status, "observations": len(c),
        "jump_outliers": jumps[:10], "jump_count": len(jumps),
        "zscore_outliers": zs[:10], "zscore_count": len(zs),
        "latest": round(float(c[-1]), 4),
    }
