"""
LBO model — an annual leveraged-buyout model in the form deal teams use:

  sources & uses → operating model (revenue, EBITDA, D&A, capex, working capital) → debt schedule (term loans with
  mandatory amortisation and a cash sweep, bullet notes, PIK mezzanine, a revolver that funds shortfalls) → tax
  (interest deductibility cap with carry-forward, loss carry-forward) → exit (multiple × EBITDA, exit fees,
  management incentive plan) → sponsor IRR and money multiple, the value-creation bridge, credit statistics and
  covenant tests.

Conventions: amounts in the reporting currency; year 0 is the closing balance sheet (LTM figures); interest on the
average balance of each year (solved by iteration — the circularity a spreadsheet model handles with "iterative
calculation"), or on opening balances (`interest_on="opening"`). Everything here is pure computation: callers pass a
complete input dict (api/pe/market.py builds one from a company's filings and live credit markets).
Modelled returns are analysis, never a track record.
"""
from __future__ import annotations

import copy
import math
from typing import Any, Dict, List, Optional

MAX_YEARS = 10
TRANCHE_KINDS = ("tla", "tlb", "notes", "mezz")
CASES = ("base", "upside", "downside")


class LboError(ValueError):
    """Inputs the model cannot run (missing EBITDA, a negative purchase price, …)."""


# ── Defaults ──────────────────────────────────────────────────────────────────────────────────────────────────────
def default_inputs() -> Dict[str, Any]:
    """A complete, illustrative input set (a 100 EBITDA business bought at 10×). Every field is documented here."""
    return {
        "name": "Illustrative target", "currency": "USD", "symbol": None,
        # Company at close (LTM)
        "revenue": 500.0,             # LTM revenue
        "ebitda": 100.0,              # LTM EBITDA (pre-IFRS 16 / US GAAP: after operating-lease cost)
        "cash": 0.0,                  # existing cash (used in the purchase, net of the minimum cash funded)
        "debt": 0.0,                  # existing debt (refinanced at close)
        # Entry
        "entry_multiple": 10.0,       # EV / LTM EBITDA
        "transaction_fee_pct": 0.02,  # advisory, legal, diligence — % of EV (expensed, funded at close)
        "financing_fee_pct": 0.025,   # arrangement fees — % of debt raised (amortised over each tranche's tenor)
        "min_cash": 10.0,             # cash kept on the balance sheet (funded at close)
        "rollover_equity": 0.0,       # management / seller equity rolled into the deal (same terms as the sponsor's)
        # Financing: tranches in seniority order (amount = multiple × LTM EBITDA unless "amount" is given)
        "base_rate": 0.04,            # current SOFR / SONIA / €STR
        "base_rate_path": None,       # optional list per year (else flat at base_rate)
        "tranches": [
            {"name": "Term Loan B", "kind": "tlb", "multiple": 4.0, "floating": True, "spread": 0.0325, "floor": 0.0,
             "amort_pct": 0.01, "tenor": 7, "sweep": True},
            {"name": "Senior notes", "kind": "notes", "multiple": 1.5, "floating": False, "coupon": 0.0775, "amort_pct": 0.0,
             "tenor": 8, "sweep": False},
        ],
        "revolver": {"commitment": 50.0, "spread": 0.03, "commitment_fee": 0.00375, "drawn_at_close": 0.0},
        "sweep_pct": 1.0,             # share of excess cash that prepays sweepable debt
        "interest_on": "average",     # "average" (iterated) or "opening" balances
        # Operating plan (scalars apply to every year; lists give year 1, 2, …)
        "years": 7,
        "revenue_growth": [0.06, 0.06, 0.05, 0.05, 0.04, 0.04, 0.04],
        "ebitda_margin": [0.205, 0.21, 0.215, 0.22, 0.22, 0.22, 0.22],
        "dna_pct": 0.03,              # D&A % revenue
        "capex_pct": 0.035,           # capex % revenue
        "nwc_pct": 0.10,              # net working capital % of the change in revenue
        "tax_rate": 0.25,
        "interest_cap_pct": 0.30,     # interest deductible up to this share of EBITDA (US §163(j) / UK CIR); None = no cap
        # Cases: shifts applied to the base plan
        "cases": {"upside": {"growth": 0.02, "margin": 0.01, "exit_multiple": 0.5},
                  "downside": {"growth": -0.04, "margin": -0.025, "exit_multiple": -1.0}},
        "case_weights": {"base": 0.5, "upside": 0.25, "downside": 0.25},
        # Exit
        "exit_year": 5,
        "exit_multiple": None,        # None = the entry multiple
        "exit_fee_pct": 0.01,         # % of exit EV
        "mip_pct": 0.10,              # management incentive plan: share of the equity gain
        # Returns and covenants
        "hurdle_irr": 0.20,
        "covenants": {"max_net_leverage": None, "step_down": 0.25, "min_interest_cover": 2.0},
    }


