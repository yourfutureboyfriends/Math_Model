"""
Moriah Capital Partners — the fund's set-up from its Future Growth Strategy (internal discussion document,
21 October 2026). Applied once to a fund (idempotent: lists and plans are only seeded when empty).

What comes from the document: the stage (Phase I research and paper portfolio), the mandate (systematic global macro
and quantitative cross-asset research; liquid listed instruments with an approved list; daily-to-monthly holding;
risk-budgeted; no borrowing or short options without approval; no stated target return), the risk policy defaults
(25% single-model and 35% single-theme ex-ante risk, no leverage, 1% daily-loss pause, 5% / 8% strategy drawdown),
the model gates G0–G5, the first-year budget lines (£0–3,000) and the 90-day and 48-month plans.

What is a proposal for the team to approve: the instruments list (UCITS / London listings — a UK account cannot
normally buy US-domiciled ETFs; spot FX pairs as research series only, since holding them would need margin, which
the no-borrowing rule excludes until a venue is approved), the £25,000 paper notional (the document's smallest size
for "meaningful cost attribution"; the plan assumes £0 capital, so this is never shown as capital), and the platform
defaults for order size (20% of NAV), price band (±5%) and price age (4 days), which the document names without levels.
"""
from __future__ import annotations

from typing import Any, Dict, List

FUND_NAME = "Moriah Capital Partners"
SOURCE = "Moriah Capital Partners — Future Growth Strategy, internal discussion document, 21 Oct 2026"

MANDATE_TEXT = """MORIAH CAPITAL PARTNERS — WRITTEN MANDATE (Phase I, from the Future Growth Strategy, Oct 2026)

Thesis to investigate: can macroeconomic policy and liquidity shocks create delayed or nonlinear repricing across
liquid global markets, and can those effects be traded systematically after costs? (An unproven hypothesis until a
genuinely out-of-sample and later live record demonstrates its usefulness.)

Research domain: US monetary-policy surprises and dollar liquidity; Japan rates, funding markets and carry; China
credit conditions and commodity transmission; Europe/Asia-to-US cross-market price adjustment.

Primary approach: systematic global macro and quantitative cross-asset research with short- to medium-horizon signals.
Markets: liquid listed instruments with reliable historical and live data; an approved-instruments list is maintained.
Initial universe: highly liquid index and rates proxies, major FX pairs, broad commodities and liquid related ETFs;
cash instruments first; derivatives only after approval.
Holding periods: daily to monthly; no high-frequency or latency-dependent strategies.
Portfolio basis: risk-budgeted positions — not equal dollar weighting or discretionary position sizing.
Capacity: liquidity, spread, slippage and broker restrictions estimated before any strategy is promoted.
Financing: no borrowing or short options without separate approval, funded stress tests and suitable controls.
Performance objective: positive net-of-cost performance with acceptable drawdowns; no stated target return until
supported by evidence.
Strategy sleeves: (1) macro transmission, (2) systematic trend (the transparent baseline), (3) cross-asset relative
value. Year one: one benchmark sleeve and one original macro-transmission sleeve.
Capital allocation: no permanent allocation; risk only after research approval, paper validation, execution review
and documented portfolio fit; each live model has a maximum loss budget, an owner and a retirement criterion.
Exclusions (until justified): leverage, illiquid assets, complex derivatives, outside investor money and public
solicitation, Cayman vehicle and recurring fund-service costs.
Reporting: simulated / paper results are never described as a fund track record."""

