"""Head-of-trading operations: NAV record per currency, stock splits on held positions, trade lifecycle with TCA
against the pre-trade estimate, and base-currency Brinson attribution against a composite benchmark."""
import pandas as pd
import pytest


@pytest.fixture()
def book(tmp_path, monkeypatch):
    from api import funds
    monkeypatch.setattr(funds, "db_path", lambda fund_id=None: str(tmp_path / "fund.db"))
    yield tmp_path


# ── NAV record per currency ──────────────────────────────────────────────────
def test_nav_series_restarts_when_the_base_currency_changes(book):
    from api import fund_store
    fund_store.record_nav({"date": "2026-10-01", "nav": 1_000_000})
    fund_store.record_nav({"date": "2026-10-02", "nav": 1_010_000})
    assert [r["currency"] for r in fund_store.nav_history()] == ["USD", "USD"]
    fund_store.update_settings({"base_currency": "GBP"})
    assert fund_store.nav_history() == []                       # the USD record is not read as GBP
    fund_store.record_nav({"date": "2026-10-05", "nav": 760_000})
    cur = fund_store.nav_history()
    assert [(r["date"], r["currency"]) for r in cur] == [("2026-10-05", "GBP")]
    assert len(fund_store.nav_history(currency=None)) == 3      # nothing deleted
    runs = fund_store.nav_series()
    assert [(r["currency"], r["snapshots"], r["current"]) for r in runs] == [("USD", 2, False), ("GBP", 1, True)]


def test_existing_nav_rows_get_the_currency_of_the_time(book):
    import sqlite3
    from api import funds
    c = sqlite3.connect(funds.db_path())
    c.execute("CREATE TABLE nav_history (date TEXT PRIMARY KEY, nav REAL NOT NULL, gross REAL, net REAL, "
              "unrealized_pnl REAL, realized_pnl REAL, var95_1d REAL, regime TEXT, positions INTEGER, recorded_at TEXT)")
    c.execute("INSERT INTO nav_history (date, nav) VALUES ('2026-09-30', 5)")
    c.commit()
    c.close()
    from api import fund_store
    assert fund_store.nav_history()[0]["currency"] == "USD"


# ── stock splits ─────────────────────────────────────────────────────────────
@pytest.fixture()
def splits(monkeypatch):
    from api import corporate_actions as ca
    table = {"NVDA": [{"ex_date": "2024-06-10", "ratio": 10.0}], "XYZ": [{"ex_date": "2026-03-02", "ratio": 0.1}]}
    monkeypatch.setattr(ca, "splits", lambda s: table.get(s.upper(), []))
    return table


def test_split_applied_once_and_value_unchanged(book, splits):
    from api import corporate_actions as ca, portfolio_store
    portfolio_store.add_position({"symbol": "NVDA", "quantity": 50, "avg_cost": 1000.0, "entry_date": "2024-01-02",
                                  "book": "Equity", "cost_usd_per_unit": 1.0})
    p = ca.pending(today="2026-10-25")
    assert len(p) == 1 and p[0]["ratio"] == 10 and not p[0]["needs_review"]
    r = ca.apply_pending_automatically()
    assert len(r["applied"]) == 1
    pos = portfolio_store.list_positions("Equity")[0]
    assert pos["quantity"] == 500 and pos["avg_cost"] == pytest.approx(100.0)
    assert pos["quantity"] * pos["avg_cost"] == pytest.approx(50 * 1000.0)    # cost basis unchanged
    assert pos["cost_usd_per_unit"] == 1.0                                     # per currency unit, not per share
    assert ca.pending(today="2026-10-25") == []                               # once only
    with pytest.raises(ValueError):
        ca.apply("Equity", "NVDA", "2024-06-10", 10.0, "pm")
    assert len(ca.applied()) == 1


def test_split_before_entry_ignored_and_trade_after_ex_date_needs_review(book, splits):
    from api import blotter_store, corporate_actions as ca, portfolio_store
    portfolio_store.add_position({"symbol": "NVDA", "quantity": 10, "avg_cost": 120.0, "entry_date": "2025-01-02", "book": "A"})
    assert ca.pending(today="2026-10-25") == []                               # bought after the split
    portfolio_store.add_position({"symbol": "XYZ", "quantity": 1000, "avg_cost": 2.0, "entry_date": "2026-01-05", "book": "B"})
    blotter_store.book_fill("B", "XYZ", 100, 2.1, 0.0, "pm")                  # a fill dated today, after the ex-date
    p = ca.pending(today="2026-10-25")
    assert len(p) == 1 and p[0]["needs_review"] and p[0]["kind"] == "consolidation"
    assert ca.apply_pending_automatically()["applied"] == []                  # left for a person


def test_split_factor_puts_old_fills_in_todays_shares(splits):
    from api import corporate_actions as ca
    from api.calculations import portfolio_analytics as pa
    assert ca.split_factor_after("NVDA", "2024-05-01T15:00:00") == 10
    assert ca.split_factor_after("NVDA", "2024-06-10") == 1                   # on the ex-date: already post-split
    trades = [{"ts": "2024-05-01", "symbol": "NVDA", "side": "BUY", "quantity": 5, "split_factor": 10}]
    h = pa.holdings_by_day([{"symbol": "NVDA", "quantity": 50, "entry_date": "2024-05-01"}], trades,
                           ["2024-04-30", "2024-05-02"])
    assert h["2024-04-30"] == {} and h["2024-05-02"] == {"NVDA": 50}