# ── Helpers ───────────────────────────────────────────────────────────────────────────────────────────────────────
def _path(v: Any, n: int, name: str) -> List[float]:
    """A scalar → n equal values; a list → padded with its last value / cut to n."""
    if v is None:
        raise LboError(f"{name} is required.")
    if isinstance(v, (int, float)):
        return [float(v)] * n
    xs = [float(x) for x in v if x is not None]
    if not xs:
        raise LboError(f"{name} is empty.")
    return (xs + [xs[-1]] * n)[:n]


def irr(flows: List[float], lo: float = -0.9999, hi: float = 1e4) -> Optional[float]:
    """Internal rate of return of annual cash flows (year 0 first), by bisection; None without a sign change."""
    def npv(r):
        return sum(cf / (1 + r) ** t for t, cf in enumerate(flows))
    if not flows or npv(lo) * npv(hi) > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        if npv(lo) * npv(mid) <= 0:
            hi = mid
        else:
            lo = mid
        if hi - lo < 1e-10:
            break
    return (lo + hi) / 2


# ── The model ─────────────────────────────────────────────────────────────────────────────────────────────────────
def run(inp: Dict[str, Any], case: str = "base") -> Dict[str, Any]:
    """Run one case. Returns sources & uses, the yearly schedules, credit statistics, covenant tests, the exit and
    the sponsor's returns with the value-creation bridge."""
    p = copy.deepcopy(inp)
    ebitda0, rev0 = float(p.get("ebitda") or 0), float(p.get("revenue") or 0)
    if ebitda0 <= 0:
        raise LboError("An LBO needs positive EBITDA (LTM).")
    if rev0 <= 0:
        raise LboError("Revenue (LTM) is required.")
    n = max(1, min(MAX_YEARS, int(p.get("years") or 7)))
    H = max(1, min(n, int(p.get("exit_year") or 5)))
    shift = (p.get("cases") or {}).get(case, {}) if case != "base" else {}
    g = [x + shift.get("growth", 0.0) for x in _path(p.get("revenue_growth"), n, "Revenue growth")]
    m = [min(0.95, x + shift.get("margin", 0.0)) for x in _path(p.get("ebitda_margin", ebitda0 / rev0), n, "EBITDA margin")]
    dna_p, capex_p, nwc_p = (_path(p.get(k), n, k) for k in ("dna_pct", "capex_pct", "nwc_pct"))
    base_path = _path(p["base_rate_path"], n, "Base rate path") if p.get("base_rate_path") else [float(p.get("base_rate") or 0)] * n
    tax_rate = float(p.get("tax_rate") or 0)
    cap = p.get("interest_cap_pct")

    # Sources & uses at close
    entry_mult = float(p["entry_multiple"])
    ev = entry_mult * ebitda0
    if ev <= 0:
        raise LboError("The entry multiple must be positive.")
    tranches = []
    for t in p.get("tranches") or []:
        amt = float(t["amount"]) if t.get("amount") is not None else float(t.get("multiple") or 0) * ebitda0
        if amt > 0:
            tranches.append({**t, "amount": amt})
    debt_raised = sum(t["amount"] for t in tranches)
    rv = p.get("revolver") or {}
    rv_close = float(rv.get("drawn_at_close") or 0)
    fin_fees = float(p.get("financing_fee_pct") or 0) * debt_raised
    txn_fees = float(p.get("transaction_fee_pct") or 0) * ev
    min_cash = float(p.get("min_cash") or 0)
    rollover = float(p.get("rollover_equity") or 0)
    existing_net_debt = float(p.get("debt") or 0) - float(p.get("cash") or 0)
    uses = {"equity_purchase": ev - existing_net_debt, "refinance_net_debt": existing_net_debt, "transaction_fees": txn_fees,
            "financing_fees": fin_fees, "cash_to_balance_sheet": min_cash}
    total_uses = sum(uses.values())
    sponsor_equity = total_uses - debt_raised - rv_close - rollover
    if sponsor_equity <= 0:
        raise LboError("The debt exceeds the purchase price and fees — no equity cheque; lower the leverage.")
    total_equity = sponsor_equity + rollover
    sources = {**{t["name"]: t["amount"] for t in tranches}, **({"Revolver (drawn)": rv_close} if rv_close else {}),
               "Rollover equity": rollover, "Sponsor equity": sponsor_equity}

    # Year loop with average-balance interest solved by iteration
    def simulate(interest_guess: Optional[List[float]]):
        bal = {t["name"]: t["amount"] for t in tranches}
        fee_left = {t["name"]: float(p.get("financing_fee_pct") or 0) * t["amount"] for t in tranches}
        rv_bal, cash, rev = rv_close, min_cash, rev0
        nol, dis_cf = 0.0, 0.0                      # loss and disallowed-interest carry-forwards
        rows, interest_used = [], []
        for y in range(1, n + 1):
            r_prev, rev = rev, rev * (1 + g[y - 1])
            ebitda = rev * m[y - 1]
            dna, capex = rev * dna_p[y - 1], rev * capex_p[y - 1]
            d_nwc = nwc_p[y - 1] * (rev - r_prev)
            ebit = ebitda - dna
            base = base_path[y - 1]
            open_bal, open_rv = dict(bal), rv_bal
            # interest on opening balances, or on the previous iteration's average
            guess = interest_guess[y - 1] if interest_guess else None
            tr_int, cash_int, pik_int = {}, 0.0, 0.0
            for t in tranches:
                rate = (max(base, float(t.get("floor") or 0)) + float(t.get("spread") or 0)) if t.get("floating") else float(t.get("coupon") or 0)
                avg = guess["avg"][t["name"]] if guess else open_bal[t["name"]]
                it = rate * avg
                tr_int[t["name"]] = {"rate": rate, "interest": it}
                if t.get("kind") == "mezz" and t.get("pik", True):
                    pik_int += it
                else:
                    cash_int += it
            rv_rate = base + float(rv.get("spread") or 0)
            rv_avg = guess["rv_avg"] if guess else open_rv
            rv_int = rv_rate * rv_avg + float(rv.get("commitment_fee") or 0) * max(0.0, float(rv.get("commitment") or 0) - rv_avg)
            cash_int += rv_int
            # financing-fee amortisation (non-cash, deductible)
            amort_fees = 0.0
            for t in tranches:
                tenor = max(1, int(t.get("tenor") or 7))
                a = min(fee_left[t["name"]], float(p.get("financing_fee_pct") or 0) * t["amount"] / tenor)
                fee_left[t["name"]] -= a
                amort_fees += a
            # tax: interest deductible up to the cap, the rest carried forward
            interest_total = cash_int + pik_int
            limit = cap * ebitda if cap is not None else float("inf")
            deductible = min(interest_total + dis_cf, max(0.0, limit))
            dis_cf = interest_total + dis_cf - deductible
            pretax = ebit - deductible - amort_fees
            use_nol = min(nol, max(0.0, pretax))
            taxable = pretax - use_nol
            nol = nol - use_nol + (-pretax if pretax < 0 else 0.0)
            tax = max(0.0, taxable) * tax_rate
            net_income = ebit - interest_total - amort_fees - tax
            # cash flow and debt service
            fcf = ebitda - cash_int - tax - capex - d_nwc                  # levered FCF before debt repayment
            mand = {}
            for t in tranches:
                if t.get("kind") == "mezz":
                    mand[t["name"]] = 0.0
                    continue
                due = float(t.get("amort_pct") or 0) * t["amount"]
                if y >= int(t.get("tenor") or 99):
                    due = bal[t["name"]]                               # maturity: the rest falls due
                mand[t["name"]] = min(bal[t["name"]], due)
            for t in tranches:
                if t.get("kind") == "mezz" and t.get("pik", True):
                    bal[t["name"]] += tr_int[t["name"]]["interest"]       # PIK accrues to principal
            cash_avail = cash + fcf - sum(mand.values()) - min_cash
            for k, v in mand.items():
                bal[k] -= v
            rv_draw = rv_repay = 0.0
            if cash_avail < 0:                                           # shortfall: the revolver funds it
                rv_draw = min(-cash_avail, max(0.0, float(rv.get("commitment") or 0) - rv_bal))
                rv_bal += rv_draw
                cash_avail += rv_draw
            else:
                rv_repay = min(rv_bal, cash_avail)
                rv_bal -= rv_repay
                cash_avail -= rv_repay
            sweep = {}
            if cash_avail > 0:
                pool = cash_avail * float(p.get("sweep_pct") if p.get("sweep_pct") is not None else 1.0)
                for t in tranches:
                    if t.get("sweep") and pool > 0:
                        s = min(bal[t["name"]], pool)
                        bal[t["name"]] -= s
                        pool -= s
                        sweep[t["name"]] = s
                cash_avail -= sum(sweep.values())
            shortfall = min(0.0, cash_avail)                              # beyond the revolver: a liquidity gap
            cash = min_cash + cash_avail
            debt = sum(bal.values()) + rv_bal
            senior = sum(bal[t["name"]] for t in tranches if t.get("kind") in ("tla", "tlb")) + rv_bal
            interest_used.append({"avg": {k: (open_bal[k] + bal[k]) / 2 for k in bal}, "rv_avg": (open_rv + rv_bal) / 2})
            rows.append({
                "year": y, "revenue": rev, "growth": g[y - 1], "ebitda": ebitda, "margin": m[y - 1], "dna": dna, "ebit": ebit,
                "capex": capex, "change_nwc": d_nwc, "cash_interest": cash_int, "pik_interest": pik_int, "fee_amortisation": amort_fees,
                "interest_deductible": deductible, "interest_disallowed_cf": dis_cf, "tax": tax, "net_income": net_income,
                "fcf": fcf, "mandatory": sum(mand.values()), "sweep": sum(sweep.values()), "revolver_draw": rv_draw,
                "revolver_repay": rv_repay, "revolver": rv_bal, "liquidity_gap": shortfall, "cash": cash,
                "balances": dict(bal), "rates": {k: v["rate"] for k, v in tr_int.items()}, "base_rate": base,
                "debt": debt, "senior_debt": senior, "net_debt": debt - cash,
                "leverage": debt / ebitda if ebitda > 0 else None, "senior_leverage": senior / ebitda if ebitda > 0 else None,
                "net_leverage": (debt - cash) / ebitda if ebitda > 0 else None,
                "interest_cover": ebitda / cash_int if cash_int > 0 else None,
                "fccr": (ebitda - capex) / (cash_int + sum(mand.values())) if (cash_int + sum(mand.values())) > 0 else None,
                "fcf_to_debt": fcf / debt if debt > 0 else None,
            })
        return rows, interest_used

    rows, used = simulate(None)
    if str(p.get("interest_on") or "average") == "average":
        for _ in range(30):                                            # converges in a handful of passes
            prev = [r["cash_interest"] + r["pik_interest"] for r in rows]
            rows, used = simulate(used)
            if max(abs(a - (r["cash_interest"] + r["pik_interest"])) for a, r in zip(prev, rows)) < 1e-9 * max(1.0, ebitda0):
                break

    # Exit and returns
    exit_mult = float(p["exit_multiple"]) if p.get("exit_multiple") is not None else entry_mult
    exit_mult += shift.get("exit_multiple", 0.0)
    ex = rows[H - 1]
    exit_ev = exit_mult * ex["ebitda"]
    exit_fees = float(p.get("exit_fee_pct") or 0) * exit_ev
    equity_gross = exit_ev - ex["net_debt"] - exit_fees
    gain = equity_gross - total_equity
    mip = float(p.get("mip_pct") or 0) * max(0.0, gain)
    equity_net = equity_gross - mip
    sponsor_share = sponsor_equity / total_equity
    sponsor_proceeds = equity_net * sponsor_share
    flows = [-sponsor_equity] + [0.0] * (H - 1) + [sponsor_proceeds]
    sponsor_irr = irr(flows) if sponsor_proceeds > 0 else -1.0
    moic = sponsor_proceeds / sponsor_equity

    # Value-creation bridge of the total equity (sums exactly to the gain net of MIP)
    net_debt_close = debt_raised + rv_close - min_cash
    bridge = {"ebitda_growth": (ex["ebitda"] - ebitda0) * entry_mult, "multiple": (exit_mult - entry_mult) * ex["ebitda"],
              "deleveraging": net_debt_close - ex["net_debt"], "fees_and_costs": -(txn_fees + fin_fees + exit_fees), "mip": -mip}
    bridge["total"] = sum(bridge.values())

    # Covenants: net leverage step-downs from a headroom over closing leverage, and minimum interest cover
    cov = p.get("covenants") or {}
    close_lev = net_debt_close / ebitda0
    start = cov.get("max_net_leverage") or round(close_lev + 1.0, 2)
    tests = []
    for r in rows:
        lim = max(close_lev * 0.5, start - float(cov.get("step_down") or 0) * (r["year"] - 1))
        icr_min = float(cov.get("min_interest_cover") or 0)
        lev_ok = r["net_leverage"] is not None and r["net_leverage"] <= lim
        icr_ok = r["interest_cover"] is None or r["interest_cover"] >= icr_min
        tests.append({"year": r["year"], "max_net_leverage": lim, "net_leverage": r["net_leverage"], "leverage_ok": lev_ok,
                      "leverage_headroom": (1 - r["ebitda"] * lim / r["net_debt"]) if r["net_debt"] > 0 and lim > 0 else None,
                      "min_interest_cover": icr_min, "interest_cover": r["interest_cover"], "cover_ok": icr_ok,
                      "liquidity_ok": r["liquidity_gap"] >= -1e-9})

    return {
        "case": case, "currency": p.get("currency"), "years": n, "exit_year": H,
        "entry": {"ev": ev, "multiple": entry_mult, "ebitda": ebitda0, "revenue": rev0, "net_debt_close": net_debt_close,
                  "leverage_close": (debt_raised + rv_close) / ebitda0, "net_leverage_close": close_lev,
                  "equity_pct": total_equity / total_uses},
        "sources": sources, "uses": uses, "total_uses": total_uses, "debt_raised": debt_raised,
        "sponsor_equity": sponsor_equity, "rollover_equity": rollover,
        "tranches": [{"name": t["name"], "kind": t.get("kind"), "amount": t["amount"], "multiple": t["amount"] / ebitda0,
                      "floating": bool(t.get("floating")), "spread": t.get("spread"), "coupon": t.get("coupon"),
                      "amort_pct": t.get("amort_pct"), "tenor": t.get("tenor"), "sweep": bool(t.get("sweep")),
                      "pik": bool(t.get("kind") == "mezz" and t.get("pik", True))} for t in tranches],
        "schedule": rows,
        "exit": {"year": H, "multiple": exit_mult, "ebitda": ex["ebitda"], "ev": exit_ev, "net_debt": ex["net_debt"],
                 "fees": exit_fees, "equity_gross": equity_gross, "mip": mip, "equity_net": equity_net},
        "returns": {"sponsor_irr": sponsor_irr, "moic": moic, "sponsor_proceeds": sponsor_proceeds, "flows": flows,
                    "hurdle_irr": p.get("hurdle_irr"), "clears_hurdle": sponsor_irr is not None and p.get("hurdle_irr") is not None
                    and sponsor_irr >= float(p["hurdle_irr"])},
        "bridge": bridge, "covenants": tests,
        "warnings": _warnings(rows, tests, close_lev, H),
    }


