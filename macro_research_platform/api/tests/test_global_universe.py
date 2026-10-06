"""Global universe clean-up: company keys, receipts, minor-unit currencies, home listings."""
from api import global_universe as gu
from api import markets as mk


def test_name_key_strips_corporate_forms():
    assert gu.name_key("NVIDIA Corporation") == gu.name_key("NVIDIA Corp.")
    assert gu.name_key("Samsung Electronics Co., Ltd.") == gu.name_key("Samsung Electronics Co Ltd")
    assert gu.name_key("BHP Group Limited") == gu.name_key("BHP Group Ltd")


def test_depositary_receipts_detected():
    assert gu.is_depositary({"symbol": "NVDC34.SA", "quoteType": "EQUITY", "shortName": "NVIDIA CORP DRN"})
    assert gu.is_depositary({"symbol": "NVDA80.BK", "quoteType": "EQUITY"})
    assert gu.is_depositary({"symbol": "SPY", "quoteType": "ETF"})
    assert not gu.is_depositary({"symbol": "PETR4.SA", "quoteType": "EQUITY", "shortName": "PETROBRAS PN"})


def test_usd_conversion_handles_minor_units():
    fx = {"GBP": 0.75, "ZAR": 18.0}
    assert gu.usd(1500.0, "GBp", fx) == 1500 / 100 / 0.75          # pence price
    assert gu.usd(3.0e11, "GBp", fx, already_major=True) == 3.0e11 / 0.75   # market cap in GBP
    assert gu.usd(100.0, "USD", fx) == 100.0


def test_home_listing_beats_adr_and_cross_listing():
    fx = {"TWD": 32.0, "EUR": 0.9, "GBP": 0.75}
    q = [
        {"symbol": "TSM", "_country": "US", "currency": "USD", "financialCurrency": "TWD", "marketCap": 1e12,
         "regularMarketPrice": 200, "averageDailyVolume3Month": 1e7, "longName": "Taiwan Semiconductor Manufacturing Company Limited"},
        {"symbol": "2330.TW", "_country": "TW", "currency": "TWD", "financialCurrency": "TWD", "marketCap": 3.2e13,
         "regularMarketPrice": 1000, "averageDailyVolume3Month": 2e7, "longName": "Taiwan Semiconductor Manufacturing Company Limited"},
        {"symbol": "NVDA", "_country": "US", "currency": "USD", "financialCurrency": "USD", "marketCap": 5e12,
         "regularMarketPrice": 200, "averageDailyVolume3Month": 2e8, "longName": "NVIDIA Corporation"},
        {"symbol": "NVD.DE", "_country": "DE", "currency": "EUR", "financialCurrency": "USD", "marketCap": 4.5e12,
         "regularMarketPrice": 180, "averageDailyVolume3Month": 1e5, "longName": "NVIDIA Corporation"},
    ]
    out = {r["symbol"]: r for r in gu.dedupe_and_rank(q, fx)}
    assert "2330.TW" in out and "TSM" not in out
    assert "NVDA" in out and "NVD.DE" not in out
    assert out["2330.TW"]["market_class"] == "Emerging" and out["NVDA"]["market_class"] == "Developed"


def test_classification_by_suffix():
    assert mk.classify("7203.T")["market_class"] == "Developed"
    assert mk.classify("RELIANCE.NS")["country"] == "IN"
    assert mk.classify("BRD.RO")["market_class"] == "Frontier"
    assert mk.classify("AAPL")["country"] == "US"
    assert mk.minor_unit_factor("ZAc") == ("ZAR", 100.0)


def test_accents_folded():
    assert gu.name_key("Nestlé S.A.") == gu.name_key("Nestle SA")


def test_non_equity_instruments_have_no_market_class():
    assert mk.classify("EURUSD=X")["asset_type"] == "Currency" and mk.classify("EURUSD=X")["market_class"] == "n/a"
    assert mk.classify("BTC-USD")["asset_type"] == "Crypto"
    assert mk.classify("GC=F")["asset_type"] == "Future"
    idx = mk.classify("^N225")
    assert idx["asset_type"] == "Index" and idx["country"] == "JP"
    assert mk.classify("BRK-B")["asset_type"] == "Equity" and mk.classify("BRK-B")["country"] == "US"


def test_similar_names_are_not_merged():
    fx = {"CAD": 1.4}
    q = [{"symbol": "BMO.TO", "_country": "CA", "currency": "CAD", "marketCap": 1.40e11, "regularMarketPrice": 190,
          "averageDailyVolume3Month": 2e6, "longName": "Bank of Montreal"},
         {"symbol": "BNS.TO", "_country": "CA", "currency": "CAD", "marketCap": 1.45e11, "regularMarketPrice": 100,
          "averageDailyVolume3Month": 5e6, "longName": "The Bank of Nova Scotia"}]
    assert {r["symbol"] for r in gu.dedupe_and_rank(q, fx)} == {"BMO.TO", "BNS.TO"}


def test_home_market_follows_reporting_currency():
    assert mk.home_country("HK", "CNY") == "CN"        # H-share / Tencent → MSCI China
    assert mk.home_country("HK", "USD") == "HK"        # AIA reports USD → Hong Kong
    assert mk.home_country("HK", "TWD") == "HK"        # only CNY reassigns HK listings
    assert mk.home_country("US", "CNY") == "CN"        # PDD
    assert mk.home_country("US", "EUR") == "US"        # EUR is multi-country: no guess
    assert mk.home_country("US", "USD") == "US"
