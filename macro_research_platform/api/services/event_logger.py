"""Production event logging for forecasts, signals, and risk outputs.

This module provides centralized event logging to the database.
It uses existing repository/database abstractions and handles failures gracefully.
"""
import logging
import os
from typing import Any, Dict, Optional
from datetime import datetime
from uuid import uuid4

logger = logging.getLogger(__name__)

# Feature flag for event logging
ENABLE_EVENT_LOGGING = os.getenv("ENABLE_EVENT_LOGGING", "true").lower() == "true"


def _is_async_context() -> bool:
    """Check if we're in an async context."""
    try:
        import asyncio
        try:
            asyncio.get_running_loop()
            return True
        except RuntimeError:
            return False
    except ImportError:
        return False


def log_forecast_event(
    event_type: str,
    payload: Dict[str, Any],
    metadata: Optional[Dict[str, Any]] = None
) -> None:
    """Persist forecast event using existing DB/repository layer.

    Args:
        event_type: Type of forecast event (e.g., 'recession', 'gdp_nowcast', 'expected_returns')
        payload: The forecast data being logged
        metadata: Additional context (source handler, regime, etc.)
    """
    if not ENABLE_EVENT_LOGGING:
        return

    try:
        # Prepare log entry
        log_entry = {
            "event_id": str(uuid4()),
            "event_type": event_type,
            "timestamp": datetime.now().isoformat(),
            "payload_summary": _summarize_payload(payload),
            "metadata": metadata or {},
        }

        # Log to Python logger (structured logging)
        logger.info(
            f"[event_logger] Forecast event: {event_type}",
            extra={"event_data": log_entry}
        )

        # TODO: Persist to database when repository layer is ready
        # This would typically call a repository method like:
        # await forecast_repository.log_forecast(log_entry)

    except Exception as e:
        # Logging failures must not break endpoint responses
        logger.error(f"[event_logger] Failed to log forecast event: {e}", exc_info=True)


def log_signal_event(
    event_type: str,
    payload: Dict[str, Any],
    metadata: Optional[Dict[str, Any]] = None
) -> None:
    """Persist signal event using existing DB/repository layer.

    Args:
        event_type: Type of signal event (e.g., 'final_signal', 'signal_stack', 'conviction')
        payload: The signal data being logged
        metadata: Additional context (regime, handler source, etc.)
    """
    if not ENABLE_EVENT_LOGGING:
        return

    try:
        # Extract key signal fields for logging
        signal_summary = {
            "final_signal": payload.get("finalSignal") or payload.get("signal"),
            "conviction": payload.get("conviction"),
            "regime": payload.get("regime") or (metadata.get("regime") if metadata else None),
        }

        log_entry = {
            "event_id": str(uuid4()),
            "event_type": event_type,
            "timestamp": datetime.now().isoformat(),
            "signal_summary": signal_summary,
            "payload_summary": _summarize_payload(payload),
            "metadata": metadata or {},
        }

        logger.info(
            f"[event_logger] Signal event: {event_type}",
            extra={"event_data": log_entry}
        )

        # TODO: Persist to SignalPrediction or SignalEvent table
        # This would create a proper database record for tracking

    except Exception as e:
        logger.error(f"[event_logger] Failed to log signal event: {e}", exc_info=True)


def log_risk_event(
    event_type: str,
    payload: Dict[str, Any],
    metadata: Optional[Dict[str, Any]] = None
) -> None:
    """Persist risk event using existing DB/repository layer.

    Args:
        event_type: Type of risk event (e.g., 'recession_probability', 'risk_metrics', 'alert')
        payload: The risk data being logged
        metadata: Additional context (source handler, severity, etc.)
    """
    if not ENABLE_EVENT_LOGGING:
        return

    try:
        # Extract key risk fields
        risk_summary = {
            "probability": payload.get("probability"),
            "level": payload.get("level") or payload.get("regime"),
        }

        log_entry = {
            "event_id": str(uuid4()),
            "event_type": event_type,
            "timestamp": datetime.now().isoformat(),
            "risk_summary": risk_summary,
            "payload_summary": _summarize_payload(payload),
            "metadata": metadata or {},
        }

        logger.info(
            f"[event_logger] Risk event: {event_type}",
            extra={"event_data": log_entry}
        )

        # TODO: Persist to risk-related tables

    except Exception as e:
        logger.error(f"[event_logger] Failed to log risk event: {e}", exc_info=True)


