"""DDM, price outlook, peer multiples and prediction-market normalisation (offline: data stubbed)."""
import math

import pytest

from api.marketdata import dcf, predmarkets as pm, security


def _inp(**kw):
    base = {"symbol": "TEST", "price": 50.0, "currency": "USD", "price_currency": "USD", "risk_free": 0.04, "beta": 0.8,
            "erp": 0.05, "industry": "Beverages", "payout_ratio": 0.6, "net_income": 1e9, "equity_book": 6e9, "risk_free_matched": True}
    base.update(kw)
    return base


@pytest.fixture
def stub_div(monkeypatch):
    monkeypatch.setattr(dcf, "_info", lambda s: {"dividendYield": 3.0, "dividendRate": 1.5, "regularMarketPrice": 50.0})
    monkeypatch.setattr(dcf, "_dividend_history", lambda s: [{"year": 2019 + k, "dps": 1.2 * 1.04 ** k} for k in range(7)])
    import api.marketdata.core as core
    monkeypatch.setattr(core, "div_yield", lambda i: 0.03)


def test_ddm_values_dividends_and_respects_constraints(stub_div):
    v = dcf.value_ddm(_inp())
    a = v["assumptions"]
    assert v["model"] == "ddm" and v["per_share"] > 0
    assert a["terminal_growth"] <= a["risk_free"] + 1e-12
    assert a["cost_of_equity_terminal"] - a["terminal_growth"] >= 0.03 - 1e-9
    assert a["growth"] <= 0.10
    # value = PV of dividends + PV of terminal value
    assert v["per_share"] == pytest.approx(v["pv_dividends"] + v["pv_terminal"])
    # a higher cost of equity lowers the value
    assert dcf.value_ddm(_inp(), discount=0.12)["per_share"] < dcf.value_ddm(_inp(), discount=0.08)["per_share"]


def test_ddm_reit_grows_dividend_directly(stub_div):
    v = dcf.value_ddm(_inp(industry="REIT—Retail", payout_ratio=2.5))
    assert v["variant"] == "dividend_growth"
    assert all(r["payout"] is None for r in v["projection"])


def test_ddm_needs_a_dividend(monkeypatch):
    monkeypatch.setattr(dcf, "_info", lambda s: {})
    monkeypatch.setattr(dcf, "_dividend_history", lambda s: [])
    import api.marketdata.core as core
    monkeypatch.setattr(core, "div_yield", lambda i: None)
    with pytest.raises(dcf.NotFound):
        dcf.value_ddm(_inp())


def test_outlook_converges_toward_value(monkeypatch):
    monkeypatch.setattr(dcf, "_realized_vol", lambda s: 0.25)
    monkeypatch.setattr(dcf, "_info", lambda s: {"targetMeanPrice": 60.0, "numberOfAnalystOpinions": 10})
    o = dcf.outlook("TEST", 50.0, 80.0, 0.08, 0.02, half_life_years=3)
    h = {r["months"]: r for r in o["horizons"]}
    assert h[1]["median"] < h[12]["median"] < h[24]["median"]
    assert h[12]["p10"] < h[12]["median"] < h[12]["p90"]
    # with no gap the median just earns the cost of equity less the yield
    o2 = dcf.outlook("TEST", 50.0, 50.0, 0.08, 0.02)
    assert {r["months"]: r for r in o2["horizons"]}[12]["median"] == pytest.approx(50 * math.exp(0.06), rel=1e-6)
    assert len(o["path"]) == 25 and o["analyst_target"] == 60.0


def test_inflation_differential_risk_free(monkeypatch):
    real = dcf.risk_free
    monkeypatch.setattr(dcf, "risk_free", lambda c: {"rate": 0.045, "source": "us", "currency_matched": True} if (c or "USD") == "USD" else real(c))
    r = real("CNY")
    assert r["currency_matched"] and r["rate"] < 0.045       # lower expected inflation than the US → lower rate