# ── trade lifecycle and TCA against the estimate ─────────────────────────────
ASSESS = {"symbol": "ULVR.L", "side": "BUY", "base_currency": "GBP",
          "size": {"quantity": 100, "notional_base": 4937.5},
          "price": {"last": 4900.0, "currency": "GBp", "market_state": "REGULAR", "quote_time": "2026-10-23T10:00:00+00:00"},
          "costs": {"half_spread_bps": {"value": 3.0, "basis": "observed bid/ask (market open)"},
                    "impact_bps": {"staged_at_cap": 2.0}, "commission_bps": {"value": 5.0},
                    "taxes_bps": {"value": 50.0}, "fx_conversion_bps": {"value": 0.0}, "total_bps": 60.0},
          "assessment": {"verdict": "feasible"}, "flags": []}


def test_tca_against_the_estimate():
    from api import trade_lifecycle as tl
    a = {"decision_price": 100.0, "half_spread_bps": 3.0, "impact_bps": 2.0, "commission_bps": 5.0, "taxes_bps": 50.0,
         "fx_bps": 0.0, "total_bps": 60.0}
    t = {"price": 101.0, "quantity": 100, "reference_price": 100.5, "commission": 5.05, "taxes": 50.5, "source": "alpaca_paper"}
    r = tl.tca("BUY", 100, a, t)
    assert r["actual"]["delay_bps"] == pytest.approx(50.0)                    # 100 → 100.5
    assert r["actual"]["execution_bps"] == pytest.approx((101 / 100.5 - 1) * 1e4, abs=0.01)
    assert r["actual"]["explicit_bps"] == pytest.approx(55.55 / 10100 * 1e4, abs=0.01)
    assert r["actual"]["implementation_shortfall_bps"] == pytest.approx(100 + 55.55 / 10100 * 1e4, abs=0.01)
    assert r["actual_minus_estimate_bps"]["execution"] == pytest.approx(r["actual"]["execution_bps"] - 5.0, abs=0.01)
    s = tl.tca("SELL", 100, a, {**t, "price": 99.0, "reference_price": 99.5})
    assert s["actual"]["execution_bps"] > 0 and s["actual"]["delay_bps"] > 0  # selling lower is a cost
    assert "note" in tl.tca("BUY", 100, None, t)


def test_lifecycle_links_assessment_order_and_fill(book):
    from api import blotter_store, portfolio_store, trade_lifecycle as tl
    aid = tl.save_assessment(ASSESS, "trader", pitch_id=None)
    assert tl.latest_assessment("ulvr.l", "buy")["id"] == aid
    blotter_store.init_db()
    idea = portfolio_store.add_trade_idea({"symbol": "ULVR.L", "direction": "LONG", "thesis": "t", "conviction": "MEDIUM",
                                           "suggested_size": 100, "book": "Equity", "allow_duplicate": True}, "trader")
    blotter_store.set_order_fields(idea["id"], side="BUY", quantity=100, assessment_id=aid, assessment_link="given")
    blotter_store.book_fill("Equity", "ULVR.L", 100, 4905.0, 24.5, "pm", "simulated", idea["id"],
                            fx={"reference_price": 4902.0, "taxes": 245.0, "currency": "GBp"})
    v = tl.lifecycle()
    o = v["orders"][0]
    assert o["assessment"]["id"] == aid and o["assessment"]["link"] == "given" and o["fill"]["price"] == 4905.0
    assert o["tca"]["simulated"] and "by construction" in o["tca"]["note"]
    assert o["tca"]["actual"]["delay_bps"] == pytest.approx((4902 / 4900 - 1) * 1e4, abs=0.01)
    assert v["summary"]["executed"] == 1 and v["summary"]["compared"] == 1 and v["summary"]["avg_estimated_bps"] == 60.0