# symbol, name, asset class, theme (economic driver), currency, tradable, note
INSTRUMENTS: List[tuple] = [
    ("CSPX.L", "iShares Core S&P 500 UCITS ETF (Acc)", "equity index", "US equity", "USD", True, ""),
    ("SWDA.L", "iShares Core MSCI World UCITS ETF (Acc)", "equity index", "global equity", "GBp", True, ""),
    ("ISF.L", "iShares Core FTSE 100 UCITS ETF (Dist)", "equity index", "UK equity", "GBp", True, ""),
    ("CSX5.L", "iShares Core EURO STOXX 50 UCITS ETF (Acc)", "equity index", "Europe equity", "EUR", True, ""),
    ("SJPA.L", "iShares Core MSCI Japan IMI UCITS ETF (Acc)", "equity index", "Japan", "GBp", True, ""),
    ("EIMI.L", "iShares Core MSCI EM IMI UCITS ETF (Acc)", "equity index", "EM / China", "USD", True, ""),
    ("IGLT.L", "iShares Core UK Gilts UCITS ETF", "rates", "UK rates", "GBP", True, ""),
    ("IGLS.L", "iShares UK Gilts 0-5yr UCITS ETF", "rates", "UK rates", "GBP", True, ""),
    ("IBTS.L", "iShares $ Treasury Bond 1-3yr UCITS ETF", "rates", "US rates", "GBP", True, ""),
    ("IDTL.L", "iShares $ Treasury Bond 20+yr UCITS ETF", "rates", "US rates", "USD", True, ""),
    ("ERNS.L", "iShares £ Ultrashort Bond UCITS ETF", "cash", "cash", "GBP", True, "cash instrument / no-trade alternative"),
    ("CMOD.L", "Invesco Bloomberg Commodity UCITS ETF", "commodities", "commodities", "USD", True, ""),
    ("SGLN.L", "iShares Physical Gold ETC", "commodities", "gold", "GBp", True, ""),
    ("BRNT.L", "WisdomTree Brent Crude Oil", "commodities", "energy", "USD", True, "ETC — check the product's structure before approval"),
    ("COPA.L", "WisdomTree Copper", "commodities", "China / industrial metals", "USD", True, "ETC — check the product's structure before approval"),
    ("GBPUSD=X", "GBP/USD spot", "fx", "US dollar liquidity", "USD", False, "research / signal series: spot FX needs margin (borrowing) — not tradable until a venue is approved"),
    ("EURUSD=X", "EUR/USD spot", "fx", "US dollar liquidity", "USD", False, "research / signal series only"),
    ("USDJPY=X", "USD/JPY spot", "fx", "Japan", "JPY", False, "research / signal series only (yen carry)"),
    ("EURGBP=X", "EUR/GBP spot", "fx", "Europe", "GBP", False, "research / signal series only"),
    ("AUDUSD=X", "AUD/USD spot", "fx", "China / commodities", "USD", False, "research / signal series only (China-commodity proxy)"),
]

BUDGET = [("Year 1 (Phase I)", "Data and infrastructure", 1000.0, "Reliable point-in-time datasets and secure compute"),
          ("Year 1 (Phase I)", "Hosting, documentation and tools", 500.0, "Versioned research repository and simple research page"),
          ("Year 1 (Phase I)", "External review and basic advice", 1000.0, "Initial agreement and scoping of relevant legal obligations"),
          ("Year 1 (Phase I)", "Contingency", 500.0, "Reserve for data gaps or operational failures")]

MILESTONES = [
    ("First 90 days", "Days 1-15", "Founders: legal identity / name clearance, founder agreement outline, roles, budget owner", "Founders", "Signed responsibility and approval matrix."),
    ("First 90 days", "Days 16-30", "Investment lead: one-page mandate, admissible instruments, research proposals", "Investment lead", "Every hypothesis has explicit success / failure tests."),
    ("First 90 days", "Days 31-45", "Engineering lead: data registry, point-in-time ingestion, repeatable testing environment", "Engineering lead", "Independent rerun produces the same result."),
    ("First 90 days", "Days 46-60", "Quant lead: baseline strategies, net-of-cost tests, initial macro-transmission prototype", "Quant lead", "Out-of-sample and look-ahead checks recorded."),
    ("First 90 days", "Days 61-75", "Risk lead: provisional limits, paper-broker adapter, incident procedure, reconciliation format", "Risk lead", "Controlled fail-safe tests and monthly report."),
    ("First 90 days", "Days 76-90", "Founders: independent review, public research wording, next-quarter funding decision", "Founders", "Meeting minutes, unresolved risks and budget signed off."),
    ("48-month gates", "0-90 days", "Founders agreement, mandate, instrument list, research repository, initial budget and assigned control owner", "Founders", "Core legal, operating and ownership questions resolved."),
    ("48-month gates", "Months 3-6", "First reproducible event dataset, documented benchmark, walk-forward testing and public research note", "Head of research", "Time integrity, cost assumptions and baseline comparison pass."),
    ("48-month gates", "Months 6-12", "Forward-tracked paper portfolio, model governance and risk dashboard", "Risk & controls", "No critical data leakage or unreconciled simulated orders."),
    ("48-month gates", "Months 12-24", "If capital and law permit, limited proprietary live account and broker-reconciled performance", "Managing partner", "Execution controls work and losses remain within limits."),
    ("48-month gates", "Months 24-36", "A complete diligence file, service provider quotes, investor eligibility and fee economics", "Managing partner", "Independent review finds commercial and regulatory viability."),
    ("48-month gates", "Months 36-48", "Conditional fund launch with outside service providers, documented commitments and adequate runway", "Managing partner", "All permissions, investor documentation and finances in place."),
]


