"""Test error handling utilities."""
import pytest
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.utils.errors import (
    safe_execute,
    DataValidationError,
    DataFetchError,
    CalculationError,
    log_and_return
)


def test_safe_execute_with_success():
    """Test safe_execute returns value on success."""
    result = safe_execute(lambda: 42, default=0)
    assert result == 42


def test_safe_execute_with_value_error():
    """Test safe_execute returns default on ValueError."""
    def raise_error():
        raise ValueError("test error")

    result = safe_execute(raise_error, default=99)
    assert result == 99


def test_safe_execute_with_key_error():
    """Test safe_execute returns default on KeyError."""
    def raise_error():
        raise KeyError("missing_field")

    result = safe_execute(raise_error, default="fallback")
    assert result == "fallback"


def test_safe_execute_with_custom_exception():
    """Test safe_execute handles custom exceptions."""
    def raise_error():
        raise DataValidationError("validation failed")

    result = safe_execute(raise_error, default=None)
    assert result is None


def test_log_and_return():
    """Test log_and_return utility."""
    error = ValueError("test")
    result = log_and_return(error, default=100, context="Test context")
    assert result == 100


def test_custom_exceptions():
    """Test custom exception types can be raised."""
    with pytest.raises(DataValidationError):
        raise DataValidationError("test")

    with pytest.raises(DataFetchError):
        raise DataFetchError("test")

    with pytest.raises(CalculationError):
        raise CalculationError("test")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
