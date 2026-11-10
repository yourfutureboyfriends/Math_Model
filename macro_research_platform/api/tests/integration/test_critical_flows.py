"""Schema contract for the critical dashboard payloads, plus live endpoint checks.

The in-process classes validate the Pydantic models and their validators — required fields,
score ranges, NaN handling, confidence clamping. They build payloads as literals rather than
calling the API, so they prove the schema rejects bad shapes; they do NOT prove any endpoint
returns one. The live class at the bottom does that, and is opt-in (MACRO_LIVE_BACKEND=1)
like api/tests/integration/test_runtime_routes.py, because building a real dashboard needs
live data and takes 15-20s cold.

This file previously claimed to test "dashboard, signals, risk, and diagnostics endpoints"
while making no request at all, so a handler returning anything would have passed.
"""
import pytest
import sys
import os
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from api.schemas.models import (
    DashboardData,
    RegimeData,
    SignalsData,
    RecessionData,
    Scores,
    SignalDetails,
)


class TestDashboardEndpoint:
    """Test dashboard endpoint critical flows."""

    def test_dashboard_data_structure(self):
        """Verify DashboardData can be created with all required fields."""
        # This mimics what the handler should return
        dashboard = DashboardData(
            regime=RegimeData(
                current="Goldilocks",
                confidence="High",
                confidenceScore=0.85,
                duration=12,
                history=[{"date": "2024-01-01", "regime": "Goldilocks"}],
                interpretations=[{"factor": "Growth", "impact": "Positive"}]
            ),
            keyMetrics={
                "growth": {"value": 2.5, "formatted": "2.5%", "direction": "up", "sparklineData": []},
                "inflation": {"value": 2.1, "formatted": "2.1%", "direction": "stable", "sparklineData": []},
                "liquidity": {"value": 0.5, "formatted": "0.5", "direction": "down", "sparklineData": []},
                "risk": {"value": 0.3, "formatted": "30%", "direction": "stable", "sparklineData": []},
                "recession": {"value": 0.15, "formatted": "15%", "direction": "stable", "sparklineData": []},
                "regimeDuration": {"text": "12 months", "className": "neutral"}
            },
            scores=Scores(growth=65, inflation=45, liquidity=50, risk=30),
            recession=RecessionData(
                probability=0.15,
                level="Low",
                logisticProb=0.12,
                emProbitProb=0.18,
                sahmValue=0.0,
                sahmSignal="No Signal",
                description="Low probability",
                components=[{"name": "Labor Market", "value": 0.1, "contribution": 0.05}],
                history=[{"date": "2024-01-01", "probability": 0.1}]
            ),
            signals=SignalsData(
                finalSignal="RISK_ON",
                growth=SignalDetails(latestScore=0.7, threeMonthChange="+0.2", score=0.7, threeMonth=0.2, state="Strong", direction="improving", interpretation="Growth positive"),
                inflation=SignalDetails(latestScore=0.3, threeMonthChange="+0.1", score=0.3, threeMonth=0.1, state="Neutral", direction="stable", interpretation="Inflation moderate"),
                liquidity=SignalDetails(latestScore=0.5, threeMonthChange="+0.2", score=0.5, threeMonth=0.2, state="Neutral", direction="stable", interpretation="Liquidity adequate"),
                risk=SignalDetails(latestScore=0.3, threeMonthChange="0.0", score=0.3, threeMonth=0.0, state="Neutral", direction="stable", interpretation="Risk moderate")
            ),
            sectorAllocation={"sectors": [], "regime": "Goldilocks", "confidence": 0.75, "totalScore": 1.75},
            riskParity={
                "holdings": [],
                "totalHoldings": 0,
                "lastRebalanced": datetime.now().isoformat(),
                "methodology": "Placeholder",
                "regimeAdjustmentActive": False,
                "lastUpdated": datetime.now().isoformat()
            },
            expectedReturns={
                "sectors": [],
                "weightedPortfolioReturn": 0.0,
                "methodology": "Placeholder",
                "lastUpdated": datetime.now().isoformat()
            },
            metadata={
                "latestDate": datetime.now().isoformat(),
                "lastRefreshed": datetime.now().isoformat(),
                "dataStatus": "current",
                "daysSinceUpdate": 0,
                "mode": "live"
            },
            timestamp=datetime.now().isoformat(),
            mode="live"
        )

        assert dashboard.regime.current == "Goldilocks"
        assert dashboard.regime.confidenceScore == 0.85
        assert dashboard.scores.growth == 65
        assert dashboard.recession.probability == 0.15
        assert dashboard.signals.finalSignal == "RISK_ON"

    def test_dashboard_scores_validation(self):
        """Test that scores are validated and clamped to 0-100."""
        # Test with out-of-range values - validators should clamp
        scores = Scores(growth=150, inflation=-20, liquidity=50, risk=200)
        assert scores.growth == 100.0  # Clamped to max
        assert scores.inflation == 0.0  # Clamped to min
        assert scores.liquidity == 50.0
        assert scores.risk == 100.0  # Clamped to max

    def test_dashboard_scores_handle_nan(self):
        """Test that NaN values are converted to defaults."""
        scores = Scores(growth=float('nan'), inflation=float('inf'), liquidity=float('-inf'), risk=None)
        assert scores.growth == 50.0
        assert scores.inflation == 50.0
        assert scores.liquidity == 50.0
        assert scores.risk == 50.0


