"""
Run an options-research stage from the command line (the dashboard runs the same thing as a server job).

    ../.venv/bin/python scripts/run_options_research.py --stage 2 [--strategies bull_put,iron_condor]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class _Say:
    cancelled = False

    def say(self, m: str) -> None:
        print(time.strftime("%H:%M:%S"), m, flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", type=int, required=True, choices=[1, 2, 3, 4])
    ap.add_argument("--strategies", default="")
    ap.add_argument("--owner", default="cli")
    a = ap.parse_args()
    from api.quant.optresearch import runner
    res = runner.run_experiment(a.stage, a.owner, job=_Say(), strategies=[s for s in a.strategies.split(",") if s] or None)
    print(json.dumps(runner.summary(res) if a.stage > 1 else {"passed": res["passed"]}, indent=1, default=str))
    print("experiment", res["experiment_id"], "runtime", res.get("runtime_s"), "s")


if __name__ == "__main__":
    main()
