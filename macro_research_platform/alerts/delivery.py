"""
Alert Delivery Engine for Macro Research Platform.

Delivers alerts via multiple channels:
- Email (smtplib) for CRITICAL alerts
- Slack webhook for CRITICAL + WARNING alerts
- Browser push notifications for all severities

Priority tiers:
- CRITICAL: Email + Slack + Browser (immediate)
- WARNING: Slack + Browser (immediate)
- INFO: Browser only (batched hourly)
"""

import os
import json
import logging
import threading
import requests
from datetime import datetime, time
from typing import Dict, Optional, Any, List
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from dataclasses import dataclass

# Setup logging
logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION (from environment variables)
# ═══════════════════════════════════════════════════════════════════════════════

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
ALERT_EMAIL_TO = os.getenv("ALERT_EMAIL_TO", "")

SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")

# ═══════════════════════════════════════════════════════════════════════════════
# ALERT COOLDOWNS (prevent alert storms)
# ═══════════════════════════════════════════════════════════════════════════════

ALERT_COOLDOWNS: Dict[str, float] = {}

COOLDOWN_PERIODS = {
    "regime_change": 0,              # Always fire immediately
    "recession_high": 3600,        # 1 hour cooldown
    "geo_risk_elevated": 14400,    # 4 hour cooldown
    "anomaly_detected": 7200,       # 2 hour cooldown
    "vix_spike": 1800,             # 30 min cooldown
    "options_extreme": 3600,        # 1 hour cooldown
    "positioning_crowded": 86400,   # 1 day cooldown
    "credit_stress": 3600,          # 1 hour cooldown
    "liquidity_crunch": 1800,       # 30 min cooldown
    "default": 3600,               # 1 hour default
}

# ═══════════════════════════════════════════════════════════════════════════════
# NOTIFICATION CONFIG (in-memory, set via API)
# ═══════════════════════════════════════════════════════════════════════════════

NOTIFICATION_CONFIG = {
    "email_enabled": bool(SMTP_USER and ALERT_EMAIL_TO),
    "slack_enabled": bool(SLACK_WEBHOOK_URL),
    "browser_enabled": True,
    "thresholds": {
        "recession_risk": 30,
        "vix": 35,
        "anomaly_score": 0.75,
        "hy_spreads": 400,
        "geo_risk": 1.5,
        "options_fear": 70,
        "options_greed": 15,
    },
    "quiet_hours": {
        "enabled": True,
        "start": 22,
        "end": 7,
    },
}


@dataclass
class Alert:
    """Alert data structure."""
    id: str
    severity: str  # critical, warning, info
    category: str  # regime, risk, geo, model
    title: str
    message: str
    action: Optional[str] = None
    timestamp: Optional[str] = None
    metadata: Optional[Dict] = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow().isoformat()
        if self.metadata is None:
            self.metadata = {}


# ═══════════════════════════════════════════════════════════════════════════════
# COOLDOWN MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════

def should_fire_alert(alert_key: str) -> bool:
    """
    Check if alert should fire based on cooldown period.

    Args:
        alert_key: Unique identifier for the alert type

    Returns:
        True if alert should fire, False if in cooldown
    """
    import time

    cooldown = COOLDOWN_PERIODS.get(alert_key, COOLDOWN_PERIODS["default"])
    if cooldown == 0:
        return True  # Always fire

    last_fired = ALERT_COOLDOWNS.get(alert_key, 0)
    current_time = time.time()

    if current_time - last_fired < cooldown:
        logger.debug(f"Alert '{alert_key}' in cooldown ({cooldown}s)")
        return False

    ALERT_COOLDOWNS[alert_key] = current_time
    return True


def reset_cooldown(alert_key: str):
    """Reset cooldown for a specific alert key."""
    ALERT_COOLDOWNS.pop(alert_key, None)


def is_quiet_hours() -> bool:
    """Check if current time is in quiet hours."""
    if not NOTIFICATION_CONFIG["quiet_hours"]["enabled"]:
        return False

    now = datetime.utcnow()
    current_hour = now.hour
    start = NOTIFICATION_CONFIG["quiet_hours"]["start"]
    end = NOTIFICATION_CONFIG["quiet_hours"]["end"]

    if start > end:  # e.g., 22:00 to 07:00
        return current_hour >= start or current_hour < end
    else:
        return start <= current_hour < end


# ═══════════════════════════════════════════════════════════════════════════════
# EMAIL DELIVERY
# ═══════════════════════════════════════════════════════════════════════════════

