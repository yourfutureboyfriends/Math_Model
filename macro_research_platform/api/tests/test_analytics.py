"""Analytics functions: FX forwards (covered interest parity) and correlation ordering."""
import pandas as pd
import pytest


def test_fx_forward_is_covered_interest_parity(monkeypatch):
    from api.marketdata import analytics, core
    monkeypatch.setattr(analytics, "_short_rate", lambda c: {"rate": {"EUR": 0.02, "USD": 0.05}[c], "date": "2099-01-01", "series": c})
    monkeypatch.setattr(core, "quote", lambda s: {"price": 1.10})
    monkeypatch.setattr(analytics, "_cached", lambda k, ttl, fn: fn())
    f = analytics.fx_forwards("EUR", "USD")
    one_year = next(t for t in f["tenors"] if t["tenor"] == "1Y")
    assert one_year["forward"] == pytest.approx(1.10 * (1 + 0.05 * 365 / 360) / (1 + 0.02 * 365 / 360))
    assert one_year["points"] > 0                       # higher USD rates → EUR trades at a forward premium
    assert f["stale_rates"] == []


def test_correlation_cluster_order_keeps_related_together():
    from api.marketdata.analytics import _cluster_order
    c = pd.DataFrame([[1, .9, .1, .1], [.9, 1, .1, .1], [.1, .1, 1, .8], [.1, .1, .8, 1]],
                     index=list("ABCD"), columns=list("ABCD"))
    order = _cluster_order(c)
    pos = {s: i for i, s in enumerate(order)}
    assert abs(pos["A"] - pos["B"]) == 1 and abs(pos["C"] - pos["D"]) == 1


def test_finra_line_parsing_and_share_classes():
    from api.marketdata.shorts import _parse
    text = "Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market\n20261009|A|100|0|400|B,Q\n20261009|AA|50|0|100|N\n20261009|BRK/B|30|0|90|N\n"
    assert _parse(text, "A") == {"short": 100.0, "exempt": 0.0, "total": 400.0}
    assert _parse(text, "AA")["total"] == 100.0
    assert _parse(text, "BRK/B")["short"] == 30.0
    assert _parse(text, "ZZZ") is None


def test_calendar_number_parsing():
    from api.marketdata.econ import _num
    assert _num("0.3%") == 0.3 and _num("150K") == 150 and _num("-1.2B") == -1.2 and _num("<0.1%") == 0.1 and _num("") is None


def test_tracking_helpers():
    from api.marketdata.tracking import CHOKEPOINTS, _km, _ship_type
    assert abs(_km(51.47, -0.454, 40.641, -73.778) - 5540) < 30          # Heathrow → JFK ≈ 5,540 km
    assert _ship_type(84) == "Tanker" and _ship_type(71) == "Cargo" and _ship_type(None) == "Unknown"
    assert all(-90 <= c["lat"] <= 90 and -180 <= c["lon"] <= 180 for c in CHOKEPOINTS.values())


def test_regions_and_country_tagging():
    from api.marketdata.countries import countries_in, country_of_symbol, region_of
    assert region_of("JP") == "apac" and region_of("DE") == "europe" and region_of("ZA") == "mea" and region_of("BR") == "americas"
    assert country_of_symbol("7203.T") == "JP" and country_of_symbol("VOD.L") == "GB" and country_of_symbol("AAPL") == "US"
    assert country_of_symbol("^N225") == "" and country_of_symbol("EURUSD=X") == ""
    tags = countries_in("Bank of Japan holds rates as yen slides; Germany's DAX rallies")
    assert "JP" in tags and "DE" in tags and "US" not in tags
    assert "US" not in countries_in("Business is a focus")          # 'us' as a word is not the US


def test_ais_not_available_codes_are_dropped():
    from api.marketdata.tracking import _ais_clean
    assert _ais_clean(102.3, 360.0, 511) == (None, None, None)
    assert _ais_clean(12.4, 87.5, 90) == (12.4, 87.5, 90)
