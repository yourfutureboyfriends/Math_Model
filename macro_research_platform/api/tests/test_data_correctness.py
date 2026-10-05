"""Regression tests for data-correctness fixes: FX bar dating, same-date spreads, measured
(not synthesised) risk analytics, history-relative commodity signals, FX conventions."""
from datetime import date

import pytest

from api.market_dates import align_daily, align_pairs, is_spot_fx


# ── FX bar dating ────────────────────────────────────────────────────────────
def test_fx_bars_move_to_previous_ny_session_and_partials_drop():
    today = date(2026, 10, 4)                               # Sunday
    dates = ["2026-09-28", "2026-09-29", "2026-10-01", "2026-10-02", "2026-10-04"]
    out = align_daily("EURUSD=X", dates, today)
    assert out == [date(2026, 9, 25), date(2026, 9, 28), date(2026, 9, 30), date(2026, 10, 1), None]
    # Monday's bar belongs to Friday; the Sunday-evening partial is dropped.


def test_bar_dated_today_is_dropped_for_fx_only():
    today = date(2026, 10, 2)
    assert align_daily("USDJPY=X", ["2026-10-02"], today) == [None]
    assert align_daily("^GSPC", ["2026-10-02"], today) == [date(2026, 10, 2)]
    assert align_daily("BTC-USD", ["2026-10-03"], today) == [date(2026, 10, 3)]


def test_align_pairs_and_detection():
    assert is_spot_fx("GBPUSD=X") and not is_spot_fx("GC=F") and not is_spot_fx("DX-Y.NYB")
    pairs = align_pairs("EURUSD=X", ["2026-09-29", "2026-09-30"], [1.1, 1.2], today=date(2026, 10, 4))
    assert pairs == [("2026-09-28", 1.1), ("2026-09-29", 1.2)]


# ── Same-date spreads ────────────────────────────────────────────────────────
def test_spread_uses_latest_common_date():
    from api.handlers.macro_inputs import DatedSeries
    ten = DatedSeries("dgs10", ["2026-09-30", "2026-10-01", "2026-10-02"], [5.29, 5.24, 5.30])
    two = DatedSeries("dgs2", ["2026-09-30", "2026-10-01"], [4.80, 4.78])
    d, a, b = ten.last_common(two)
    assert d == "2026-10-01" and round((a - b) * 100, 1) == 46.0   # not 5.30 - 4.78 = 52bp


# ── Risk analytics are measured ──────────────────────────────────────────────
def test_performance_stats_from_returns():
    from api.calculations.risk_analytics import performance_stats, drawdown_stats
    port = [0.01, -0.02, 0.015, -0.005, 0.01] * 20
    bench = [0.008, -0.01, 0.01, -0.004, 0.006] * 20
    p = performance_stats(port, bench, rf_annual=0.0)
    assert p["available"] and p["observations"] == 100
    # Sortino is not "Sharpe × 1.2" and IR is not "Sharpe × 0.8" any more
    assert p["sortinoRatio"] != round(p["sharpeRatio"] * 1.2, 2)
    assert p["betaVsSpy"] > 1.0                             # port moves ~1.6x bench
    assert p["var95"] == pytest.approx(0.02, abs=1e-9)      # worst 5% day
    dd = drawdown_stats([0.1, -0.2, 0.05])
    assert dd["max_drawdown"] == pytest.approx(-0.2) and dd["days_in_drawdown"] == 2


def test_correlation_block_is_measured():
    from api.calculations.risk_analytics import correlation_block
    a = [0.01, -0.01] * 40
    c = correlation_block({"A": a, "B": [x * 2 for x in a], "C": [-x for x in a]}, window=63)
    m = dict(zip(c["assets"], c["matrix3m"]))
    assert m["A"][1] == 1.0 and m["A"][2] == -1.0
    assert c["diversificationScore"] == 0.0 and c["diversificationRating"] == "POOR"


# ── Commodity signals relative to history ────────────────────────────────────
def test_copper_gold_signal_follows_trend_not_fixed_level():
    from api.calculations.commodity_signals import copper_gold_signal, broad_commodity_momentum
    days = [f"2026-{m:02d}-{d:02d}" for m in range(1, 7) for d in range(1, 29)][:100]
    gold = {d: 4000.0 for d in days}
    copper = {d: 5.0 + i * 0.02 for i, d in enumerate(days)}            # copper rising vs gold
    s = copper_gold_signal(copper, gold)
    assert s["value"] < 1.8 and s["signal"] == "RISK-ON"             # old rule: always RISK-OFF
    assert broad_commodity_momentum([{"change3m": 5}, {"change3m": 1}])["signal"] == "RISING"
    assert broad_commodity_momentum([])["signal"] == "UNAVAILABLE"


# ── FX conventions ───────────────────────────────────────────────────────────
def test_usd_base_pairs_are_not_inverted():
    from api.providers.yahoo_provider import YahooFinanceProvider as P
    assert P.SYMBOL_MAP["USDJPY"] == "USDJPY=X" and not P.INVERT_SYMBOLS


def test_sector_playbook_tilt_needs_relative_strength_confirmation():
    from api.calculations.metrics import calculate_sector_allocation
    stats = {"Financials": {"percentile": 0.14, "z": -0.88, "relativeReturn": -0.071, "etf": "XLF"},
             "Energy": {"percentile": 0.9, "z": 0.74, "relativeReturn": 0.05, "etf": "XLE"}}
    out = {s["name"]: s for s in calculate_sector_allocation("reflation", 0.8, 0.6, sector_stats=stats,
                                                             confidence=0.6)["sectors"]}
    assert out["Financials"]["playbookStance"] == "Overweight" and out["Financials"]["signal"] == "Neutral"
    assert out["Energy"]["signal"] == "Overweight"


def test_growth_direction_uses_three_month_window():
    from api.calculations import signals
    assert signals._GROWTH_TREND_OFFSET == 63


def test_ny_fx_closes_from_hourly_bars():
    import pandas as pd
    from api.market_dates import ny_fx_closes
    idx = pd.date_range("2026-10-02 14:00", "2026-10-05 18:00", freq="h", tz="America/New_York")
    bars = pd.DataFrame({"Close": range(len(idx))}, index=idx, dtype=float)
    out = ny_fx_closes(bars, now=pd.Timestamp("2026-10-05 18:30", tz="America/New_York"))
    # Friday's close = the 16:00 bar; no weekend sessions; Monday complete after 17:00 NY
    assert out["2026-10-02"] == float(idx.get_loc(pd.Timestamp("2026-10-02 16:00", tz="America/New_York")))
    assert "2026-10-03" not in out and "2026-10-04" not in out
    assert "2026-10-05" in out
    # Before the cutoff, Monday is still forming
    early = ny_fx_closes(bars[bars.index < pd.Timestamp("2026-10-05 12:00", tz="America/New_York")],
                         now=pd.Timestamp("2026-10-05 12:00", tz="America/New_York"))
    assert "2026-10-05" not in early and "2026-10-02" in early