def _warnings(rows, tests, close_lev, H) -> List[str]:
    w = []
    if close_lev > 7.0:
        w.append(f"Closing net leverage {close_lev:.1f}× EBITDA is above what lenders typically underwrite (≈4–7×).")
    gap = [r["year"] for r in rows if r["liquidity_gap"] < -1e-6]
    if gap:
        w.append(f"Cash runs out beyond the revolver in year {gap[0]} — the plan does not fund itself.")
    br = [t["year"] for t in tests[:H] if not (t["leverage_ok"] and t["cover_ok"])]
    if br:
        w.append(f"Covenant breach in year {br[0]} (before the exit).")
    return w


# ── Analysis ──────────────────────────────────────────────────────────────────────────────────────────────────────
def cases(inp: Dict[str, Any]) -> Dict[str, Any]:
    """Base, upside and downside, and the probability-weighted IRR / multiple."""
    out = {c: run(inp, c) for c in CASES}
    w = inp.get("case_weights") or {"base": 0.5, "upside": 0.25, "downside": 0.25}
    tw = sum(w.get(c, 0) for c in CASES) or 1.0
    irr_w = sum(w.get(c, 0) * (out[c]["returns"]["sponsor_irr"] or -1.0) for c in CASES) / tw
    moic_w = sum(w.get(c, 0) * out[c]["returns"]["moic"] for c in CASES) / tw
    return {"cases": out, "weighted": {"irr": irr_w, "moic": moic_w, "weights": w}}