class TestSignalsEndpoint:
    """Test signals endpoint critical flows."""

    def test_signals_data_structure(self):
        """Verify SignalsData structure is valid."""
        signals = SignalsData(
            finalSignal="RISK_ON",
            growth=SignalDetails(
                latestScore=0.7,
                threeMonthChange="+0.2",
                score=0.7,
                threeMonth=0.2,
                state="Strong",
                direction="improving",
                interpretation="Growth signals positive",
                history=[0.6, 0.65, 0.7],
                historyLabels=["Jan", "Feb", "Mar"]
            ),
            inflation=SignalDetails(latestScore=0.3, threeMonthChange="+0.1", score=0.3, threeMonth=0.1, state="Neutral", direction="stable", interpretation="Inflation moderate"),
            liquidity=SignalDetails(latestScore=0.5, threeMonthChange="+0.2", score=0.5, threeMonth=0.2, state="Neutral", direction="stable", interpretation="Liquidity adequate"),
            risk=SignalDetails(latestScore=0.3, threeMonthChange="0.0", score=0.3, threeMonth=0.0, state="Neutral", direction="stable", interpretation="Risk moderate")
        )

        assert signals.finalSignal == "RISK_ON"
        assert signals.growth.direction == "improving"
        assert len(signals.growth.history) == 3

    def test_signal_details_validation(self):
        """Test SignalDetails validation."""
        # NaN values should be converted to 0.0
        details = SignalDetails(latestScore=float('nan'), threeMonthChange="0.0", score=float('nan'), threeMonth=0.0, state="Neutral", direction="stable")
        assert details.latestScore == 0.0
        assert details.threeMonthChange == "0.0"


class TestRiskEndpoint:
    """Test risk/recession endpoint critical flows."""

    def test_recession_data_structure(self):
        """Verify RecessionData structure is valid."""
        recession = RecessionData(
            probability=0.25,
            level="Medium",
            logisticProb=0.22,
            emProbitProb=0.28,
            sahmValue=0.3,
            sahmSignal="No Signal",
            description="Medium probability",
            components=[
                {"name": "Labor Market", "value": 0.1, "contribution": 0.05},
                {"name": "Yield Curve", "value": -0.2, "contribution": 0.02}
            ],
            history=[
                {"date": "2024-01-01", "probability": 0.1},
                {"date": "2024-02-01", "probability": 0.15}
            ]
        )

        assert recession.probability == 0.25
        assert recession.level == "Medium"
        assert len(recession.components) == 2

    def test_recession_probability_validation(self):
        """Test that probabilities are clamped to 0-1."""
        # Out of range and NaN values should be handled
        recession = RecessionData(
            probability=1.5,  # Should be clamped to 1.0
            level="High",
            logisticProb=-0.5,  # Should be clamped to 0.0
            emProbitProb=float('nan'),  # Should become None (unavailable), not a fake 0%
            sahmValue=0.0,
            sahmSignal="No Signal",
            description="Test",
            components=[],
            history=[]
        )
        assert recession.probability == 1.0
        assert recession.logisticProb == 0.0
        assert recession.emProbitProb is None


