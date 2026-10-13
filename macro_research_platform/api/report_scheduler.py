"""
Report Scheduler for Macro Research Platform.

Auto-generates reports at scheduled times and stores them in archive.
Scheduled times:
- morning_briefing: 07:00 UTC (before market open)
- midday_update: 12:00 UTC (midday check)
- eod_summary: 17:00 UTC (end of day)

Keeps last 30 days of reports, purges older ones.
"""

import json
import logging
import threading
import requests
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional, List
from dataclasses import dataclass

# Setup logging
logger = logging.getLogger(__name__)

# Report archive directory
REPORTS_DIR = Path(__file__).parent.parent / "reports" / "archive"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

# Schedule configuration
SCHEDULE = {
    "morning_briefing": "07:00",
    "midday_update": "12:00",
    "eod_summary": "17:00",
}

# Report type to endpoint mapping
REPORT_TYPES = {
    "morning_briefing": {
        "name": "Morning Briefing",
        "type": "morning-briefing",
        "description": "Full 4-page institutional morning briefing",
    },
    "midday_update": {
        "name": "Midday Update",
        "type": "risk-summary",
        "description": "Risk indicators and signal update",
    },
    "eod_summary": {
        "name": "End of Day Summary",
        "type": "global-macro",
        "description": "Global macro summary and daily wrap",
    },
}

# Retention days
RETENTION_DAYS = 30


@dataclass
class ScheduledReport:
    """Represents a scheduled report."""
    report_type: str
    name: str
    schedule_time: str
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None

    def __post_init__(self):
        if self.next_run is None:
            self._calculate_next_run()

    def _calculate_next_run(self):
        """Calculate next run time based on schedule."""
        now = datetime.utcnow()
        hour, minute = map(int, self.schedule_time.split(':'))
        next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if next_run <= now:
            next_run += timedelta(days=1)
        self.next_run = next_run

    def should_run(self) -> bool:
        """Check if report should run now."""
        if self.next_run is None:
            return False
        return datetime.utcnow() >= self.next_run

    def mark_run(self):
        """Mark report as run and calculate next run."""
        self.last_run = datetime.utcnow()
        self._calculate_next_run()


class ReportScheduler:
    """
    Scheduler for auto-generating reports at scheduled times.

    Usage:
        scheduler = ReportScheduler(api_base_url="http://localhost:8000")
        scheduler.start()
        # ... later
        scheduler.stop()
    """

    def __init__(self, api_base_url: str = "http://localhost:8000"):
        self.api_base_url = api_base_url
        self.reports_dir = REPORTS_DIR
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.reports: Dict[str, ScheduledReport] = {}
        self._init_reports()

    def _init_reports(self):
        """Initialize scheduled reports from config."""
        for report_type, config in REPORT_TYPES.items():
            schedule_time = SCHEDULE.get(report_type, "07:00")
            self.reports[report_type] = ScheduledReport(
                report_type=report_type,
                name=config["name"],
                schedule_time=schedule_time,
            )

    def start(self):
        """Start the scheduler in background thread."""
        if self.running:
            logger.warning("[Scheduler] Already running")
            return

        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        logger.info("[Scheduler] Report scheduler started")

    def stop(self):
        """Stop the scheduler."""
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=5)
        logger.info("[Scheduler] Report scheduler stopped")

    def _run_loop(self):
        """Main scheduler loop."""
        while self.running:
            try:
                # Check each report
                for report_type, report in self.reports.items():
                    if report.should_run():
                        self._generate_report(report_type)
                        report.mark_run()

                # Cleanup old reports daily
                if datetime.utcnow().hour == 3:  # 3 AM UTC cleanup
                    self._cleanup_old_reports()

            except Exception as e:
                logger.error(f"[Scheduler] Error in run loop: {e}")

            # Sleep for 60 seconds before next check
            import time
            time.sleep(60)

    def _generate_report(self, report_type: str) -> Optional[Path]:
        """
        Generate a report and save to archive.

        Args:
            report_type: Type of report to generate

        Returns:
            Path to saved report or None on failure
        """
        config = REPORT_TYPES.get(report_type)
        if not config:
            logger.error(f"[Scheduler] Unknown report type: {report_type}")
            return None

        now = datetime.utcnow()
        date_str = now.strftime("%Y-%m-%d")
        time_str = now.strftime("%H%M")

        # Generate filename
        filename = f"{report_type}_{date_str}_{time_str}.html"
        filepath = self.reports_dir / filename

        try:
            # Fetch report from API
            url = f"{self.api_base_url}/api/report/export"
            params = {
                "format": "html",
                "type": config["type"],
            }

            logger.info(f"[Scheduler] Generating {report_type}...")
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()

            # Save report
            html_content = response.text
            with open(filepath, "w") as f:
                f.write(html_content)

            logger.info(f"[Scheduler] Saved {report_type} to {filepath}")

            # Also save JSON metadata
            metadata = {
                "reportType": report_type,
                "name": config["name"],
                "generatedAt": now.isoformat(),
                "filepath": str(filepath),
                "description": config["description"],
            }
            meta_path = self.reports_dir / f"{report_type}_{date_str}_{time_str}.json"
            with open(meta_path, "w") as f:
                json.dump(metadata, f, indent=2)

            return filepath

        except Exception as e:
            logger.error(f"[Scheduler] Failed to generate {report_type}: {e}")
            return None

    def _cleanup_old_reports(self):
        """Purge reports older than RETENTION_DAYS."""
        try:
            cutoff = datetime.utcnow() - timedelta(days=RETENTION_DAYS)
            count = 0

            for file in self.reports_dir.iterdir():
                if file.is_file():
                    # Try to parse date from filename
                    try:
                        # Format: {type}_{date}_{time}.html
                        parts = file.stem.split("_")
                        if len(parts) >= 2:
                            date_str = parts[1]
                            file_date = datetime.strptime(date_str, "%Y-%m-%d")
                            if file_date < cutoff:
                                file.unlink()
                                count += 1
                    except (ValueError, IndexError):
                        pass

            if count > 0:
                logger.info(f"[Scheduler] Cleaned up {count} old reports")

        except Exception as e:
            logger.error(f"[Scheduler] Cleanup failed: {e}")

    def get_report_archive(self, days: int = 30) -> List[Dict]:
        """
        Get list of archived reports.

        Args:
            days: Number of days to look back

        Returns:
            List of report metadata dictionaries
        """
        try:
            cutoff = datetime.utcnow() - timedelta(days=days)
            reports = []

            for file in self.reports_dir.glob("*.json"):
                try:
                    with open(file, "r") as f:
                        metadata = json.load(f)
                        generated_at = datetime.fromisoformat(
                            metadata.get("generatedAt", "1970-01-01")
                        )
                        if generated_at >= cutoff:
                            reports.append(metadata)
                except Exception:
                    pass

            # Sort by generated time, newest first
            reports.sort(key=lambda x: x.get("generatedAt", ""), reverse=True)
            return reports

        except Exception as e:
            logger.error(f"[Scheduler] Failed to get archive: {e}")
            return []

    def get_latest_report(self, report_type: str) -> Optional[Dict]:
        """Get metadata for the latest report of a given type."""
        try:
            reports = self.get_report_archive(days=30)
            for report in reports:
                if report.get("reportType") == report_type:
                    return report
            return None
        except Exception:
            return None

    def get_status(self) -> Dict:
        """Get current scheduler status."""
        return {
            "running": self.running,
            "reports": {
                name: {
                    "name": report.name,
                    "schedule": report.schedule_time,
                    "lastRun": report.last_run.isoformat() if report.last_run else None,
                    "nextRun": report.next_run.isoformat() if report.next_run else None,
                }
                for name, report in self.reports.items()
            },
            "archiveCount": len(list(self.reports_dir.glob("*.html"))),
            "retentionDays": RETENTION_DAYS,
        }


