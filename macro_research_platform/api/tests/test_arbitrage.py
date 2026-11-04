"""Prediction-market cross-venue arbitrage, ETF premium/discount and the VIX formula variables — offline."""
import numpy as np
import pandas as pd
import pytest

from api.marketdata import etfarb, predarb


# ── Fees and order-book walking ─────────────────────────────────────────────
def test_kalshi_fee_matches_published_formula():
    # ⌈0.07 × C × P × (1−P)⌉ to the cent: 100 contracts at 50¢ → $1.75; 1 contract at 50¢ → 2¢
    assert predarb.kalshi_fee(100, 0.50) == 1.75
    assert predarb.kalshi_fee(1, 0.50) == 0.02
    assert predarb.kalshi_fee(10, 0.99) == 0.01


def test_walk_stops_when_the_pair_costs_a_dollar():
    yes_poly = [(0.40, 100), (0.45, 100), (0.55, 100)]           # Polymarket YES asks
    no_kal = [(0.50, 150), (0.52, 100)]                         # Kalshi NO asks (fee leg)
    r = predarb._walk(yes_poly, no_kal, "b", 0.07, 0.0)
    # 100 @ .40+.50, 50 @ .45+.50 and 50 @ .45+.52 (each + ≈1.75¢ fee) cost < $1; .55+.52 stops it.
    assert r["contracts"] == 200
    assert 0 < r["edge_per_contract"] < 0.10
    assert abs(r["profit"] - (r["contracts"] - r["outlay"])) < 1e-6


def test_walk_returns_nothing_without_an_edge():
    assert predarb._walk([(0.60, 10)], [(0.45, 10)], "b", 0.07, 0.0) == {"contracts": 0}


def test_quote_edge_uses_asks_not_mids():
    pm_m = {"bid": 0.48, "ask": 0.50}
    km_m = {"bid": 0.55, "ask": 0.57}
    out = {o["dir"]: o for o in predarb._quote_edge(pm_m, km_m, 0.0, 0.0)}
    assert out["poly_yes_kalshi_no"]["cost"] == pytest.approx(0.50 + 0.45)     # NO ask = 1 − YES bid
    assert out["kalshi_yes_poly_no"]["cost"] == pytest.approx(0.57 + 0.52)
    assert out["poly_yes_kalshi_no"]["edge"] == pytest.approx(0.05)


# ── Question matching ───────────────────────────────────────────────────────
def _ev(venue, title, questions, end="2026-10-29"):
    return {"venue": venue, "title": title, "category": "Fed & rates", "end": end, "id": title, "slug": "x", "series": "KX",
            "markets": [{"id": f"{venue}-{i}", "label": q, "question": q, "binary": True, "yes": 0.5, "bid": 0.49, "ask": 0.51,
                         "end": end} for i, q in enumerate(questions)]}


def test_matcher_pairs_same_questions_and_rejects_lookalikes(monkeypatch):
    poly = [_ev("Polymarket", "Fed Decision in October?", [
                "Will there be no change in Fed interest rates after the October 2026 meeting?",
                "Will the Fed decrease interest rates by 25 bps after the October 2026 meeting?"]),
            _ev("Polymarket", "Core CPI", ["Will Core CPI MoM be 0.3% in September?"]),
            _ev("Polymarket", "Republican nominee", ["Will Marco Rubio win the 2028 Republican presidential nomination?",
                                                     "Will Sarah Huckabee Sanders win the 2028 Republican presidential nomination?"],
                end="2028-11-07")]
    kal = [_ev("Kalshi", "Fed decision in Oct 2026?", [
                "Will the Federal Reserve Hike rates by 0bps at their October 2026 meeting?",
                "Will the Federal Reserve Cut rates by 25bps at their October 2026 meeting?"]),
           _ev("Kalshi", "CPI Core", ["Will CPI Core rise more than 0.3% in September?"]),
           _ev("Kalshi", "2028 Republican presidential nominee", [
               "Will Marco Rubio be the nominee for the Presidency for the Republican party?",
               "Will Marco Rubio and Sarah Huckabee Sanders be the 2028 Republican Presidential ticket?"], end="2028-11-07")]
    monkeypatch.setattr(predarb.pm, "catalog", lambda: {"events": poly + kal})
    # A 9-question catalog gives unrealistic word weights, so score loosely; the filters are what's tested.
    got = {m["poly"]["m"]["question"]: m["kalshi"]["m"]["question"] for m in predarb.match(min_score=0.2)}
    assert "0bps" in got["Will there be no change in Fed interest rates after the October 2026 meeting?"]
    assert "Cut rates by 25bps" in got["Will the Fed decrease interest rates by 25 bps after the October 2026 meeting?"]
    assert "Marco Rubio be the nominee" in got["Will Marco Rubio win the 2028 Republican presidential nomination?"]
    assert "Will Core CPI MoM be 0.3% in September?" not in got                 # exact bucket ≠ "more than"
    assert "Will Sarah Huckabee Sanders win the 2028 Republican presidential nomination?" not in got   # combo ticket


