"""
Alerting module for data integrity failures.
Supports email and Slack notifications when critical data issues occur.
"""
import logging
import os
from typing import List, Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# Alert severity levels
class AlertSeverity:
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"

class DataIntegrityAlerter:
    """
    Handles alerting for data integrity issues.
    Supports email (via SMTP) and Slack webhooks.
    """

    def __init__(self):
        self.slack_webhook_url = os.getenv("SLACK_WEBHOOK_URL")
        self.email_enabled = os.getenv("ALERT_EMAIL_ENABLED", "false").lower() == "true"
        self.smtp_host = os.getenv("SMTP_HOST", "localhost")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.alert_email_from = os.getenv("ALERT_EMAIL_FROM", "alerts@localhost")
        self.alert_email_to = os.getenv("ALERT_EMAIL_TO", "").split(",")

        # Rate limiting - don't spam
        self._last_alert_time: Optional[datetime] = None
        self._min_alert_interval_seconds = int(os.getenv("ALERT_INTERVAL_SECONDS", "300"))  # 5 min default

    def _can_send_alert(self) -> bool:
        """Check if enough time has passed since last alert."""
        if self._last_alert_time is None:
            return True
        elapsed = (datetime.now() - self._last_alert_time).total_seconds()
        return elapsed >= self._min_alert_interval_seconds

    async def send_data_integrity_alert(
        self,
        errors: List[str],
        severity: str = AlertSeverity.WARNING,
        context: Optional[Dict] = None
    ) -> bool:
        """
        Send alert for data integrity issues.

        Args:
            errors: List of error messages
            severity: AlertSeverity level
            context: Additional context dict

        Returns:
            True if alert was sent successfully
        """
        if not self._can_send_alert():
            logger.debug("Alert rate limited - skipping")
            return False

        self._last_alert_time = datetime.now()

        # Build alert message
        title = f"Data Integrity Alert: {len(errors)} errors detected"
        message = self._format_alert_message(errors, severity, context)

        # Send to all configured channels
        success = False

        if self.slack_webhook_url:
            try:
                await self._send_slack_alert(title, message, severity)
                success = True
            except Exception as e:
                logger.error(f"Failed to send Slack alert: {e}")

        if self.email_enabled:
            try:
                await self._send_email_alert(title, message, severity)
                success = True
            except Exception as e:
                logger.error(f"Failed to send email alert: {e}")

        # Always log
        if severity == AlertSeverity.CRITICAL:
            logger.critical(f"[ALERT] {title}: {errors[:3]}")
        else:
            logger.warning(f"[ALERT] {title}: {errors[:3]}")

        return success

    def _format_alert_message(
        self,
        errors: List[str],
        severity: str,
        context: Optional[Dict]
    ) -> str:
        """Format alert message for display."""
        lines = [
            f"Severity: {severity.upper()}",
            f"Timestamp: {datetime.now().isoformat()}",
            f"Error Count: {len(errors)}",
            "",
            "Errors:",
        ]
        for i, error in enumerate(errors[:10], 1):  # Top 10 errors
            lines.append(f"  {i}. {error}")

        if context:
            lines.append("")
            lines.append("Context:")
            for key, value in context.items():
                lines.append(f"  {key}: {value}")

        return "\n".join(lines)

    async def _send_slack_alert(self, title: str, message: str, severity: str):
        """Send alert to Slack via webhook."""
        import aiohttp

        # Color based on severity
        color_map = {
            AlertSeverity.INFO: "#36a64f",
            AlertSeverity.WARNING: "#ff9900",
            AlertSeverity.CRITICAL: "#ff0000"
        }

        payload = {
            "attachments": [{
                "color": color_map.get(severity, "#ff9900"),
                "title": title,
                "text": message,
                "footer": "Macro Research Platform",
                "ts": int(datetime.now().timestamp())
            }]
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.slack_webhook_url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                if response.status != 200:
                    raise Exception(f"Slack returned {response.status}")

    async def _send_email_alert(self, title: str, message: str, severity: str):
        """Send alert via email (SMTP)."""
        import aiosmtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        if not self.alert_email_to or self.alert_email_to == ['']:
            return

        msg = MIMEMultipart()
        msg['From'] = self.alert_email_from
        msg['To'] = ", ".join(self.alert_email_to)
        msg['Subject'] = f"[{severity.upper()}] {title}"

        msg.attach(MIMEText(message, 'plain'))

        await aiosmtplib.send(
            msg,
            hostname=self.smtp_host,
            port=self.smtp_port,
            use_tls=True
        )


# Global alerter instance
_data_alerter: Optional[DataIntegrityAlerter] = None

def get_alerter() -> DataIntegrityAlerter:
    """Get or create global alerter instance."""
    global _data_alerter
    if _data_alerter is None:
        _data_alerter = DataIntegrityAlerter()
    return _data_alerter


async def alert_on_data_integrity(
    errors: List[str],
    severity: str = AlertSeverity.WARNING,
    context: Optional[Dict] = None
):
    """
    Convenience function to send data integrity alert.

    Usage:
        await alert_on_data_integrity(
            errors=["Inflation 50% out of bounds"],
            severity=AlertSeverity.CRITICAL
        )
    """
    alerter = get_alerter()
    return await alerter.send_data_integrity_alert(errors, severity, context)
