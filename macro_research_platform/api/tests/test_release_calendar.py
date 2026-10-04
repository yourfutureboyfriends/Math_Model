"""Release-calendar freshness: grade data against when it is actually published."""
from datetime import date

import pytest

from api.release_calendar import SERIES, assess

SPEC = {s.series_id: s for s in SERIES}
SUN = date(2026, 10, 4)            # a Sunday
assert SUN.weekday() == 6


def _state(series_id, last, today):
    r = assess(SPEC[series_id], last, today)
    return r["state"], r["status"]


def test_monthly_cpi_is_current_between_releases():
    # The old fixed-age check called this STALE (64 days "old"); Sept CPI isn't out until mid-Oct.
    r = assess(SPEC["CPIAUCSL"], date(2026, 8, 1), SUN)
    assert (r["state"], r["status"]) == ("CURRENT", "FRESH")
    assert r["next_expected_release"] == "2026-10-15"


@pytest.mark.parametrize("today,expected", [
    (date(2026, 10, 18), ("DUE", "FRESH")),          # Sept CPI due Oct 15: within grace
    (date(2026, 10, 25), ("LATE", "STALE")),         # past the grace window
])
def test_monthly_release_window(today, expected):
    assert _state("CPIAUCSL", date(2026, 8, 1), today) == expected


def test_two_missing_months_is_critical():
    assert _state("CPIAUCSL", date(2026, 7, 1), date(2026, 10, 25)) == ("MISSING_PERIODS", "CRITICAL")
    assert _state("M2SL", date(2026, 8, 1), SUN) == ("CURRENT", "FRESH")   # was CRITICAL before


def test_quarterly_gdp():
    assert _state("A191RL1Q225SBEA", date(2026, 4, 1), SUN)[0] == "CURRENT"
    assert _state("A191RL1Q225SBEA", date(2026, 4, 1), date(2026, 11, 3))[0] == "DUE"
    assert _state("A191RL1Q225SBEA", date(2026, 4, 1), date(2026, 11, 20))[0] == "LATE"


def test_daily_series_respect_weekends_and_publication_lag():
    # Sunday: Friday's close publishes Monday, so Thursday's is the latest due.
    assert _state("DGS10", date(2026, 10, 1), SUN)[0] == "CURRENT"
    assert _state("DGS10", date(2026, 10, 2), SUN)[0] == "CURRENT"
    assert _state("DGS10", date(2026, 9, 29), SUN)[0] == "DUE"             # 2 bdays: holiday slack
    assert _state("DGS10", date(2026, 9, 25), SUN) == ("LATE", "STALE")
    assert _state("DGS10", date(2026, 9, 1), SUN) == ("MISSING_PERIODS", "CRITICAL")


def test_weekly_claims():
    last = date(2026, 9, 26)                                                # week ending Saturday
    assert _state("ICSA", last, SUN)[0] == "CURRENT"
    assert _state("ICSA", last, date(2026, 10, 9))[0] == "DUE"
    assert _state("ICSA", last, date(2026, 10, 20))[1] == "CRITICAL"


def test_jobs_report_published_days_after_month_end():
    assert _state("PAYEMS", date(2026, 9, 1), SUN)[0] == "CURRENT"
    assert _state("PAYEMS", date(2026, 8, 1), SUN)[0] == "DUE"              # Sept report due ~Oct 3


def test_unavailable_series_is_unknown_not_fresh():
    r = assess(SPEC["CPIAUCSL"], None, SUN)
    assert r["status"] == "UNKNOWN" and r["state"] == "UNAVAILABLE"


def test_ui_metric_keys_are_covered():
    keys = {s.metric for s in SERIES}
    # Key Metrics cards and StaleBadges reference these.
    assert {"growth", "inflation", "liquidity", "risk", "recession", "hy_spread", "two_ten", "m2",
            "fed_funds"} <= keys
    assert len(keys) == len(SERIES)