def test_peer_multiples_rebuilt_in_one_currency(monkeypatch):
    monkeypatch.setattr(security, "to_usd", lambda amt, ccy: None if amt is None else amt * {"USD": 1.0, "TWD": 1 / 32, "GBP": 1.25}[ccy])
    # an ADR trading in USD that reports in TWD: Yahoo's P/B of 93 is a unit error
    m = security.peer_multiples({"currency": "USD", "financialCurrency": "TWD", "marketCap": 1e12, "netIncomeToCommon": 1.6e12,
                                 "totalRevenue": 3.2e12, "ebitda": 2e12, "totalDebt": 0, "totalCash": 0, "priceToBook": 93.0,
                                 "bookValue": 4.86, "sharesOutstanding": 5e9, "trailingEps": 10, "forwardEps": 12})
    assert m["pe"] == pytest.approx(32e12 / 1.6e12)
    assert m["price_to_book"] is None                         # inconsistent per-share book → not meaningful
    assert m["forward_pe"] == pytest.approx(m["pe"] * 10 / 12)
    # losses → n/m rather than a negative multiple
    assert security.peer_multiples({"currency": "USD", "financialCurrency": "USD", "marketCap": 1e9, "netIncomeToCommon": -1e8})["pe"] is None


def test_area_of_country():
    assert security.area_of_country("Japan") == "Asia-Pacific"
    assert security.area_of_country("Germany") == "Europe"
    assert security.area_of_country("United States") == "Americas"
    assert security.area_of_symbol("SAP.DE") == "Europe"


def test_kalshi_market_uses_tight_midpoint():
    m = pm._kalshi_market({"ticker": "X-1", "status": "active", "yes_sub_title": "Hold", "last_price_dollars": "0.70",
                           "previous_price_dollars": "0.60", "yes_bid_dollars": "0.80", "yes_ask_dollars": "0.82", "volume_24h_fp": "5000"}, "X")
    assert m["yes"] == pytest.approx(0.81) and not m["thin"]
    wide = pm._kalshi_market({"ticker": "X-2", "status": "active", "last_price_dollars": "0.30", "yes_bid_dollars": "0.10",
                              "yes_ask_dollars": "0.50", "volume_24h_fp": "10"}, "X")
    assert wide["yes"] == pytest.approx(0.30) and wide["thin"]


def test_poly_market_parses_json_fields():
    m = pm._poly_market({"question": "Will X?", "outcomes": '["Yes","No"]', "outcomePrices": '["0.25","0.75"]', "clobTokenIds": '["t1","t2"]',
                         "bestBid": 0.24, "bestAsk": 0.26, "volume24hr": 10000, "groupItemTitle": "X", "active": True})
    assert m["binary"] and m["yes"] == 0.25 and m["id"] == "t1" and m["spread"] == pytest.approx(0.02)


def test_categories():
    assert pm._category("Fed decision in October?", []) == "Fed & rates"
    assert pm._category("Counter-Strike: Vitality vs MOUZ (BO3)", ["Esports"]) == "Sports"
    assert pm._category("Will Israel strike Iran?", []) == "Geopolitics"


def test_related_matches_whole_words(monkeypatch):
    ev = lambda t, cat="Economy", v=5000: {"venue": "Polymarket", "id": t, "title": t, "category": cat, "tags": [], "volume_24h": v, "volume": v,
                                          "liquidity": 0, "end": None, "markets": [{"id": t, "label": "Yes", "yes": 0.5, "binary": True, "thin": False,
                                                                                     "outcomes": [], "volume_24h": v}]}
    monkeypatch.setattr(pm, "catalog", lambda: {"events": [ev("Fed decision in December?"), ev("Federer wins?", "Sports"), ev("Fedex earnings beat?"),
                                                           ev("Elon Musk # tweets this week?")]})
    titles = [e["title"] for e in pm.related(["fed"])["events"]]
    assert titles == ["Fed decision in December?"]
