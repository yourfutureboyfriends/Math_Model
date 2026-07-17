"""
Central logging configuration — one consistent format for the whole backend.

All application modules acquire their logger with ``logging.getLogger(__name__)`` and let
records propagate to the root logger. Calling :func:`setup_logging` once at startup installs
a single formatter on the root handler so every line looks the same:

    2026-07-10 14:03:11 | INFO    | api.handlers.market_handler | fetched 3 symbols

The module name (``%(name)s``) carries the context that ad-hoc ``[PREFIX]`` tags used to,
so new code should NOT hand-roll bracketed prefixes — just log to the module logger.

Level is controlled by the ``LOG_LEVEL`` env var (default INFO). Idempotent: safe to call
more than once (e.g. from both import time and the app lifespan).
"""
from __future__ import annotations

import logging
import os
import sys

LOG_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_CONFIGURED = False


def setup_logging(level: str | None = None) -> None:
    """Install one consistent formatter on the root logger.

    Re-formats existing root handlers (rather than removing uvicorn's) so application logs
    are uniform without disturbing uvicorn's own operational/access loggers.

    Args:
        level: log level name (e.g. "DEBUG"); falls back to ``$LOG_LEVEL`` then INFO.
    """
    global _CONFIGURED
    resolved = (level or os.getenv("LOG_LEVEL", "INFO")).upper()
    lvl = getattr(logging, resolved, logging.INFO)

    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)
    root = logging.getLogger()
    if not root.handlers:
        root.addHandler(logging.StreamHandler(sys.stdout))
    for handler in root.handlers:
        handler.setFormatter(formatter)
    root.setLevel(lvl)

    # Keep the two application namespaces at the configured level and propagating to root.
    for name in ("api", "database"):
        lg = logging.getLogger(name)
        lg.setLevel(lvl)
        lg.propagate = True

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Convenience accessor; equivalent to ``logging.getLogger(name)`` after setup."""
    if not _CONFIGURED:
        setup_logging()
    return logging.getLogger(name)