def _with(inp: Dict[str, Any], **kw) -> Dict[str, Any]:
    q = copy.deepcopy(inp)
    q.update(kw)
    return q


def _scale_leverage(inp: Dict[str, Any], total_multiple: float) -> Dict[str, Any]:
    """The same tranche mix scaled to a total debt / EBITDA."""
    q = copy.deepcopy(inp)
    cur = sum(float(t.get("multiple") or 0) for t in q["tranches"] if t.get("amount") is None)
    if cur <= 0:
        return q
    for t in q["tranches"]:
        if t.get("amount") is None:
            t["multiple"] = float(t.get("multiple") or 0) * total_multiple / cur
    return q


def sensitivity(inp: Dict[str, Any]) -> Dict[str, Any]:
    """Sponsor IRR grids: entry × exit multiple, leverage × revenue growth, exit year × exit multiple."""
    e0 = float(inp["entry_multiple"])
    x0 = float(inp["exit_multiple"]) if inp.get("exit_multiple") is not None else e0
    lev0 = sum(float(t.get("multiple") or 0) for t in inp["tranches"] if t.get("amount") is None)
    entry_axis = [round(e0 + d, 2) for d in (-2, -1, 0, 1, 2)]
    exit_axis = [round(x0 + d, 2) for d in (-2, -1, 0, 1, 2)]
    lev_axis = [round(lev0 + d, 2) for d in (-1.5, -0.75, 0, 0.75, 1.5) if lev0 + d > 0]
    growth_shift = [-0.04, -0.02, 0.0, 0.02, 0.04]
    years = [y for y in (3, 4, 5, 6, 7) if y <= int(inp.get("years") or 7)]

    def irr_of(q):
        try:
            return run(q)["returns"]["sponsor_irr"]
        except LboError:
            return None
    grid1 = [[irr_of(_with(inp, entry_multiple=e, exit_multiple=x)) for x in exit_axis] for e in entry_axis]
    grid2 = []
    for lv in lev_axis:
        row = []
        for gs in growth_shift:
            q = _scale_leverage(inp, lv)
            n = int(q.get("years") or 7)
            q["revenue_growth"] = [x + gs for x in _path(q["revenue_growth"], n, "growth")]
            row.append(irr_of(q))
        grid2.append(row)
    grid3 = [[irr_of(_with(inp, exit_year=y, exit_multiple=x)) for x in exit_axis] for y in years]
    return {"entry_exit": {"rows": entry_axis, "cols": exit_axis, "irr": grid1, "row_label": "Entry EV/EBITDA", "col_label": "Exit EV/EBITDA"},
            "leverage_growth": {"rows": lev_axis, "cols": growth_shift, "irr": grid2, "row_label": "Total debt / EBITDA", "col_label": "Revenue growth vs plan"},
            "year_exit": {"rows": years, "cols": exit_axis, "irr": grid3, "row_label": "Exit year", "col_label": "Exit EV/EBITDA"}}


