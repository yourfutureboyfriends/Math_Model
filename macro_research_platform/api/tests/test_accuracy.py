"""Accuracy regressions: bill bond-equivalent yields and SEC holding-company reorganizations."""
import math

from api.marketdata.fixed_income import bill_bey
from api.providers import sec_edgar


def test_bill_bey_short_bill_is_simple_interest():
    # 13-week bill at 98.75 for 91 days: (100-P)/P * 365/t
    assert math.isclose(bill_bey(98.75, 91), 1.25 / 98.75 * 365 / 91, rel_tol=1e-12)


def test_bill_bey_long_bill_satisfies_treasury_identity():
    # Over half a year, Treasury's BEY solves P * (1 + (t/365 - 0.5) y) * (1 + y/2) = 100.
    for px, days in ((96.0, 364), (97.5, 280), (95.2, 360)):
        y = bill_bey(px, days)
        assert math.isclose(px * (1 + (days / 365 - 0.5) * y) * (1 + y / 2), 100, rel_tol=1e-10)


def test_bill_bey_continuous_at_half_year():
    # The one-day step across 182 -> 183 days matches the step just after it (no jump).
    across = bill_bey(97.6, 182) - bill_bey(97.6, 183)
    after = bill_bey(97.6, 183) - bill_bey(97.6, 184)
    assert math.isclose(across, after, rel_tol=0.05)


def _facts(name, accns, tag_pts):
    return {"entityName": name, "facts": {"us-gaap": {"Revenues": {"units": {"USD": [
        {"start": s, "end": e, "val": v, "accn": a, "filed": f, "form": "10-Q"} for s, e, v, a, f in tag_pts]}}}}}


def test_new_holding_company_inherits_predecessor_history(monkeypatch):
    new = _facts("NewCo Holdings", None, [("2026-04-01", "2026-06-30", 120, "0000034088-26-000093", "2026-08-03")])
    old = _facts("OldCo", None, [("2025-07-01", "2025-09-30", 100, "0000034088-25-000050", "2025-11-01"),
                                 ("2026-01-01", "2026-03-31", 110, "0000034088-26-000010", "2026-05-01")])
    monkeypatch.setattr(sec_edgar, "_raw_facts", lambda cik: {2115436: new, 34088: old}.get(cik))
    f = sec_edgar.company_facts(2115436)
    assert f["predecessor"]["cik"] == 34088
    vals = sorted(p["val"] for p in f["facts"]["us-gaap"]["Revenues"]["units"]["USD"])
    assert vals == [100, 110, 120]


def test_established_filer_is_not_merged(monkeypatch):
    own = _facts("SelfCo", None, [(f"202{i}-01-01", f"202{i}-03-31", i, f"0000000320-2{i}-00000{i}", f"202{i}-05-01")
                                  for i in range(5)])
    monkeypatch.setattr(sec_edgar, "_raw_facts", lambda cik: own if cik == 320 else None)
    assert "predecessor" not in sec_edgar.company_facts(320)
