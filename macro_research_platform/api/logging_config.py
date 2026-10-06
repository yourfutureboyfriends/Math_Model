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
import re
import sys

LOG_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_CONFIGURED = False

# Secrets that libraries put in log lines (requests' HTTPError text carries the full URL,
# e.g. FRED's ...&api_key=<key>&...): query/form parameters and bearer tokens.
_SECRET_PARAM = re.compile(r"(?i)\b(api[_-]?key|apikey|access[_-]?token|refresh[_-]?token|token|secret|"
                           r"client[_-]?secret|password|passwd|signature|sig)=([^&\s'\"<>]+)")
_BEARER = re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._~+/=-]{8,}")


def redact(text: str) -> str:
    """Mask secret values in a string (parameter names are kept)."""
    if not text:
        return text
    return _BEARER.sub(r"\1 ***", _SECRET_PARAM.sub(r"\1=***", text))


class RedactSecretsFilter(logging.Filter):
    """Handler filter: masks secrets in every record that passes through, whichever logger
    (app, library, uvicorn) produced it. Arguments are redacted one by one so formatters that
    use structured args (uvicorn's access log) keep working; exception text is redacted too."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: self._arg(v) for k, v in record.args.items()}
            else:
                record.args = tuple(self._arg(a) for a in record.args)
        if record.exc_info and not record.exc_text:
            record.exc_text = redact(logging.Formatter().formatException(record.exc_info))
        return True

    @staticmethod
    def _arg(a):
        if isinstance(a, str):
            return redact(a)
        if isinstance(a, (int, float, bool)) or a is None:
            return a
        s = str(a)
        r = redact(s)
        return r if r != s else a


_REDACT = RedactSecretsFilter()


def install_redaction() -> None:
    """Attach the redaction filter to every handler of the root and uvicorn loggers."""
    for name in ("", "uvicorn", "uvicorn.error", "uvicorn.access"):
        for handler in logging.getLogger(name).handlers:
            if _REDACT not in handler.filters:
                handler.addFilter(_REDACT)


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
    install_redaction()

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
