"""Unit tests for validation orchestrator."""
import pytest
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Import directly from file to avoid triggering services/__init__.py
import importlib.util
spec = importlib.util.spec_from_file_location(
    "validation_orchestrator",
    os.path.join(os.path.dirname(__file__), '..', 'services', 'validation_orchestrator.py')
)
vo_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vo_module)

ValidationResult = vo_module.ValidationResult
validate_regime_payload = vo_module.validate_regime_payload
validate_signal_payload = vo_module.validate_signal_payload
validate_risk_payload = vo_module.validate_risk_payload
validate_dashboard_payload = vo_module.validate_dashboard_payload
validate_market_payload = vo_module.validate_market_payload
validate_business_payload = vo_module.validate_business_payload
get_validation_status = vo_module.get_validation_status


class TestValidationResult:
    """Test ValidationResult container."""

    def test_valid_result(self):
        result = ValidationResult(valid=True)
        assert result.valid is True
        assert result.issues == []
        assert "timestamp" in result.to_dict()

    def test_invalid_result_with_issues(self):
        result = ValidationResult(valid=False, issues=["Field X is missing"])
        assert result.valid is False
        assert result.issues == ["Field X is missing"]

    def test_bool_conversion(self):
        assert bool(ValidationResult(valid=True)) is True
        assert bool(ValidationResult(valid=False)) is False


class TestValidateRegimePayload:
    """Test regime payload validation."""

    def test_valid_regime_payload(self):
        payload = {
            "current_regime": "goldilocks",
            "probability": 0.85,
        }
        result = validate_regime_payload(payload)
        assert result.valid is True

    def test_invalid_regime_value(self):
        payload = {
            "current_regime": "invalid_regime",
            "probability": 0.85,
        }
        result = validate_regime_payload(payload)
        assert result.valid is False
        assert any("Invalid regime" in issue for issue in result.issues)

    def test_invalid_probability_too_high(self):
        payload = {
            "current_regime": "goldilocks",
            "probability": 1.5,
        }
        result = validate_regime_payload(payload)
        assert result.valid is False
        assert any("between 0 and 1" in issue for issue in result.issues)

    def test_invalid_probability_negative(self):
        payload = {
            "current_regime": "goldilocks",
            "probability": -0.5,
        }
        result = validate_regime_payload(payload)
        assert result.valid is False

    def test_empty_payload(self):
        result = validate_regime_payload({})
        assert result.valid is True  # No required fields


class TestValidateSignalPayload:
    """Test signal payload validation."""

    def test_valid_signal_payload(self):
        payload = {
            "signal_value": 0.5,
            "conviction": 0.8,
            "finalSignal": "Bullish",
            "scores": {
                "growth": 0.5,
                "inflation": -0.3,
            }
        }
        result = validate_signal_payload(payload)
        assert result.valid is True

    def test_signal_value_out_of_range(self):
        payload = {
            "signal_value": 1.5,  # Out of range
        }
        result = validate_signal_payload(payload)
        assert result.valid is False
        assert any("-1 and 1" in issue for issue in result.issues)

    def test_conviction_out_of_range(self):
        payload = {
            "conviction": -0.5,  # Out of range
        }
        result = validate_signal_payload(payload)
        assert result.valid is False

    def test_invalid_final_signal(self):
        payload = {
            "finalSignal": "InvalidSignal",
        }
        result = validate_signal_payload(payload)
        assert result.valid is False

    def test_scores_out_of_range(self):
        payload = {
            "scores": {
                "growth": 2.0,  # Out of range
            }
        }
        result = validate_signal_payload(payload)
        assert result.valid is False


