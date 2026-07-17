"""Integration tests for production end-to-end flows.

Phase 5 Step 6: Verify dashboard, signals, risk, and diagnostics flows work correctly.
Tests verify validation orchestration and event logging are wired correctly.
"""
import pytest
import sys
import os
import importlib.util
from datetime import datetime

# Add api directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))


def load_module_directly(module_path, module_name):
    """Load a module directly without triggering __init__.py imports."""
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestValidationOrchestrationWired:
    """Test that validation orchestration is properly wired."""

    def test_validation_orchestrator_functions(self):
        """Validation orchestrator functions work correctly."""
        # Load directly to avoid services/__init__.py circular imports
        vo_path = os.path.join(
            os.path.dirname(__file__), '..', '..',
            'services', 'validation_orchestrator.py'
        )
        vo = load_module_directly(vo_path, 'validation_orchestrator')

        # Test basic validation
        result = vo.validate_dashboard_payload({
            "regime": {"current_regime": "goldilocks", "probability": 0.85},
            "signals": {"finalSignal": "Neutral", "conviction": 0.7},
            "recession": {"probability": 0.25},
            "timestamp": datetime.now().isoformat(),
        })

        assert isinstance(result, vo.ValidationResult)
        assert result.valid is True

    def test_validation_detects_invalid_regime(self):
        """Validation detects invalid regime values."""
        vo_path = os.path.join(
            os.path.dirname(__file__), '..', '..',
            'services', 'validation_orchestrator.py'
        )
        vo = load_module_directly(vo_path, 'validation_orchestrator')

        result = vo.validate_regime_payload({
            "current_regime": "invalid_regime",
            "probability": 0.85,
        })

        assert result.valid is False
        assert any("Invalid regime" in issue for issue in result.issues)

    def test_validation_detects_out_of_range_probability(self):
        """Validation detects probability out of range."""
        vo_path = os.path.join(
            os.path.dirname(__file__), '..', '..',
            'services', 'validation_orchestrator.py'
        )
        vo = load_module_directly(vo_path, 'validation_orchestrator')

        result = vo.validate_risk_payload({
            "probability": 1.5,  # Out of range
        })

        assert result.valid is False
        assert any("between 0 and 1" in issue for issue in result.issues)


class TestEventLoggerWired:
    """Test that event logger is properly wired."""

    def test_event_logger_functions_exist(self):
        """Event logger functions exist."""
        el_path = os.path.join(
            os.path.dirname(__file__), '..', '..',
            'services', 'event_logger.py'
        )
        el = load_module_directly(el_path, 'event_logger')

        # Verify functions exist
        assert callable(el.log_signal_event)
        assert callable(el.log_risk_event)
        assert callable(el.log_dashboard_event)
        assert callable(el.log_validation_event)
        assert callable(el.get_logging_status)

    def test_logging_status_returns_dict(self):
        """Logging status returns expected structure."""
        el_path = os.path.join(
            os.path.dirname(__file__), '..', '..',
            'services', 'event_logger.py'
        )
        el = load_module_directly(el_path, 'event_logger')

        status = el.get_logging_status()
        assert isinstance(status, dict)
        assert "enabled" in status
        assert "loggers_available" in status

    def test_event_logging_does_not_crash(self):
        """Event logging handles errors gracefully."""
        el_path = os.path.join(
            os.path.dirname(__file__), '..', '..',
            'services', 'event_logger.py'
        )
        el = load_module_directly(el_path, 'event_logger')

        # Should not raise exception even with minimal data
        try:
            el.log_signal_event(
                "test_signal",
                {"finalSignal": "Neutral", "conviction": 0.7},
                metadata={"test": True}
            )
        except Exception as e:
            pytest.fail(f"log_signal_event raised exception: {e}")


class TestRuntimeStatusWired:
    """Test that runtime status service is properly wired."""

    def test_runtime_status_functions_exist(self):
        """Runtime status functions exist."""
        rs_path = os.path.join(
            os.path.dirname(__file__), '..', '..',
            'services', 'runtime_status.py'
        )
        rs = load_module_directly(rs_path, 'runtime_status')

        # Verify functions exist
        assert callable(rs.get_cache_status)
        assert callable(rs.get_validation_status)
        assert callable(rs.get_data_freshness_status)
        assert callable(rs.get_scheduler_status)
        assert callable(rs.get_system_health)
        assert callable(rs.get_full_diagnostics)

    def test_system_health_returns_dict(self):
        """System health returns expected structure."""
        rs_path = os.path.join(
            os.path.dirname(__file__), '..', '..',
            'services', 'runtime_status.py'
        )
        rs = load_module_directly(rs_path, 'runtime_status')

        health = rs.get_system_health()
        assert isinstance(health, dict)
        assert "status" in health
        assert "timestamp" in health
        assert "components" in health

    def test_full_diagnostics_structure(self):
        """Full diagnostics has expected sections."""
        rs_path = os.path.join(
            os.path.dirname(__file__), '..', '..',
            'services', 'runtime_status.py'
        )
        rs = load_module_directly(rs_path, 'runtime_status')

        diagnostics = rs.get_full_diagnostics()
        assert isinstance(diagnostics, dict)

        # Check for expected sections
        expected_sections = ["status", "caches", "validation", "scheduler", "logging", "timestamp"]
        for section in expected_sections:
            assert section in diagnostics, f"Missing section: {section}"


