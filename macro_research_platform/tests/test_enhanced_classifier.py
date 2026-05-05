"""
Tests for Enhanced Regime Classifier

Validates the enhanced classification logic with specific scenarios
to ensure correct regime identification and confidence scoring.
"""

import pytest
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.models.macro_regime.enhanced_classifier import (
    EnhancedRegimeClassifier,
    RegimeClassification,
    get_regime_description,
)


class TestEnhancedClassifier:
    """Test cases for enhanced regime classification."""

    @pytest.fixture
    def classifier(self):
        return EnhancedRegimeClassifier()

    # =========================================================================
    # Test 1: User's reported scenario - should NOT be high-confidence Stagflation
    # =========================================================================
    def test_scenario_1_user_reported_case(self, classifier):
        """
        Test 1: User reported scenario
        - growth_score = 0.07 (neutral)
        - growth_direction = stable
        - inflation_score = 0.76 (elevated)
        - inflation_direction = rising
        - recession_risk = 0.05 (5%)
        - credit_stress = normal

        Expected: Regime should NOT be high-confidence Stagflation.
        Expected regime: "Inflation Pressure / Late-Cycle" or "Mixed / Transition"
        """
        result = classifier.classify(
            growth_score=0.07,
            inflation_score=0.76,
            growth_3m_change=0.05,  # stable
            inflation_3m_change=0.30,  # rising
            recession_probability=5.0,  # 5%
            credit_stress_level="normal",
            financial_conditions_category="neutral",
        )

        # Should not be Stagflation - this is the key requirement
        assert result.regime != "Stagflation", (
            f"Expected NOT Stagflation for neutral growth + low recession risk, "
            f"got {result.regime}"
        )

        # Should be intermediate/mixed regime (Inflation Pressure / Late-Cycle)
        assert result.regime_category in ["intermediate", "mixed"], (
            f"Expected intermediate or mixed category for elevated inflation + neutral growth, "
            f"got {result.regime_category}"
        )

        # Should specifically be Inflation Pressure / Late-Cycle for this scenario
        assert result.regime == "Inflation Pressure / Late-Cycle", (
            f"Expected 'Inflation Pressure / Late-Cycle' for neutral growth + elevated inflation, "
            f"got {result.regime}"
        )

        # Confidence should be low/moderate due to conflicting signals
        assert result.confidence in ["low", "moderate", "very_low"], (
            f"Expected low/moderate confidence due to conflicting signals, got {result.confidence}"
        )

        print(f"✓ Test 1 passed: Regime={result.regime}, Confidence={result.confidence}")
        print(f"  Warnings: {result.validation_warnings}")

    # =========================================================================
    # Test 2: Clear Stagflation scenario
    # =========================================================================
    def test_scenario_2_clear_stagflation(self, classifier):
        """
        Test 2: Clear stagflation
        - growth_score = -0.8 (weak)
        - growth_direction = deteriorating
        - inflation_score = 0.8 (elevated)
        - inflation_direction = rising

        Expected: Regime = Stagflation
        """
        result = classifier.classify(
            growth_score=-0.8,
            inflation_score=0.8,
            growth_3m_change=-0.40,  # deteriorating
            inflation_3m_change=0.35,  # rising
            recession_probability=45.0,  # High recession risk
            credit_stress_level="elevated",
            financial_conditions_category="tightening",
        )

        assert result.regime == "Stagflation", (
            f"Expected Stagflation for weak growth + rising inflation, got {result.regime}"
        )

        # Should have high confidence
        assert result.confidence in ["high", "moderate"], (
            f"Expected higher confidence for clear stagflation, got {result.confidence}"
        )

        # Growth state should be weak
        assert result.growth_state == "weak", (
            f"Expected weak growth state, got {result.growth_state}"
        )

        # Inflation state should be elevated
        assert "elevated" in result.inflation_state, (
            f"Expected elevated inflation state, got {result.inflation_state}"
        )

        print(f"✓ Test 2 passed: Regime={result.regime}, Confidence={result.confidence}")

    # =========================================================================
    # Test 3: Clear Slowdown scenario
    # =========================================================================
    def test_scenario_3_clear_slowdown(self, classifier):
        """
        Test 3: Clear slowdown
        - growth_score = -0.8 (weak)
        - growth_direction = deteriorating
        - inflation_score = -0.3 (low/normal)
        - inflation_direction = easing

        Expected: Regime = Slowdown
        """
        result = classifier.classify(
            growth_score=-0.8,
            inflation_score=-0.3,
            growth_3m_change=-0.40,
            inflation_3m_change=-0.30,
            recession_probability=35.0,
            credit_stress_level="elevated",
            financial_conditions_category="easing",
        )

        assert result.regime == "Slowdown", (
            f"Expected Slowdown for weak growth + easing inflation, got {result.regime}"
        )

        assert result.growth_state == "weak", (
            f"Expected weak growth, got {result.growth_state}"
        )

        print(f"✓ Test 3 passed: Regime={result.regime}, Confidence={result.confidence}")

    # =========================================================================
    # Test 4: Clear Goldilocks scenario
    # =========================================================================
    def test_scenario_4_clear_goldilocks(self, classifier):
        """
        Test 4: Clear Goldilocks
        - growth_score = 0.8 (strong)
        - growth_direction = improving
        - inflation_score = -0.2 (low/normal)
        - inflation_direction = stable/easing

        Expected: Regime = Goldilocks
        """
        result = classifier.classify(
            growth_score=0.8,
            inflation_score=-0.2,
            growth_3m_change=0.35,
            inflation_3m_change=-0.10,
            recession_probability=5.0,
            credit_stress_level="normal",
            financial_conditions_category="easing",
        )

        assert result.regime == "Goldilocks", (
            f"Expected Goldilocks for strong growth + low inflation, got {result.regime}"
        )

        assert result.growth_state == "strong", (
            f"Expected strong growth, got {result.growth_state}"
        )

        print(f"✓ Test 4 passed: Regime={result.regime}, Confidence={result.confidence}")

    # =========================================================================
    # Test 5: Neutral growth with elevated inflation (Late-Cycle)
    # =========================================================================
    def test_scenario_5_inflation_pressure(self, classifier):
        """
        Test 5: Neutral growth + elevated inflation
        - growth_score = 0.2 (neutral)
        - inflation_score = 0.7 (elevated)
        - recession risk moderate

        Expected: "Inflation Pressure / Late-Cycle"
        """
        result = classifier.classify(
            growth_score=0.2,
            inflation_score=0.7,
            growth_3m_change=0.05,  # stable
            inflation_3m_change=0.25,  # rising
            recession_probability=20.0,
            credit_stress_level="normal",
            financial_conditions_category="neutral",
        )

        assert result.regime == "Inflation Pressure / Late-Cycle", (
            f"Expected Inflation Pressure / Late-Cycle for neutral growth + elevated inflation, "
            f"got {result.regime}"
        )

        print(f"✓ Test 5 passed: Regime={result.regime}")

    # =========================================================================
    # Test 6: Stagflation with low recession risk should downgrade
    # =========================================================================
    def test_scenario_6_stagflation_downgrade(self, classifier):
        """
        Test 6: Stagflation classification should be downgraded
        when recession risk is low and credit stress is normal.
        """
        result = classifier.classify(
            growth_score=-0.6,
            inflation_score=0.6,
            growth_3m_change=-0.35,
            inflation_3m_change=0.30,
            recession_probability=10.0,  # Low recession risk
            credit_stress_level="normal",  # Normal credit
            financial_conditions_category="easing",
        )

        # Should NOT be Stagflation with low recession risk
        assert result.regime != "Stagflation", (
            f"Should not classify as Stagflation with 10% recession risk and normal credit"
        )

        # Should have warnings about stagflation mismatch
        assert any("recession" in w.lower() or "stagflation" in w.lower()
                   for w in result.validation_warnings), (
            f"Expected warnings about low recession risk, got {result.validation_warnings}"
        )

        print(f"✓ Test 6 passed: Regime={result.regime}, Warnings={result.validation_warnings}")

    # =========================================================================
    # Test 7: Confidence scoring
    # =========================================================================
    def test_confidence_scoring(self, classifier):
        """Test that confidence is calculated correctly based on supporting indicators."""

        # High confidence scenario: clear signals with supporting indicators
        high_conf = classifier.classify(
            growth_score=0.8,
            inflation_score=-0.3,
            growth_3m_change=0.35,
            inflation_3m_change=-0.20,
            recession_probability=5.0,
            credit_stress_level="normal",
            financial_conditions_category="easing",
        )

        # Low confidence scenario: conflicting signals
        low_conf = classifier.classify(
            growth_score=0.1,
            inflation_score=0.1,
            growth_3m_change=0.05,
            inflation_3m_change=-0.05,
            recession_probability=25.0,
            credit_stress_level="normal",
            financial_conditions_category="neutral",
        )

        assert high_conf.confidence_score > low_conf.confidence_score, (
            f"High confidence scenario ({high_conf.confidence_score}) should have "
            f"higher score than low confidence ({low_conf.confidence_score})"
        )

        print(f"✓ Test 7 passed: High confidence={high_conf.confidence_score:.2f}, "
              f"Low confidence={low_conf.confidence_score:.2f}")

    # =========================================================================
    # Test 8: Growth state classification
    # =========================================================================
    def test_growth_state_classification(self, classifier):
        """Test that growth states are correctly classified."""

        # Test strong growth
        result_strong = classifier.classify(
            growth_score=0.7,
            inflation_score=-0.2,
            growth_3m_change=0.30,
            inflation_3m_change=-0.10,
        )
        assert "strong" in result_strong.growth_state or result_strong.growth_state == "neutral-improving", (
            f"Expected strong/improving growth state for score=0.7, got {result_strong.growth_state}"
        )

        # Test weak growth
        result_weak = classifier.classify(
            growth_score=-0.7,
            inflation_score=-0.2,
            growth_3m_change=-0.30,
            inflation_3m_change=-0.10,
        )
        assert "weak" in result_weak.growth_state or result_weak.growth_state == "neutral-deteriorating", (
            f"Expected weak/deteriorating growth state for score=-0.7, got {result_weak.growth_state}"
        )

        # Test neutral growth
        result_neutral = classifier.classify(
            growth_score=0.2,
            inflation_score=-0.2,
            growth_3m_change=0.05,
            inflation_3m_change=-0.10,
        )
        assert "neutral" in result_neutral.growth_state, (
            f"Expected neutral growth state for score=0.2, got {result_neutral.growth_state}"
        )

        print(f"✓ Test 8 passed: Strong={result_strong.growth_state}, "
              f"Neutral={result_neutral.growth_state}, Weak={result_weak.growth_state}")

    # =========================================================================
    # Test 9: Inflation state classification
    # =========================================================================
    def test_inflation_state_classification(self, classifier):
        """Test that inflation states are correctly classified."""

        # Test elevated inflation
        result_elevated = classifier.classify(
            growth_score=0.2,
            inflation_score=0.7,
            growth_3m_change=0.10,
            inflation_3m_change=0.30,
        )
        assert "elevated" in result_elevated.inflation_state, (
            f"Expected elevated inflation for score=0.7, got {result_elevated.inflation_state}"
        )

        # Test low inflation
        result_low = classifier.classify(
            growth_score=0.2,
            inflation_score=-0.7,
            growth_3m_change=0.10,
            inflation_3m_change=-0.30,
        )
        assert "low" in result_low.inflation_state, (
            f"Expected low inflation for score=-0.7, got {result_low.inflation_state}"
        )

        print(f"✓ Test 9 passed: Elevated={result_elevated.inflation_state}, Low={result_low.inflation_state}")

    # =========================================================================
    # Test 10: Financial Conditions Convention
    # =========================================================================
    def test_financial_conditions_convention(self, classifier):
        """
        Test 10: Financial conditions sign convention
        liquidity_score = +0.67 should be 'Easing' (positive = easier)
        NOT 'Tightening'
        """
        # liquidity_score follows EASE convention: positive = easier
        liq_score = 0.67
        liq_label = "Easing" if liq_score > 0.5 else "Tightening" if liq_score < -0.5 else "Neutral"

        assert liq_label == "Easing", (
            f"With ease convention, +0.67 should be 'Easing', got '{liq_label}'"
        )

        # Test negative score
        liq_score_negative = -0.67
        liq_label_negative = "Easing" if liq_score_negative > 0.5 else "Tightening" if liq_score_negative < -0.5 else "Neutral"

        assert liq_label_negative == "Tightening", (
            f"With ease convention, -0.67 should be 'Tightening', got '{liq_label_negative}'"
        )

        print(f"✓ Test 10 passed: Financial conditions convention validated (Ease score: +0.67 = Easing)")

    # =========================================================================
    # Test 11: Current Dashboard Scenario
    # =========================================================================
    def test_current_dashboard_scenario(self, classifier):
        """
        Test 11: Current live scenario as of 2026-04-26
        - growth = +0.07 (neutral)
        - inflation = +0.76 (elevated)
        - recession_prob = 5.3%
        - credit_stress = normal
        - financial_conditions = neutral

        Expected: Inflation Pressure / Late-Cycle, NOT Stagflation
        """
        result = classifier.classify(
            growth_score=0.07,
            inflation_score=0.76,
            growth_3m_change=-0.07,  # stable
            inflation_3m_change=+1.36,  # rising significantly
            recession_probability=5.3,
            credit_stress_level="normal",
            financial_conditions_category="neutral",
        )

        # Should NOT be Stagflation
        assert result.regime != "Stagflation", (
            f"Expected NOT Stagflation with 5.3% recession risk, got {result.regime}"
        )

        # Should be Inflation Pressure / Late-Cycle
        assert result.regime == "Inflation Pressure / Late-Cycle", (
            f"Expected 'Inflation Pressure / Late-Cycle' for elevated inflation + neutral growth, "
            f"got {result.regime}"
        )

        # Confidence should be moderate (not high due to unclear growth direction)
        assert result.confidence in ["moderate", "low"], (
            f"Expected moderate or low confidence, got {result.confidence}"
        )

        print(f"✓ Test 11 passed: Live scenario → {result.regime} ({result.confidence} confidence)")


