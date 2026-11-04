"""A/B timing of the Code Lab data loader on the global universe: `old` loads data.py, corpactions.py and codeserver.py
as committed at a git revision (default HEAD) in place of the working copies; `new` uses the working copies. Runs the
load twice and reports both (the second is warm-cache). No profiler.

    ../.venv/bin/python scripts/ab_load_data.py old|new [revision]
"""
import json
import resource
import subprocess
import sys
import time
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _swap(rev: str) -> None:
    for name in ("data", "corpactions", "codeserver"):
        path = ROOT / "api" / "quant" / f"{name}.py"
        src = subprocess.run(["git", "show", f"{rev}:macro_research_platform/api/quant/{name}.py"], cwd=ROOT,
                             capture_output=True, text=True, check=True).stdout
        mod = types.ModuleType(f"api.quant.{name}")
        mod.__file__ = str(path)
        mod.__package__ = "api.quant"
        sys.modules[f"api.quant.{name}"] = mod
        exec(compile(src, str(path), "exec"), mod.__dict__)     # noqa: S102 — our own committed source


def main() -> None:
    which = sys.argv[1]
    if which == "old":
        _swap(sys.argv[2] if len(sys.argv) > 2 else "HEAD")
    from api.quant import codelab, codeserver
    names = codeserver.tradable_universe("GLOBAL")
    u = list(dict.fromkeys(["ACWI", "SPY"] + names))
    times = []
    for _ in range(2):
        t = time.perf_counter()
        d = codeserver.load_data(u, "2011-01-03", limit=codelab.LARGE_UNIVERSE_LIMIT, allow_missing=True)
        times.append(round(time.perf_counter() - t, 1))
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1 << 20)
    print(json.dumps({"version": which, "seconds": times, "shape": list(d.close.shape), "peak_rss_mb": round(rss)}))


if __name__ == "__main__":
    main()