def max_entry(inp: Dict[str, Any], hurdle: Optional[float] = None) -> Dict[str, Any]:
    """The highest entry multiple (and EV) at which the base case still earns the hurdle IRR, with the financing held
    at the same turns of EBITDA."""
    h = float(hurdle if hurdle is not None else inp.get("hurdle_irr") or 0.20)
    x_fixed = inp.get("exit_multiple") if inp.get("exit_multiple") is not None else float(inp["entry_multiple"])

    def f(mult):
        try:
            r = run(_with(inp, entry_multiple=mult, exit_multiple=x_fixed))["returns"]["sponsor_irr"]
            return r if r is not None else -1.0
        except LboError:
            return None
    # The lowest price the financing allows (below it the debt exceeds the price: no equity cheque, no IRR)
    a, b = 0.0, max(1.0, float(inp["entry_multiple"]))
    while f(b) is None and b < 200:
        b *= 2
    if f(b) is None:
        return {"hurdle": h, "multiple": None, "ev": None, "note": "The financing does not fit at any price."}
    for _ in range(60):
        mid = (a + b) / 2
        if f(mid) is None:
            a = mid
        else:
            b = mid
    lo = b + 0.05                                  # just above the boundary (a near-zero cheque: a huge IRR)
    if (f(lo) or -1.0) < h:
        return {"hurdle": h, "multiple": None, "ev": None,
                "note": f"The hurdle is not reachable at any price the financing allows (≥ {lo:.1f}× EBITDA)."}
    hi = max(lo * 1.5, float(inp["entry_multiple"]) * 1.5)
    while (f(hi) or -1.0) >= h and hi < 200:
        hi *= 2
    for _ in range(80):
        mid = (lo + hi) / 2
        v = f(mid)
        if v is not None and v >= h:
            lo = mid
        else:
            hi = mid
    out = {"hurdle": h, "multiple": lo, "ev": lo * float(inp["ebitda"]), "exit_multiple": x_fixed}
    if inp.get("shares") and inp.get("price"):
        eq = lo * float(inp["ebitda"]) - (float(inp.get("debt") or 0) - float(inp.get("cash") or 0))
        out["price_per_share"] = eq / float(inp["shares"])
        out["premium_to_price"] = out["price_per_share"] / float(inp["price"]) - 1
    return out