class TestHandlersValidationWired:
    """Test that handlers have validation wired."""

    def test_dashboard_handler_imports_validation(self):
        """Dashboard handler imports validation orchestrator."""
        handler_path = os.path.join(
            os.path.dirname(__file__), '..', '..',
            'handlers', 'dashboard_handler.py'
        )

        with open(handler_path, 'r') as f:
            content = f.read()

        assert 'validate_dashboard_payload' in content
        assert 'log_dashboard_event' in content
        assert 'log_validation_event' in content

    def test_signal_handler_imports_validation(self):
        """Signal handler imports validation orchestrator."""
        handler_path = os.path.join(
            os.path.dirname(__file__), '..', '..',
            'handlers', 'signal_handler.py'
        )

        with open(handler_path, 'r') as f:
            content = f.read()

        assert 'validate_signal_payload' in content
        assert 'log_signal_event' in content
        assert 'log_validation_event' in content

    def test_risk_handler_imports_validation(self):
        """Risk handler imports validation orchestrator."""
        handler_path = os.path.join(
            os.path.dirname(__file__), '..', '..',
            'handlers', 'risk_handler.py'
        )

        with open(handler_path, 'r') as f:
            content = f.read()

        assert 'validate_risk_payload' in content
        assert 'log_risk_event' in content
        assert 'log_validation_event' in content


class TestConfigurationFlags:
    """Test that configuration flags are properly set."""

    def test_runtime_validation_enabled_by_default(self):
        """Runtime validation is enabled by default."""
        vo_path = os.path.join(
            os.path.dirname(__file__), '..', '..',
            'services', 'validation_orchestrator.py'
        )
        vo = load_module_directly(vo_path, 'validation_orchestrator')

        assert vo.ENABLE_RUNTIME_VALIDATION is True

    def test_event_logging_enabled_by_default(self):
        """Event logging is enabled by default."""
        el_path = os.path.join(
            os.path.dirname(__file__), '..', '..',
            'services', 'event_logger.py'
        )
        el = load_module_directly(el_path, 'event_logger')

        assert el.ENABLE_EVENT_LOGGING is True

    def test_config_has_validation_flags(self):
        """Config module has validation flags."""
        config_path = os.path.join(
            os.path.dirname(__file__), '..', '..',
            'config.py'
        )
        config = load_module_directly(config_path, 'config')

        assert hasattr(config, 'ENABLE_RUNTIME_VALIDATION')
        assert hasattr(config, 'ENABLE_EVENT_LOGGING')
        assert hasattr(config, 'ENABLE_DIAGNOSTICS')


class TestDiagnosticsEndpoint:
    """Test diagnostics endpoint structure."""

    def test_diagnostics_router_has_runtime_endpoint(self):
        """Diagnostics router has runtime endpoint."""
        diagnostics_path = os.path.join(
            os.path.dirname(__file__), '..', '..',
            'diagnostics.py'
        )

        with open(diagnostics_path, 'r') as f:
            content = f.read()

        assert '/runtime' in content or 'diagnostics_runtime' in content
        assert 'get_full_diagnostics' in content


class TestEnvConfiguration:
    """Test environment configuration."""

    def test_env_example_has_phase5_flags(self):
        """.env.example has Phase 5 configuration flags."""
        env_path = os.path.join(
            os.path.dirname(__file__), '..', '..', '..', '..',
            '.env.example'
        )

        # Handle case where file might be in different location
        if not os.path.exists(env_path):
            # Try alternative path
            alt_env_path = os.path.join(
                os.path.dirname(__file__), '..', '..', '..',
                '.env.example'
            )
            if os.path.exists(alt_env_path):
                env_path = alt_env_path
            else:
                pytest.skip(".env.example file not found")

        with open(env_path, 'r') as f:
            content = f.read()

        assert 'ENABLE_RUNTIME_VALIDATION' in content
        assert 'ENABLE_EVENT_LOGGING' in content
        assert 'ENABLE_DIAGNOSTICS' in content


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
