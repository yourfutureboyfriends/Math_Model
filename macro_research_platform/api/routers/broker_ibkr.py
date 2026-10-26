"""IBKR link per fund (api/brokerage/ibkr.py) — read-only: status, broker snapshot, broker reconciliation, and a
one-time import of the broker's positions into the fund's book. No order routing."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

router = APIRouter(tags=["broker"])


def _cap(request: Request, cap: str) -> Dict[str, Any]:
    from api import positions
    return positions.require(request, cap)


async def _snapshot(fund: str, source: str) -> Dict[str, Any]:
    from api.brokerage import ibkr
    try:
        return await asyncio.wait_for(asyncio.to_thread(ibkr.broker_snapshot, fund, source), timeout=120)
    except asyncio.TimeoutError:
        raise HTTPException(504, "IBKR did not answer in time — try again")
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except (RuntimeError, ValueError) as e:
        raise HTTPException(409, str(e))
    except Exception as e:                                                     # noqa: BLE001 — network / format
        raise HTTPException(502, f"IBKR request failed: {type(e).__name__}: {str(e)[:200]}")


@router.get("/api/v1/broker/ibkr")
async def ibkr_status(request: Request):
    """What is configured for this fund and whether the local gateway is signed in (no secrets returned)."""
    from api import funds
    from api.brokerage import ibkr
    _cap(request, "view_book")
    fid = funds.current()
    return {**ibkr.config(fid), "gateway": await asyncio.to_thread(ibkr.gateway_status, fid)}


@router.get("/api/v1/broker/ibkr/snapshot")
async def ibkr_snapshot(request: Request, source: str = Query("auto", pattern="^(auto|flex|gateway)$")):
    from api import funds
    _cap(request, "view_book")
    return await _snapshot(funds.current(), source)


@router.post("/api/v1/broker/ibkr/reconcile")
async def ibkr_reconcile(request: Request, source: str = Query("auto", pattern="^(auto|flex|gateway)$")):
    """Platform positions vs the broker's, recorded with the fund's reconciliations; breaks open an incident (and halt
    execution when the fund's governance is on)."""
    from api import funds, governance as gov, portfolio_store
    from api.brokerage import ibkr
    u = _cap(request, "reconcile")
    snap = await _snapshot(funds.current(), source)
    mine = await asyncio.to_thread(portfolio_store.list_positions, None)
    rec = ibkr.reconcile_positions(mine, snap["positions"])

    def store():
        gov.init_db()
        from api.portfolio_store import _conn
        with _conn() as c:
            cur = c.execute("INSERT INTO gov_reconciliations (ts, ok, checked, breaks, notes, run_by) VALUES (?,?,?,?,?,?)",
                            (datetime.now(timezone.utc).isoformat(timespec="seconds"), 1 if rec["ok"] else 0, len(rec["rows"]),
                             json.dumps(rec["breaks"]), f"broker reconciliation — IBKR {snap['source']}, account {snap.get('account_id')}",
                             u["username"]))
            c.commit()
            rid = cur.lastrowid
        if not rec["ok"]:
            desc = f"IBKR reconciliation #{rid}: {len(rec['breaks'])} break(s) " + ", ".join(b["ticker"] for b in rec["breaks"][:6])
            if gov.settings()["enabled"]:
                gov.start_halt("reconciliation", desc, u["username"])
            else:
                gov.open_incident("broker_reconciliation", desc, u["username"], "medium")
        return rid
    rid = await asyncio.to_thread(store)
    return {"id": rid, **rec, "source": snap["source"], "account_id": snap.get("account_id"), "cash": snap.get("cash")}


class ImportIn(BaseModel):
    book: str = Field("IBKR", max_length=60)
    confirm: bool = False


@router.post("/api/v1/broker/ibkr/import")
async def ibkr_import(body: ImportIn, request: Request, source: str = Query("auto", pattern="^(auto|flex|gateway)$")):
    """Set the fund's book to the broker's positions (one-time onboarding or re-base): positions in `book` are replaced
    by IBKR's — quantity and average cost (price units checked against market data). Audit-logged; needs confirm."""
    from api import audit_store, funds, portfolio_store
    from api.brokerage import ibkr
    u = _cap(request, "execute_orders")
    if not body.confirm:
        raise HTTPException(400, "set confirm=true — this replaces the book's positions with the broker's")
    snap = await _snapshot(funds.current(), source)

    def run():
        from api.marketdata import core
        from datetime import date
        before = portfolio_store.list_positions(body.book)
        rows, notes = [], []
        for b in snap["positions"]:
            if (b.get("asset_class") or "STK").upper() == "CASH" or not b.get("quantity"):
                continue
            t = ibkr.to_yahoo(b["symbol"], b.get("exchange"), b.get("currency"))
            cost = b.get("cost_price") or b.get("mark_price")
            try:                                       # IBKR may quote London lines in pounds, Yahoo in pence (or vice versa)
                last = (core.quote(t) or {}).get("price")
                if last and b.get("mark_price"):
                    ratio = last / b["mark_price"]
                    if 80 < ratio < 120:
                        cost, notes = cost * 100, notes + [f"{t}: cost converted pounds → pence"]
                    elif 0.008 < ratio < 0.012:
                        cost, notes = cost / 100, notes + [f"{t}: cost converted pence → pounds"]
            except Exception:                                                  # noqa: BLE001 — keep IBKR's units
                notes.append(f"{t}: no market price to check units")
            rows.append({"symbol": t, "quantity": float(b["quantity"]), "avg_cost": float(cost or 0), "book": body.book,
                         "asset_class": "Equity" if (b.get("asset_class") or "STK") == "STK" else b.get("asset_class"),
                         "entry_date": date.today().isoformat()})
        for p in before:
            portfolio_store.delete_position(p["id"])
        if rows:
            portfolio_store.add_positions_bulk(rows)
        audit_store.add_decision("broker_import", f"Book '{body.book}' set to IBKR {snap['source']} positions of account "
                                                  f"{snap.get('account_id')}: {len(rows)} position(s) (replaced {len(before)})",
                                 user=u["username"], target=f"book:{body.book}",
                                 before_state=[{k: p.get(k) for k in ('symbol', 'quantity', 'avg_cost')} for p in before],
                                 after_state=rows)
        return rows, notes
    rows, notes = await asyncio.to_thread(run)
    return {"imported": len(rows), "book": body.book, "positions": rows, "notes": notes, "source": snap["source"],
            "account_id": snap.get("account_id")}
