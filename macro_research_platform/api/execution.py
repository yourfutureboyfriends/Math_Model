"""
Order execution adapters.

* SIMULATED (default): fill at the latest real close, with the fund's cost estimate as
  commission. Booked straight into the blotter.
* ALPACA PAPER: market order sent to Alpaca's PAPER trading API only. Enabled solely when
  BROKER_ROUTING=alpaca_paper AND ALPACA_API_KEY / ALPACA_SECRET_KEY are set. The endpoint is
  hard-coded to paper-api.alpaca.markets — this module cannot reach a live account.
  The fill is booked at Alpaca's reported average fill price once the order fills.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Optional

PAPER_URL = "https://paper-api.alpaca.markets"


@dataclass
class Fill:
    filled: bool
    price: Optional[float]
    quantity: float
    source: str
    broker_order_id: Optional[str] = None
    status: str = "filled"
    detail: str = ""


def execution_mode() -> str:
    if (os.getenv("BROKER_ROUTING", "").lower() == "alpaca_paper"
            and os.getenv("ALPACA_API_KEY") and os.getenv("ALPACA_SECRET_KEY")):
        return "alpaca_paper"
    return "simulated"


def simulated_fill(signed_qty: float, last_price: Optional[float]) -> Fill:
    if not last_price or last_price <= 0:
        return Fill(False, None, signed_qty, "simulated", status="rejected", detail="no price available")
    return Fill(True, float(last_price), signed_qty, "simulated")


def alpaca_paper_fill(symbol: str, signed_qty: float, session=None,
                      poll_seconds: float = 10.0) -> Fill:
    """Submit a market order to Alpaca PAPER and wait briefly for the fill."""
    import requests
    s = session or requests.Session()
    headers = {"APCA-API-KEY-ID": os.getenv("ALPACA_API_KEY", ""),
               "APCA-API-SECRET-KEY": os.getenv("ALPACA_SECRET_KEY", "")}
    body = {"symbol": symbol, "qty": str(abs(signed_qty)), "side": "buy" if signed_qty > 0 else "sell",
            "type": "market", "time_in_force": "day"}
    r = s.post(f"{PAPER_URL}/v2/orders", json=body, headers=headers, timeout=10)
    if r.status_code >= 300:
        return Fill(False, None, signed_qty, "alpaca_paper", status="rejected",
                    detail=f"broker rejected: HTTP {r.status_code} {r.text[:200]}")
    order = r.json()
    oid = order.get("id")
    deadline = time.time() + poll_seconds
    while True:
        if order.get("status") == "filled" and order.get("filled_avg_price"):
            return Fill(True, float(order["filled_avg_price"]), signed_qty, "alpaca_paper", oid)
        if order.get("status") in ("canceled", "expired", "rejected"):
            return Fill(False, None, signed_qty, "alpaca_paper", oid, order["status"],
                        f"broker status {order['status']}")
        if time.time() >= deadline:
            return Fill(False, None, signed_qty, "alpaca_paper", oid, "submitted",
                        "submitted to broker; not filled yet (e.g. market closed)")
        time.sleep(1.0)
        order = s.get(f"{PAPER_URL}/v2/orders/{oid}", headers=headers, timeout=10).json()
