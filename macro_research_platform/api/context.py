"""
Security context — everything the platform knows about one listed company, gathered from every area so a stock page
can show it in one strip:

  book        the fund's positions in it, and the Futu account's (when FutuOpenD runs)
  macro       the signal regime and the macro model's regime for the company's economy, and what each regime's
              sector playbook says about the company's sector (overweight / underweight / neutral)
  valuation   the DCF's value per share against the price (three-stage FCFF, the platform's default model)
  yours       your alerts and journal entries on it, and the team's notes
  pe          LBO deals in this fund's pipeline for it

Each part runs in parallel under its own time limit; a part that fails or times out is reported as unavailable and
never blocks the rest. Read-only.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

# Yahoo sector → SPDR sector ETF (the playbooks in api/regime_context.py are written in ETFs)
SECTOR_ETF = {"Technology": "XLK", "Consumer Cyclical": "XLY", "Financial Services": "XLF", "Real Estate": "XLRE",
              "Energy": "XLE", "Basic Materials": "XLB", "Utilities": "XLU", "Consumer Defensive": "XLP",
              "Healthcare": "XLV", "Industrials": "XLI", "Communication Services": "XLC"}
EURO_AREA = {"Germany", "France", "Italy", "Spain", "Netherlands", "Belgium", "Austria", "Ireland", "Finland", "Portugal",
             "Greece", "Luxembourg", "Slovakia", "Slovenia", "Lithuania", "Latvia", "Estonia", "Croatia", "Cyprus", "Malta"}
MODEL_TO_PLAYBOOK = {"Deflationary slowdown": "Slowdown"}


def _stance(regime: Optional[str], etf: Optional[str]) -> Dict[str, Any]:
    from api.regime_context import RegimeContext
    if not regime or not etf:
        return {"regime": regime, "stance": None}
    name = MODEL_TO_PLAYBOOK.get(regime, regime)
    name = next((k for k in ("Goldilocks", "Reflation", "Stagflation", "Slowdown") if k.lower() == str(name).lower()), name)
    pb = RegimeContext(regime=name, confidence=0, growth_zscore=0, inflation_zscore=0,
                       liquidity_zscore=0, duration_months=0, timestamp=0).sector_playbook
    stance = "overweight" if etf in pb.get("overweight", []) else "underweight" if etf in pb.get("underweight", []) else "neutral"
    return {"regime": regime, "stance": stance, "rationale": pb.get("rationale")}


async def _part(fn: Callable, timeout: float, *a) -> Any:
    try:
        r = fn(*a)
        if asyncio.iscoroutine(r):
            return await asyncio.wait_for(r, timeout)
        return r
    except Exception as e:                             # one part's failure never sinks the strip
        logger.debug("[context] %s: %s", getattr(fn, "__name__", fn), e)
        return {"unavailable": str(e) or type(e).__name__}


def _thread(fn: Callable, timeout: float, *a):
    return _part(lambda: asyncio.wait_for(asyncio.to_thread(fn, *a), timeout), timeout + 1)


async def build(symbol: str, owner: str) -> Dict[str, Any]:
    s = symbol.strip().upper()
    from api.marketdata.core import _info

    info = await _thread(_info, 15, s)
    info = info if isinstance(info, dict) and "unavailable" not in info else {}
    sector, country = info.get("sector"), info.get("country")
    etf = SECTOR_ETF.get(sector or "")

    async def signal_regime():
        from api.handlers.dashboard_handler import get_dashboard_data
        d = await get_dashboard_data(mode="live")
        return {"regime": d.regime.current, "confidence": getattr(d.regime, "confidenceScore", None)}

    async def model_regime():
        from api.model.engine import world_summary
        w = await world_summary()
        econ = "us" if country in (None, "United States") else "ea" if country in EURO_AREA else "row"
        for e in w.get("economies") or []:
            if (e.get("economy") or {}).get("id") == econ and e.get("available"):
                return {"economy": (e.get("economy") or {}).get("name"), "regime": e.get("regime"),
                        "probability": (e.get("probabilities") or {}).get(e.get("regime")), "as_of": e.get("as_of")}
        return {"unavailable": "no model for this economy"}

    def book():
        from api import portfolio_store
        rows = [p for p in portfolio_store.list_positions() if str(p.get("symbol") or "").upper() == s]
        return {"fund": [{"quantity": p.get("quantity"), "avg_cost": p.get("avg_cost"), "book": p.get("book"),
                          "entry_date": p.get("entry_date")} for p in rows]}

    def futu():
        # separate from the fund book: OpenD can be slow to answer, and must never hide the fund's own positions
        from api.providers import futu_provider as fp
        if not fp.opend_running():
            return []
        from api.marketdata.core import _cached
        fu = _cached("ctx:futu_positions", 60, fp.positions) or {}               # one OpenD round trip a minute
        return [{"quantity": p.get("quantity"), "market_value": p.get("market_value"), "unrealized_pl": p.get("unrealized_pl"),
                 "currency": p.get("currency")} for p in fu.get("positions") or [] if str(p.get("symbol") or "").upper() == s]

    def valuation():
        from api.marketdata.core import _cached
        return _cached(f"ctx:valuation:{s}", 1800, lambda: _valuation(s))

    def _valuation(s):
        from api.marketdata import dcf
        inp = dcf.inputs(s)
        if inp.get("is_financial"):
            return {"unavailable": "financial company — the DCF page uses an excess-return model"}
        v = dcf.value(inp)
        return {"per_share": v.get("per_share"), "price": v.get("price"), "upside": v.get("upside"), "model": v.get("model"),
                "currency": inp.get("price_currency") or inp.get("currency")}

    def yours():
        from api.marketdata import usertools
        alerts = [a for a in usertools.list_alerts(owner) if str(a.get("symbol") or "").upper() == s]
        journal = [j for j in usertools.list_journal(owner).get("entries", []) if str(j.get("symbol") or "").upper() == s]
        notes = usertools.list_notes(s, 20)
        return {"alerts": [{"kind": a.get("label"), "value": a.get("value"), "active": bool(a.get("active"))} for a in alerts],
                "journal": [{"date": j.get("date"), "side": j.get("side"), "status": j.get("status"), "return_pct": j.get("return_pct")} for j in journal[:5]],
                "journal_count": len(journal), "notes": [{"author": n.get("author"), "text": (n.get("text") or "")[:160], "at": n.get("created_at")} for n in notes[:3]],
                "notes_count": len(notes)}

    def pe():
        from api.pe import deals
        return {"deals": [{"id": d["id"], "name": d["name"], "stage": d["stage"], "irr": (d.get("summary") or {}).get("irr")}
                          for d in deals.list_deals() if str(d.get("symbol") or "").upper() == s]}

    sig, mod, bk, fu, val, yo, pe_ = await asyncio.gather(
        _part(signal_regime, 20), _part(model_regime, 20), _thread(book, 8), _thread(futu, 15), _thread(valuation, 25),
        _thread(yours, 8), _thread(pe, 8))
    if isinstance(bk, dict) and "unavailable" not in bk:
        bk["futu"] = fu if isinstance(fu, list) else []
        if not isinstance(fu, list):
            bk["futu_unavailable"] = True
    macro = {"sector": sector, "industry": info.get("industry"), "sector_etf": etf, "country": country,
             "signal": {**(sig if isinstance(sig, dict) else {}), **_stance((sig or {}).get("regime") if isinstance(sig, dict) else None, etf)},
             "model": {**(mod if isinstance(mod, dict) else {}), **_stance((mod or {}).get("regime") if isinstance(mod, dict) else None, etf)}}
    return {"symbol": s, "name": info.get("longName") or info.get("shortName"), "quote_type": info.get("quoteType"),
            "book": bk, "macro": macro, "valuation": val, "yours": yo, "pe": pe_,
            "earnings_date": info.get("earningsTimestamp")}
