"""
Interactive Brokers link — READ-ONLY, per fund (e.g. BIFS's IBKR education account).

Two official routes, configured in .env by the fund (never entered through the app):

  Flex Web Service (statements, T+1)   IBKR_<FUND>_FLEX_TOKEN, IBKR_<FUND>_FLEX_QUERY_ID
      A Flex Query (Account Management → Reports → Flex Queries) with Open Positions, Trades and Cash Report
      sections, XML format; a Flex Web Service token (Reports → Settings → Flex Web Service). Daily statements —
      the broker-side record for reconciliation.
  Client Portal Gateway (live)          IBKR_GATEWAY_URL (default https://localhost:5000), IBKR_<FUND>_ACCOUNT_ID
      IBKR's gateway, run on this machine; the account holder signs in to it in their own browser. Positions and
      balances live while the session lasts.

The account is pinned per fund (IBKR_<FUND>_ACCOUNT_ID): data from any other account is refused, so two funds can
never mix. Nothing here places, modifies or cancels orders — routing would need separate, explicit authorisation.
<FUND> is the fund id in upper case (BIFS, MAIN).
"""
from __future__ import annotations

import logging
import os
import time
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)
FLEX_BASE = os.getenv("IBKR_FLEX_BASE", "https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService")

# IBKR listing exchange → Yahoo suffix (the platform's ticker convention)
EXCHANGE_SUFFIX = {"LSE": ".L", "LSEETF": ".L", "LSEIOB1": ".L", "IBIS": ".DE", "XETRA": ".DE", "FWB": ".F", "AEB": ".AS",
                   "SBF": ".PA", "BVME": ".MI", "BM": ".MC", "EBS": ".SW", "TSE": ".T", "SEHK": ".HK", "ASX": ".AX",
                   "TSEJ": ".T", "SGX": ".SI", "TSX": ".TO", "VENTURE": ".V", "OSE": ".OL", "SFB": ".ST", "KFB": ".CO",
                   "VSE": ".VI", "ENEXT.BE": ".BR", "IBIS2": ".DE"}
US_EXCHANGES = {"NYSE", "NASDAQ", "ARCA", "AMEX", "BATS", "ISLAND", "NYSEARCA", "PINK", "IEX", "SMART"}


def _env(fund: str, key: str) -> Optional[str]:
    v = os.getenv(f"IBKR_{fund.upper()}_{key}")
    return v.strip() if v else None


def config(fund: str) -> Dict[str, Any]:
    """What is configured for the fund (never the secrets themselves)."""
    gw = os.getenv("IBKR_GATEWAY_URL", "https://localhost:5000").rstrip("/")
    return {"fund": fund, "account_id": _env(fund, "ACCOUNT_ID"), "flex_configured": bool(_env(fund, "FLEX_TOKEN") and _env(fund, "FLEX_QUERY_ID")),
            "gateway_url": gw, "gateway_local": urlparse(gw).hostname in ("localhost", "127.0.0.1"),
            "env_keys": [f"IBKR_{fund.upper()}_ACCOUNT_ID", f"IBKR_{fund.upper()}_FLEX_TOKEN", f"IBKR_{fund.upper()}_FLEX_QUERY_ID",
                         "IBKR_GATEWAY_URL"], "order_routing": False}


def to_yahoo(symbol: str, exchange: Optional[str], currency: Optional[str] = None) -> str:
    """IBKR symbol + listing exchange → the platform's ticker (BRK B → BRK-B; VOD on LSE → VOD.L)."""
    s = (symbol or "").strip().upper().replace(" ", "-")
    ex = (exchange or "").upper()
    if ex in EXCHANGE_SUFFIX:
        s = s.rstrip(".") + EXCHANGE_SUFFIX[ex]
    elif ex not in US_EXCHANGES and currency and currency.upper() in ("GBP", "GBX"):
        s = s + ".L"
    return s


# ── Flex Web Service ─────────────────────────────────────────────────────────
def _flex_get(path: str, params: Dict[str, str]) -> ET.Element:
    r = requests.get(f"{FLEX_BASE}/{path}", params=params, timeout=40, headers={"User-Agent": "MacroTerminal/8 (python-requests)"})
    r.raise_for_status()
    return ET.fromstring(r.content)


