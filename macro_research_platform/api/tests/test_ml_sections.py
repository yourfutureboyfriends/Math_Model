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
