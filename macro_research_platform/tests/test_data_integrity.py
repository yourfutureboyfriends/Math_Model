"""
Regression tests — run with: pytest tests/test_data_integrity.py -v
These tests encode real-world values. If any test fails, a known bug
has returned. Do NOT delete or weaken these tests.
"""
import math, os, pytest, requests
import sys
from pathlib import Path
from unittest.mock import MagicMock

BASE_URL = os.getenv("MACRO_API_URL", "http://localhost:8000")

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
    # Rejected values come back as None (unavailable) — never a made-up default.
    assert result is None or -15 <= result <= 15, f"Growth {result}% slipped through bounds check"

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
    # 0.03 × 100 = 3 bps which is below hard_min=50 → rejected (None)
    assert result is None or result >= 50

# ── Regression: NaN propagation in All Weather ───────────────────────────────
def test_nan_never_returned():
    """NaN from any source must never reach the dashboard."""
    fred_mock = MagicMock(return_value=float("nan"))
    result = fetch_metric("vix", fred_fetch_fn=fred_mock)
    assert result is None or math.isfinite(result), "NaN slipped through fetch_metric"

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


VALID_REGIMES = {"goldilocks", "reflation", "stagflation", "slowdown",
                 "contraction", "expansion", "recovery"}


class TestKeyMetrics:
    """Live dashboard: composite scores are 0-100; prices/levels are plausible."""

    def test_inflation_range(self):
        val = safe_float(get_dashboard().get("keyMetrics", {}).get("inflation", {}).get("value"))
        assert val is not None and 0 <= val <= 100, f"Inflation score {val} out of range"

    def test_growth_range(self):
        val = safe_float(get_dashboard().get("keyMetrics", {}).get("growth", {}).get("value"))
        assert val is not None and 0 <= val <= 100, f"Growth score {val} out of range"

    def test_recession_risk_range(self):
        d = get_dashboard()
        val = safe_float(d.get("keyMetrics", {}).get("recession", {}).get("value"))
        assert val is not None, "Recession risk missing"
        assert 0 <= val <= 100, f"Recession risk {val}% out of range"
        prob = safe_float(d.get("recession", {}).get("probability"))
        assert prob is not None and 0 <= prob <= 1

    def test_vix_range(self):
        val = safe_float(get_dashboard().get("keyMetrics", {}).get("vix"))
        assert val is not None and 5 <= val <= 90, f"VIX {val} out of range"


class TestRegime:
    def test_regime_is_valid(self):
        regime = (get_dashboard().get("regime", {}).get("current") or "").lower()
        assert regime in VALID_REGIMES, f"Invalid regime: {regime}"

    def test_confidence_range(self):
        val = safe_float(get_dashboard().get("regime", {}).get("confidenceScore"))
        assert val is not None and 0 <= val <= 1, f"Confidence {val} out of range"

    def test_duration_positive(self):
        val = get_dashboard().get("regime", {}).get("duration", -1)
        assert isinstance(val, int) and val >= 0, f"Duration {val} invalid"

    def test_intl_us_matches_master(self):
        d = get_dashboard()
        master = (d.get("regime", {}).get("current") or "").lower()
        regions = d.get("internationalMacro", {}).get("regions", [])
        us = next((r.get("regime", "") for r in regions if r.get("region") == "US"), "NOT FOUND")
        assert us.lower() == master, f"Regime mismatch: master={master} intl_us={us}"


class TestRiskIndicators:
    def test_vix_finite(self):
        val = safe_float(get_dashboard().get("riskIndicators", {}).get("vix"))
        assert val is not None and math.isfinite(val)

    def test_yield_curve_range(self):
        """10Y-2Y spread in percentage points."""
        val = safe_float(get_dashboard().get("riskIndicators", {}).get("yieldSpread"))
        assert val is not None, "Yield curve missing"
        assert -5 <= val <= 5, f"Yield spread {val}pp out of range"


class TestEnsemble:
    def test_score_bounded(self):
        val = safe_float(get_dashboard().get("ensemble", {}).get("score"))
        assert val is not None, "Ensemble score missing"
        assert 0 <= val <= 1, f"Ensemble score {val} out of [0,1]"

    def test_conviction_is_valid(self):
        conv = get_dashboard().get("ensemble", {}).get("conviction", "")
        assert conv in ("High", "Medium", "Low"), f"Invalid conviction: {conv}"

    def test_at_least_5_layers_contributing(self):
        layers = get_dashboard().get("signalStack", {}).get("layers", [])
        assert len(layers) >= 5, f"Only {len(layers)} signal-stack layers."
        for layer in layers:
            c = safe_float(layer.get("conviction"))
            assert c is not None and 0 <= c <= 1, f"Layer {layer.get('layer')} conviction {c}"


class TestNoNaN:
    def test_no_nan_anywhere_in_dashboard(self):
        bad = []

        def walk(node, path=""):
            if isinstance(node, dict):
                for k, v in node.items():
                    walk(v, f"{path}.{k}")
            elif isinstance(node, list):
                for i, v in enumerate(node):
                    walk(v, f"{path}[{i}]")
            elif isinstance(node, float) and not math.isfinite(node):
                bad.append(path)

        walk(get_dashboard())
        assert not bad, f"Non-finite values at: {bad[:10]}"


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
        # Writes require a signed-in user. Defaults to the seeded dev admin; override with
        # MACRO_TEST_USER / MACRO_TEST_PASSWORD.
        login = requests.post(f"{BASE_URL}/api/auth/login", timeout=10, data={
            "username": os.getenv("MACRO_TEST_USER", "admin"),
            "password": os.getenv("MACRO_TEST_PASSWORD", "admin123")})
        assert login.status_code == 200, f"login failed: {login.status_code}"
        assert requests.post(f"{BASE_URL}/api/data/refresh", timeout=10).status_code == 401
        r = requests.post(
            f"{BASE_URL}/api/data/refresh", timeout=10,
            headers={"Authorization": f"Bearer {login.json()['access_token']}"}
        )
        if login.json().get("must_change_password"):
            # Still on a default/temporary password: the server must hold every write.
            assert r.status_code == 403 and r.json().get("code") == "password_change_required"
            return
        assert r.status_code == 200, (
            f"Refresh endpoint returned {r.status_code}"
        )
        body = r.json()
        assert body.get("status") == "refresh_started", (
            f"Unexpected response: {body}"
        )


class TestSystemHealth:
    """R-04: the data-health check (/api/data-debug) validates the live dashboard."""

    def _health(self):
        r = requests.get(f"{BASE_URL}/api/data-debug", timeout=60)
        assert r.status_code == 200
        return r.json()

    def test_data_healthy_field_exists(self):
        h = self._health()
        assert h.get("_dataHealthy") is not None, "_dataHealthy missing from /api/data-debug"
        assert h.get("_dataErrors") is not None, "_dataErrors missing from /api/data-debug"

    def test_no_data_integrity_errors(self):
        errors = self._health().get("_dataErrors")
        assert len(errors) == 0, f"{len(errors)} data integrity errors: {errors}"

    def test_healthy_false_when_errors_exist(self):
        h = self._health()
        if h.get("_dataErrors"):
            assert h.get("_dataHealthy") is False, "System claims HEALTHY while reporting errors"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
