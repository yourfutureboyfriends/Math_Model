"""
Regression tests — run with: pytest tests/test_data_integrity.py -v
These tests encode real-world values. If any test fails, a known bug
has returned. Do NOT delete or weaken these tests.
"""
import math, pytest, requests
import sys
from pathlib import Path
from unittest.mock import MagicMock

BASE_URL = "http://localhost:3002"

def get_dashboard():
    r = requests.get(f"{BASE_URL}/api/dashboard", timeout=15)
    assert r.status_code == 200, f"Dashboard returned {r.status_code}"
    return r.json()

def safe_float(v):
    try:
        return float(v)
    except:
        return None

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.data_contracts import CONTRACTS
from api.data_fetcher import fetch_metric, validate_dashboard_snapshot
from api.regime_context import build_regime_context

# ── Regression: the +109.5% growth bug ──────────────────────────────────────
def test_growth_109_pct_is_rejected():
    """REGRESSION: raw value of 109.5 must be rejected by hard bounds."""
    fred_mock = MagicMock(return_value=109.5)
    result = fetch_metric("growth", fred_fetch_fn=fred_mock)
    assert -15 <= result <= 15, f"Growth {result}% slipped through bounds check"

def test_growth_uses_annualised_series():
    """Must use A191RL1Q225SBEA (percent change), not GDPC1 (index level)."""
    contract = CONTRACTS["growth"]
    assert contract.fred_series == "A191RL1Q225SBEA", \
        "Wrong FRED series for growth — must be percent change, not level"

# ── Regression: HY spread unit conversion ────────────────────────────────────
def test_hy_spread_pct_to_bps_conversion():
    """FRED returns 2.83 (percent). Must convert to 283 bps."""
    fred_mock = MagicMock(return_value=2.83)
    result = fetch_metric("hy_spread", fred_fetch_fn=fred_mock)
    assert 100 <= result <= 2000, f"HY spread {result} not in bps range"
    assert result > 10, f"HY spread {result} looks like percent, not bps"
    assert abs(result - 283) < 5, f"Expected ~283 bps, got {result}"

def test_hy_spread_3_bps_is_rejected():
    """REGRESSION: 3 bps (= 0.03 pct input) is implausible — reject."""
    fred_mock = MagicMock(return_value=0.03)
    result = fetch_metric("hy_spread", fred_fetch_fn=fred_mock)
    # 0.03 × 100 = 3 bps which is below hard_min=50 → use fallback
    assert result == CONTRACTS["hy_spread"].fallback_value or result >= 50

# ── Regression: NaN propagation in All Weather ───────────────────────────────
def test_nan_never_returned():
    """NaN from any source must never reach the dashboard."""
    fred_mock = MagicMock(return_value=float("nan"))
    result = fetch_metric("vix", fred_fetch_fn=fred_mock)
    assert math.isfinite(result), "NaN slipped through fetch_metric"

# ── Regression: regime misclassification ─────────────────────────────────────
def test_goldilocks_requires_low_inflation():
    """3.3% CPI must NOT produce Goldilocks regime."""
    ctx = build_regime_context(growth_val=2.0, inflation_val=3.3)
    assert ctx.regime != "Goldilocks", \
        f"3.3% inflation cannot be Goldilocks, got {ctx.regime}"

def test_stagflation_with_current_data():
    """GDP +2.0%, CPI +3.3% → Stagflation (below potential, above target)."""
    ctx = build_regime_context(growth_val=2.0, inflation_val=3.3)
    assert ctx.regime in ["Stagflation", "Reflation"], \
        f"Expected Stagflation/Reflation, got {ctx.regime}"

def test_regime_context_is_immutable():
    """RegimeContext must be frozen — no section can mutate it."""
    ctx = build_regime_context(2.0, 3.3)
    with pytest.raises(Exception):
        ctx.regime = "Goldilocks"   # type: ignore

