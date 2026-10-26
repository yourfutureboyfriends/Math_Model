"""
Alert delivery beyond the in-app toast and browser notification. Opt-in, configured only in .env:

  ALERT_WEBHOOK_URL   POSTs {"text": ...} (Slack / Discord / Teams incoming webhooks, ntfy.sh topics accept this)
  ALERT_SMTP_HOST, ALERT_SMTP_PORT (587), ALERT_SMTP_USER, ALERT_SMTP_PASSWORD, ALERT_EMAIL_FROM, ALERT_EMAIL_TO

Nothing is sent when neither is configured. Failures are logged, never raised into the alert checker.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def channels() -> dict:
    """Which delivery channels are configured (webhook, email)."""
    return {"webhook": bool(os.getenv("ALERT_WEBHOOK_URL")),
            "email": bool(os.getenv("ALERT_SMTP_HOST") and os.getenv("ALERT_EMAIL_TO"))}


def deliver(owner: str, text: str) -> dict:
    """Send a message through every configured channel; returns per-channel success. Errors are logged without secrets.
    """
    sent = {}
    url = os.getenv("ALERT_WEBHOOK_URL")
    if url:
        try:
            import requests
            r = requests.post(url, json={"text": f"[{owner}] {text}", "content": f"[{owner}] {text}"}, timeout=10)
            sent["webhook"] = r.status_code < 300
        except Exception as e:
            logger.warning("[notify] webhook failed: %s", type(e).__name__)
            sent["webhook"] = False
    host, to = os.getenv("ALERT_SMTP_HOST"), os.getenv("ALERT_EMAIL_TO")
    if host and to:
        try:
            import smtplib
            from email.message import EmailMessage
            m = EmailMessage()
            m["Subject"] = (text.strip().splitlines() or [""])[0][:120]      # one line: a newline is not a valid subject
            m["From"] = os.getenv("ALERT_EMAIL_FROM") or os.getenv("ALERT_SMTP_USER") or to
            m["To"] = to
            m.set_content(f"{text}\n\nUser: {owner}\n— Macro Terminal alerts")
            with smtplib.SMTP(host, int(os.getenv("ALERT_SMTP_PORT", "587")), timeout=15) as s:
                s.starttls()
                if os.getenv("ALERT_SMTP_USER"):
                    s.login(os.getenv("ALERT_SMTP_USER"), os.getenv("ALERT_SMTP_PASSWORD", ""))
                s.send_message(m)
            sent["email"] = True
        except Exception as e:
            logger.warning("[notify] email failed: %s", type(e).__name__)
            sent["email"] = False
    return sent
