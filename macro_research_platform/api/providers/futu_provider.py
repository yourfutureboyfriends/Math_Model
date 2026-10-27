"""
Futu OpenAPI — read-only market data and holdings through the FutuOpenD gateway running on this computer.

What it adds: real-time quotes for Hong Kong, China A-shares (Stock Connect) and US stocks (subject to the account's
quote entitlements), the real order book and tick-by-tick trades, capital flow (money in / out, split by order size),
the Hong Kong broker queue, and the account's positions for the Position Manager.

READ-ONLY by design: this module never unlocks trading and never places, modifies or cancels an order — those calls
do not appear anywhere in it (a test checks the source). Order routing needs separate, explicit authorisation.

Setup: install FutuOpenD and log in there (the password stays in OpenD; nothing is stored here). Defaults to
127.0.0.1:11111; FUTU_OPEND_HOST / FUTU_OPEND_PORT in .env override.
"""
from __future__ import annotations

import logging
import os
import socket
import threading
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)
_lock = threading.Lock()
_ctx: Dict[str, Any] = {"quote": None, "subs": {}}
SUB_KEEP = 70          # Futu requires a subscription to last ≥ 60 s before it can be cancelled
SUB_MAX = 40           # stay well inside the account's subscription quota


class FutuUnavailable(RuntimeError):
    """OpenD is not running / not logged in, or the account lacks the quote right."""


def _addr() -> tuple:
    return os.getenv("FUTU_OPEND_HOST", "127.0.0.1"), int(os.getenv("FUTU_OPEND_PORT", "11111"))


def opend_running() -> bool:
    host, port = _addr()
    try:
        with socket.create_connection((host, port), timeout=1.5):
            return True
    except OSError:
        return False


# ── symbols ──────────────────────────────────────────────────────────────────
def to_futu(symbol: str) -> Optional[str]:
    """Yahoo-style symbol → Futu code: 0700.HK → HK.00700, AAPL → US.AAPL, 600519.SS → SH.600519, 000001.SZ → SZ.000001,
    D05.SI → SG.D05. None for markets Futu does not quote here."""
    s = symbol.strip().upper()
    base, _, suf = s.rpartition(".") if "." in s else (s, "", "")
    if not suf and not any(c in s for c in "=^"):
        return f"US.{s.replace('-', '.')}"
    if suf == "HK":
        return f"HK.{int(base):05d}" if base.isdigit() else None
    if suf == "SS":
        return f"SH.{base}"
    if suf == "SZ":
        return f"SZ.{base}"
    if suf == "SI":
        return f"SG.{base}"
    return None


def from_futu(code: str) -> str:
    mkt, _, c = code.partition(".")
    if mkt == "HK":
        return f"{int(c):04d}.HK" if c.isdigit() else f"{c}.HK"
    if mkt == "US":
        return c.replace(".", "-")
    return {"SH": f"{c}.SS", "SZ": f"{c}.SZ", "SG": f"{c}.SI"}.get(mkt, code)


# ── connection ───────────────────────────────────────────────────────────────
def _quote_ctx():
    """A shared quote connection (OpenD allows few connections; one is reused)."""
    if not opend_running():
        raise FutuUnavailable("FutuOpenD is not running on this computer — open it and log in (default port 11111).")
    from futu import OpenQuoteContext
    with _lock:
        if _ctx["quote"] is None:
            host, port = _addr()
            _ctx["quote"] = OpenQuoteContext(host=host, port=port)
        return _ctx["quote"]


def _reset() -> None:
    with _lock:
        q = _ctx["quote"]
        _ctx["quote"], _ctx["subs"] = None, {}
    try:
        if q is not None:
            q.close()
    except Exception:
        pass


def _ok(ret, data, what: str):
    from futu import RET_OK
    if ret != RET_OK:
        msg = str(data)
        if any(k in msg.lower() for k in ("disconnect", "not connected", "connect")):
            _reset()
        raise FutuUnavailable(f"Futu {what}: {msg[:200]}")
    return data


def _subscribe(code: str, subtypes: List[Any]) -> None:
    """Subscribe once per (code, type); unsubscribe the oldest beyond SUB_MAX after their minimum duration."""
    from futu import SubType
    q = _quote_ctx()
    need = [t for t in subtypes if (code, t) not in _ctx["subs"]]
    if need:
        _ok(*q.subscribe([code], need, subscribe_push=False), f"subscribe {code}")
        now = time.time()
        for t in need:
            _ctx["subs"][(code, t)] = now
    if len(_ctx["subs"]) > SUB_MAX:
        old = sorted((v, k) for k, v in _ctx["subs"].items() if time.time() - v > SUB_KEEP)[: len(_ctx["subs"]) - SUB_MAX]
        for _, (c, t) in old:
            try:
                q.unsubscribe([c], [t])
                _ctx["subs"].pop((c, t), None)
            except Exception:
                pass


