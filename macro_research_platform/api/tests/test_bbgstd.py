"""FWCV / FOMC / EM / EA: forward rates follow from the curve, the Fed screen sets the dots against futures, the earnings
matrix groups quarters into fiscal years with split-adjusted growth, and the season scorecard counts beats and reactions."""
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from api.marketdata import bbgstd


@pytest.fixture(autouse=True)
def no_cache(monkeypatch):
    monkeypatch.setattr(bbgstd, "_cached", lambda key, ttl, fn: fn())


def test_forward_rates_compound_back_to_the_spot_curve():
    curve = [(1.0, 3.0), (2.0, 3.5), (5.0, 4.0), (10.0, 4.5)]
    f = bbgstd.forward_rate(curve, 1, 1)
    assert (1.035 ** 2) == pytest.approx(1.03 * (1 + f / 100))
    assert bbgstd.forward_rate(curve, 5, 5) == pytest.approx(((1.045 ** 10 / 1.04 ** 5) ** (1 / 5) - 1) * 100)
    assert bbgstd.forward_rate(curve, 10, 10) is None                       # no extrapolation past 10 years
    flat = [(1.0, 4.0), (10.0, 4.0)]
    assert bbgstd.forward_rate(flat, 3, 2) == pytest.approx(4.0)


def test_fomc_sets_the_dots_against_futures(monkeypatch):
    from api.marketdata import extras, insights
    y = date.today().year
    series = {"DFEDTARU": {"2025-12-11": 4.0, "2026-03-19": 3.75, "2026-09-18": 4.0},
              "DFEDTARL": {"2025-12-11": 3.75, "2026-03-19": 3.5, "2026-09-18": 3.75},
              "DFF": {"2026-10-30": 3.88}, "FEDTARMD": {f"{y}-01-01": 4.1, f"{y + 1}-01-01": 3.9}, "FEDTARMDLR": {f"{y}-01-01": 3.0}}
    monkeypatch.setattr(insights, "_fred", lambda sid, years: series.get(sid, {}))
    monkeypatch.setattr(extras, "wirp", lambda: {"meetings": [{"meeting": f"{y}-12-09", "implied_rate": 4.05},
                                                               {"meeting": f"{y + 1}-06-17", "implied_rate": 4.30},
                                                               {"meeting": f"{y + 1}-12-08", "implied_rate": 4.20}], "as_of": "x"})
    r = bbgstd.fomc()
    assert (r["target_lower"], r["target_upper"]) == (3.75, 4.0)
    assert [d["change_bp"] for d in r["decisions"]] == [25, -25]           # newest first; the first row isn't a move
    gap = {g["year"]: g for g in r["dots_vs_market"]}
    assert gap[y]["gap_bp"] == pytest.approx(-5) and gap[y + 1]["gap_bp"] == pytest.approx(30)
    assert r["sep"]["fed_funds"]["longer_run"] == 3.0


def test_earnings_matrix_groups_quarters_into_fiscal_years_and_adjusts_for_splits(monkeypatch):
    from api.marketdata import corporate, extras
    from api.providers import sec_edgar as se
    monkeypatch.setattr(extras, "_company_only", lambda s, w: None)
    monkeypatch.setattr(se, "resolve", lambda s: {"cik": 1})
    monkeypatch.setattr(se, "company_facts", lambda cik: {"entityName": "Test Co"})
    monkeypatch.setattr(se, "_pick_tag", lambda facts, tags: ("t", ["pts"]))
    q = [("2024-03-31", 3.0, "2024-04-30"), ("2024-06-30", 3.0, "2024-07-30"), ("2024-09-30", 3.0, "2024-10-30"), ("2024-12-31", 3.0, "2025-02-15"),
         ("2025-03-31", 1.2, "2025-04-30"), ("2025-06-30", 1.1, "2025-07-30")]
    monkeypatch.setattr(se, "quarterly", lambda pts: [{"end": e, "val": v, "filed": f} for e, v, f in q])
    monkeypatch.setattr(se, "annual", lambda pts: [{"end": "2024-12-31", "val": 12.0, "filed": "2025-02-15"}])
    monkeypatch.setattr(corporate, "actions", lambda s: {"splits": [{"date": "2025-03-01", "ratio": 3.0}]})
    r = bbgstd.earnings_matrix("TST")
    fy24, fy25 = r["rows"]
    assert (fy24["fiscal_year"], fy24["complete"], len(fy24["quarters"])) == (2024, True, 4)
    assert fy24["quarters"][0]["eps"] == pytest.approx(1.0) and fy24["eps"] == pytest.approx(4.0)   # pre-split figures ÷ 3
    assert (fy25["complete"], [x["q"] for x in fy25["quarters"]]) == (False, [1, 2])
    assert fy25["quarters"][0]["eps_yoy"] == pytest.approx(0.2)            # 1.2 vs 1.0, not vs 3.0


def test_earnings_analysis_counts_beats_misses_and_reactions(monkeypatch):
    from api.marketdata import funds
    from api.providers import massive
    monkeypatch.setattr(funds, "index_members", lambda code: {"name": "S&P 500", "source": "t", "members": [
        {"symbol": "AAA", "sector": "Tech", "weight": 0.6}, {"symbol": "BBB", "sector": "Tech", "weight": 0.3},
        {"symbol": "CCC", "sector": "Energy", "weight": 0.1}, {"symbol": "DDD", "sector": "Energy", "weight": 0.0}]})
    d1, d2 = date.today() - timedelta(days=6), date.today() - timedelta(days=5)
    cal = [{"symbol": "AAA", "company": "A", "datetime": f"{d1}T12:00:00", "timing": "BMO", "eps_estimate": 1.0, "eps_reported": 1.1, "surprise_pct": 10.0},
           {"symbol": "BBB", "company": "B", "datetime": f"{d1}T21:00:00", "timing": "AMC", "eps_estimate": 2.0, "eps_reported": 1.8, "surprise_pct": -10.0},
           {"symbol": "CCC", "company": "C", "datetime": f"{d2}T12:00:00", "timing": "BMO", "eps_estimate": 0.5, "eps_reported": 0.5, "surprise_pct": 0.0},
           {"symbol": "DDD", "company": "D", "datetime": f"{date.today() + timedelta(days=3)}T12:00:00", "timing": "BMO", "eps_estimate": 1.0,
            "eps_reported": None, "surprise_pct": None}]
    monkeypatch.setattr(bbgstd, "_calendar_weeks", lambda s, e, cap: cal)
    idx = pd.to_datetime([d1 - timedelta(days=1), d1, d2])
    monkeypatch.setattr(massive, "panel", lambda syms, days: pd.DataFrame({"AAA": [100, 105, 106], "BBB": [50, 50, 45], "CCC": [10, 10, 11]}, index=idx))
    r = bbgstd.earnings_analysis("SPX", 30)
    assert (r["reported"], r["members"]) == (3, 4) and r["beat_rate"] == pytest.approx(1 / 3) and r["miss_rate"] == pytest.approx(1 / 3)
    by = {x["symbol"]: x for x in r["reports"]}
    assert by["AAA"]["reaction"] == pytest.approx(0.05)                   # before the open: same day
    assert by["BBB"]["reaction"] == pytest.approx(-0.10)                  # after the close: next session
    assert r["avg_reaction_miss"] == pytest.approx(-0.10) and r["reported_weight"] == pytest.approx(1.0)
    assert [u["symbol"] for u in r["upcoming"]] == ["DDD"]
    with pytest.raises(bbgstd.NotFound):
        bbgstd.earnings_analysis("UKX")
