"""
Multi-currency accounting for the fund: USD per unit of a listing's quote currency as of a date (minor units such as
GBp / ZAc / ILA handled), the fund's base currency per USD, and the conversions the book uses:

  market value (base)  = quantity × price × USD-per-unit(today)  × base-per-USD(today)
  cost basis   (base)  = quantity × avg cost × USD-per-unit(cost) × base-per-USD(entry date)
  FX P&L               = quantity × price × (rate(today) − rate(cost)),  local P&L = unrealised − FX P&L

USD-per-unit at cost is stored per position (weighted over its fills), so a later change of base currency keeps the
history right. Rates are the last observed close on or before the date (never a later one).
"""
from __future__ import annotations

import threading
from datetime import date
from typing import Dict, Optional, Tuple

import pandas as pd

_SERIES: Dict[str, pd.Series] = {}
_lock = threading.Lock()


def _major_usd_series(major: str) -> Optional[pd.Series]:
    """USD per one unit of `major`, daily (cached in-process for the day)."""
    major = major.upper()
    if major == "USD":
        return None
    key = f"{major}:{date.today()}"
    with _lock:
        if key in _SERIES:
            return _SERIES[key]
    from api.quant import codeserver
    try:
        idx = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=260 * 12)
        s = codeserver.usd_per(major, [d.strftime("%Y-%m-%d") for d in idx])
        s = s.dropna()
    except Exception:                                                          # noqa: BLE001 — no FX → None
        s = None
    with _lock:
        _SERIES[key] = s
    return s


def usd_per_major(major: str, on: Optional[str] = None) -> Optional[float]:
    """USD per one unit of a major currency as of `on` (YYYY-MM-DD; today when None)."""
    if (major or "USD").upper() == "USD":
        return 1.0
    s = _major_usd_series(major)
    if s is None or s.empty:
        return None
    if on is None:
        return float(s.iloc[-1])
    t = pd.Timestamp(str(on)[:10])
    s2 = s[s.index <= t]
    return float(s2.iloc[-1]) if len(s2) else None


def usd_per_unit(quote_ccy: Optional[str], on: Optional[str] = None) -> Optional[float]:
    """USD per one unit of a quote currency (GBp = 0.01 GBP) as of `on`."""
    from api.markets import minor_unit_factor
    major, div = minor_unit_factor(quote_ccy or "USD")
    r = usd_per_major(major, on)
    return (r / div) if r else None


def base_per_usd(base: str, on: Optional[str] = None) -> Optional[float]:
    """Units of the base currency per US dollar on a date (latest when `on` is None), or None when the rate is
    unavailable.
    """
    r = usd_per_major(base or "USD", on)
    return (1.0 / r) if r else None


def entry_date_of(pos: Dict) -> Optional[str]:
    """A position's entry date (YYYY-MM-DD) — the entry date, else the row's creation date — or None."""
    d = pos.get("entry_date") or pos.get("created_at")
    return str(d)[:10] if d else None


def convert_position(p: Dict, base: str, usd_now: Optional[float]) -> Dict:
    """Fill base-currency market value, cost basis, unrealised and its local / FX split on an enriched position
    (local values from calculations.portfolio.enrich_position). Returns the position (changed in place)."""
    from api.markets import minor_unit_factor
    qty = float(p.get("quantity") or 0.0)
    avg = float(p.get("avg_cost") or 0.0)
    ccy = p.get("currency") or "USD"
    entry = entry_date_of(p)
    major, div = minor_unit_factor(ccy)
    if major == (base or "USD").upper():
        rate_now = rate_cost = 1.0 / div           # the base currency itself (GBp in a GBP fund): exact, no FX
    else:
        usd_now = usd_per_unit(ccy) or usd_now      # one FX source for both legs (no cross-source drift)
        usd_cost = p.get("cost_usd_per_unit") or (usd_per_unit(ccy, entry) if entry else None) or usd_now
        if not p.get("cost_usd_per_unit") and not entry:
            p["cost_fx_estimated"] = True           # no entry date: cost converted at today's rate
        b_now, b_entry = base_per_usd(base), base_per_usd(base, entry) if entry else base_per_usd(base)
        if not (usd_now and usd_cost and b_now and b_entry):
            p["fx_unavailable"] = True
            return p
        rate_now, rate_cost = usd_now * b_now, usd_cost * b_entry
    p["fx_rate_to_base"], p["cost_fx_rate_to_base"] = rate_now, rate_cost
    p["cost_basis"] = round(qty * avg * rate_cost, 2)
    p["cost_basis_local"] = round(qty * avg, 4)
    if p.get("current_price") is not None:
        mv_local = qty * float(p["current_price"])
        p["market_value_local"] = round(mv_local, 4)
        p["unrealized_pnl_local"] = round(qty * (float(p["current_price"]) - avg), 4)
        p["market_value"] = round(mv_local * rate_now, 2)
        p["unrealized_pnl"] = round(p["market_value"] - p["cost_basis"], 2)
        p["fx_pnl"] = round(mv_local * (rate_now - rate_cost), 2)
        p["local_pnl"] = round(p["unrealized_pnl"] - p["fx_pnl"], 2)
    p["value_currency"] = base
    return p


def fill_rates(symbol: str, base: str) -> Tuple[str, Optional[float], Optional[float]]:
    """(quote currency, USD per unit, base per USD) at a fill now."""
    from api.handlers.portfolio_analytics import _usd_per_unit
    ccy, usd = _usd_per_unit(symbol)
    return ccy, usd, base_per_usd(base)
