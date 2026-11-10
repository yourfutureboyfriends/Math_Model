"""Section experts: the live reading must survive a walk-forward record cached on a different day — a series that has
since become unavailable, and a newer month the record has never seen."""
import numpy as np

from api.ml import sections as SX


class _Task:
    name, known_after, features = "synthetic", 6, ["a"]


def _data(months, drop=()):
    rng = np.random.default_rng(0)
    out = {}
    for k in ("a", "b", "c", "ebp", "ts"):
        if k not in drop:
            out[k] = {m: float(v) for m, v in zip(months, rng.normal(size=len(months)))}
    return out


def _months(n):
    return [f"{1980 + i // 12}-{i % 12 + 1:02d}" for i in range(n)]


def test_live_reading_survives_a_stale_cached_record():
    months = _months(480)
    rng = np.random.default_rng(1)
    y_of = {m: int(v) for m, v in zip(months, rng.random(len(months)) < 0.2)}
    sec = {"a": "core", "b": "credit", "c": "credit", "ebp": "credit", "ts": "rates_curve"}
    wf = SX.walk_forward(_Task(), months, y_of, _data(months), sec)
    # a day later: series 'c' is gone and one more month exists, with no answer yet
    later = months + ["2020-01"]
    y_later = {**y_of, "2020-01": None}
    data_later = _data(later, drop=("c",))
    out = SX.live(_Task(), later, y_later, data_later, {k: v for k, v in sec.items() if k != "c"}, wf, {})
    assert 0 < out["probability_raw"] < 1
    assert out["as_of"] == "2020-01"
    credit = next(r for r in out["sections"] if r["section"] == "credit")
    assert credit["inputs"] == 2                                            # 'c' dropped, not a KeyError
    assert {s["key"] for s in out["situation"]} == set(SX.SITUATIONS)


def test_the_ragged_edge_carries_at_most_three_months():
    s = {"2026-06": 1.0, "2026-07": 2.0}
    out = SX._extend(s, 3)
    assert out["2026-10"] == 2.0 and "2026-11" not in out                # the last known value, three months on
    assert SX._extend({"2025-11": 5.0}, 2)["2026-01"] == 5.0             # across a year end


def test_history_reads_the_record_the_result_was_built_from(monkeypatch):
    """compute() stores the walk-forward under a fingerprinted key; history() must read that key, not rebuild one."""
    from api.ml import engine as E
    import api.handlers.macro_inputs as MI
    task = next(iter(E.TASKS))
    record = {"history": {"months": ["2000-01", "2000-02"], "y": [0, 1], "raw": {"champion": [0.2, 0.6]}}}
    seen = []
    monkeypatch.setattr(E, "cached", lambda name: {"available": True, "backtest_key": "ml_bt6_abc_sec2_" + name})
    monkeypatch.setattr(MI, "_disk_load", lambda name, max_age=None: (seen.append(name), {"data": record})[1])
    out = E.history(task)
    assert seen == [f"ri_ml_bt6_abc_sec2_{task}"]
    assert out["months"] == ["2000-01", "2000-02"] and "champion" in out["models"]


def test_a_failed_refresh_keeps_the_last_good_series(monkeypatch):
    """A rate-limited rebuild must not cache a panel with series silently missing."""
    from api.ml import fred_fetch as FF
    import api.handlers.macro_inputs as MI
    prev = {"p_CPIAUCSL": {"2026-09": 0.1}, "p_PAYEMS": {"2026-09": 0.2}}
    monkeypatch.setattr(MI, "_disk_load", lambda name, max_age=None: {"data": prev} if name == "ri_ml_panel" else None)
    out = FF.keep_last_good("ml_panel", {"p_PAYEMS": {"2026-10": 0.3}}, ["p_PAYEMS", "p_CPIAUCSL", "p_NEVER"])
    assert out["p_PAYEMS"] == {"2026-10": 0.3}                              # fresh data wins
    assert out["p_CPIAUCSL"] == {"2026-09": 0.1}                            # failed: last good copy
    assert "p_NEVER" not in out


def test_fred_reads_are_retried(monkeypatch):
    from api.ml import fred_fetch as FF
    monkeypatch.setattr(FF.time, "sleep", lambda s: None)
    calls = []

    class F:
        def get_series(self, sid, **kw):
            calls.append(sid)
            if len(calls) < 3:
                raise RuntimeError("Too Many Requests")
            return [1.0]
    assert FF.get_series(F(), "CPIAUCSL") == [1.0] and len(calls) == 3


def test_a_mostly_failed_build_is_refused_not_cached(monkeypatch):
    import pytest
    from api.ml import fred_fetch as FF
    import api.handlers.macro_inputs as MI
    monkeypatch.setattr(MI, "_disk_load", lambda name, max_age=None: None)
    with pytest.raises(RuntimeError):
        FF.keep_last_good("ml_extended", {}, ["x_A", "x_B", "x_C"])