# Global scheduler instance
_scheduler: Optional[ReportScheduler] = None


def get_scheduler(api_base_url: str = "http://localhost:8000") -> ReportScheduler:
    """Get or create global scheduler instance."""
    global _scheduler
    if _scheduler is None:
        _scheduler = ReportScheduler(api_base_url)
    return _scheduler


def start_scheduler(api_base_url: str = "http://localhost:8000"):
    """Start the report scheduler."""
    scheduler = get_scheduler(api_base_url)
    scheduler.start()
    return scheduler


def stop_scheduler():
    """Stop the report scheduler."""
    global _scheduler
    if _scheduler:
        _scheduler.stop()
        _scheduler = None


def get_archive_stats() -> Dict:
    """Get archive statistics for display."""
    try:
        reports = list(REPORTS_DIR.glob("*.html"))
        if not reports:
            return {
                "totalReports": 0,
                "latestReport": None,
                "reportTypes": {},
            }

        # Get latest report
        latest = max(reports, key=lambda f: f.stat().st_mtime)
        latest_type = latest.stem.split("_")[0]
        latest_date = datetime.fromtimestamp(latest.stat().st_mtime)

        # Count by type
        by_type = {}
        for report in reports:
            try:
                rtype = report.stem.split("_")[0]
                by_type[rtype] = by_type.get(rtype, 0) + 1
            except IndexError:
                pass

        return {
            "totalReports": len(reports),
            "latestReport": {
                "type": latest_type,
                "date": latest_date.isoformat(),
                "filename": latest.name,
            },
            "reportTypes": by_type,
        }
    except Exception as e:
        logger.error(f"Failed to get archive stats: {e}")
        return {
            "totalReports": 0,
            "latestReport": None,
            "reportTypes": {},
            "error": str(e),
        }


if __name__ == "__main__":
    # Test the scheduler
    logging.basicConfig(level=logging.INFO)

    scheduler = ReportScheduler()
    print(f"Reports directory: {REPORTS_DIR}")
    print(f"Scheduled reports:")
    for name, report in scheduler.reports.items():
        print(f"  {name}: {report.schedule_time} (next: {report.next_run})")

    # Generate a test report
    print("\nGenerating test report...")
    result = scheduler._generate_report("morning_briefing")
    if result:
        print(f"Generated: {result}")

    # Get archive stats
    print("\nArchive stats:")
    stats = get_archive_stats()
    print(json.dumps(stats, indent=2))