def test_fed_key_and_comparator():
    assert predarb._fed_key("Will the Federal Reserve Hike rates by 0bps at their October 2026 meeting?") == (2026, 10, 0)
    assert predarb._fed_key("Will the Fed increase interest rates by 25 bps after the December 2026 meeting?") == (2026, 12, 25)
    assert predarb._fed_key("How many times will the Fed cut rates in 2026?") is None
    assert predarb._comparator("Will CPI rise more than 0.3%?") == "gt"
    assert predarb._comparator("Will CPI be 0.6% or more?") == "ge"
    assert predarb._comparator("Will Core CPI MoM be 0.3%?") == "eq"


def test_rf_interpolates_the_curve():
    curve = [(0.25, 0.04), (1.0, 0.045), (2.0, 0.05)]
    assert predarb._rf(curve, 365) == pytest.approx(0.045)
    assert predarb._rf(curve, 548) == pytest.approx(0.04750, abs=1e-4)
    assert predarb._rf(curve, 30) == 0.04 and predarb._rf([], 30) is None


# ── ETF premium / discount ──────────────────────────────────────────────────
def test_etf_premium_uses_close_vs_nav(monkeypatch):
    fake = {"SPY": {"symbol": "SPY", "nav": 500.0, "close": 500.1}, "EWJ": {"symbol": "EWJ", "nav": 70.0, "close": 70.7},
            "ETHA": {"symbol": "ETHA", "nav": 20.43, "close": 55.99}}                  # stale NAV from Yahoo

    def one(sym):
        f = fake.get(sym)
        if not f:
            return None
        return {**f, "name": sym, "last": f["close"], "premium_bp": round((f["close"] / f["nav"] - 1) * 1e4, 1),
                "move_since_close_bp": 0.0, "aum": 1e9, "volume": 1, "expense_pct": 0.09, "as_of": None}
    monkeypatch.setattr(etfarb, "_one", one)
    monkeypatch.setattr(etfarb, "_cached", lambda k, ttl, fn: fn())
    r = etfarb.snapshot()
    assert [x["symbol"] for x in r["rows"]] == ["EWJ", "SPY"]                  # sorted by |premium|
    assert r["rows"][0]["premium_bp"] == 100.0 and r["rows"][1]["premium_bp"] == 2.0
    assert r["flagged"] == ["EWJ"]                                            # ≥ 50bp for international
    assert "SPY" not in r["missing"] and "QQQ" in r["missing"]
    assert [u["symbol"] for u in r["unreliable"]] == ["ETHA"]


# ── VIX variables in formulas ───────────────────────────────────────────────
def test_vix_variables_broadcast_and_align(monkeypatch):
    from api.quant import data as qdata, expr
    idx = pd.bdate_range("2020-01-01", periods=50)
    close = pd.DataFrame({"SPY": np.linspace(100, 110, 50), "QQQ": np.linspace(200, 190, 50)}, index=idx)
    vix = pd.Series(np.r_[np.full(10, np.nan), np.linspace(15, 30, 40)], index=idx)
    monkeypatch.setattr(qdata, "panel", lambda syms, start=None, end=None: ({"close": pd.DataFrame({syms[0]: vix})}, []))
    out = expr.evaluate("vix - 20", expr.Ctx(close, mkt=close["SPY"]))
    assert out.shape == close.shape and (out["SPY"].dropna() == out["QQQ"].dropna()).all()
    assert out.iloc[:10].isna().all().all() and out.iloc[-1, 0] == pytest.approx(10)
