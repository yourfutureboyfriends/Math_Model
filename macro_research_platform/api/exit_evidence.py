"""
Exit-rule evidence: the entry model's price-only buy signals (api/calculations/stock_timing.price_signal_history,
no look-ahead) managed by each exit rule (api/calculations/trade_management.EXIT_RULES), plus a 63-day hold with no
management as the baseline — over the stock screener's 30 large caps, 10 years of daily prices, 0.1% round-trip
cost. Each rule trades the signals independently, one position per stock at a time. Also split into the first and
second half of the period, to check the ranking is stable. Results are cached for a week
(data/processed/exit_evidence.json); a run takes about ten seconds once prices are cached by Yahoo.

Caveat stated with the results: the sample is today's largest stocks over a strong decade (survivorship), which
flatters rules that hold longer — compare the rules with each other, not the absolute numbers.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from api.calculations import stock_timing as st
from api.calculations import trade_management as tm

logger = logging.getLogger(__name__)
FILE = Path(__file__).resolve().parent.parent / "data" / "processed" / "exit_evidence.json"
MAX_AGE = 7 * 86400
_state: Dict[str, Any] = {"running": False, "error": None}
RULES = {"hold63": "Baseline: hold 63 sessions, no management", **tm.EXIT_RULES}


def _trades(c, h, l, sig, rule: str) -> List[Dict[str, float]]:
    out, i, n = [], 260, len(c)
    while i < n - 1:
        if sig[i] != 1:
            i += 1
            continue
        if rule == "hold63":
            j = min(n - 1, i + 63)
            if j <= i:
                break
            out.append({"ret": float(c[j] / c[i] - 1), "r": 0.0, "days": j - i})
            i = j + 1
            continue
        t = tm.simulate_exit(c, h, l, i, rule)
        if t is None:
            break
        out.append(t)
        i += t["days"] + 1
    return out


def run() -> Dict[str, Any]:
    """Run the comparison and save it."""
    import yfinance as yf
    from api.routers.stock import DEFAULT_UNIVERSE
    t0 = time.time()
    full = {r: [] for r in RULES}
    halves = {r: ([], []) for r in RULES}
    used = []
    for s in DEFAULT_UNIVERSE:
        try:
            hst = yf.Ticker(s).history(period="10y", interval="1d", auto_adjust=True).dropna(subset=["Close"])
        except Exception as e:                                                 # noqa: BLE001 — skip a failed download
            logger.warning("[exit-evidence] %s: %s", s, e)
            continue
        if len(hst) < 600:
            continue
        c, h, l = (hst[k].to_numpy(dtype=float) for k in ("Close", "High", "Low"))
        sig = st.price_signal_history(c, h, l)
        mid = len(c) // 2
        s1, s2 = sig.copy(), sig.copy()
        s1[mid:] = 0
        s2[:mid] = 0
        for r in RULES:
            full[r] += _trades(c, h, l, sig, r)
            halves[r][0].extend(_trades(c, h, l, s1, r))
            halves[r][1].extend(_trades(c, h, l, s2, r))
        used.append(s)
    out = {"rules": [{"rule": r, "label": RULES[r], **tm.summarise_trades(full[r]),
                      "first_half": tm.summarise_trades(halves[r][0]), "second_half": tm.summarise_trades(halves[r][1])}
                     for r in RULES],
           "universe": used, "period": "10 years of daily prices", "cost_round_trip": 0.001,
           "computed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "runtime_s": round(time.time() - t0, 1),
           "caveat": "Today's largest stocks over a strong decade (survivorship) flatter rules that hold longer: compare "
                     "the rules with each other, not the absolute numbers."}
    FILE.parent.mkdir(parents=True, exist_ok=True)
    FILE.write_text(json.dumps(out))
    return out


def latest() -> Optional[Dict[str, Any]]:
    """The saved comparison, with its age; None if never run."""
    try:
        d = json.loads(FILE.read_text())
    except Exception:
        return None
    d["stale"] = time.time() - FILE.stat().st_mtime > MAX_AGE
    return d


async def ensure() -> Dict[str, Any]:
    """The comparison, starting a background run if it is missing or older than a week."""
    d = latest()
    if (d is None or d.get("stale")) and not _state["running"]:
        async def go():
            _state.update(running=True, error=None)
            try:
                await asyncio.to_thread(run)
            except Exception as e:                                             # noqa: BLE001 — reported in status
                _state["error"] = str(e)[:200]
            finally:
                _state["running"] = False
        # keep a reference: asyncio holds tasks weakly, and an unreferenced task can be collected mid-run
        _state["task"] = asyncio.get_running_loop().create_task(go())
    return {"result": d, "running": _state["running"], "error": _state["error"]}
