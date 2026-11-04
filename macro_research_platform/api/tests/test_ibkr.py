"""IBKR link: ticker mapping, Flex parsing, account pinning, reconciliation and the import guard (no network)."""
import xml.etree.ElementTree as ET

import pytest

FLEX = """<FlexQueryResponse queryName="bifs" type="AF"><FlexStatements count="1">
<FlexStatement accountId="DU1234567" fromDate="20261023" toDate="20261023" whenGenerated="20261026;080000">
<OpenPositions>
 <OpenPosition accountId="DU1234567" symbol="AZN" conid="1" assetCategory="STK" listingExchange="LSE" currency="GBP"
   position="25" markPrice="128.24" costBasisPrice="120.10" positionValue="3206" levelOfDetail="SUMMARY" reportDate="20261023"/>
 <OpenPosition accountId="DU1234567" symbol="BRK B" conid="2" assetCategory="STK" listingExchange="NYSE" currency="USD"
   position="10" markPrice="480" costBasisPrice="450" positionValue="4800" levelOfDetail="SUMMARY"/>
 <OpenPosition accountId="DU1234567" symbol="BRK B" conid="2" assetCategory="STK" listingExchange="NYSE" currency="USD"
   position="10" markPrice="480" levelOfDetail="LOT"/>
</OpenPositions>
<Trades><Trade symbol="AZN" listingExchange="LSE" currency="GBP" buySell="BUY" quantity="25" tradePrice="120.10"
   ibCommission="-3" tradeDate="20261020" tradeID="9"/></Trades>
<CashReport><CashReportCurrency currency="BASE_SUMMARY" endingCash="91234.5" endingSettledCash="91234.5"/></CashReport>
</FlexStatement></FlexStatements></FlexQueryResponse>"""


def test_ticker_mapping():
    from api.brokerage import ibkr
    assert ibkr.to_yahoo("AZN", "LSE", "GBP") == "AZN.L"
    assert ibkr.to_yahoo("BRK B", "NYSE", "USD") == "BRK-B"
    assert ibkr.to_yahoo("SAP", "IBIS", "EUR") == "SAP.DE"
    assert ibkr.to_yahoo("ULVR", None, "GBP") == "ULVR.L"


def test_parse_flex_summary_rows_only():
    from api.brokerage import ibkr
    d = ibkr.parse_flex(ET.fromstring(FLEX))
    assert d["accounts"][0]["account_id"] == "DU1234567"
    assert [(p["symbol"], p["quantity"]) for p in d["positions"]] == [("AZN", 25.0), ("BRK B", 10.0)]   # LOT row skipped
    assert d["trades"][0]["commission"] == -3 and d["cash"][0]["ending_cash"] == 91234.5


def test_account_pin_refuses_other_accounts(monkeypatch):
    from api.brokerage import ibkr
    monkeypatch.setenv("IBKR_BIFS_ACCOUNT_ID", "DU9999999")
    monkeypatch.setattr(ibkr, "gateway_status", lambda f: {"authenticated": False})
    monkeypatch.setattr(ibkr, "flex_statement", lambda f: ET.fromstring(FLEX))
    with pytest.raises(PermissionError):
        ibkr.broker_snapshot("bifs")
    monkeypatch.setenv("IBKR_BIFS_ACCOUNT_ID", "DU1234567")
    assert ibkr.broker_snapshot("bifs")["source"] == "flex"


def test_reconcile_positions():
    from api.brokerage import ibkr
    d = ibkr.parse_flex(ET.fromstring(FLEX))
    r = ibkr.reconcile_positions([{"symbol": "AZN.L", "quantity": 25}, {"symbol": "ULVR.L", "quantity": 5}], d["positions"])
    st = {x["ticker"]: x["status"] for x in r["rows"]}
    assert st == {"AZN.L": "match", "BRK-B": "broker_only", "ULVR.L": "platform_only"} and not r["ok"]


def test_gateway_must_be_local(monkeypatch):
    from api.brokerage import ibkr
    monkeypatch.setenv("IBKR_GATEWAY_URL", "https://example.com:5000")
    assert ibkr.config("bifs")["gateway_local"] is False
    with pytest.raises(RuntimeError):
        ibkr._gw("bifs", "iserver/auth/status")


def test_import_needs_confirm_and_capability(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import api.core.auth as auth
    from api import funds, positions
    from api.brokerage import ibkr
    from api.core import accounts
    path = str(tmp_path / "d.db")
    monkeypatch.setattr(funds, "db_path", lambda fund_id=None: path)
    monkeypatch.setattr(auth, "get_db_path", lambda: path)
    accounts.invalidate_cache(); accounts.migrate()
    for u in ("pm", "analyst"):
        accounts.set_password(u, f"Ibkr-{u}-Pass-2026!x")
    positions._bust()
    monkeypatch.setattr(ibkr, "broker_snapshot", lambda f, s="auto": {**ibkr.parse_flex(ET.fromstring(FLEX)), "source": "flex", "account_id": "DU1234567"})
    from api.marketdata import core
    monkeypatch.setattr(core, "quote", lambda s: {"price": 12824.0} if s == "AZN.L" else {"price": 480.0})
    from api.main import app
    c = {}
    for u in ("pm", "analyst"):
        c[u] = TestClient(app); c[u].headers["Authorization"] = f"Bearer {accounts.issue_token(accounts.get_user(u))}"
    assert c["analyst"].post("/api/v1/broker/ibkr/import", json={"confirm": True}).status_code == 403
    assert c["pm"].post("/api/v1/broker/ibkr/import", json={}).status_code == 400
    r = c["pm"].post("/api/v1/broker/ibkr/import", json={"confirm": True})
    assert r.status_code == 200, r.text
    rows = {p["symbol"]: p for p in r.json()["positions"]}
    assert rows["AZN.L"]["avg_cost"] == pytest.approx(12010.0) and rows["BRK-B"]["avg_cost"] == 450.0   # pounds → pence
    rec = c["pm"].post("/api/v1/broker/ibkr/reconcile").json()
    assert rec["ok"] and rec["matched"] == 2
    accounts.invalidate_cache(); positions._bust()
