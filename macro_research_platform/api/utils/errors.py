"""Standard exception handling utilities."""
import logging
from typing import Optional, Any, Callable
from functools import wraps

logger = logging.getLogger(__name__)


class DataValidationError(Exception):
    """Raised when data validation fails."""
    pass


class DataFetchError(Exception):
    """Raised when external data fetch fails."""
    pass


class CalculationError(Exception):
    """Raised when calculation fails."""
    pass


def safe_execute(
    func: Callable,
    default: Any = None,
    error_msg: Optional[str] = None,
    log_level: str = "warning"
) -> Any:
    """
    Safely execute function with standardized error handling.

    Args:
        func: Function to execute
        default: Default value to return on error
        error_msg: Custom error message prefix
        log_level: Logging level (debug, info, warning, error)

    Returns:
        Function result or default value

    Examples:
        >>> result = safe_execute(lambda: risky_calculation(), default=0.0)
        >>> result = safe_execute(fetch_data, default={}, error_msg="FRED API failed")
    """
    try:
        return func()
    except ValueError as e:
        msg = f"{error_msg}: Invalid value - {e}" if error_msg else f"Invalid value: {e}"
        getattr(logger, log_level)(msg)
        return default
    except KeyError as e:
        msg = f"{error_msg}: Missing key - {e}" if error_msg else f"Missing key: {e}"
        getattr(logger, log_level)(msg)
        return default
    except DataValidationError as e:
        msg = f"{error_msg}: Validation failed - {e}" if error_msg else f"Validation failed: {e}"
        getattr(logger, log_level)(msg)
        return default
    except DataFetchError as e:
        msg = f"{error_msg}: Data fetch failed - {e}" if error_msg else f"Data fetch failed: {e}"
        getattr(logger, log_level)(msg)
        return default
    except Exception as e:
        msg = f"{error_msg}: Unexpected error - {e}" if error_msg else f"Unexpected error: {e}"
        getattr(logger, log_level)(msg, exc_info=True)
        return default


def safe_endpoint(default_response: Any = None):
    """
    Decorator for endpoint error handling.

    Catches exceptions and returns fallback response with error logging.

    Args:
        default_response: Response to return on error

    Examples:
        >>> @safe_endpoint(default_response={"error": "Internal error"})
        >>> async def get_data():
        >>>     return compute_data()
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except ValueError as e:
                logger.error(f"Endpoint {func.__name__}: Invalid input - {e}")
                return default_response
            except KeyError as e:
                logger.error(f"Endpoint {func.__name__}: Missing field - {e}")
                return default_response
            except Exception as e:
                logger.error(f"Endpoint {func.__name__}: Unexpected error - {e}", exc_info=True)
                return default_response
        return wrapper
    return decorator


def log_and_return(
    error: Exception,
    default: Any,
    context: str = "",
    level: str = "error"
) -> Any:
    """
    Log exception and return default value.

    Args:
        error: Exception to log
        default: Default value to return
        context: Context message
        level: Log level

    Returns:
        Default value
    """
    error_type = type(error).__name__
    msg = f"{context}: {error_type} - {error}" if context else f"{error_type}: {error}"

    if level == "error":
        logger.error(msg, exc_info=True)
    elif level == "warning":
        logger.warning(msg)
    else:
        logger.info(msg)

    return default
