"""Helper utility functions."""
import socket
import logging
from pathlib import Path
from typing import Any, Optional
import numpy as np

logger = logging.getLogger(__name__)

# Get project root (assumes this file is in api/utils/)
_PROJECT_ROOT = Path(__file__).parent.parent.parent


def find_free_port(preferred: int = 8000, fallbacks=None) -> int:
    """
    Return the first available port from the preferred list.

    Args:
        preferred: Preferred port number
        fallbacks: List of fallback ports

    Returns:
        Available port number
    """
    if fallbacks is None:
        fallbacks = [8001, 8002, 8080, 9000]
    candidates = [preferred] + fallbacks

    for port in candidates:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(("", port))
                return port
        except OSError:
            continue

    # Last resort: let OS assign any free port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def write_port_file(port: int, path: str = ".api_port") -> None:
    """
    Write the active port to a shared file for frontend to read.

    Args:
        port: Port number to write
        path: Path to port file (relative to project root)
    """
    port_path = _PROJECT_ROOT / path
    try:
        with open(port_path, "w") as f:
            f.write(str(port))
        logger.info(f"[MACRO OS] API running on port {port}")
        logger.info(f"[MACRO OS] Port written to {port_path}")
    except Exception as e:
        logger.warning(f"[MACRO OS] Could not write port file: {e}")


def read_port_file(path: str = ".api_port") -> Optional[int]:
    """
    Read the port from the shared file.

    Args:
        path: Path to port file (relative to project root)

    Returns:
        Port number or None if file not found/invalid
    """
    port_path = _PROJECT_ROOT / path
    try:
        with open(port_path, "r") as f:
            content = f.read().strip()
            port = int(content)
            return port
    except (FileNotFoundError, ValueError):
        return None


def scrub_nans(obj: Any) -> Any:
    """
    Recursively replace NaN/Infinity with None in any nested dict/list.
    Apply this to all computed data before returning to frontend.

    Args:
        obj: Object to clean (dict, list, float, or other)

    Returns:
        Cleaned object with NaN/Inf replaced by None
    """
    if isinstance(obj, dict):
        return {k: scrub_nans(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [scrub_nans(v) for v in obj]
    elif isinstance(obj, float):
        if np.isnan(obj) or np.isinf(obj):
            return None
        return round(obj, 6)
    return obj


def safe_float(val: Any, default: float = 0.0) -> float:
    """
    Safely convert a value to float, returning default if NaN or invalid.

    Args:
        val: Value to convert
        default: Default value if conversion fails

    Returns:
        Float value or default
    """
    try:
        f = float(val)
        if np.isnan(f) or np.isinf(f):
            return default
        return f
    except (TypeError, ValueError):
        return default


def safe_pct(val: Any, default: Optional[float] = None) -> Optional[float]:
    """
    Safely convert a value to percentage, returning default if None/NaN/invalid.
    Used for CTA trend calculations to prevent null toFixed() errors in frontend.

    Args:
        val: Value to convert
        default: Default value if conversion fails

    Returns:
        Rounded percentage value or default
    """
    if val is None:
        return default
    try:
        f = float(val)
        if np.isnan(f) or np.isinf(f):
            return default
        return round(f, 1)
    except (TypeError, ValueError):
        return default


def format_confidence(value: Any) -> str:
    """
    Format confidence value to High/Medium/Low string.

    Args:
        value: Confidence value (float 0-1, percentage string, or None)

    Returns:
        Formatted confidence string
    """
    if value is None:
        return "Medium"
    if isinstance(value, (int, float)):
        v = float(value)
        return "High" if v >= 0.7 else "Medium" if v >= 0.4 else "Low"
    if isinstance(value, str):
        if value.endswith('%'):
            return value
        try:
            return format_confidence(float(value))
        except ValueError:
            return value
    return "Medium"


def parse_position_size(value: Any) -> float:
    """
    Parse position size value to float.

    Args:
        value: Position size value (string, int, float, or None)

    Returns:
        Parsed position size as float
    """
    if value is None:
        return 0.0
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0


def safe_execute(func: callable, default: Any = None, log_errors: bool = True) -> Any:
    """
    Safely execute computation with error handling.

    Args:
        func: Function to execute
        default: Default value on error
        log_errors: Whether to log errors

    Returns:
        Function result or default value
    """
    try:
        return func()
    except Exception as e:
        if log_errors:
            logger.warning(f"safe_execute failed: {e}")
        return default
