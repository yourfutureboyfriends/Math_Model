"""BORROW / DARK / PROB / CRPR / LEAG / SPF: the stock-loan file parses, off-exchange shares add up, the option-implied
density integrates to one and recovers a lognormal, coverage maps to the right rating, deals are counted once per company,
and survey quarters line up with the previous survey."""
import io
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from api.marketdata import bbgextra


@pytest.fixture(autouse=True)
def no_cache(monkeypatch):
    monkeypatch.setattr(bbgextra, "_cached", lambda key, ttl, fn: fn())


FILE = """#BOF|2026.11.01|19:05:05
#SYM|CUR|NAME|CON|ISIN|REBATERATE|FEERATE|AVAILABLE|FIGI|
AAPL|USD|APPLE INC|265598|US0378331005|3.6300|0.2500|>10000000|BBG000B9XRY4|
BRK B|USD|BERKSHIRE HATHAWAY INC-CL B|72063691|X|3.6000|0.2800|5000000|X|
SQZ|USD|SQUEEZE CO|1|X|-40.1000|43.8800|1500|X|
#EOF|3
"""


def test_borrow_parses_ibkrs_file_and_maps_symbols(monkeypatch):
    monkeypatch.setattr(bbgextra, "_ftp_text", lambda name: FILE)
    r = bbgextra.borrow("AAPL")
    assert (r["fee"], r["rebate"], r["available"], r["tier"]) == (0.25, 3.63, 10_000_000, "general collateral")
    assert r["as_of"] == "2026-11-01 19:05:05"
    assert bbgextra.borrow("BRK-B")["available"] == 5_000_000                 # Yahoo's BRK-B is IBKR's "BRK B"
    assert bbgextra.borrow("SQZ")["tier"] == "hard to borrow"
    assert bbgextra._borrow_key("0700.HK") == ("hongkong.txt", "700")
    with pytest.raises(bbgextra.NotFound):
        bbgextra.borrow("NOPE")


def test_dark_pool_shares_use_consolidated_weekly_volume(monkeypatch):
    from api.marketdata import core
    monday = date.today() - timedelta(days=date.today().weekday())
    w = str(monday - timedelta(weeks=3))
    rows = [{"summaryTypeCode": "ATS_W_SMBL", "totalWeeklyShareQuantity": 100.0, "totalWeeklyTradeCount": 10},
            {"summaryTypeCode": "OTC_W_SMBL", "totalWeeklyShareQuantity": 300.0, "totalWeeklyTradeCount": 30},
            {"summaryTypeCode": "ATS_W_SMBL_FIRM", "marketParticipantName": "DARK ONE", "totalWeeklyShareQuantity": 100.0, "totalWeeklyTradeCount": 10},
            {"summaryTypeCode": "OTC_W_SMBL_FIRM", "marketParticipantName": "WHOLESALER", "totalWeeklyShareQuantity": 300.0, "totalWeeklyTradeCount": 3}]
    monkeypatch.setattr(bbgextra, "_finra_week", lambda sym, week, tier: rows if week == w and tier == "T1" else [])
    idx = pd.bdate_range(w, periods=5)
    monkeypatch.setattr(core, "yahoo_download", lambda syms, **k: pd.DataFrame({"Volume": [200.0] * 5}, index=idx))
    r = bbgextra.dark_pool("TST", weeks=4)
    assert r["latest_week"] == w and r["off_exchange_share"] == pytest.approx(0.4) and r["ats_share"] == pytest.approx(0.1)
    assert r["venues"][0]["venue"] == "WHOLESALER" and r["venues"][0]["avg_trade"] == pytest.approx(100)


