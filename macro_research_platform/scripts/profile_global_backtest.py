"""
Profile the 10-year, ~3,100-stock GLOBAL Code Lab backtest stage by stage (data load, account calendar, one strategy
call, the walk-forward ledger, the research checks) and report wall time, peak memory and the hottest functions.

    ../.venv/bin/python scripts/profile_global_backtest.py STRATEGY.py [--out results.json] [--no-checks]

Runs locally on a strategy file you own (the profile needs the engine in-process); the server never runs user code
outside the sandbox.
"""
from __future__ import annotations

import argparse
import cProfile
import io
import json
import pstats
import resource
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def rss_mb() -> float:
    r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return round(r / (1 << 20) if sys.platform == "darwin" else r / 1024, 1)        # bytes on macOS, KiB on Linux


def top(prof: cProfile.Profile, n: int = 25) -> list:
    s = io.StringIO()
    st = pstats.Stats(prof, stream=s)
    rows = []
    for (f, line, fn), (cc, nc, tt, ct, _) in st.stats.items():
        rows.append({"fn": f"{Path(f).name}:{line}:{fn}", "calls": nc, "self_s": round(tt, 2), "cum_s": round(ct, 2)})
    return sorted(rows, key=lambda r: -r["self_s"])[:n]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("strategy")
    ap.add_argument("--out", default="profile_global.json")
    ap.add_argument("--no-checks", action="store_true")
    a = ap.parse_args()
    from api.quant import codelab, codeserver, sandbox
    code = Path(a.strategy).read_text()
    head = sandbox.check(code)
    st = codelab.load_strategy(code)
    out = {"strategy": a.strategy, "engine": codelab.ENGINE_VERSION, "stages": {}}

    def stage(name, fn, profile=False):
        t0 = time.perf_counter()
        prof = cProfile.Profile() if profile else None
        if prof:
            prof.enable()
        res = fn()
        if prof:
            prof.disable()
        out["stages"][name] = {"seconds": round(time.perf_counter() - t0, 2), "peak_rss_mb": rss_mb(),
                               **({"hot": top(prof)} if prof else {})}
        print(name, out["stages"][name]["seconds"], "s", rss_mb(), "MB", flush=True)
        Path(a.out).write_text(json.dumps(out, indent=1))              # checkpoint after every stage
        return res

    names = stage("universe", lambda: codeserver.tradable_universe(head["tradable"]))
    universe = list(dict.fromkeys(head["universe"] + names))
    data = stage("load_data", lambda: codeserver.load_data(universe, head["start"], limit=codelab.LARGE_UNIVERSE_LIMIT,
                                                           allow_missing=True, account=head["account"]), profile=True)
    if head.get("calendar"):
        data = stage("account_calendar", lambda: codeserver.account_session_data(data, head["calendar"]))
    out["shape"] = list(data.close.shape)
    stage("strategy_once", lambda: st["strategy"](data), profile=True)
    bm = codeserver.benchmark_series(head["benchmark"], data.close.index[0].strftime("%Y-%m-%d"), data.account_currency)
    stage("evaluate_walk_forward", lambda: codelab.evaluate(st["strategy"], data, st["params"], st["start"],
                                                            codelab.run_costs(st, None), bm, st["holdout"], st["code_hash"],
                                                            checks=False), profile=True)
    if not a.no_checks:
        stage("research_checks", codelab.research_checks, profile=True)
    out["total_seconds"] = round(sum(s["seconds"] for s in out["stages"].values()), 1)
    Path(a.out).write_text(json.dumps(out, indent=1))
    print("total", out["total_seconds"], "s")


if __name__ == "__main__":
    main()
