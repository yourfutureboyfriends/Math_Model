"""Options research: stage-1 correctness checks, exit logic, and the controlled configuration hand-off."""
import json

import numpy as np
import pytest


def test_stage1_checks_pass():
    from api.quant.optresearch import selfcheck
    failed = [c for c in selfcheck.run_all() if not c["passed"]]
    assert not failed, failed


def test_stop_loss_triggers_on_a_crash():
    from api.quant.optresearch import market, simulate as sim, strategies as st, vol
    p = market.synthetic(700, ["SPY", "AAA"])
    p.a["px"][400:, 1] *= 0.7                     # a 30% gap down in AAA
    p.a["close"][400:, 1] *= 0.7
    surf = vol.synthetic_surface(p)
    day = p.dates.values.astype("datetime64[D]").astype(np.int64)
    cand = {"t": np.array([380]), "j": np.array([1]), "score": np.ones(1, np.float32),
            "feat": {k: np.ones(1, np.float32) for k in ("iv_rv", "iv_pct", "mom_rank", "adx", "range_z", "mom6", "spy_ret20")}}
    ts = sim.simulate(p, surf, "bull_put", st.DEFAULTS["bull_put"], cand)
    ex = sim.apply_exits(ts, 0.5, 2.0, 21, day)
    assert ex["reason"][0] == 1                    # stop-loss
    assert ex["pnl"][0] < 0 and ex["pnl"][0] >= -ts["max_loss"][0] - 0.1


def test_approval_needs_confirmation_acknowledgement_and_rolls_back(tmp_path, monkeypatch):
    from api.quant.optresearch import deploy
    monkeypatch.setattr(deploy, "ROOT", tmp_path)
    res = {"experiment_id": "x1", "stage": 2, "universe": {}, "limitations": [], "portfolio_defaults": {},
           "strategies": {"iron_condor": {"chosen": {"params": {"short_delta": 0.16}}, "segments": {"development": {}, "validation": {}},
                                          "survival": {"survived": False}, "data_class": "model_observed_iv"}}}
    a = deploy.export_candidate(res, "iron_condor", "tester")
    f = a["config"]
    name = f"iron_condor-v{f['version']}.json"
    with pytest.raises(ValueError):
        deploy.approve(name, "admin", "approve it")                          # wrong confirmation
    with pytest.raises(ValueError):
        deploy.approve(name, "admin", "APPROVE iron_condor-v1")              # failed validation, no acknowledgement
    out = deploy.approve(name, "admin", "APPROVE iron_condor-v1", acknowledge=True, reason="test")
    assert out["warnings"] and deploy.production()["active"]["iron_condor"]["version"] == 1
    b = deploy.export_candidate(res, "iron_condor", "tester")
    deploy.approve("iron_condor-v2.json", "admin", "APPROVE iron_condor-v2", acknowledge=True, reason="test")
    assert deploy.production()["active"]["iron_condor"]["version"] == 2
    deploy.rollback("iron_condor", "admin")
    assert deploy.production()["active"]["iron_condor"]["version"] == 1
    with pytest.raises(ValueError):                                          # approved files are immutable
        deploy.approve("iron_condor-v2.json", "admin", "APPROVE iron_condor-v2", acknowledge=True, reason="again")
    # a tampered candidate is refused
    c = tmp_path / "candidates" / "iron_condor-v2.json"
    d = json.loads(c.read_text()); d["params"]["short_delta"] = 0.5; c.write_text(json.dumps(d))
    (tmp_path / "approved" / "iron_condor-v2.json").unlink()
    with pytest.raises(ValueError, match="hash"):
        deploy.approve("iron_condor-v2.json", "admin", "APPROVE iron_condor-v2", acknowledge=True, reason="x")


def test_walk_forward_uses_only_prior_data():
    import pandas as pd
    from api.quant.optresearch import validate
    dates = pd.bdate_range("2016-01-01", "2023-12-31")
    n = len(dates)
    a = np.where(dates.year < 2019, 0.002, -0.002)       # good early, bad later
    b = np.full(n, 0.0001)
    wf = validate.walk_forward({"a": a, "b": b}, dates, np.zeros(n))
    first = wf["choices"][0]
    assert first["year"] == 2018 and first["config"] == "a"     # chosen on 2016–2017 only
    assert any(c["config"] == "b" for c in wf["choices"] if c["year"] >= 2021)
