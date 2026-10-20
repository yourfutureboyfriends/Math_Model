"""The per-run container (api/quant/sandbox.py): its isolation flags, and a real run on synthetic data that must match the
process sandbox exactly. The live test is skipped when Docker or the sandbox image is not available."""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from api.quant import sandbox

CODE = '''
import numpy as np
import pandas as pd
from dataclasses import dataclass
from scipy import stats
UNIVERSE = ["AAA", "BBB"]
START = "2019-06-03"

@dataclass
class Cfg:
    n: int = 60

class Model:
    def __init__(self, cfg):
        self.cfg = cfg
    @property
    def n(self):
        return self.cfg.n
    def weights(self, close):
        r = close.pct_change(self.n).fillna(0)
        p = pd.DataFrame(stats.norm.cdf(r / 0.1), index=r.index, columns=r.columns)
        return (p > 0.5).astype(float) / 2

def strategy(data, **params):
    return Model(Cfg()).weights(data.close)
'''


def test_container_flags_close_every_exit():
    cmd = sandbox._docker_cmd(Path("/tmp/x"), "qsbx-test", 240)
    s = " ".join(cmd)
    for flag in ("--network none", "--read-only", "--cap-drop ALL", "--security-opt no-new-privileges", "--pids-limit 256",
                 "--memory 4g", "--rm"):
        assert flag in s, flag
    mounts = [cmd[i + 1] for i, c in enumerate(cmd) if c == "-v"]
    assert mounts[0] == "/tmp/x:/work:rw" and all(m.endswith(":ro") for m in mounts[1:])     # only the run folder writable
    assert not any("/Users" in m.split(":")[1] for m in mounts)


def _fake_prepare(code, head, costs, light, tmp, say, cancelled=lambda: False):
    rng = np.random.default_rng(3)
    idx = pd.bdate_range("2019-01-01", periods=300)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0004, 0.01, (300, 2)), axis=0))
    arrays = {"close": close, "open": close, "high": close * 1.003, "low": close * 0.997, "volume": np.full((300, 2), 5e6),
              "rf": np.zeros(300), "vix": np.full(300, 15.0), "observed": np.ones((300, 2), bool),
              "usd_per_unit": np.ones(300), "dates": idx.values.astype("datetime64[ns]").astype(np.int64)}
    np.savez(tmp / "data.npz", **arrays)
    (tmp / "meta.json").write_text(json.dumps({"tickers": ["AAA", "BBB"], "start": "2019-06-03", "params": {}, "costs": {},
                                               "rf_known": True, "provenance": {}, "instruments": None,
                                               "account_currency": "USD", "micro_cols": {}, "light": True}))
    (tmp / "strategy.py").write_text(code)
    return {"cpu": 120, "tickers": 2, "days": 300}


@pytest.mark.skipif(not sandbox.docker_status(refresh=True)["docker"], reason="Docker or the sandbox image is not available")
def test_container_run_matches_the_process_sandbox(monkeypatch):
    monkeypatch.setattr(sandbox, "_prepare", _fake_prepare)
    in_container = sandbox.run(CODE, light=True)
    assert in_container["provenance"]["isolation"].startswith("docker container")
    monkeypatch.setenv("MACRO_SANDBOX_DOCKER", "0")
    sandbox._DOCKER.update(ok=None)
    in_process = sandbox.run(CODE, light=True)
    sandbox._DOCKER.update(ok=None)
    assert in_process["provenance"]["isolation"].startswith("process sandbox")
    assert in_container["metrics"] == in_process["metrics"]
