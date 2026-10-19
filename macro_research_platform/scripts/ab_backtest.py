"""Same-process A/B of the ledger (codelab.backtest): the committed engine at a git revision vs the working copy, on
identical data and target weights, timed alternately (ABAB) so machine load affects both equally.

    ../.venv/bin/python scripts/ab_backtest.py STRATEGY.py [revision]
"""
import json
import subprocess
import sys
import time
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> None:
    import numpy as np
    from api.quant import codelab as new, codeserver, sandbox
    rev = sys.argv[2] if len(sys.argv) > 2 else "HEAD"
    src = subprocess.run(["git", "show", f"{rev}:macro_research_platform/api/quant/codelab.py"], cwd=ROOT,
                         capture_output=True, text=True, check=True).stdout
    old = types.ModuleType("codelab_old")
    old.__file__ = str(ROOT / "api" / "quant" / "codelab.py")
    exec(compile(src, "codelab_old", "exec"), old.__dict__)          # noqa: S102 — our own committed source
    code = Path(sys.argv[1]).read_text()
    head = sandbox.check(code)
    st = new.load_strategy(code)
    names = codeserver.tradable_universe(head["tradable"])
    d = codeserver.load_data(list(dict.fromkeys(head["universe"] + names)), head["start"],
                             limit=new.LARGE_UNIVERSE_LIMIT, allow_missing=True, account=head["account"])
    if head.get("calendar"):
        d = codeserver.account_session_data(d, head["calendar"])
    W = new.run_weights(st["strategy"], d, {})
    out = {"shape": list(d.close.shape), "old": [], "new": []}
    res = {}
    for which in ("old", "new", "old", "new"):
        mod = old if which == "old" else new
        t = time.perf_counter()
        r = mod.backtest(W, d, None, st["start"])
        out[which].append(round(time.perf_counter() - t, 2))
        res[which] = r["ret"]
    out["identical_returns"] = bool(np.allclose(res["old"].to_numpy(), res["new"].to_numpy(), atol=1e-12, equal_nan=True))
    print(json.dumps(out))


if __name__ == "__main__":
    main()