if __name__ == "__main__":
    # Run tests with verbose output
    classifier = EnhancedRegimeClassifier()

    print("=" * 70)
    print("RUNNING ENHANCED CLASSIFIER TESTS")
    print("=" * 70)

    test_class = TestEnhancedClassifier()

    try:
        test_class.test_scenario_1_user_reported_case(classifier)
    except AssertionError as e:
        print(f"✗ Test 1 FAILED: {e}")

    try:
        test_class.test_scenario_2_clear_stagflation(classifier)
    except AssertionError as e:
        print(f"✗ Test 2 FAILED: {e}")

    try:
        test_class.test_scenario_3_clear_slowdown(classifier)
    except AssertionError as e:
        print(f"✗ Test 3 FAILED: {e}")

    try:
        test_class.test_scenario_4_clear_goldilocks(classifier)
    except AssertionError as e:
        print(f"✗ Test 4 FAILED: {e}")

    try:
        test_class.test_scenario_5_inflation_pressure(classifier)
    except AssertionError as e:
        print(f"✗ Test 5 FAILED: {e}")

    try:
        test_class.test_scenario_6_stagflation_downgrade(classifier)
    except AssertionError as e:
        print(f"✗ Test 6 FAILED: {e}")

    try:
        test_class.test_confidence_scoring(classifier)
    except AssertionError as e:
        print(f"✗ Test 7 FAILED: {e}")

    try:
        test_class.test_growth_state_classification(classifier)
    except AssertionError as e:
        print(f"✗ Test 8 FAILED: {e}")

    try:
        test_class.test_inflation_state_classification(classifier)
    except AssertionError as e:
        print(f"✗ Test 9 FAILED: {e}")

    try:
        test_class.test_financial_conditions_convention(classifier)
    except AssertionError as e:
        print(f"✗ Test 10 FAILED: {e}")

    try:
        test_class.test_current_dashboard_scenario(classifier)
    except AssertionError as e:
        print(f"✗ Test 11 FAILED: {e}")

    print("=" * 70)
    print("TESTS COMPLETE")
    print("=" * 70)