def ebitda_cushion(inp: Dict[str, Any]) -> Dict[str, Any]:
    """How far EBITDA can fall (a permanent cut from year 1 on, vs the base plan) before the first covenant breach
    and before cash runs out — the lender's view of the deal."""
    def at(cut):
        q = copy.deepcopy(inp)
        n = int(q.get("years") or 7)
        q["ebitda_margin"] = [x * (1 - cut) for x in _path(q.get("ebitda_margin"), n, "margin")]
        return run(q)

    def search(fails):
        lo, hi = 0.0, 0.95
        if fails(at(lo)):
            return 0.0
        if not fails(at(hi)):
            return None
        for _ in range(40):
            mid = (lo + hi) / 2
            if fails(at(mid)):
                hi = mid
            else:
                lo = mid
        return lo
    H = int(inp.get("exit_year") or 5)
    cov = search(lambda r: any(not (t["leverage_ok"] and t["cover_ok"]) for t in r["covenants"][:H]))
    liq = search(lambda r: any(x["liquidity_gap"] < -1e-6 for x in r["schedule"][:H]))
    return {"to_covenant_breach": cov, "to_liquidity_gap": liq}


def analyse(inp: Dict[str, Any]) -> Dict[str, Any]:
    """Everything the workbench shows: the three cases, sensitivities, the maximum price at the hurdle, the EBITDA
    cushion."""
    c = cases(inp)
    return {**c, "sensitivity": sensitivity(inp), "max_entry": max_entry(inp), "cushion": ebitda_cushion(inp),
            "inputs": inp}