def flex_statement(fund: str, max_wait_s: int = 60) -> ET.Element:
    """Request the fund's Flex statement and wait for it (IBKR generates it asynchronously)."""
    tok, q = _env(fund, "FLEX_TOKEN"), _env(fund, "FLEX_QUERY_ID")
    if not (tok and q):
        raise RuntimeError(f"Flex is not configured: set IBKR_{fund.upper()}_FLEX_TOKEN and IBKR_{fund.upper()}_FLEX_QUERY_ID in .env")
    root = _flex_get("SendRequest", {"t": tok, "q": q, "v": "3"})
    if (root.findtext("Status") or "").lower() != "success":
        raise RuntimeError(f"IBKR Flex refused the request: {root.findtext('ErrorMessage') or root.findtext('ErrorCode') or 'unknown error'}")
    ref = root.findtext("ReferenceCode")
    deadline = time.time() + max_wait_s
    while True:
        st = _flex_get("GetStatement", {"t": tok, "q": ref, "v": "3"})
        if st.tag != "FlexStatementResponse":
            return st                                  # the statement itself
        code = st.findtext("ErrorCode")
        if code not in ("1019", "1018") or time.time() > deadline:   # 1019: generation in progress; 1018: rate limit
            raise RuntimeError(f"IBKR Flex statement not available: {st.findtext('ErrorMessage') or code}")
        time.sleep(3)


def _f(x: Optional[str]) -> Optional[float]:
    try:
        return float(x) if x not in (None, "") else None
    except ValueError:
        return None


def parse_flex(root: ET.Element) -> Dict[str, Any]:
    """Positions, trades and cash from a Flex XML statement (any field set; missing fields stay None)."""
    stmts = root.findall(".//FlexStatement")
    if not stmts:
        raise ValueError("no FlexStatement in the response")
    out: Dict[str, Any] = {"accounts": [], "positions": [], "trades": [], "cash": []}
    for s in stmts:
        acct = s.get("accountId")
        out["accounts"].append({"account_id": acct, "from": s.get("fromDate"), "to": s.get("toDate"), "generated": s.get("whenGenerated")})
        for p in s.findall(".//OpenPositions/OpenPosition"):
            if (p.get("levelOfDetail") or "SUMMARY").upper() not in ("SUMMARY", ""):
                continue
            out["positions"].append({"account_id": acct, "symbol": p.get("symbol"), "conid": p.get("conid"),
                                     "asset_class": p.get("assetCategory"), "exchange": p.get("listingExchange"),
                                     "currency": p.get("currency"), "quantity": _f(p.get("position")),
                                     "mark_price": _f(p.get("markPrice")), "cost_price": _f(p.get("costBasisPrice")),
                                     "market_value": _f(p.get("positionValue")), "date": p.get("reportDate")})
        for t in s.findall(".//Trades/Trade"):
            out["trades"].append({"account_id": acct, "symbol": t.get("symbol"), "exchange": t.get("listingExchange"),
                                  "currency": t.get("currency"), "side": t.get("buySell"), "quantity": _f(t.get("quantity")),
                                  "price": _f(t.get("tradePrice")), "commission": _f(t.get("ibCommission")),
                                  "date": t.get("tradeDate"), "trade_id": t.get("tradeID")})
        for c in s.findall(".//CashReport/CashReportCurrency"):
            out["cash"].append({"account_id": acct, "currency": c.get("currency"), "ending_cash": _f(c.get("endingCash")),
                                "ending_settled": _f(c.get("endingSettledCash"))})
    return out


# ── Client Portal Gateway ────────────────────────────────────────────────────
def _gw(fund: str, path: str) -> Any:
    cfg = config(fund)
    if not cfg["gateway_local"]:
        raise RuntimeError("IBKR_GATEWAY_URL must point at this machine (localhost) — the gateway holds the signed-in session")
    # the gateway serves a self-signed certificate on localhost: verification is skipped for localhost only
    r = requests.get(f"{cfg['gateway_url']}/v1/api/{path}", timeout=15, verify=False)
    if r.status_code == 401:
        raise PermissionError("the IBKR gateway is running but not signed in — sign in at " + cfg["gateway_url"])
    r.raise_for_status()
    return r.json()


