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
from typing import Dict, Optional

PAPER_URL = "https://paper-api.alpaca.markets"


@dataclass
class Fill:
    """The result of executing an order: whether it filled, price, quantity, source and broker id."""
    filled: bool
    price: Optional[float]
    quantity: float
    source: str
    broker_order_id: Optional[str] = None
    status: str = "filled"
    detail: str = ""
    reference_price: Optional[float] = None       # the decision / last close the fill is measured against
    est_cost_bps: Optional[float] = None          # modelled half-spread + impact applied to a simulated fill
    taxes: Optional[float] = None                 # statutory transfer taxes, in the listing's currency


def execution_mode() -> str:
    """"alpaca_paper" when BROKER_ROUTING=alpaca_paper and Alpaca keys are set, else "simulated"."""
    if (os.getenv("BROKER_ROUTING", "").lower() == "alpaca_paper"
            and os.getenv("ALPACA_API_KEY") and os.getenv("ALPACA_SECRET_KEY")):
        return "alpaca_paper"
    return "simulated"


def simulated_fill(signed_qty: float, last_price: Optional[float], cost_bps: float = 0.0,
                   tax_bps: float = 0.0) -> Fill:
    """A paper fill at the last close moved against the order by the modelled half-spread + market impact
    (`cost_bps`), with statutory transfer taxes (`tax_bps`) booked separately. The close is kept as the reference
    price, so TCA measures the fill against it."""
    if not last_price or last_price <= 0:
        return Fill(False, None, signed_qty, "simulated", status="rejected", detail="no price available")
    px = float(last_price) * (1 + (1 if signed_qty > 0 else -1) * max(cost_bps, 0.0) / 1e4)
    taxes = abs(signed_qty) * px * max(tax_bps, 0.0) / 1e4
    return Fill(True, px, signed_qty, "simulated", reference_price=float(last_price), est_cost_bps=round(cost_bps, 2),
                taxes=round(taxes, 4), detail=f"close {last_price:g} + {cost_bps:.1f} bp modelled spread/impact")


def modelled_cost_bps(symbol: str, quantity: float) -> Dict[str, float]:
    """Half-spread (liquidity / volatility model) + square-root impact at the order's share of 20-day volume, and the
    market's statutory transfer tax rates — the same models as the pre-trade assessment."""
    import math
    import pandas as pd
    from api.handlers import pretrade_feasibility as pf
    from api.markets import classify
    from api.quant.instruments import TAXES
    out = {"half_spread_bps": 0.0, "impact_bps": 0.0, "tax_buy_bps": 0.0, "tax_sell_bps": 0.0}
    try:
        bars = pf._bars_frame(symbol, "1y")
        if len(bars) >= 63:
            from api.calculations import fx_accounting as fa
            from api.quant.codelab import half_spread_bps
            rate = fa.usd_per_unit(bars.attrs.get("currency") or "USD") or 1.0
            hs = half_spread_bps(bars[["close"]].set_axis([symbol], axis=1), bars[["volume"]].set_axis([symbol], axis=1),
                                 usd_per_unit=pd.Series(rate, index=bars.index))
            out["half_spread_bps"] = float(hs.iloc[-1, 0])
            adv = float(bars["volume"].tail(20).mean())
            if adv > 0:
                out["impact_bps"] = pf.IMPACT_BP * math.sqrt(abs(quantity) / adv * 100)
    except Exception:                                                         # noqa: BLE001 — no model: close only
        pass
    b, s_, _ = TAXES.get((classify(symbol).get("country") or "US").upper(), (0.0, 0.0, None))
    out["tax_buy_bps"], out["tax_sell_bps"] = b, s_
    return out


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