# ── Dashboard snapshot validation ────────────────────────────────────────────
def test_snapshot_catches_implausible_growth():
    data = {"keyMetrics": {"growth": {"value": 109.5}, "inflation": {"value": 3.3},
            "vix": 20.0, "recessionRisk": 30.0},
            "riskIndicators": {"hyCredit": 283, "vix": 20.0, "yieldCurve": 51}}
    errors = validate_dashboard_snapshot(data)
    assert any("growth" in e.lower() or "OUT_OF_BOUNDS" in e for e in errors)

def test_snapshot_passes_with_valid_data():
    data = {"keyMetrics": {"growth": {"value": 2.0}, "inflation": {"value": 3.3},
            "vix": 20.0, "recessionRisk": 30.0},
            "riskIndicators": {"hyCredit": 283, "vix": 20.0, "yieldCurve": 51},
            "gmoForecasts": {"assets": [{"ticker": "SPY", "expectedReturn": -2.0}]}}
    errors = validate_dashboard_snapshot(data)
    assert errors == [], f"Valid data produced errors: {errors}"


class TestKeyMetrics:
    """R-04: Key Metrics section snapshot tests"""

    def test_inflation_range(self):
        d    = get_dashboard()
        infl = safe_float(
            d.get("keyMetrics", {}).get("inflation", {}).get("value")
        )
        assert infl is not None, "Inflation value missing"
        assert 0 <= infl <= 15, f"Inflation {infl} out of range"

    def test_growth_range(self):
        d   = get_dashboard()
        val = safe_float(
            d.get("keyMetrics", {}).get("growth", {}).get("value")
        )
        assert val is not None, "Growth value missing"
        assert -10 <= val <= 10, f"Growth {val} out of range"

    def test_recession_risk_range(self):
        d   = get_dashboard()
        val = safe_float(
            d.get("keyMetrics", {}).get("recessionRisk")
        )
        assert val is not None, "Recession risk missing"
        assert 0 <= val <= 100, f"Recession risk {val} out of range"

    def test_vix_range(self):
        d   = get_dashboard()
        val = safe_float(d.get("keyMetrics", {}).get("vix"))
        assert val is not None, "VIX missing from keyMetrics"
        assert 5 <= val <= 90, f"VIX {val} out of range"


class TestRegime:
    """R-04: Regime Classification section snapshot tests"""

    def test_regime_is_valid(self):
        d      = get_dashboard()
        regime = d.get("regime", {}).get("current", "")
        valid  = {"Goldilocks", "Reflation", "Stagflation", "Slowdown"}
        assert regime in valid, f"Invalid regime: {regime}"

    def test_confidence_range(self):
        d   = get_dashboard()
        val = safe_float(
            d.get("regime", {}).get(
                "confidenceScore",
                d.get("regime", {}).get("confidence")
            )
        )
        assert val is not None, "Regime confidence missing"
        assert 0.0 <= val <= 1.0, f"Confidence {val} out of range"

    def test_duration_positive(self):
        d   = get_dashboard()
        val = d.get("regime", {}).get("duration", 0)
        assert val is not None, "Regime duration missing"
        assert int(val) >= 1, f"Duration {val} must be at least 1"

    def test_intl_us_matches_master(self):
        """R-04: regression — intl US must equal master regime"""
        d         = get_dashboard()
        master    = d.get("regime", {}).get("current", "")
        economies = (
            d.get("internationalMacro", {}).get("economies", [])
        )
        us        = next(
            (e for e in economies if e.get("name") == "US"), {}
        )
        intl_us = us.get("regime", "NOT FOUND")
        assert master == intl_us, (
            f"Regime mismatch: master={master} intl_us={intl_us}"
        )


class TestRiskIndicators:
    """R-04: Risk Indicators section snapshot tests"""

    def test_hy_spread_in_bps_not_percent(self):
        """R-04: regression — HY must be bps not raw FRED percent"""
        d   = get_dashboard()
        val = safe_float(
            d.get("riskIndicators", {}).get("hyCredit")
        )
        assert val is not None, "HY spread missing"
        assert 50 <= val <= 2500, f"HY spread {val} not in bps range"
        assert val > 10, f"HY spread {val} looks like percent not bps"

    def test_vix_finite(self):
        d   = get_dashboard()
        val = safe_float(
            d.get("riskIndicators", {}).get("vix")
        )
        assert val is not None, "Risk Indicators VIX missing"
        assert math.isfinite(val), "Risk Indicators VIX is NaN"
        assert 5 <= val <= 90, f"VIX {val} out of range"

    def test_yield_curve_range(self):
        d   = get_dashboard()
        val = safe_float(
            d.get("riskIndicators", {}).get("yieldCurve")
        )
        assert val is not None, "Yield curve missing"
        assert -300 <= val <= 300, f"Yield curve {val} out of range"