def setup(fund_id: str = "main", user: str = "admin", paper_notional: float = 25_000.0) -> Dict[str, Any]:
    """Configure a fund as Moriah Capital Partners (Phase I). Settings are (re)applied; lists seed only when empty."""
    from api import fund_store, funds, governance as gov
    from api.portfolio_store import _conn
    tok = funds.CURRENT.set(fund_id)
    try:
        f = funds.get(fund_id)
        if not f:
            raise LookupError(f"fund {fund_id} not found")
        funds.update(fund_id, name=FUND_NAME)
        before = fund_store.get_settings()
        from api.handlers.pretrade_feasibility import DEFAULT_MANDATE
        fund_store.update_settings({
            "fund_name": FUND_NAME, "base_currency": "GBP", "benchmark": "CASH_GBP", "capital": float(paper_notional),
            "capital_basis": (f"Paper notional £{paper_notional:,.0f} for the Phase I paper portfolio — not capital. The "
                              "plan assumes £0 starting capital and no external assets."),
            "governance": True, "stage": "research", "require_approved_model": True,
            "risk_policy": dict(gov.DEFAULT_RISK_POLICY), "mandate_text": MANDATE_TEXT,
            "mandate": {**DEFAULT_MANDATE, "long_only": True, "developed_markets_only": False, "max_position_pct": 0.25,
                        "max_sector_pct": 1.0, "min_cash_pct": 0.0},
        })
        fund_store.set_limit_overrides({"gross_exposure": {"soft": 0.95, "hard": 1.00},
                                        "net_exposure_abs": {"soft": 0.95, "hard": 1.00},
                                        "drawdown": {"soft": 0.05, "hard": 0.08},
                                        "single_name": {"soft": 0.20, "hard": 0.25}})
        gov.init_db()
        seeded = {}
        with _conn() as c:
            if not c.execute("SELECT COUNT(*) FROM gov_instruments").fetchone()[0]:
                for sym, name, ac, theme, ccy, tradable, note in INSTRUMENTS:
                    c.execute("INSERT INTO gov_instruments (symbol, name, asset_class, theme, currency, tradable, status, note, "
                              "proposed_by, proposed_at) VALUES (?,?,?,?,?,?,'proposed',?,?,?)",
                              (sym, name, ac, theme, ccy, 1 if tradable else 0, note or "proposed from the plan's initial universe",
                               "setup", gov._now()))
                seeded["instruments"] = len(INSTRUMENTS)
            if not c.execute("SELECT COUNT(*) FROM gov_budget").fetchone()[0]:
                for period, cat, amt, outcome in BUDGET:
                    c.execute("INSERT INTO gov_budget (period, category, amount, currency, outcome) VALUES (?,?,?,?,?)",
                              (period, cat, amt, "GBP", outcome))
                seeded["budget_lines"] = len(BUDGET)
            if not c.execute("SELECT COUNT(*) FROM gov_milestones").fetchone()[0]:
                for i, (plan, period, out, owner, acc) in enumerate(MILESTONES):
                    c.execute("INSERT INTO gov_milestones (plan, period, output, owner, acceptance, sort) VALUES (?,?,?,?,?,?)",
                              (plan, period, out, owner, acc, i))
                seeded["milestones"] = len(MILESTONES)
            c.commit()
        from api import positions
        n_pos = positions.seed("moriah")
        if n_pos:
            seeded["positions"] = n_pos
        gov._audit("fund_setup", f"Fund configured as {FUND_NAME} (Phase I research & paper portfolio) from: {SOURCE}",
                   user, "fund", before={k: before.get(k) for k in ("fund_name", "base_currency", "benchmark", "capital")},
                   after={"seeded": seeded})
        return {"fund": fund_id, "name": FUND_NAME, "seeded": seeded, "settings": gov.settings()}
    finally:
        funds.CURRENT.reset(tok)