def gateway_status(fund: str) -> Dict[str, Any]:
    try:
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        st = _gw(fund, "iserver/auth/status")
        return {"reachable": True, "authenticated": bool(st.get("authenticated")), "connected": bool(st.get("connected")),
                "competing": bool(st.get("competing"))}
    except PermissionError as e:
        return {"reachable": True, "authenticated": False, "detail": str(e)}
    except Exception as e:                                                     # noqa: BLE001 — not running
        return {"reachable": False, "authenticated": False, "detail": f"{type(e).__name__}: {str(e)[:160]}"}


def gateway_snapshot(fund: str) -> Dict[str, Any]:
    """Live positions and balances of the fund's pinned account through the signed-in gateway."""
    acct = _env(fund, "ACCOUNT_ID")
    if not acct:
        raise RuntimeError(f"set IBKR_{fund.upper()}_ACCOUNT_ID so only this fund's account is read")
    accts = [a.get("accountId") or a.get("id") for a in (_gw(fund, "portfolio/accounts") or [])]
    if acct not in accts:
        raise PermissionError(f"account {acct} is not available in the signed-in gateway session")
    pos, page = [], 0
    while page < 20:
        chunk = _gw(fund, f"portfolio/{acct}/positions/{page}") or []
        pos += chunk
        if len(chunk) < 100:
            break
        page += 1
    ledger = _gw(fund, f"portfolio/{acct}/ledger") or {}
    return {"account_id": acct, "source": "gateway",
            "positions": [{"account_id": acct, "symbol": p.get("contractDesc") or p.get("ticker"), "conid": p.get("conid"),
                           "asset_class": p.get("assetClass"), "exchange": p.get("listingExchange"), "currency": p.get("currency"),
                           "quantity": p.get("position"), "mark_price": p.get("mktPrice"), "cost_price": p.get("avgCost"),
                           "market_value": p.get("mktValue")} for p in pos],
            "cash": [{"account_id": acct, "currency": k, "ending_cash": v.get("cashbalance"), "ending_settled": v.get("settledcash")}
                     for k, v in ledger.items() if isinstance(v, dict)]}


def broker_snapshot(fund: str, source: str = "auto") -> Dict[str, Any]:
    """The broker's view of the fund's account: live gateway when signed in, else the latest Flex statement."""
    acct = _env(fund, "ACCOUNT_ID")
    if source in ("auto", "gateway") and gateway_status(fund).get("authenticated"):
        return gateway_snapshot(fund)
    if source == "gateway":
        raise RuntimeError("the IBKR gateway is not signed in")
    data = parse_flex(flex_statement(fund))
    accounts = {a["account_id"] for a in data["accounts"]}
    if acct and accounts - {acct}:
        raise PermissionError(f"the Flex statement contains account(s) {sorted(accounts - {acct})} that are not this fund's ({acct})")
    if not acct and len(accounts) > 1:
        raise PermissionError("the Flex statement covers several accounts: set IBKR_<FUND>_ACCOUNT_ID")
    return {**data, "account_id": acct or next(iter(accounts), None), "source": "flex"}


def reconcile_positions(platform: List[Dict[str, Any]], broker: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Platform book vs broker positions by ticker (all books summed): matched, quantity breaks, and names held on one
    side only."""
    mine: Dict[str, float] = {}
    for p in platform:
        s = str(p["symbol"]).upper()
        mine[s] = mine.get(s, 0.0) + float(p.get("quantity") or 0)
    theirs: Dict[str, Tuple[float, Dict[str, Any]]] = {}
    for b in broker:
        if (b.get("asset_class") or "STK").upper() in ("CASH",):
            continue
        t = to_yahoo(b.get("symbol") or "", b.get("exchange"), b.get("currency"))
        q = float(b.get("quantity") or 0)
        theirs[t] = (theirs.get(t, (0.0, b))[0] + q, b)
    rows = []
    for t in sorted(set(mine) | set(theirs)):
        a, (bq, raw) = mine.get(t, 0.0), theirs.get(t, (0.0, {}))
        status = "match" if abs(a - bq) < 1e-6 else ("broker_only" if t not in mine else "platform_only" if t not in theirs else "quantity_break")
        rows.append({"ticker": t, "platform": a, "broker": bq, "difference": a - bq, "status": status,
                     "broker_symbol": raw.get("symbol"), "exchange": raw.get("exchange"), "currency": raw.get("currency")})
    breaks = [r for r in rows if r["status"] != "match"]
    return {"ok": not breaks, "rows": rows, "breaks": breaks, "matched": len(rows) - len(breaks)}
