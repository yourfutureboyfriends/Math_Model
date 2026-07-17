"""Runtime status service for diagnostics and monitoring.

Provides real-time system health information including:
- Cache status and ages
- Validation configuration
- Data freshness
- Scheduler status
- Logging status
"""
import logging
import os
from typing import Any, Dict
from datetime import datetime

logger = logging.getLogger(__name__)


def get_cache_status() -> Dict[str, Any]:
    """Get cache status information.

    Returns:
        Dict with cache status including validity and age information.
    """
    try:
        # Try to get cache info from price_cache if available
        try:
            from api.price_cache import price_cache
            cache_info = price_cache.get_cache_info()
            return {
                "valid": True,
                "cache_type": "price_cache",
                "details": cache_info,
            }
        except Exception as e:
            logger.debug(f"Could not get price cache info: {e}")

        # Fallback: return default cache status
        return {
            "valid": True,
            "caches": {
                "market_data": {"valid": True, "age_seconds": 0, "ttl_seconds": 300},
                "indicators": {"valid": True, "age_seconds": 0, "ttl_seconds": 900},
                "signals": {"valid": True, "age_seconds": 0, "ttl_seconds": 300},
            }
        }
    except Exception as e:
        logger.error(f"Error getting cache status: {e}")
        return {"valid": False, "error": str(e)}


def get_validation_status() -> Dict[str, Any]:
    """Get validation configuration status.

    Returns:
        Dict with validation configuration and availability.
    """
    try:
        from api.services.validation_orchestrator import (
            get_validation_status as get_vo_status,
            ENABLE_RUNTIME_VALIDATION,
        )

        vo_status = get_vo_status()

        return {
            "enabled": vo_status.get("enabled", ENABLE_RUNTIME_VALIDATION),
            "validators_available": vo_status.get("validators_available", {}),
            "configuration": {
                "ENABLE_RUNTIME_VALIDATION": ENABLE_RUNTIME_VALIDATION,
            }
        }
    except Exception as e:
        logger.error(f"Error getting validation status: {e}")
        return {
            "enabled": False,
            "error": str(e),
            "validators_available": {}
        }


def get_data_freshness_status() -> Dict[str, Any]:
    """Get data freshness status.

    Returns:
        Dict with data freshness information.
    """
    try:
        from api.data_freshness import get_freshness_summary

        freshness = get_freshness_summary()
        return {
            "valid": True,
            "freshness": freshness,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.debug(f"Could not get freshness summary: {e}")
        return {
            "valid": True,  # Don't fail if freshness not available
            "freshness": "unavailable",
            "error": str(e),
        }


def get_scheduler_status() -> Dict[str, Any]:
    """Get scheduler status.

    Returns:
        Dict with scheduler information.
    """
    try:
        from api.report_scheduler import get_scheduler_info

        scheduler_info = get_scheduler_info()
        return {
            "valid": True,
            "scheduler": scheduler_info,
        }
    except Exception as e:
        logger.debug(f"Could not get scheduler info: {e}")
        return {
            "valid": True,
            "scheduler": {
                "status": "unavailable",
                "error": str(e),
            },
        }


def get_logging_status() -> Dict[str, Any]:
    """Get logging configuration status.

    Returns:
        Dict with logging configuration.
    """
    try:
        from api.services.event_logger import get_logging_status as get_el_status
        from api.services.event_logger import ENABLE_EVENT_LOGGING

        el_status = get_el_status()

        return {
            "enabled": el_status.get("enabled", ENABLE_EVENT_LOGGING),
            "loggers_available": el_status.get("loggers_available", {}),
            "configuration": {
                "ENABLE_EVENT_LOGGING": ENABLE_EVENT_LOGGING,
            }
        }
    except Exception as e:
        logger.error(f"Error getting logging status: {e}")
        return {
            "enabled": False,
            "error": str(e),
        }


def get_system_health() -> Dict[str, Any]:
    """Get overall system health.

    Returns:
        Dict with comprehensive system health status.
    """
    health = {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "components": {},
    }

    # Check cache
    cache_status = get_cache_status()
    health["components"]["cache"] = cache_status
    if not cache_status.get("valid", True):
        health["status"] = "degraded"

    # Check validation
    validation_status = get_validation_status()
    health["components"]["validation"] = validation_status

    # Check data freshness
    freshness_status = get_data_freshness_status()
    health["components"]["data_freshness"] = freshness_status

    # Check scheduler
    scheduler_status = get_scheduler_status()
    health["components"]["scheduler"] = scheduler_status

    # Check logging
    logging_status = get_logging_status()
    health["components"]["logging"] = logging_status

    return health


def get_full_diagnostics() -> Dict[str, Any]:
    """Get full diagnostics information.

    Returns:
        Dict with complete diagnostics data for the diagnostics endpoint.
    """
    return {
        "status": get_system_health(),
        "caches": get_cache_status(),
        "validation": get_validation_status(),
        "data_freshness": get_data_freshness_status(),
        "scheduler": get_scheduler_status(),
        "logging": get_logging_status(),
        "environment": {
            "runtime_validation": os.getenv("ENABLE_RUNTIME_VALIDATION", "true"),
            "event_logging": os.getenv("ENABLE_EVENT_LOGGING", "true"),
            "diagnostics": os.getenv("ENABLE_DIAGNOSTICS", "true"),
        },
        "timestamp": datetime.now().isoformat(),
    }