def _records(df) -> List[Dict[str, Any]]:
    import math
    out = []
    for r in df.to_dict("records"):
        out.append({k: (None if isinstance(v, float) and (math.isnan(v) or math.isinf(v)) else v) for k, v in r.items()})
    return out


# ── market data ──────────────────────────────────────────────────────────────
def status() -> Dict[str, Any]:
    """Whether OpenD is reachable and logged in, and the quote entitlements by market."""
    if not opend_running():
        return {"connected": False, "reason": "FutuOpenD is not running (or not on port 11111)."}
    try:
        q = _quote_ctx()
        st = _ok(*q.get_global_state(), "state")
        info = {}
        try:
            from futu import RET_OK
            ret, u = q.get_user_info()
            if ret == RET_OK:
                info = {k: v for k, v in (u or {}).items() if k in ("hk_qot_right", "us_qot_right", "cn_qot_right", "hk_option_qot_right",
                                                                     "us_option_qot_right", "sub_quota", "history_kl_quota")}
        except Exception:
            pass
        return {"connected": True, "logged_in": bool(st.get("qot_logined")), "trade_logged_in": bool(st.get("trd_logined")),
                "markets": {k: st.get(k) for k in ("market_hk", "market_us", "market_sh", "market_sz") if k in st},
                "entitlements": info, "server_version": st.get("server_ver")}
    except FutuUnavailable as e:
        return {"connected": False, "reason": str(e)}


def snapshot(symbols: List[str]) -> List[Dict[str, Any]]:
    """Real-time snapshot (no subscription needed): last, change, bid/ask, volume, turnover for up to 400 codes."""
    codes = [c for c in (to_futu(s) for s in symbols) if c]
    if not codes:
        raise FutuUnavailable("None of these symbols trade on a market Futu quotes here (HK, US, SH, SZ, SG).")
    df = _ok(*_quote_ctx().get_market_snapshot(codes[:400]), "snapshot")
    out = []
    for r in _records(df):
        last, prev = r.get("last_price"), r.get("prev_close_price")
        out.append({"symbol": from_futu(r["code"]), "code": r["code"], "name": r.get("name"), "price": last,
                    "previous_close": prev, "change_pct": (last / prev - 1) if last and prev else None,
                    "bid": r.get("bid_price"), "ask": r.get("ask_price"), "volume": r.get("volume"), "turnover": r.get("turnover"),
                    "high": r.get("high_price"), "low": r.get("low_price"), "open": r.get("open_price"),
                    "update_time": r.get("update_time"), "suspended": r.get("suspension")})
    return out


def order_book(symbol: str, depth: int = 10) -> Dict[str, Any]:
    from futu import SubType
    code = to_futu(symbol) or ""
    if not code:
        raise FutuUnavailable(f"Futu does not quote {symbol} here.")
    _subscribe(code, [SubType.ORDER_BOOK])
    ob = _ok(*_quote_ctx().get_order_book(code, num=depth), "order book")
    side = lambda xs: [{"price": p, "volume": v, "orders": n} for p, v, n, *_ in xs]
    return {"symbol": symbol, "code": code, "bids": side(ob.get("Bid", [])), "asks": side(ob.get("Ask", [])),
            "time": ob.get("svr_recv_time_bid") or ob.get("svr_recv_time_ask"), "source": "Futu OpenAPI (real-time order book)"}


def ticks(symbol: str, n: int = 200) -> Dict[str, Any]:
    """Tick-by-tick trades with the exchange's buy / sell direction (not estimated from bars)."""
    from futu import SubType
    code = to_futu(symbol) or ""
    if not code:
        raise FutuUnavailable(f"Futu does not quote {symbol} here.")
    _subscribe(code, [SubType.TICKER])
    df = _ok(*_quote_ctx().get_rt_ticker(code, num=n), "ticks")
    rows = [{"time": r.get("time"), "price": r.get("price"), "volume": r.get("volume"), "turnover": r.get("turnover"),
             "side": {"BUY": 1, "SELL": -1}.get(str(r.get("ticker_direction")), 0)} for r in _records(df)]
    buy = sum(r["volume"] or 0 for r in rows if r["side"] > 0)
    sell = sum(r["volume"] or 0 for r in rows if r["side"] < 0)
    return {"symbol": symbol, "code": code, "ticks": rows[::-1], "buy_volume": buy, "sell_volume": sell,
            "buy_share": buy / (buy + sell) if buy + sell else None, "source": "Futu OpenAPI (exchange tick direction)"}