def log_dashboard_event(
    payload: Dict[str, Any],
    metadata: Optional[Dict[str, Any]] = None
) -> None:
    """Log dashboard generation event.

    Args:
        payload: The dashboard data
        metadata: Additional context (mode, handler source, etc.)
    """
    if not ENABLE_EVENT_LOGGING:
        return

    try:
        # Extract key dashboard fields
        dashboard_summary = {
            "regime": payload.get("regime", {}).get("current") if isinstance(payload.get("regime"), dict) else None,
            "signal": payload.get("signals", {}).get("finalSignal") if isinstance(payload.get("signals"), dict) else None,
            "recession_prob": payload.get("recession", {}).get("probability") if isinstance(payload.get("recession"), dict) else None,
        }

        log_entry = {
            "event_id": str(uuid4()),
            "event_type": "dashboard_generated",
            "timestamp": datetime.now().isoformat(),
            "dashboard_summary": dashboard_summary,
            "metadata": metadata or {},
        }

        logger.info(
            "[event_logger] Dashboard event: dashboard_generated",
            extra={"event_data": log_entry}
        )

    except Exception as e:
        logger.error(f"[event_logger] Failed to log dashboard event: {e}", exc_info=True)


def log_validation_event(
    handler_name: str,
    validation_result: Any,
    payload_summary: Optional[Dict[str, Any]] = None
) -> None:
    """Log validation results.

    Args:
        handler_name: Name of the handler that was validated
        validation_result: The ValidationResult object
        payload_summary: Optional summary of the payload that was validated
    """
    if not ENABLE_EVENT_LOGGING:
        return

    try:
        log_entry = {
            "event_id": str(uuid4()),
            "event_type": "validation",
            "timestamp": datetime.now().isoformat(),
            "handler": handler_name,
            "valid": getattr(validation_result, 'valid', False),
            "issues": getattr(validation_result, 'issues', []),
            "payload_summary": payload_summary or {},
        }

        if log_entry["valid"]:
            logger.debug(
                f"[event_logger] Validation passed for {handler_name}",
                extra={"event_data": log_entry}
            )
        else:
            logger.warning(
                f"[event_logger] Validation failed for {handler_name}",
                extra={"event_data": log_entry}
            )

    except Exception as e:
        logger.error(f"[event_logger] Failed to log validation event: {e}", exc_info=True)


def _summarize_payload(payload: Dict[str, Any], max_depth: int = 2) -> Dict[str, Any]:
    """Create a summary of payload for logging (avoid storing huge blobs).

    Args:
        payload: The full payload
        max_depth: Maximum recursion depth for nested dicts

    Returns:
        A summary dict with top-level keys and their types/short values
    """
    if not isinstance(payload, dict):
        return {"value": str(payload)[:100]}

    summary = {}
    for key, value in payload.items():
        if isinstance(value, dict) and max_depth > 0:
            # Recursively summarize nested dicts
            summary[key] = _summarize_payload(value, max_depth - 1)
        elif isinstance(value, list):
            # Just note the list length
            summary[key] = f"<list[{len(value)}]>"
        elif isinstance(value, (int, float, bool, str)):
            # Keep primitive values
            summary[key] = value
        else:
            # Stringify other types with truncation
            summary[key] = str(value)[:50]

    return summary


def get_logging_status() -> Dict[str, Any]:
    """Return current logging configuration status."""
    return {
        "enabled": ENABLE_EVENT_LOGGING,
        "loggers_available": {
            "forecast": True,
            "signal": True,
            "risk": True,
            "dashboard": True,
            "validation": True,
        }
    }