class TestAllWeather:
    """R-04: All Weather snapshot tests — regression for NaN bug"""

    def test_portfolio_vol_not_nan(self):
        d   = get_dashboard()
        val = safe_float(
            d.get("advancedIndicators", {})
             .get("allWeather", {})
             .get("portfolioVol")
        )
        assert val is not None, "All Weather portfolioVol missing"
        assert math.isfinite(val), "portfolioVol is NaN"
        assert val > 0, "portfolioVol is zero or negative"
        assert val < 50, f"portfolioVol={val} implausibly high"

    def test_diversification_ratio_not_nan(self):
        d   = get_dashboard()
        val = safe_float(
            d.get("advancedIndicators", {})
             .get("allWeather", {})
             .get("diversificationRatio")
        )
        assert val is not None, "All Weather DR missing"
        assert math.isfinite(val), "DR is NaN"
        assert val > 0, "DR is zero or negative"
        assert val < 10, f"DR={val} implausibly high"


class TestEnsemble:
    """R-04: Ensemble section snapshot tests"""

    def test_score_not_exactly_zero(self):
        """R-04: regression — score was 0.000 when all layers broken"""
        d   = get_dashboard()
        en  = d.get(
            "ensembleSignal", d.get("masterEnsemble", {})
        )
        val = safe_float(en.get("score"))
        assert val is not None, "Ensemble score missing"
        assert math.isfinite(val), "Ensemble score is NaN"
        assert val != 0.0, (
            "Ensemble score is exactly 0.000 — layers not contributing"
        )

    def test_score_bounded(self):
        d   = get_dashboard()
        en  = d.get(
            "ensembleSignal", d.get("masterEnsemble", {})
        )
        val = safe_float(en.get("score"))
        assert val is not None, "Ensemble score missing"
        assert -1.0 <= val <= 1.0, f"Score {val} out of bounds"

    def test_stance_is_valid(self):
        d      = get_dashboard()
        en     = d.get(
            "ensembleSignal", d.get("masterEnsemble", {})
        )
        stance = en.get("stance", "")
        valid  = {
            "STRONG_RISK_ON", "RISK_ON", "SLIGHT_RISK_ON",
            "INFLATION_HEDGE", "NEUTRAL", "SLIGHT_RISK_OFF",
            "RISK_OFF", "STRONG_RISK_OFF",
        }
        assert stance in valid, f"Invalid stance: {stance}"

    def test_at_least_5_layers_contributing(self):
        """R-04: regression — all layers were 0% before R-02 fix"""
        d        = get_dashboard()
        en       = d.get(
            "ensembleSignal", d.get("masterEnsemble", {})
        )
        contribs = en.get("contributions", {})
        non_zero = sum(
            1 for v in contribs.values()
            if safe_float(v) is not None
            and safe_float(v) != 0.0
        )
        assert non_zero >= 5, (
            f"Only {non_zero} layers contributing. "
            f"Expected at least 5. Layers still broken."
        )