class TestRegimeEndpoint:
    """Test regime endpoint critical flows."""

    def test_regime_data_validation(self):
        """Test RegimeData validation."""
        # Test NaN confidenceScore handling
        regime = RegimeData(
            current="Goldilocks",
            confidence="High",
            confidenceScore=float('nan'),
            duration=12,
            history=[],
            interpretations=[]
        )
        assert regime.confidenceScore == 0.0

    def test_regime_confidence_score_clamping(self):
        """Test confidenceScore is properly validated."""
        regime = RegimeData(
            current="Goldilocks",
            confidence="High",
            confidenceScore="0.85",  # String should be converted
            duration=12,
            history=[],
            interpretations=[]
        )
        assert isinstance(regime.confidenceScore, float)
        assert regime.confidenceScore == 0.85


class TestErrorHandling:
    """Test error handling in critical flows."""

    def test_dashboard_with_partial_data(self):
        """Test that dashboard can handle partial/missing data gracefully."""
        # This tests the validator's ability to handle edge cases
        scores = Scores()  # Use all defaults
        assert scores.growth == 50.0
        assert scores.inflation == 50.0
        assert scores.liquidity == 50.0
        assert scores.risk == 50.0

    def test_signal_with_empty_history(self):
        """Test SignalDetails handles empty history."""
        details = SignalDetails(latestScore=0.5, threeMonthChange="+0.1", score=0.5, threeMonth=0.1, state="Neutral", direction="stable", history=None)
        assert details.history == []


# ── Live endpoint checks (opt-in) ────────────────────────────────────────────
# Mirrors api/tests/integration/test_runtime_routes.py: skipped unless opted in, and a
# refused connection or a start-up timeout skips rather than fails.
LIVE = os.getenv("MACRO_LIVE_BACKEND") == "1"
BASE = os.getenv("MACRO_BACKEND_URL", "http://localhost:8000")


@pytest.fixture(scope="module")
def live():
    if not LIVE:
        pytest.skip("set MACRO_LIVE_BACKEND=1 to check the running server's payloads")
    import time
    import requests
    deadline = time.time() + 90
    while time.time() < deadline:                   # wait out start-up and cache warm-up
        try:
            if requests.get(f"{BASE}/api/health", timeout=5).status_code == 200:
                return requests
        except requests.RequestException:
            pass
        time.sleep(2)
    pytest.skip(f"no backend answered on {BASE} within 90s")


class TestLiveDashboardContract:
    """The real handler's payload must satisfy the schema the literals above describe."""

    def test_dashboard_response_validates_against_the_schema(self, live):
        r = live.get(f"{BASE}/api/dashboard", timeout=60)
        assert r.status_code == 200, f"GET /api/dashboard -> {r.status_code}: {r.text[:200]}"
        # model_validate raises on any shape the schema rejects, so this fails if the
        # handler drifts from DashboardData — which the literal-based tests cannot detect.
        dashboard = DashboardData.model_validate(r.json())

        assert dashboard.regime is not None and dashboard.regime.current
        assert 0.0 <= dashboard.regime.confidenceScore <= 1.0
        for name in ("growth", "inflation", "liquidity", "risk"):
            score = getattr(dashboard.scores, name)
            assert 0.0 <= score <= 100.0, f"scores.{name}={score} outside 0-100"
        assert dashboard.metadata.dataStatus, "metadata.dataStatus must say where the data came from"
        assert dashboard.timestamp

    def test_dashboard_sectors_carry_real_rationales(self, live):
        r = live.get(f"{BASE}/api/dashboard", timeout=60)
        assert r.status_code == 200, r.text[:200]
        dashboard = DashboardData.model_validate(r.json())
        sectors = (dashboard.sectorAllocation.sectors if dashboard.sectorAllocation else []) or []
        assert sectors, "a live dashboard with no sector allocation is not a passing contract"
        for s in sectors:
            assert s.rationale and len(s.rationale) >= 10, f"{s.name}: rationale {s.rationale!r}"
            assert "0.00x" not in s.rationale, f"{s.name}: rationale is an unfilled template"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
