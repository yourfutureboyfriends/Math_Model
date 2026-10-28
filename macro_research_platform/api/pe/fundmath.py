"""
Private-fund mathematics on dated cash flows (contributions negative, distributions positive, the latest NAV as the
residual value):

  performance   XIRR, TVPI / DPI / RVPI, paid-in capital, and the public-market equivalents —
                Kaplan-Schoar PME (KS-PME > 1 = beat the index), Direct Alpha (Gredil, Griffiths & Stucke 2014: the
                annual excess return over the index) and the Long-Nickels PME IRR (the index's IRR on the same flows)
  waterfall     the distribution waterfall between LPs and the GP — return of capital, preferred return (compounded
                on the dated contributions), GP catch-up, then the carried-interest split. European (whole fund) by
                default; American (deal-by-deal) on a list of deals.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional


def _d(x) -> date:
    return x if isinstance(x, date) else date.fromisoformat(str(x)[:10])


def xirr(flows: List[Dict[str, Any]]) -> Optional[float]:
    """Annualised IRR of dated cash flows [{date, amount}] (actual/365), by bisection."""
    fl = sorted(((_d(f["date"]), float(f["amount"])) for f in flows if f.get("amount")), key=lambda x: x[0])
    if not fl or min(a for _, a in fl) >= 0 or max(a for _, a in fl) <= 0:
        return None
    t0 = fl[0][0]

    def npv(r):
        return sum(a / (1 + r) ** ((d - t0).days / 365.0) for d, a in fl)
    lo, hi = -0.9999, 1e4
    if npv(lo) * npv(hi) > 0:
        return None
    for _ in range(300):
        mid = (lo + hi) / 2
        if npv(lo) * npv(mid) <= 0:
            hi = mid
        else:
            lo = mid
        if hi - lo < 1e-11:
            break
    return (lo + hi) / 2


def performance(flows: List[Dict[str, Any]], nav: float = 0.0, nav_date: Optional[str] = None,
                index: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
    """Fund performance from dated flows (negative = called capital, positive = distributions) and the current NAV.
    `index` ({date: level}) adds the public-market equivalents."""
    fl = sorted(({"date": _d(f["date"]), "amount": float(f["amount"])} for f in flows), key=lambda f: f["date"])
    if not fl:
        raise ValueError("No cash flows.")
    end = _d(nav_date) if nav_date else max(f["date"] for f in fl)
    paid_in = -sum(f["amount"] for f in fl if f["amount"] < 0)
    dist = sum(f["amount"] for f in fl if f["amount"] > 0)
    if paid_in <= 0:
        raise ValueError("No capital has been called (no negative flows).")
    all_flows = fl + ([{"date": end, "amount": float(nav)}] if nav else [])
    out = {"paid_in": paid_in, "distributed": dist, "nav": float(nav), "as_of": end.isoformat(),
           "dpi": dist / paid_in, "rvpi": float(nav) / paid_in, "tvpi": (dist + float(nav)) / paid_in,
           "irr": xirr([{"date": f["date"], "amount": f["amount"]} for f in all_flows]),
           "first": fl[0]["date"].isoformat(), "years": (end - fl[0]["date"]).days / 365.0}
    if index:
        out["pme"] = pme(fl, float(nav), end, index)
    return out


def _level(index: Dict[str, float], d: date) -> Optional[float]:
    """The index level on or before a date."""
    keys = [k for k in index if _d(k) <= d]
    return float(index[max(keys, key=_d)]) if keys else None


def pme(fl: List[Dict[str, Any]], nav: float, end: date, index: Dict[str, float]) -> Dict[str, Any]:
    """KS-PME, Direct Alpha and the Long-Nickels PME IRR against an index ({date: level})."""
    I_end = _level(index, end)
    if not I_end:
        return {"error": "The index has no level at the valuation date."}
    fv_contrib = fv_dist = 0.0
    scaled = []
    for f in fl:
        I_t = _level(index, f["date"])
        if not I_t:
            return {"error": f"The index has no level on {f['date'].isoformat()}."}
        grow = I_end / I_t
        if f["amount"] < 0:
            fv_contrib += -f["amount"] * grow
        else:
            fv_dist += f["amount"] * grow
        scaled.append({"date": f["date"], "amount": f["amount"] * grow})
    ks = (fv_dist + nav) / fv_contrib if fv_contrib else None
    # Direct Alpha: the IRR of the flows compounded to the end date at the index return, as a continuous rate → annual
    da_irr = xirr(scaled + [{"date": end, "amount": nav}]) if nav or any(s["amount"] > 0 for s in scaled) else None
    direct_alpha = da_irr                                   # annual (discrete); the continuous form is ln(1 + α)
    # Long-Nickels: invest each contribution in the index, take the same distributions out; the index's IRR
    bal, last = 0.0, None
    for f in fl:
        I_t = _level(index, f["date"])
        if last is not None:
            bal *= I_t / last
        bal += -f["amount"]
        last = I_t
    ln_nav = bal * (I_end / last) if last else 0.0
    ln_irr = xirr([{"date": f["date"], "amount": f["amount"]} for f in fl] + [{"date": end, "amount": ln_nav}])
    out = {"ks_pme": ks, "direct_alpha": direct_alpha, "ln_pme_irr": ln_irr, "index_return": I_end / _level(index, fl[0]["date"]) - 1}
    if ln_nav < 0:
        out["ln_pme_note"] = ("Long-Nickels PME is not defined here: the fund distributed more than the index position was worth, "
                              "so the replicating portfolio goes negative (use KS-PME and Direct Alpha).")
    return out


def waterfall(contributions: List[Dict[str, Any]], distributions: List[Dict[str, Any]], pref: float = 0.08,
              carry: float = 0.20, catch_up: float = 1.0, compounding: bool = True) -> Dict[str, Any]:
    """European (whole-fund) waterfall. Each distribution is split in order: (1) LPs get their contributed capital
    back, (2) the preferred return on it (compounded annually from each contribution's date until it is repaid),
    (3) the GP catches up — `catch_up` of each unit goes to the GP until it has `carry` of the profit so far —
    (4) the rest splits (1 − carry) / carry. Returns the split of every distribution and the totals."""
    events = sorted([(_d(c["date"]), "c", float(abs(c["amount"]))) for c in contributions] +
                    [(_d(x["date"]), "d", float(x["amount"])) for x in distributions], key=lambda e: (e[0], e[1] != "c"))
    capital_out, pref_accrued, last = 0.0, 0.0, None
    lp_profit = gp_profit = 0.0
    totals = {"return_of_capital": 0.0, "preferred": 0.0, "catch_up": 0.0, "split_lp": 0.0, "split_gp": 0.0}
    rows = []
    for d, kind, amt in events:
        if last is not None and capital_out + pref_accrued > 0:
            yrs = (d - last).days / 365.0
            base = capital_out + (pref_accrued if compounding else 0.0)
            pref_accrued += base * ((1 + pref) ** yrs - 1) if compounding else capital_out * pref * yrs
        last = d
        if kind == "c":
            capital_out += amt
            continue
        left = amt
        roc = min(left, capital_out)
        capital_out -= roc
        left -= roc
        pr = min(left, pref_accrued)
        pref_accrued -= pr
        left -= pr
        lp_profit += pr
        cu = 0.0
        if left > 0 and catch_up > 0:
            # GP catch-up: of each unit x the GP takes catch_up·x until GP = carry × all profit, i.e.
            # x = (carry·(LP + GP) − GP) / (catch_up − carry)   (a catch-up at or below the carry rate never catches up)
            need = (carry * (lp_profit + gp_profit) - gp_profit) / (catch_up - carry) if catch_up > carry else 0.0
            cu = min(left, max(0.0, need))
            gp_part = cu * catch_up
            lp_profit += cu - gp_part
            gp_profit += gp_part
            left -= cu
        s_lp, s_gp = left * (1 - carry), left * carry
        lp_profit += s_lp
        gp_profit += s_gp
        gp_cu = cu * catch_up
        totals["return_of_capital"] += roc
        totals["preferred"] += pr
        totals["catch_up"] += gp_cu
        totals["split_lp"] += s_lp + (cu - gp_cu)
        totals["split_gp"] += s_gp
        rows.append({"date": d.isoformat(), "amount": amt, "return_of_capital": roc, "preferred": pr,
                     "catch_up_gp": gp_cu, "catch_up_lp": cu - gp_cu, "split_lp": s_lp, "split_gp": s_gp,
                     "lp": roc + pr + (cu - gp_cu) + s_lp, "gp": gp_cu + s_gp})
    lp_total = sum(r["lp"] for r in rows)
    gp_total = sum(r["gp"] for r in rows)
    contributed = sum(abs(float(c["amount"])) for c in contributions)
    profit = sum(r["amount"] for r in rows) - contributed
    lp_flows = [{"date": c["date"], "amount": -abs(float(c["amount"]))} for c in contributions] + \
               [{"date": r["date"], "amount": r["lp"]} for r in rows]
    gross_flows = [{"date": c["date"], "amount": -abs(float(c["amount"]))} for c in contributions] + \
                  [{"date": r["date"], "amount": r["amount"]} for r in rows]
    return {"rows": rows, "totals": totals, "lp_total": lp_total, "gp_carry": gp_total, "contributed": contributed,
            "profit": profit, "gp_share_of_profit": gp_total / profit if profit > 0 else 0.0,
            "lp_net_irr": xirr(lp_flows), "gross_irr": xirr(gross_flows),
            "lp_net_multiple": lp_total / contributed if contributed else None,
            "unreturned_capital": capital_out, "pref_outstanding": pref_accrued,
            "terms": {"pref": pref, "carry": carry, "catch_up": catch_up, "compounding": compounding, "style": "european"}}


def index_levels(symbol: str, start: str) -> Dict[str, float]:
    """Daily closes of a public index / ETF from `start` (Yahoo Finance; total-return series such as ^SP500TR
    are preferred for a PME)."""
    import yfinance as yf
    from datetime import timedelta
    # two weeks early: a flow dated on a market holiday (or the first day) still finds the previous close
    begin = (_d(start) - timedelta(days=14)).isoformat()
    df = yf.download(symbol, start=begin, interval="1d", auto_adjust=True, progress=False, multi_level_index=False)
    if df is None or df.empty:
        raise ValueError(f"No price history for {symbol}.")
    c = df["Close"].dropna()
    return {d.strftime("%Y-%m-%d"): float(v) for d, v in c.items()}