# ── Brinson in the base currency against a composite benchmark ───────────────
def test_brinson_base_reconciles_to_the_real_benchmark(book, monkeypatch):
    from api import portfolio_store
    from api.calculations import benchmark as bm
    from api.handlers import portfolio_analytics as h
    days = pd.bdate_range("2026-09-01", periods=30)
    rng = __import__("numpy").random.default_rng(7)

    def walk(mu):
        return pd.Series(100 * (1 + rng.normal(mu, 0.01, len(days))).cumprod(), index=days)
    prices = {"AAA": walk(0.002), "BBB": walk(-0.001), **{e: walk(0.0005) for e in set(h.WORLD_SECTOR_ETF.values())}}
    bench = walk(0.0008).pct_change().dropna()
    monkeypatch.setattr(bm, "in_base", lambda s, base: prices[s])
    monkeypatch.setattr(bm, "series", lambda code, base: {"returns": bench, "start": str(days[1].date())})
    monkeypatch.setattr(h, "_sector_of", lambda s: {"AAA": "Technology", "BBB": "Healthcare"}[s])
    monkeypatch.setattr(h, "benchmark_sector_weights", lambda code: {"weights": {"Technology": 0.6, "Healthcare": 0.4}, "legs": {}})
    monkeypatch.setattr(h, "book_in_base", lambda book=None: {
        "base": "GBP", "nav": 100_000.0, "capital": 100_000.0, "benchmark": "BIFS",
        "positions": [{"symbol": "AAA", "quantity": 300, "cost_basis": 30_000.0, "unrealized_pnl": 0.0},
                      {"symbol": "BBB", "quantity": 200, "cost_basis": 20_000.0, "unrealized_pnl": 0.0}]})
    portfolio_store.add_position({"symbol": "AAA", "quantity": 300, "avg_cost": 100, "entry_date": "2026-09-01"})
    portfolio_store.add_position({"symbol": "BBB", "quantity": 200, "avg_cost": 100, "entry_date": "2026-09-01"})
    r = h.brinson_base(None, "BIFS")
    assert r["available"] and r["currency"] == "GBP"
    e = r["effects_bps"]
    # allocation + selection + interaction + benchmark construction = active return vs the real blend
    assert sum(e.values()) + r["benchmark_construction_bps"] == pytest.approx(r["active_return_bps"], abs=0.3)
    assert r["benchmark_return"] == pytest.approx(float((1 + bench[bench.index > days[1]]).prod() - 1), abs=1e-4)
    assert {row["sector"] for row in r["by_sector"]} >= {"Technology", "Healthcare", "Cash"}


# ── the whole chain over HTTP: assessment → order (linked) → four-eyes → fill → lifecycle ──
def test_assessment_order_fill_lifecycle_over_http(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import api.core.auth as auth
    from api import funds
    from api.core import accounts
    path = str(tmp_path / "d.db")
    monkeypatch.setattr(funds, "db_path", lambda fund_id=None: path)
    monkeypatch.setattr(auth, "get_db_path", lambda: path)
    accounts.invalidate_cache()
    accounts.migrate()
    for u in ("pm", "risk", "analyst"):
        accounts.set_password(u, f"Ops-{u}-Pass-2026!x")
    from api import execution
    from api.calculations import fx_accounting
    from api.handlers import market_handler, pretrade_feasibility as pf
    from api.routers import fund as fund_router
    monkeypatch.setattr(pf, "assess", lambda *a, **k: dict(ASSESS))

    async def ok(*a, **k):
        return {"decision": "PASS", "reasons": []}

    async def closes(sym):
        return [4890.0, 4902.0]
    monkeypatch.setattr(fund_router, "_run_pretrade", ok)
    monkeypatch.setattr(market_handler, "_fetch_closes_literal", closes)
    monkeypatch.setattr(execution, "modelled_cost_bps", lambda s, q: {"half_spread_bps": 3.0, "impact_bps": 2.0,
                                                                     "tax_buy_bps": 50.0, "tax_sell_bps": 0.0})
    monkeypatch.setattr(fx_accounting, "fill_rates", lambda s, b: ("GBp", 0.0133, 0.75))
    from api.main import app
    c = {}
    for u in ("pm", "risk", "analyst"):
        c[u] = TestClient(app)
        c[u].headers["Authorization"] = f"Bearer {accounts.issue_token(accounts.get_user(u))}"
    a = c["analyst"].post("/api/v1/trading/pretrade-assessment", json={"symbol": "ULVR.L", "side": "BUY", "quantity": 100})
    assert a.status_code == 200, a.text
    aid = a.json()["assessment_id"]
    o = c["analyst"].post("/api/v1/orders", json={"symbol": "ULVR.L", "side": "BUY", "quantity": 100, "book": "Equity"})
    assert o.status_code == 200, o.text
    order = o.json()["order"]
    assert order["assessment_id"] == aid and order["assessment_link"].startswith("automatic")
    assert c["analyst"].post("/api/v1/orders", json={"symbol": "AZN.L", "side": "BUY", "quantity": 1,
                                                     "assessment_id": aid}).status_code == 400   # wrong name
    assert c["risk"].post(f"/api/v1/orders/{order['id']}/approve", json={"note": "ok"}).status_code == 200
    ex = c["pm"].post(f"/api/v1/orders/{order['id']}/execute")
    assert ex.status_code == 200, ex.text
    v = c["pm"].get("/api/v1/trading/lifecycle").json()
    row = v["orders"][0]
    assert row["assessment"]["id"] == aid and row["fill"] and row["approved_by"] == "risk"
    t = row["tca"]
    assert t["simulated"] and t["decision_price"] == 4900.0 and t["reference_price"] == 4902.0
    assert t["actual"]["execution_bps"] == pytest.approx(5.0, abs=0.05)       # close + modelled 5 bp
    assert t["actual_minus_estimate_bps"]["execution"] == pytest.approx(0.0, abs=0.05)
    assert c["pm"].get("/api/v1/corporate-actions").status_code == 200
    assert TestClient(app).get("/api/v1/trading/lifecycle").status_code == 401
    accounts.invalidate_cache()