def build_email_html(alert: Alert, context: Optional[Dict] = None) -> str:
    """Build HTML email body for alert."""

    severity_colors = {
        "critical": "#c1121f",
        "warning": "#ca6702",
        "info": "#0066cc",
    }
    severity_color = severity_colors.get(alert.severity, "#495057")

    context = context or {}
    regime = context.get("regime", "Unknown")
    regime_conf = context.get("regime_confidence", 0.8)
    signal = context.get("signal", "NEUTRAL")
    score = context.get("ensemble_score", 0.0)

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Macro Research Platform Alert</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                margin: 0;
                padding: 20px;
                background: #f5f5f5;
            }}
            .container {{
                max-width: 600px;
                margin: 0 auto;
                background: #ffffff;
                border-radius: 8px;
                overflow: hidden;
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            }}
            .header {{
                background: #1a1a2e;
                color: white;
                padding: 20px;
                text-align: center;
            }}
            .header h1 {{
                margin: 0;
                font-size: 18px;
                font-weight: 600;
            }}
            .header .subtitle {{
                margin-top: 4px;
                font-size: 12px;
                opacity: 0.8;
            }}
            .severity-badge {{
                display: inline-block;
                padding: 4px 12px;
                border-radius: 4px;
                font-size: 11px;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 0.5px;
                color: white;
                background: {severity_color};
            }}
            .timestamp {{
                font-size: 12px;
                color: #6c757d;
                margin-top: 8px;
            }}
            .content {{
                padding: 24px;
            }}
            .alert-title {{
                font-size: 20px;
                font-weight: 600;
                color: #1a1a2e;
                margin-bottom: 12px;
            }}
            .alert-message {{
                font-size: 14px;
                line-height: 1.6;
                color: #495057;
                margin-bottom: 20px;
            }}
            .context-box {{
                background: #f8f9fa;
                border-left: 4px solid #006d5b;
                padding: 16px;
                margin-bottom: 20px;
            }}
            .context-row {{
                display: flex;
                justify-content: space-between;
                padding: 4px 0;
                font-size: 13px;
            }}
            .context-label {{
                color: #6c757d;
            }}
            .context-value {{
                font-weight: 600;
                color: #1a1a2e;
            }}
            .action-box {{
                background: #e8f5f1;
                border: 1px solid #006d5b;
                border-radius: 4px;
                padding: 16px;
                margin-bottom: 20px;
            }}
            .action-title {{
                font-size: 11px;
                text-transform: uppercase;
                letter-spacing: 0.5px;
                color: #006d5b;
                font-weight: 600;
                margin-bottom: 4px;
            }}
            .action-text {{
                font-size: 14px;
                color: #1a1a2e;
            }}
            .button {{
                display: inline-block;
                background: #006d5b;
                color: white;
                text-decoration: none;
                padding: 12px 24px;
                border-radius: 4px;
                font-size: 14px;
                font-weight: 500;
            }}
            .footer {{
                background: #f8f9fa;
                padding: 16px 24px;
                text-align: center;
                font-size: 11px;
                color: #6c757d;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>MACRO RESEARCH PLATFORM</h1>
                <div class="subtitle">Alert Notification</div>
                <div class="timestamp">{alert.timestamp}</div>
                <div style="margin-top: 12px;">
                    <span class="severity-badge">{alert.severity.upper()}</span>
                </div>
            </div>

            <div class="content">
                <div class="alert-title">{alert.title}</div>
                <div class="alert-message">{alert.message}</div>

                <div class="context-box">
                    <div class="context-row">
                        <span class="context-label">Current Regime:</span>
                        <span class="context-value">{regime} ({regime_conf:.1%})</span>
                    </div>
                    <div class="context-row">
                        <span class="context-label">Ensemble Signal:</span>
                        <span class="context-value">{signal} ({score:+.2f})</span>
                    </div>
                </div>

                {f'<div class="action-box"><div class="action-title">Recommended Action</div><div class="action-text">{alert.action}</div></div>' if alert.action else ''}

                <div style="text-align: center;">
                    <a href="http://localhost:3002" class="button">View Dashboard</a>
                </div>
            </div>

            <div class="footer">
                This alert was generated by the Macro Research Platform.<br>
                Macro Research Platform · Confidential Research · Not Investment Advice
            </div>
        </div>
    </body>
    </html>
    """
    return html


def send_email_alert(alert: Alert, context: Optional[Dict] = None) -> bool:
    """
    Send alert via email.

    Args:
        alert: Alert to send
        context: Additional context (regime, signal, etc.)

    Returns:
        True if sent successfully, False otherwise
    """
    if not SMTP_USER or not ALERT_EMAIL_TO:
        logger.info("Email not configured — skipping")
        return False

    if not NOTIFICATION_CONFIG["email_enabled"]:
        logger.debug("Email notifications disabled")
        return False

    try:
        import smtplib

        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"[MACRO OS] {alert.severity.upper()}: {alert.title}"
        msg["From"] = SMTP_USER
        msg["To"] = ALERT_EMAIL_TO

        html_content = build_email_html(alert, context)
        msg.attach(MIMEText(html_content, "html"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_USER, ALERT_EMAIL_TO, msg.as_string())

        logger.info(f"Alert email sent: {alert.title}")
        return True

    except Exception as e:
        logger.warning(f"Email alert failed: {e}")
        return False


def send_email_alert_async(alert: Alert, context: Optional[Dict] = None):
    """Send email alert in background thread."""
    threading.Thread(
        target=send_email_alert,
        args=(alert, context),
        daemon=True
    ).start()


# ═══════════════════════════════════════════════════════════════════════════════
# SLACK DELIVERY
# ═══════════════════════════════════════════════════════════════════════════════

def build_slack_payload(alert: Alert, context: Optional[Dict] = None) -> Dict:
    """Build Slack Block Kit payload for alert."""

    context = context or {}
    regime = context.get("regime", "Unknown")
    regime_conf = context.get("regime_confidence", 0.8)
    signal = context.get("signal", "NEUTRAL")
    score = context.get("ensemble_score", 0.0)

    severity_emoji = {
        "critical": "⚡",
        "warning": "⚠️",
        "info": "ℹ️",
    }.get(alert.severity, "📊")

    payload = {
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{severity_emoji} MACRO OS: {alert.title}",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Severity:*\n{alert.severity.upper()}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Time:*\n{alert.timestamp[:16]}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Regime:*\n{regime} ({regime_conf:.0%})"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Signal:*\n{signal} ({score:+.2f})"
                    }
                ]
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{alert.title}*\n{alert.message}"
                }
            }
        ]
    }

    if alert.action:
        payload["blocks"].append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Action:* {alert.action}"
            }
        })

    return payload


def send_slack_alert(alert: Alert, context: Optional[Dict] = None) -> bool:
    """
    Send alert via Slack webhook.

    Args:
        alert: Alert to send
        context: Additional context

    Returns:
        True if sent successfully, False otherwise
    """
    if not SLACK_WEBHOOK_URL:
        logger.info("Slack not configured — skipping")
        return False

    if not NOTIFICATION_CONFIG["slack_enabled"]:
        logger.debug("Slack notifications disabled")
        return False

    try:
        payload = build_slack_payload(alert, context)
        response = requests.post(
            SLACK_WEBHOOK_URL,
            json=payload,
            timeout=5,
            headers={"Content-Type": "application/json"}
        )
        response.raise_for_status()

        logger.info(f"Slack alert sent: {alert.title}")
        return True

    except Exception as e:
        logger.warning(f"Slack alert failed: {e}")
        return False


def send_slack_alert_async(alert: Alert, context: Optional[Dict] = None):
    """Send Slack alert in background thread."""
    threading.Thread(
        target=send_slack_alert,
        args=(alert, context),
        daemon=True
    ).start()


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN ALERT DISPATCHER
# ═══════════════════════════════════════════════════════════════════════════════

def dispatch_alert(
    alert: Alert,
    context: Optional[Dict] = None,
    alert_key: Optional[str] = None
) -> Dict[str, bool]:
    """
    Dispatch alert to all configured channels based on severity.

    Priority tiers:
    - CRITICAL: Email + Slack + Browser
    - WARNING: Slack + Browser
    - INFO: Browser only

    Args:
        alert: Alert to dispatch
        context: Additional context for templates
        alert_key: Key for cooldown tracking

    Returns:
        Dict mapping channel name to success status
    """
    results = {}

    # Check quiet hours for non-critical alerts
    if alert.severity != "critical" and is_quiet_hours():
        logger.info(f"Alert in quiet hours, queueing: {alert.title}")
        # Store for later delivery (could implement a queue)
        return {"queued": True, "reason": "quiet_hours"}

    # Check cooldown
    if alert_key and not should_fire_alert(alert_key):
        logger.debug(f"Alert in cooldown, skipping: {alert_key}")
        return {"sent": False, "reason": "cooldown"}

    # Dispatch based on severity
    if alert.severity == "critical":
        # CRITICAL: All channels
        if NOTIFICATION_CONFIG["email_enabled"]:
            send_email_alert_async(alert, context)
            results["email"] = True

        if NOTIFICATION_CONFIG["slack_enabled"]:
            send_slack_alert_async(alert, context)
            results["slack"] = True

        results["browser"] = True  # Always broadcast to browser

    elif alert.severity == "warning":
        # WARNING: Slack + Browser
        if NOTIFICATION_CONFIG["slack_enabled"]:
            send_slack_alert_async(alert, context)
            results["slack"] = True

        results["browser"] = True

    else:  # info
        # INFO: Browser only
        results["browser"] = True

    logger.info(f"Alert dispatched: {alert.title} ({alert.severity}) -> {list(results.keys())}")
    return results


def get_delivery_status() -> Dict:
    """Get current alert delivery configuration status."""
    active_channels = []

    if NOTIFICATION_CONFIG["email_enabled"]:
        active_channels.append("email")
    if NOTIFICATION_CONFIG["slack_enabled"]:
        active_channels.append("slack")
    if NOTIFICATION_CONFIG["browser_enabled"]:
        active_channels.append("browser")

    return {
        "active_channels": active_channels,
        "config": {
            "email": NOTIFICATION_CONFIG["email_enabled"],
            "slack": NOTIFICATION_CONFIG["slack_enabled"],
            "browser": NOTIFICATION_CONFIG["browser_enabled"],
        },
        "thresholds": NOTIFICATION_CONFIG["thresholds"],
        "quiet_hours": NOTIFICATION_CONFIG["quiet_hours"],
        "cooldown_periods": COOLDOWN_PERIODS,
    }


def update_config(config_update: Dict) -> Dict:
    """Update notification configuration."""
    global NOTIFICATION_CONFIG

    # Update enabled flags
    if "email_enabled" in config_update:
        NOTIFICATION_CONFIG["email_enabled"] = config_update["email_enabled"] and bool(SMTP_USER)
    if "slack_enabled" in config_update:
        NOTIFICATION_CONFIG["slack_enabled"] = config_update["slack_enabled"] and bool(SLACK_WEBHOOK_URL)
    if "browser_enabled" in config_update:
        NOTIFICATION_CONFIG["browser_enabled"] = config_update["browser_enabled"]

    # Update thresholds
    if "thresholds" in config_update:
        NOTIFICATION_CONFIG["thresholds"].update(config_update["thresholds"])

    # Update quiet hours
    if "quiet_hours" in config_update:
        NOTIFICATION_CONFIG["quiet_hours"].update(config_update["quiet_hours"])

    logger.info(f"Notification config updated: {NOTIFICATION_CONFIG}")
    return NOTIFICATION_CONFIG


# ═══════════════════════════════════════════════════════════════════════════════
# TEST ALERT
# ═══════════════════════════════════════════════════════════════════════════════

def send_test_alert(channel: str = "all") -> Dict[str, bool]:
    """
    Send a test alert to specified channel(s).

    Args:
        channel: 'all', 'email', 'slack', or 'browser'

    Returns:
        Dict of results per channel
    """
    test_alert = Alert(
        id="test-001",
        severity="warning",
        category="test",
        title="Test Alert",
        message="This is a test alert from the Macro Research Platform. Your notification channels are working correctly.",
        action="No action required. This is just a test.",
    )

    context = {
        "regime": "Goldilocks",
        "regime_confidence": 0.85,
        "signal": "RISK-ON",
        "ensemble_score": 0.62,
    }

    results = {}

    if channel in ("all", "email"):
        results["email"] = send_email_alert(test_alert, context)

    if channel in ("all", "slack"):
        results["slack"] = send_slack_alert(test_alert, context)

    if channel in ("all", "browser"):
        results["browser"] = True  # Browser always "succeeds" (frontend handles)

    return results


if __name__ == "__main__":
    # Test the delivery engine
    logging.basicConfig(level=logging.INFO)

    print("Alert Delivery Engine Status:")
    print(json.dumps(get_delivery_status(), indent=2))

    # Test cooldown logic
    print("\nTesting cooldown logic:")
    print(f"should_fire_alert('test_alert'): {should_fire_alert('test_alert')}")
    print(f"should_fire_alert('test_alert'): {should_fire_alert('test_alert')} (should be False)")

    # Send test alert if channels configured
    if NOTIFICATION_CONFIG["email_enabled"] or NOTIFICATION_CONFIG["slack_enabled"]:
        print("\nSending test alert...")
        results = send_test_alert("all")
        print(f"Results: {results}")
    else:
        print("\nNo channels configured. Set SMTP_USER, SMTP_PASS, ALERT_EMAIL_TO, or SLACK_WEBHOOK_URL.")
