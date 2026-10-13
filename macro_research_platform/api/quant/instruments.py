"""
Instrument metadata for the Code Lab: listing country, quote currency and its unit (GBp = pence),
the account-currency conversion, and venue transaction taxes. The account currency is the strategy's
ACCOUNT_CURRENCY (default USD; any currency in ACCOUNT_CURRENCIES).

Transaction taxes are approximate statutory rates (2025–26), in bp of traded value; exemptions,
thresholds and caps (AIM shares, small caps under the FTT size limits, Malaysian stamp caps…) are
not modelled, and rates change — they are shown with every result.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

ACCOUNT_CCY = "USD"            # default
# Currencies an account can be kept in: every currency of the tradable universe plus the majors (each has a Yahoo
# USD cross, `XXX=X`, giving units per 1 USD).
ACCOUNT_CURRENCIES = ("USD", "EUR", "JPY", "GBP", "CNY", "HKD", "CHF", "CAD", "AUD", "NZD", "SEK", "NOK", "DKK",
                      "SGD", "KRW", "TWD", "INR", "IDR", "MYR", "THB", "PHP", "ILS", "ZAR", "SAR", "QAR", "AED",
                      "TRY", "PLN", "CZK", "HUF", "RON", "ISK", "BRL", "MXN", "CLP", "ARS", "COP", "PEN")


def account_currency(x: Optional[str]) -> str:
    c = (x or ACCOUNT_CCY).strip().upper()
    if c not in ACCOUNT_CURRENCIES:
        raise ValueError(f"ACCOUNT_CURRENCY '{c}' is not supported. Use one of: {', '.join(ACCOUNT_CURRENCIES)}.")
    return c

# country → (buy bp, sell bp, description)
TAXES: Dict[str, tuple] = {
    "GB": (50.0, 0.0, "UK stamp duty reserve tax 0.5% on purchases"),
    "IE": (100.0, 0.0, "Irish stamp duty 1% on purchases"),
    "FR": (40.0, 0.0, "French financial transaction tax 0.4% on purchases (large caps)"),
    "IT": (10.0, 0.0, "Italian FTT 0.1% on purchases"),
    "ES": (20.0, 0.0, "Spanish FTT 0.2% on purchases (large caps)"),
    "BE": (35.0, 35.0, "Belgian tax on stock exchange transactions 0.35% each side"),
    "CH": (7.5, 7.5, "Swiss securities transfer tax ~0.075% each side"),
    "HK": (10.0, 10.0, "Hong Kong stamp duty 0.1% each side"),
    "CN": (0.0, 5.0, "China stamp duty 0.05% on sales"),
    "TW": (0.0, 30.0, "Taiwan securities transaction tax 0.3% on sales"),
    "KR": (0.0, 15.0, "Korea securities transaction tax ~0.15% on sales (set annually)"),
    "IN": (10.0, 10.0, "India securities transaction tax 0.1% each side (delivery)"),
    "MY": (10.0, 10.0, "Malaysia stamp duty ~0.1% each side (capped)"),
    "ID": (0.0, 10.0, "Indonesia transaction tax 0.1% on sales"),
    "PH": (0.0, 60.0, "Philippines stock transaction tax 0.6% on sales"),
    "ZA": (25.0, 0.0, "South Africa securities transfer tax 0.25% on purchases"),
}


def _universe_rows() -> Dict[str, Dict[str, Any]]:
    from api import global_universe
    try:
        return {str(r.get("symbol", "")).upper(): r for r in global_universe.load(rebuild_if_stale=False).get("stocks", [])}
    except Exception:                                          # noqa: BLE001
        return {}


def _quote_ccy(sym: str, country: str, row: Optional[Dict[str, Any]]) -> str:
    """Quote currency as Yahoo reports it (GBp, ZAc, ILA for minor units)."""
    if row and row.get("currency"):
        return row["currency"]
    try:
        from api.marketdata.core import _info
        c = (_info(sym) or {}).get("currency")
        if c:
            return c
    except Exception:                                          # noqa: BLE001
        pass
    from api.markets import COUNTRIES
    default = (COUNTRIES.get(country) or {}).get("ccy", "USD")
    return {"GB": "GBp", "ZA": "ZAc", "IL": "ILA"}.get(country, default)


def meta(symbols: List[str]) -> Dict[str, Dict[str, Any]]:
    """Per-symbol metadata: listing country, quote currency and unit, FX ticker, venue taxes, and — for names in the
    tradable universe — name, sector, region and MSCI market class (strategies may group or neutralise by them)."""
    from api.markets import country_of, fx_ticker, minor_unit_factor
    rows = _universe_rows()
    out = {}
    for s in symbols:
        country = country_of(s)
        row = rows.get(s) or rows.get(s.replace("-", ".")) or {}
        q = _quote_ccy(s, country, row) if country != "US" else "USD"
        ccy, divisor = minor_unit_factor(q)
        buy, sell, why = TAXES.get(country, (0.0, 0.0, None))
        out[s] = {"country": country, "quote_currency": q, "currency": ccy, "unit_divisor": divisor,
                  "fx_ticker": fx_ticker(ccy), "tax_buy_bps": buy, "tax_sell_bps": sell, "tax_note": why,
                  "sec_fee": country == "US", "name": row.get("name"), "sector": row.get("sector"),
                  "region": row.get("region"), "market_class": row.get("market_class")}
    return out