class TestBusinessLayer:
    """R-04: Business Layer section snapshot tests"""

    def test_returns_not_implausible(self):
        """R-04: regression — returns were +1500% before B-06 fix"""
        d       = get_dashboard()
        bl      = d.get("businessLayer", {})
        returns = bl.get("expectedReturns", [])
        for r in returns:
            val = safe_float(r.get("return"))
            if val is not None:
                assert abs(val) <= 50, (
                    f"Return {val}% for {r.get('name')} is implausible. "
                    f"Must be within -50 to +50."
                )

    def test_positions_not_all_zero(self):
        """R-04: regression — all positions were 0.0% before B-07 fix"""
        d         = get_dashboard()
        bl        = d.get("businessLayer", {})
        positions = bl.get("positions", [])
        if len(positions) == 0:
            pytest.skip("No positions returned — check if section exists")
        non_zero = sum(
            1 for p in positions
            if (safe_float(p.get("weight", 0)) or 0) > 0
        )
        assert non_zero > 0, (
            f"All {len(positions)} positions are 0.0%. "
            f"Optimizer still broken."
        )

    def test_description_not_stale(self):
        """R-04: regression — description showed +0.1 before B-04 fix"""
        d    = get_dashboard()
        bl   = d.get("businessLayer", {})
        desc = bl.get("research", {}).get("description", "")
        assert "+0.1" not in desc, (
            f"Business Layer still showing stale +0.1 growth: {desc}"
        )


class TestGDPNowcast:
    """R-04: GDP Nowcast section snapshot tests"""

    def test_yoy_plausible(self):
        """R-04: regression — YoY was +5.29% from summing not compounding"""
        d   = get_dashboard()
        gnc = d.get("gdpNowcast", {})
        yoy = safe_float(
            gnc.get("yoy", gnc.get("yoyAnnualised"))
        )
        assert yoy is not None, "GDP YoY missing"
        assert 0 <= yoy <= 6, (
            f"GDP YoY {yoy}% implausible. "
            f"Likely still summing not compounding quarterly rates."
        )

    def test_qoq_plausible(self):
        d   = get_dashboard()
        gnc = d.get("gdpNowcast", {})
        qoq = safe_float(
            gnc.get("qoqAnnualised", gnc.get("qoq"))
        )
        assert qoq is not None, "GDP QoQ missing"
        assert -10 <= qoq <= 10, f"GDP QoQ {qoq}% out of range"


class TestDataPipeline:
    """R-04: Data Pipeline section snapshot tests"""

    def test_freshness_endpoint_exists(self):
        r = requests.get(
            f"{BASE_URL}/api/data/freshness", timeout=10
        )
        assert r.status_code == 200, (
            f"Freshness endpoint returned {r.status_code}. "
            f"Endpoint not wired into main.py."
        )

    def test_csv_not_stale(self):
        r = requests.get(
            f"{BASE_URL}/api/data/freshness", timeout=10
        )
        assert r.status_code == 200
        d = r.json()
        assert d.get("csvIsStale") == False, (
            f"CSV is stale: age={d.get('csvAgeHours')} hours. "
            f"Pipeline not running correctly."
        )

    def test_refresh_endpoint_exists(self):
        r = requests.post(
            f"{BASE_URL}/api/data/refresh", timeout=10
        )
        assert r.status_code == 200, (
            f"Refresh endpoint returned {r.status_code}"
        )
        body = r.json()
        assert body.get("status") == "refresh_started", (
            f"Unexpected response: {body}"
        )


class TestSystemHealth:
    """R-04: System Health section snapshot tests"""

    def test_data_healthy_field_exists(self):
        """R-04: regression — health was HEALTHY during contradictions"""
        d       = get_dashboard()
        healthy = d.get("_dataHealthy")
        assert healthy is not None, (
            "_dataHealthy field missing from dashboard response. "
            "validate_dashboard_snapshot not wired into endpoint."
        )

    def test_no_data_integrity_errors(self):
        d      = get_dashboard()
        errors = d.get("_dataErrors")
        assert errors is not None, (
            "_dataErrors field missing. "
            "validate_dashboard_snapshot not wired into endpoint."
        )
        assert len(errors) == 0, (
            f"{len(errors)} data integrity errors: {errors}"
        )

    def test_healthy_false_when_errors_exist(self):
        """
        R-04: if _dataErrors is non-empty then _dataHealthy must be False.
        System cannot be healthy while reporting data errors.
        """
        d       = get_dashboard()
        healthy = d.get("_dataHealthy", True)
        errors  = d.get("_dataErrors", [])
        if len(errors) > 0:
            assert healthy == False, (
                f"System claims HEALTHY but has {len(errors)} errors. "
                f"Health check not reading from _dataErrors."
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