def capital_flow(symbol: str) -> Dict[str, Any]:
    """Today's net money flow (intraday) and the split of in / out flows by order size."""
    code = to_futu(symbol) or ""
    if not code:
        raise FutuUnavailable(f"Futu does not quote {symbol} here.")
    q = _quote_ctx()
    flow = _records(_ok(*q.get_capital_flow(code), "capital flow"))
    dist = _records(_ok(*q.get_capital_distribution(code), "capital distribution"))
    d = dist[0] if dist else {}
    sizes = {}
    for k in ("super", "big", "mid", "small"):
        i, o = d.get(f"capital_in_{k}"), d.get(f"capital_out_{k}")
        if i is not None or o is not None:
            sizes[k] = {"in": i, "out": o, "net": (i or 0) - (o or 0)}
    return {"symbol": symbol, "code": code, "intraday": [{"time": r.get("capital_flow_item_time"), "net_inflow": r.get("in_flow"),
                                                          "main_inflow": r.get("main_in_flow")} for r in flow],
            "by_order_size": sizes, "update_time": d.get("update_time"),
            "note": "Futu classifies each trade by order size (super > big > mid > small); 'main' money is super + big orders.",
            "source": "Futu OpenAPI (capital flow)"}


def broker_queue(symbol: str) -> Dict[str, Any]:
    """Hong Kong only: the brokers queued at the best bid and ask levels."""
    from futu import SubType
    code = to_futu(symbol) or ""
    if not code.startswith("HK."):
        raise FutuUnavailable("The broker queue is published for Hong Kong stocks only.")
    _subscribe(code, [SubType.BROKER])
    ret, bid, ask = _quote_ctx().get_broker_queue(code)
    _ok(ret, bid, "broker queue")
    pick = lambda df, side: [{"broker": r.get(f"{side}_broker_name"), "broker_id": r.get(f"{side}_broker_id"),
                              "level": r.get(f"{side}_broker_pos")} for r in _records(df)]
    return {"symbol": symbol, "code": code, "bid": pick(bid, "bid"), "ask": pick(ask, "ask"), "source": "Futu OpenAPI (HKEX broker queue)"}


# ── holdings (read-only) ─────────────────────────────────────────────────────
def positions() -> Dict[str, Any]:
    """The account's positions across Futu's brokerage entities — query only (no unlock, no orders)."""
    if not opend_running():
        raise FutuUnavailable("FutuOpenD is not running (or not on port 11111).")
    from futu import RET_OK, OpenSecTradeContext, SecurityFirm, TrdEnv, TrdMarket
    host, port = _addr()
    out, accounts = [], []
    for firm in (SecurityFirm.FUTUSECURITIES, SecurityFirm.FUTUINC, SecurityFirm.FUTUSG, SecurityFirm.FUTUAU,
                 SecurityFirm.FUTUCA, SecurityFirm.FUTUMY, SecurityFirm.FUTUJP):
        ctx = OpenSecTradeContext(filter_trdmarket=TrdMarket.NONE, host=host, port=port, security_firm=firm)
        try:
            ret, accs = ctx.get_acc_list()
            if ret != RET_OK or accs is None or accs.empty:
                continue
            for a in _records(accs):
                if a.get("trd_env") != TrdEnv.REAL:
                    continue
                accounts.append({"firm": firm, "acc_id": str(a.get("acc_id"))[-4:]})   # last four digits only
                ret, pos = ctx.position_list_query(trd_env=TrdEnv.REAL, acc_id=a["acc_id"])
                if ret != RET_OK or pos is None:
                    continue
                for p in _records(pos):
                    if not p.get("qty"):
                        continue
                    out.append({"symbol": from_futu(p["code"]), "code": p["code"], "name": p.get("stock_name"),
                                "quantity": p.get("qty"), "average_cost": p.get("average_cost") or p.get("cost_price"),
                                "price": p.get("nominal_price"), "market_value": p.get("market_val"),
                                "unrealized_pl": p.get("pl_val"), "currency": p.get("currency"),
                                "side": p.get("position_side"), "account": str(a.get("acc_id"))[-4:]})
        finally:
            ctx.close()
    return {"positions": out, "accounts": accounts, "read_only": True,
            "source": "Futu OpenAPI (position query; trading is never unlocked here)"}
