"""
Economic Calendar Client for Macro Research Platform.

Fetches high-impact economic events from free public APIs.
Provides event filtering, countdown timers, and position sizing alerts.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from zoneinfo import ZoneInfo

import requests

logger = logging.getLogger(__name__)


@dataclass
class EconomicEvent:
    """Represents a single economic event."""
    title: str
    country: str
    currency: str
    date: datetime
    impact: str  # HIGH, MEDIUM, LOW
    forecast: Optional[str] = None
    previous: Optional[str] = None
    actual: Optional[str] = None
    event_id: Optional[str] = None


@dataclass
class CalendarAlert:
    """Position sizing alert based on upcoming events."""
    message: str
    severity: str  # info, warning, critical
    minutes_until: int
    event_title: str


class EconomicCalendarClient:
    """
    Client for fetching and processing economic calendar data.

    Data sources:
    - ForexFactory public calendar (no auth required)
    """

    HIGH_IMPACT_KEYWORDS = [
        "NFP", "Non-Farm", "Employment", "Unemployment",
        "CPI", "Inflation", "PCE",
        "FOMC", "Fed", "ECB", "BOE", "BOJ", "RBA",
        "GDP", "PMI", "Manufacturing",
        "Interest Rate", "Policy Rate",
        "Retail Sales", "Industrial Production"
    ]

    def __init__(self):
        self.cache = None
        self.cache_time = None
        self.cache_duration = timedelta(hours=1)

        # Major central bank meeting dates (hardcoded, updated quarterly)
        # These are approximate - user should update every 6 months
        self.central_bank_meetings = {
            "FED": [  # Federal Reserve
                "2025-01-29", "2025-03-19", "2025-05-07", "2025-06-11",
                "2025-07-30", "2025-09-17", "2025-10-29", "2025-12-10",
                "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-10",
                "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-09",
            ],
            "ECB": [  # European Central Bank
                "2025-01-30", "2025-03-06", "2025-04-17", "2025-06-05",
                "2025-07-24", "2025-09-11", "2025-10-23", "2025-12-11",
                "2026-01-29", "2026-03-12", "2026-04-30", "2026-06-04",
                "2026-07-23", "2026-09-10", "2026-10-22", "2026-12-10",
            ],
            "BOE": [  # Bank of England
                "2025-02-06", "2025-03-20", "2025-05-08", "2025-06-19",
                "2025-08-07", "2025-09-18", "2025-11-06", "2025-12-18",
                "2026-02-05", "2026-03-19", "2026-05-07", "2026-06-18",
                "2026-08-06", "2026-09-17", "2026-11-05", "2026-12-17",
            ],
            "BOJ": [  # Bank of Japan
                "2025-01-24", "2025-03-19", "2025-04-30", "2025-06-13",
                "2025-07-31", "2025-09-18", "2025-10-31", "2025-12-19",
                "2026-01-23", "2026-03-18", "2026-04-29", "2026-06-12",
                "2026-07-30", "2026-09-17", "2026-10-30", "2026-12-18",
            ],
        }

    def _get_cached_or_fetch(self, url: str) -> Optional[List[Dict]]:
        """Check cache or fetch fresh data."""
        now = datetime.now()

        if self.cache and self.cache_time and (now - self.cache_time) < self.cache_duration:
            logger.info("Using cached economic calendar data")
            return self.cache

        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()

            self.cache = data
            self.cache_time = now
            return data
        except Exception as e:
            logger.warning(f"Failed to fetch economic calendar: {e}")
            return None

    def fetch_forexfactory_calendar(self) -> List[EconomicEvent]:
        """
        Fetch calendar from ForexFactory public API.

        Returns events for current and next week.
        """
        url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

        data = self._get_cached_or_fetch(url)
        if not data:
            return []

        events = []
        utc = ZoneInfo("UTC")

        for item in data:
            try:
                # Parse the date
                date_str = item.get("date", "")
                time_str = item.get("time", "")

                if not date_str:
                    continue

                # Combine date and time
                if time_str and time_str not in ["", "Tentative", "All Day"]:
                    try:
                        event_time = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
                    except ValueError:
                        event_time = datetime.strptime(date_str, "%Y-%m-%d")
                else:
                    event_time = datetime.strptime(date_str, "%Y-%m-%d")

                event_time = event_time.replace(tzinfo=utc)

                # Map impact level
                impact = item.get("impact", "Low").upper()
                if impact not in ["HIGH", "MEDIUM", "LOW"]:
                    impact = "LOW"

                # Check if it's a high-impact event by keywords
                title = item.get("title", "")
                if impact != "HIGH" and self._is_high_impact_by_title(title):
                    impact = "HIGH"

                event = EconomicEvent(
                    title=title,
                    country=item.get("country", ""),
                    currency=item.get("currency", ""),
                    date=event_time,
                    impact=impact,
                    forecast=item.get("forecast"),
                    previous=item.get("previous"),
                    actual=item.get("actual"),
                    event_id=item.get("id")
                )

                events.append(event)

            except Exception as e:
                logger.warning(f"Failed to parse calendar event: {e}")
                continue

        # Sort by date
        events.sort(key=lambda x: x.date)

        return events

    def _is_high_impact_by_title(self, title: str) -> bool:
        """Check if event title contains high-impact keywords."""
        title_upper = title.upper()
        return any(keyword.upper() in title_upper for keyword in self.HIGH_IMPACT_KEYWORDS)

    def get_high_impact_events(self, days_ahead: int = 7) -> List[EconomicEvent]:
        """
        Get high-impact events for the next N days.

        Args:
            days_ahead: Number of days to look ahead

        Returns:
            List of high-impact EconomicEvent objects
        """
        all_events = self.fetch_forexfactory_calendar()
        now = datetime.now(ZoneInfo("UTC"))
        cutoff = now + timedelta(days=days_ahead)

        high_impact = [
            e for e in all_events
            if e.impact == "HIGH" and now <= e.date <= cutoff
        ]

        return high_impact

    def get_positioning_alerts(self) -> List[CalendarAlert]:
        """
        Generate position sizing alerts based on upcoming events.

        Returns:
            List of alerts with severity and timing
        """
        events = self.get_high_impact_events(days_ahead=3)
        now = datetime.now(ZoneInfo("UTC"))
        alerts = []

        for event in events:
            minutes_until = int((event.date - now).total_seconds() / 60)

            if minutes_until < 0:
                continue

            # Determine severity based on event type and timing
            severity = "info"
            message = f"{event.title} in {self._format_time_remaining(minutes_until)}"

            if minutes_until <= 30:
                severity = "critical"
                message = f"MARKET-MOVING EVENT IN {minutes_until} MINUTES — consider reducing position sizing"
            elif minutes_until <= 120:
                severity = "warning"
                message = f"{event.title} in {self._format_time_remaining(minutes_until)} — elevated volatility expected"
            elif "FOMC" in event.title.upper() or "Fed" in event.title:
                severity = "warning"
                message = f"Fed event: {event.title} on {event.date.strftime('%b %d')}"
            elif "NFP" in event.title.upper() or "Non-Farm" in event.title:
                severity = "warning"
                message = f"NFP release: {event.date.strftime('%b %d %H:%M')} UTC"

            alerts.append(CalendarAlert(
                message=message,
                severity=severity,
                minutes_until=minutes_until,
                event_title=event.title
            ))

        # Sort by urgency (minutes until)
        alerts.sort(key=lambda x: x.minutes_until)

        return alerts

    def _format_time_remaining(self, minutes: int) -> str:
        """Format minutes remaining into human-readable string."""
        if minutes < 60:
            return f"{minutes}m"
        hours = minutes // 60
        mins = minutes % 60
        if hours < 24:
            return f"{hours}h {mins}m" if mins > 0 else f"{hours}h"
        days = hours // 24
        remaining_hours = hours % 24
        return f"{days}d {remaining_hours}h" if remaining_hours > 0 else f"{days}d"

    def get_next_central_bank_meetings(self) -> List[Dict[str, Any]]:
        """
        Get next scheduled central bank meetings.

        Returns:
            List of upcoming CB meetings with dates
        """
        now = datetime.now().date()
        meetings = []

        for bank, dates in self.central_bank_meetings.items():
            for date_str in dates:
                meeting_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                if meeting_date >= now:
                    days_until = (meeting_date - now).days
                    meetings.append({
                        "bank": bank,
                        "date": date_str,
                        "days_until": days_until,
                        "formatted_date": meeting_date.strftime("%b %d, %Y")
                    })
                    break  # Only next meeting per bank

        meetings.sort(key=lambda x: x["days_until"])
        return meetings

    def to_dict(self) -> Dict[str, Any]:
        """Convert calendar data to dictionary for API response."""
        events = self.get_high_impact_events(days_ahead=14)
        alerts = self.get_positioning_alerts()
        cb_meetings = self.get_next_central_bank_meetings()

        now = datetime.now(ZoneInfo("UTC"))

        return {
            "events": [
                {
                    "title": e.title,
                    "country": e.country,
                    "currency": e.currency,
                    "date": e.date.isoformat(),
                    "time": e.date.strftime("%H:%M") if e.date.hour > 0 else None,
                    "impact": e.impact,
                    "forecast": e.forecast,
                    "previous": e.previous,
                    "actual": e.actual,
                    "is_today": e.date.date() == now.date(),
                    "is_tomorrow": (e.date.date() - now.date()).days == 1,
                }
                for e in events[:20]  # Limit to 20 events
            ],
            "alerts": [
                {
                    "message": a.message,
                    "severity": a.severity,
                    "minutes_until": a.minutes_until,
                    "event_title": a.event_title,
                }
                for a in alerts[:5]  # Top 5 alerts
            ],
            "central_bank_meetings": cb_meetings[:6],  # Next 6 CB meetings
            "last_updated": now.isoformat(),
        }


# Singleton instance for reuse
_calendar_client: Optional[EconomicCalendarClient] = None


def get_economic_calendar() -> EconomicCalendarClient:
    """Get or create economic calendar client singleton."""
    global _calendar_client
    if _calendar_client is None:
        _calendar_client = EconomicCalendarClient()
    return _calendar_client