def test_probability_density_integrates_to_one_and_matches_a_flat_smile(monkeypatch):
    from api.marketdata import security
    S, iv = 100.0, 0.30
    strikes = np.arange(60, 145, 5.0)
    chain = {"expiry": "2027-01-15", "expirations": ["2027-01-15"], "underlying": S, "days": 73, "rate": 0.0, "dividend_yield": 0.0,
             "calls": [{"strike": k, "iv": iv} for k in strikes], "puts": [{"strike": k, "iv": iv} for k in strikes], "source": "test"}
    monkeypatch.setattr(security, "options", lambda sym, exp=None: chain)
    r = bbgextra.probability("TST", "2027-01-15")
    T = 73 / 365
    assert r["atm_iv"] == pytest.approx(iv, abs=1e-6)
    assert r["percentiles"][50] == pytest.approx(S * np.exp(-0.5 * iv * iv * T), rel=0.01)     # lognormal median
    for lv in r["levels"]:                                                                       # flat smile → lognormal
        assert lv["p_above"] == pytest.approx(lv["p_above_lognormal"], abs=0.01)
        assert lv["p_above"] + lv["p_below"] == pytest.approx(1, abs=1e-6)
    assert r["left_tail_vs_lognormal"] == pytest.approx(1, abs=0.05)


@pytest.mark.parametrize("cov,rating", [(None, "AAA"), (40, "AAA"), (7, "AA"), (3.5, "A-"), (2.6, "BBB"), (1.6, "B"), (0.5, "C"), (-1, "D")])
def test_synthetic_rating_follows_the_coverage_table(cov, rating):
    assert bbgextra.synthetic_rating(cov)[0] == rating


def test_league_table_counts_each_company_once(monkeypatch):
    import requests

    class R:
        def __init__(self, hits):
            self._h = hits

        def raise_for_status(self):
            pass

        def json(self):
            return {"hits": {"hits": self._h}}
    hit = lambda cik, name, form, d: {"_source": {"ciks": [cik], "display_names": [f"{name}  (CIK {cik})"], "form": form, "file_date": d}}
    data = {"Goldman Sachs": [hit("1", "Alpha Inc (ALP)", "PREM14A", "2026-05-01"), hit("1", "Alpha Inc (ALP)", "DEFM14A", "2026-06-01"),
                              hit("2", "Beta Corp (BET)", "S-4", "2026-07-01")],
            "Lazard": [hit("3", "Gamma (GAM)", "DEFM14A", "2026-08-01")]}
    monkeypatch.setattr(bbgextra, "ADVISERS", list(data))
    monkeypatch.setattr(requests, "get", lambda url, params, headers, timeout: R(data[params["q"].split("Opinion of ")[1].strip('"')]))
    r = bbgextra.league_table(365)
    assert [(x["bank"], x["deals"]) for x in r["rows"]] == [("Goldman Sachs", 2), ("Lazard", 1)]
    alpha = next(c for c in r["rows"][0]["companies"] if c["company"].startswith("Alpha"))
    assert alpha["filed"] == "2026-05-01" and alpha["forms"] == ["DEFM14A", "PREM14A"]


def test_spf_lines_up_quarters_with_the_previous_survey(monkeypatch):
    import requests
    df = pd.DataFrame({"YEAR": [2026, 2026], "QUARTER": [2, 3], "CPI1": [3.0, 3.1], "CPI2": [2.9, 2.2], "CPI3": [2.5, 2.4],
                       "CPI4": [2.4, 2.3], "CPI5": [2.3, 2.3], "CPI6": [2.2, 2.2], "CPIA": [3.5, 3.6], "CPIB": [2.5, 2.3], "CPIC": [2.4, 2.3]})
    buf = io.BytesIO()
    df.to_excel(buf, index=False)

    class R:
        content = buf.getvalue()

        def raise_for_status(self):
            pass
    monkeypatch.setattr(bbgextra, "SPF_VARS", {"cpi": ("x.xlsx", "CPI", "CPI")})
    monkeypatch.setattr(requests, "get", lambda url, headers, timeout: R())
    r = bbgextra.spf_consensus()
    q = r["series"]["cpi"]["quarters"]
    assert r["survey"] == "2026 Q3" and q[0] == {"period": "2026 Q3", "median": 2.2, "previous_survey": 2.5}
    assert q[1]["period"] == "2026 Q4"
    a = {x["year"]: x for x in r["series"]["cpi"]["annual"]}
    assert a[2026]["previous_survey"] == 3.5 and a[2027]["median"] == 2.3 and a[2027]["previous_survey"] == 2.5