class TestValidateRiskPayload:
    """Test risk payload validation."""

    def test_valid_risk_payload(self):
        payload = {
            "probability": 0.25,
            "models": {
                "logistic": {"probability": 0.22, "signal": "Low"},
                "sahm": {"probability": 0.18, "signal": "Low"},
            },
            "sharpe": 0.85,
            "maxDrawdown": -8.5,
        }
        result = validate_risk_payload(payload)
        assert result.valid is True

    def test_invalid_recession_probability(self):
        payload = {
            "probability": 1.5,  # Out of range
        }
        result = validate_risk_payload(payload)
        assert result.valid is False

    def test_invalid_model_probability(self):
        payload = {
            "models": {
                "logistic": {"probability": -0.5},  # Out of range
            },
        }
        result = validate_risk_payload(payload)
        assert result.valid is False

    def test_non_numeric_sharpe(self):
        payload = {
            "sharpe": "not_a_number",
        }
        result = validate_risk_payload(payload)
        assert result.valid is False


class TestValidateDashboardPayload:
    """Test dashboard payload validation."""

    def test_valid_dashboard_payload(self):
        payload = {
            "regime": {"current_regime": "goldilocks", "probability": 0.85},
            "signals": {"signal_value": 0.5, "conviction": 0.8},
            "recession": {"probability": 0.25},
            "timestamp": "2026-05-07T10:00:00Z",
        }
        result = validate_dashboard_payload(payload)
        assert result.valid is True
        assert "sections_validated" in result.metadata

    def test_missing_timestamp(self):
        payload = {
            "regime": {"current_regime": "goldilocks"},
        }
        result = validate_dashboard_payload(payload)
        assert result.valid is False
        assert any("timestamp" in issue for issue in result.issues)

    def test_invalid_nested_regime(self):
        payload = {
            "regime": {"current_regime": "invalid", "probability": 0.85},
            "timestamp": "2026-05-07T10:00:00Z",
        }
        result = validate_dashboard_payload(payload)
        assert result.valid is False

    def test_multiple_validation_issues(self):
        payload = {
            "regime": {"current_regime": "invalid"},
            "signals": {"signal_value": 2.0},  # Out of range
            "recession": {"probability": 1.5},  # Out of range
        }
        result = validate_dashboard_payload(payload)
        assert result.valid is False
        assert len(result.issues) >= 3  # Multiple issues


class TestValidateMarketPayload:
    """Test market/prices payload validation."""

    def test_valid_market_payload(self):
        payload = {
            "prices": {
                "SPY": {"price": 450.0, "change": 1.5},
            },
            "rates": {
                "TENYR": 4.5,
            },
        }
        result = validate_market_payload(payload)
        assert result.valid is True

    def test_empty_market_payload(self):
        result = validate_market_payload({})
        assert result.valid is True


class TestValidateBusinessPayload:
    """Test business/trade payload validation."""

    def test_valid_business_payload(self):
        payload = {
            "recommendation": "BUY",
            "conviction": 0.85,
            "tradeIdeas": [],
        }
        result = validate_business_payload(payload)
        assert result.valid is True

    def test_invalid_recommendation(self):
        payload = {
            "recommendation": "HOLD_AND_PRAY",
        }
        result = validate_business_payload(payload)
        assert result.valid is False

    def test_invalid_conviction(self):
        payload = {
            "conviction": 2.0,  # Out of range
        }
        result = validate_business_payload(payload)
        assert result.valid is False


class TestGetValidationStatus:
    """Test validation status reporting."""

    def test_validation_status_structure(self):
        status = get_validation_status()
        assert "enabled" in status
        assert "validators_available" in status
        assert isinstance(status["validators_available"], dict)

    def test_validators_listed(self):
        status = get_validation_status()
        validators = status["validators_available"]

        # If validators loaded successfully, check expected keys
        if "error" not in validators:
            expected = ["regime", "signal", "recession", "conviction", "expected_returns", "portfolio", "momentum", "nowcast"]
            for validator in expected:
                assert validator in validators
        else:
            # If import failed (e.g., missing asyncpg), just verify error is reported
            assert "error" in validators


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
