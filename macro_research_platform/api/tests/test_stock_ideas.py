"""Stock ideas: sector-capped ranking, reasons vs risks, day-over-day changes, track record."""
from datetime import date, timedelta

import numpy as np

from api import stock_ideas as si


def test_diversify_caps_each_sector():
    rows = [{"symbol": f"E{i}", "sector": "Energy", "s": 1 - i / 10} for i in range(6)] + \
           [{"symbol": "T1", "sector": "Tech", "s": 0.1}]
    out = si.diversify(rows, "s", limit=10, per_sector=3)
    assert [r["symbol"] for r in out] == ["E0", "E1", "E2", "T1"]


def test_rationale_separates_reasons_from_risks():
    full = {"components": {
        "trend": {"score": 1.0}, "momentum": {"return_12_1": 0.4},
        "earnings": {"surprise_pct": -27.0, "days_since": 30, "next_date": (date.today() + timedelta(days=5)).isoformat()},
        "analysts": {"upside": 0.02, "upgrades": 0, "downgrades": 2, "target_raises": 1, "target_cuts": 3},
        "quality": {"score": 0.7}}, "timing": {"state": "extended"}}
    r = si.rationale(full)
    assert "Uptrend (above 50/200-day)" in r["pros"] and "High quality" in r["pros"]
    assert any("EPS surprise -27%" in x for x in r["cons"]) and any("Earnings in 5d" in x for x in r["cons"])
    assert any("downgrade" in x for x in r["cons"]) and "Price stretched" in r["cons"]
    assert not any("EPS" in x for x in r["pros"])


def test_diff_runs():
    prev = {"buy": [{"symbol": "A"}, {"symbol": "B"}]}
    cur = {"buy": [{"symbol": "B"}, {"symbol": "C"}]}
    assert si.diff_runs(prev, cur) == {"new": ["C"], "dropped": ["A"]}
    assert si.diff_runs(None, cur) == {"new": ["B", "C"], "dropped": []}


def test_track_record_vs_spx_and_min_age():
    old = (date.today() - timedelta(days=10)).isoformat()
    new = date.today().isoformat()
    log = [{"date": old, "spx": 100.0, "buy": [{"symbol": "A", "price": 50.0}, {"symbol": "B", "price": 20.0}]},
           {"date": new, "spx": 110.0, "buy": [{"symbol": "C", "price": 10.0}]}]
    tr = si.track_record(log, {"A": 60.0, "B": 20.0, "C": 11.0}, spx_now=110.0)
    assert tr["ideas"] == 2                              # today's idea is too young to count
    assert tr["avg_return"] == np.mean([0.2, 0.0]).round(4)
    assert tr["avg_excess"] == round(np.mean([0.2 - 0.1, 0.0 - 0.1]), 4) and tr["beat_spx"] == 0.5


def test_price_snapshot_uptrend():
    rng = np.random.default_rng(3)
    c = 100 * np.exp(np.cumsum(rng.normal(0.001, 0.01, 400)))
    snap = si.price_snapshot(c, c * 1.01, c * 0.99)
    assert snap["above_200d"] and snap["price_setup"] > 0.35


def test_cap_by_does_not_group_missing_values():
    rows = [{"symbol": f"X{i}", "country": "JP", "sector": None, "s": 1 - i / 100} for i in range(8)]
    out = si.cap_by(rows, "s", 20, {"country": 6, "sector": 2})
    assert len(out) == 6                                   # country cap applies, missing sector does not


def test_gappy_price_series_gives_no_nan_score():
    """A price series with gaps (thin frontier listings) must not produce a NaN set-up,
    which made /api/v1/stock/ideas fail JSON encoding."""
    import numpy as np
    from api import stock_ideas as si
    c = np.linspace(50, 80, 400)
    c[150] = np.nan
    snap = si.price_snapshot(c, c * 1.01, c * 0.99)
    assert snap is None or np.isfinite(snap["price_setup"])
    rows = si._group_stats([{"country": "LT", "price_setup": float("nan"), "above_200d": True}], "country")
    assert rows[0]["avg_setup"] is None
