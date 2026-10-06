"""Secrets never reach the logs (a FRED 429 once printed the full URL with api_key=...)."""
import logging

from api.logging_config import RedactSecretsFilter, redact


def test_redact_patterns():
    url = "https://api.stlouisfed.org/fred/series/observations?series_id=X&api_key=f269abc123&file_type=json"
    assert "f269abc123" not in redact(url) and "api_key=***" in redact(url) and "series_id=X" in redact(url)
    assert redact("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.abc.def") == "Authorization: Bearer ***"
    assert redact("password=hunter22 user=bob") == "password=*** user=bob"
    assert redact("nothing secret here") == "nothing secret here"


def _render(msg, *args, exc=None):
    rec = logging.LogRecord("t", logging.WARNING, __file__, 1, msg, args, exc)
    RedactSecretsFilter().filter(rec)
    return logging.Formatter("%(message)s").format(rec)


def test_filter_redacts_message_args_and_exception_objects():
    err = RuntimeError("429 Client Error for url: https://x/y?api_key=SECRETKEY99&limit=8")
    out = _render("FRED fetch failed for %s: %s", "BAMLH0A0HYM2", err)
    assert "SECRETKEY99" not in out and "BAMLH0A0HYM2" in out
    try:
        raise ValueError("token=abcdef123456 leaked")
    except ValueError:
        import sys
        out = _render("boom", exc=sys.exc_info())
    assert "abcdef123456" not in out


def test_structured_args_survive():
    # uvicorn's access formatter reads record.args as a tuple of (client, method, path, ...)
    rec = logging.LogRecord("uvicorn.access", logging.INFO, __file__, 1, '%s - "%s %s"',
                            ("127.0.0.1:1", "GET", "/api/x?token=abcdefgh123"), None)
    RedactSecretsFilter().filter(rec)
    assert isinstance(rec.args, tuple) and rec.args[2] == "/api/x?token=***"
