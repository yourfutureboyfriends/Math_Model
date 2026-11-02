"""SWAP / CDSX / CDSA / EXTH / TRAN: par rates come only from spot-starting outright trades, index levels use the right
quote convention, single-name trades group by issuer, movers filter by size, and transcript search finds the passage."""
from datetime import date

import pandas as pd
import pytest

from api.marketdata import bbgfree


@pytest.fixture(autouse=True)
def no_cache(monkeypatch):
    monkeypatch.setattr(bbgfree, "_cached", lambda key, ttl, fn: fn())


def _swap(name, rate, eff, exp, exe="2026-10-30T14:00:00Z", pkg="False", notional="100,000,000", leg=1):
    return {"Action type": "NEWT", "Event type": "TRAD", "Execution Timestamp": exe, "Effective Date": eff, "Expiration Date": exp,
            "Fixed rate-Leg 1": str(rate) if leg == 1 else None, "Fixed rate-Leg 2": str(rate) if leg == 2 else None,
            "Notional amount-Leg 1": notional, "Package indicator": pkg, "UPI Underlier Name": name}


def test_swap_curve_uses_spot_outright_trades_and_drops_off_market_prints():
    rows = [_swap("USD-SOFR-OIS Compound", 0.0450, "2026-11-03", "2036-11-03"),
            _swap("USD-SOFR-OIS Compound", 0.0452, "2026-11-03", "2036-11-03", notional="250,000,000+", leg=2),
            _swap("USD-SOFR-OIS Compound", 0.0300, "2026-11-03", "2036-11-03", notional="1,000,000"),       # off-market
            _swap("USD-SOFR-OIS Compound", 0.0480, "2031-11-03", "2041-11-03"),                              # forward start
            _swap("USD-SOFR-OIS Compound", 0.0470, "2026-11-03", "2036-11-03", pkg="True"),                  # package leg
            _swap("USD-SOFR-OIS Compound", 0.0440, "2026-11-03", "2028-11-03"),
            _swap("USD-SOFR-OIS Compound", 0.0442, "2026-11-03", "2028-11-03")]
    c = bbgfree.swap_curve_from_tape(pd.DataFrame(rows))["USD"]
    assert set(c) == {2, 10}
    assert c[10]["trades"] == 2 and c[10]["rate"] == pytest.approx(4.52)   # the 250M print dominates the weighted median
    assert c[2]["rate"] in (pytest.approx(4.40), pytest.approx(4.42))


def test_notional_parses_capped_blocks_and_rejects_placeholders():
    assert bbgfree._notional("250,000,000+") == 250e6
    assert bbgfree._notional("99,999,999,999,999,999,999.99999") is None
    assert bbgfree._notional(None) is None


def test_cds_levels_take_spreads_for_ig_and_prices_for_hy():
    def t(name, sp, nota, exp="2031-12-20", coupon="0.01"):
        return {"Action type": "NEWT", "UPI Underlier Name": name, "Expiration Date": exp, "Spread-Leg 1": str(sp),
                "Spread notation-Leg 1": str(nota), "Fixed rate-Leg 1": coupon, "Notional amount-Leg 1": "10,000,000"}
    df = pd.DataFrame([t("CDX.NA.IG", 0.0062, 3), t("CDX.NA.IG", 0.0064, 3), t("CDX.NA.IG", 0.0070, 3, exp="2031-06-20"),
                       t("CDX.NA.HY", 105.8, 1, coupon="0.05"), t("CDX.NA.HY", 105.9, 1, coupon="0.05"), t("CDX.NA.HY", 0.0106, 3, coupon="0.05")])
    lv = bbgfree.cds_levels_from_tape(df)
    assert lv["CDX.NA.IG"]["level"] == pytest.approx(63) and lv["CDX.NA.IG"]["maturity"] == "2031-12-20"
    hy = lv["CDX.NA.HY"]
    assert hy["quote"] == "price" and hy["level"] == pytest.approx(105.85)
    assert hy["spread_equiv_bp"] == pytest.approx(500 - 5.85 / 4.3 * 100)


def test_single_name_cds_groups_bonds_by_issuer(monkeypatch):
    def t(isin, fisn="NA/CDS Corp SN Sr"):
        return {"Action type": "NEWT", "UPI FISN": fisn, "Underlier ID-Leg 1": isin, "Notional amount-Leg 1": "5,000,000", "UPI Underlier Name": "SR NT"}
    df = pd.DataFrame([t("US67066GAN43"), t("US67066GAM69"), t("US105756CE88", "NA/CDS Sov SN Sr"), t("XX")])
    monkeypatch.setattr(bbgfree, "_latest_tapes", lambda kind, n, regime="cftc": [(date(2026, 10, 30), df)])
    monkeypatch.setattr(bbgfree, "_figi_names", lambda isins: {"US67066GAN43": {"name": "NVIDIA CORP", "ticker": "NVDA 2 06/15/31"}})
    r = bbgfree.single_name_cds(1)
    assert r["rows"][0]["name"] == "NVIDIA CORP" and r["rows"][0]["trades"] == 2          # two NVIDIA bonds, one entity
    assert r["rows"][1]["sovereign"] is True and r["total_trades"] == 3


def test_extended_hours_filters_small_and_penny_stocks(monkeypatch):
    from api.providers import benzinga
    monkeypatch.setattr(benzinga, "available", lambda: True)
    movers = {"result": {"fromDate": "a", "toDate": "b", "gainers": [
        {"symbol": "BIG", "price": 50, "changePercent": 12.5, "marketCap": "2000000000"},
        {"symbol": "TINY", "price": 4, "changePercent": 400, "marketCap": "10000000"},
        {"symbol": "PENNY", "price": 0.5, "changePercent": 80, "marketCap": "900000000"}], "losers": []}}
    monkeypatch.setattr(benzinga, "_get", lambda path, params, ttl: movers)
    r = bbgfree.extended_hours("pre_market")
    assert [g["symbol"] for g in r["gainers"]] == ["BIG"] and r["gainers"][0]["change_pct"] == pytest.approx(0.125)
    with pytest.raises(bbgfree.NotFound):
        bbgfree.extended_hours("lunch")


def test_transcript_search_finds_the_answer_inside_long_prepared_remarks(monkeypatch):
    remarks = " ".join(["Revenue grew and margins expanded across every segment this quarter."] * 30
                       + ["Net interest income should be about ninety billion dollars next year, our outlook for NII is unchanged."]
                       + ["Expenses were in line."] * 20)
    calls = [{"id": 2, "date": "2026-10-13", "fiscal_year": 2026, "fiscal_quarter": 3,
              "paragraphs": [{"speaker": "CFO", "text": remarks}, {"speaker": "Analyst", "text": "Thanks."}]},
             {"id": 1, "date": "2026-07-14", "fiscal_year": 2026, "fiscal_quarter": 2,
              "paragraphs": [{"speaker": "CFO", "text": "Our net interest income outlook rises."}]}]
    monkeypatch.setattr(bbgfree, "_calls", lambda symbol: calls)
    r = bbgfree.transcript_search("TST", "net interest income outlook")
    long_hit = next(h for h in r["hits"] if h["call_id"] == 2)
    assert "ninety billion" in long_hit["text"] and len(long_hit["text"]) < 1000      # the passage, not the whole speech
    assert {h["call_id"] for h in r["hits"]} == {1, 2}
    with pytest.raises(bbgfree.NotFound):
        bbgfree.transcript_search("TST", "the and of")
