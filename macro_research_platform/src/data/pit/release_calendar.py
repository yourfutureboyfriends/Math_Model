"""
Release Calendar

Tracks when major macro data is normally released.
Prevents backtests from using data before it was actually available.

Typical release schedules for US macro data:
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class ReleaseSchedule:
    """Defines when a data series is typically released."""
    series_id: str
    series_name: str
    frequency: str                    # M, Q, A, W, D
    typical_release_day: int          # Day of month/week
    typical_release_lag_days: int     # Days after period end
    release_time: str                 # "08:30", "09:45", etc.
    source_agency: str                # BLS, BEA, Fed, etc.
    # For monthly: which week (1st, 2nd, 3rd, 4th)
    release_week_of_month: Optional[int] = None
    # Business days or calendar days
    use_business_days: bool = True


class ReleaseCalendar:
    """
    Central calendar for macro data releases.

    Ensures backtests respect publication schedules.
    """

    # Standard US macro release schedules
    DEFAULT_SCHEDULES: Dict[str, ReleaseSchedule] = {
        # Employment Situation (BLS) - First Friday of month, 8:30am
        "PAYEMS": ReleaseSchedule(
            series_id="PAYEMS",
            series_name="Nonfarm Payrolls",
            frequency="M",
            typical_release_day=1,  # First Friday
            typical_release_lag_days=3,  # ~3 days after month end
            release_time="08:30",
            source_agency="BLS",
            release_week_of_month=1,
        ),
        "UNRATE": ReleaseSchedule(
            series_id="UNRATE",
            series_name="Unemployment Rate",
            frequency="M",
            typical_release_day=1,
            typical_release_lag_days=3,
            release_time="08:30",
            source_agency="BLS",
            release_week_of_month=1,
        ),

        # CPI (BLS) - ~10-15th of month, 8:30am
        "CPIAUCSL": ReleaseSchedule(
            series_id="CPIAUCSL",
            series_name="CPI (All Urban Consumers)",
            frequency="M",
            typical_release_day=15,
            typical_release_lag_days=15,
            release_time="08:30",
            source_agency="BLS",
        ),
        "CPILFESL": ReleaseSchedule(
            series_id="CPILFESL",
            series_name="Core CPI",
            frequency="M",
            typical_release_day=15,
            typical_release_lag_days=15,
            release_time="08:30",
            source_agency="BLS",
        ),

        # PPI (BLS) - ~13-15th of month, 8:30am
        "PPIACO": ReleaseSchedule(
            series_id="PPIACO",
            series_name="Producer Price Index",
            frequency="M",
            typical_release_day=14,
            typical_release_lag_days=14,
            release_time="08:30",
            source_agency="BLS",
        ),

        # Retail Sales (Census) - ~13-15th of month, 8:30am
        "RSAFS": ReleaseSchedule(
            series_id="RSAFS",
            series_name="Retail Sales",
            frequency="M",
            typical_release_day=15,
            typical_release_lag_days=15,
            release_time="08:30",
            source_agency="Census",
        ),

        # Industrial Production (Fed) - ~15-17th of month, 9:15am
        "INDPRO": ReleaseSchedule(
            series_id="INDPRO",
            series_name="Industrial Production",
            frequency="M",
            typical_release_day=16,
            typical_release_lag_days=16,
            release_time="09:15",
            source_agency="Fed",
        ),

        # GDP (BEA) - Advance: ~30 days after quarter end
        "GDP": ReleaseSchedule(
            series_id="GDP",
            series_name="Gross Domestic Product",
            frequency="Q",
            typical_release_day=30,
            typical_release_lag_days=30,
            release_time="08:30",
            source_agency="BEA",
        ),

        # ISM PMI - First business day of month, 10:00am
        "ISM": ReleaseSchedule(
            series_id="ISM",
            series_name="ISM Manufacturing PMI",
            frequency="M",
            typical_release_day=1,
            typical_release_lag_days=1,
            release_time="10:00",
            source_agency="ISM",
        ),

        # FOMC Decisions - 8 per year, typically Wednesday
        "FEDFUNDS": ReleaseSchedule(
            series_id="FEDFUNDS",
            series_name="Federal Funds Rate",
            frequency="M",
            typical_release_day=1,
            typical_release_lag_days=0,
            release_time="14:00",
            source_agency="Fed",
        ),

        # Initial Claims (DOL) - Weekly, Thursday 8:30am
        "ICSA": ReleaseSchedule(
            series_id="ICSA",
            series_name="Initial Claims",
            frequency="W",
            typical_release_day=4,  # Thursday
            typical_release_lag_days=5,
            release_time="08:30",
            source_agency="DOL",
        ),
    }

    def __init__(self):
        self.schedules: Dict[str, ReleaseSchedule] = self.DEFAULT_SCHEDULES.copy()
        self.actual_release_dates: Dict[str, List[datetime]] = {}

    def estimate_release_date(
        self,
        series_id: str,
        observation_date: datetime
    ) -> Optional[datetime]:
        """
        Estimate when data for a given observation date was released.

        This is used when true vintage data is not available.
        """
        if series_id not in self.schedules:
            logger.warning(f"No release schedule for {series_id}, using default 30-day lag")
            return observation_date + timedelta(days=30)

        schedule = self.schedules[series_id]

        if schedule.frequency == "M":
            return self._estimate_monthly_release(schedule, observation_date)
        elif schedule.frequency == "Q":
            return self._estimate_quarterly_release(schedule, observation_date)
        elif schedule.frequency == "W":
            return self._estimate_weekly_release(schedule, observation_date)
        else:
            return observation_date + timedelta(days=schedule.typical_release_lag_days)

    def _estimate_monthly_release(
        self,
        schedule: ReleaseSchedule,
        observation_date: datetime
    ) -> datetime:
        """Estimate release date for monthly data."""
        # Start from first day of next month
        if observation_date.month == 12:
            next_month = datetime(observation_date.year + 1, 1, 1)
        else:
            next_month = datetime(observation_date.year, observation_date.month + 1, 1)

        # Apply typical lag
        estimated = next_month + timedelta(days=schedule.typical_release_lag_days)

        # Adjust for specific release patterns
        if schedule.release_week_of_month:
            # Find the Nth Friday (for payrolls)
            target_day = self._get_nth_weekday(
                estimated.year, estimated.month,
                4,  # Friday
                schedule.release_week_of_month
            )
            estimated = target_day

        return estimated

    def _estimate_quarterly_release(
        self,
        schedule: ReleaseSchedule,
        observation_date: datetime
    ) -> datetime:
        """Estimate release date for quarterly data."""
        # Quarter end
        quarter = (observation_date.month - 1) // 3 + 1
        quarter_end_month = quarter * 3

        # Advance estimate: ~30 days after quarter end
        # Second estimate: ~60 days after
        # Final: ~90 days after
        return observation_date + timedelta(days=schedule.typical_release_lag_days)

    def _estimate_weekly_release(
        self,
        schedule: ReleaseSchedule,
        observation_date: datetime
    ) -> datetime:
        """Estimate release date for weekly data."""
        # Weekly data typically released a few days after the week ends
        return observation_date + timedelta(days=schedule.typical_release_lag_days)

    def _get_nth_weekday(
        self,
        year: int,
        month: int,
        weekday: int,  # 0=Mon, 4=Fri
        n: int
    ) -> datetime:
        """Get the Nth occurrence of a weekday in a month."""
        import calendar

        # Get calendar for month
        cal = calendar.Calendar()
        month_days = cal.monthdayscalendar(year, month)

        # Find Nth occurrence of weekday
        count = 0
        for week in month_days:
            if week[weekday] != 0:
                count += 1
                if count == n:
                    return datetime(year, month, week[weekday])

        # Fallback to last occurrence
        for week in reversed(month_days):
            if week[weekday] != 0:
                return datetime(year, month, week[weekday])

        raise ValueError(f"Cannot find {n}th weekday in {year}-{month}")

    def get_release_schedule(self, series_id: str) -> Optional[ReleaseSchedule]:
        """Get release schedule for a series."""
        return self.schedules.get(series_id)

    def add_release_date(
        self,
        series_id: str,
        observation_date: datetime,
        actual_release_date: datetime
    ) -> None:
        """
        Record an actual release date to improve future estimates.

        This should be called when we observe true publication dates
        (e.g., from ALFRED or news archives).
        """
        key = f"{series_id}_{observation_date.strftime('%Y-%m')}"

        if key not in self.actual_release_dates:
            self.actual_release_dates[key] = []

        self.actual_release_dates[key].append(actual_release_date)

    def get_data_availability_matrix(
        self,
        series_ids: List[str],
        start_date: datetime,
        end_date: datetime,
        as_of_date: Optional[datetime] = None
    ) -> pd.DataFrame:
        """
        Create a matrix showing when each series was available.

        Useful for understanding data availability for backtests.
        """
        as_of = as_of_date or datetime.now()
        dates = pd.date_range(start_date, end_date, freq='D')

        matrix = pd.DataFrame(index=dates, columns=series_ids)
        matrix[:] = False

        for series_id in series_ids:
            schedule = self.schedules.get(series_id)
            if not schedule:
                continue

            current = start_date
            while current <= end_date:
                release = self.estimate_release_date(series_id, current)
                if release and release <= as_of:
                    # Mark all dates from release onwards as having this data
                    mask = matrix.index >= release
                    matrix.loc[mask, series_id] = True

                # Move to next period
                if schedule.frequency == "M":
                    if current.month == 12:
                        current = datetime(current.year + 1, 1, 1)
                    else:
                        current = datetime(current.year, current.month + 1, 1)
                elif schedule.frequency == "Q":
                    quarter = (current.month - 1) // 3
                    if quarter == 3:
                        current = datetime(current.year + 1, 1, 1)
                    else:
                        current = datetime(current.year, (quarter + 1) * 3 + 1, 1)
                else:
                    current += timedelta(days=30)

        return matrix

    def get_next_releases(
        self,
        days_ahead: int = 7
    ) -> List[Tuple[datetime, str, str]]:
        """
        Get upcoming data releases for the next N days.

        Returns list of (date, series_name, source_agency) tuples.
        """
        today = datetime.now()
        end = today + timedelta(days=days_ahead)

        upcoming = []

        for series_id, schedule in self.schedules.items():
            # Estimate next release
            # This is simplified - in practice would need calendar logic
            next_release = today + timedelta(days=schedule.typical_release_lag_days)

            if today <= next_release <= end:
                upcoming.append((
                    next_release,
                    schedule.series_name,
                    schedule.source_agency
                ))

        return sorted(upcoming, key=lambda x: x[0])


def validate_no_lookahead(
    df: pd.DataFrame,
    as_of_date: datetime,
    release_calendar: ReleaseCalendar
) -> pd.DataFrame:
    """
    Validate that a DataFrame contains no lookahead bias.

    Returns a cleaned DataFrame with any future data removed.
    """
    clean_data = df.copy()

    for col in clean_data.columns:
        schedule = release_calendar.get_release_schedule(col)
        if not schedule:
            continue

        for idx in clean_data.index:
            if isinstance(idx, datetime):
                release = release_calendar.estimate_release_date(col, idx)
                if release and release > as_of_date:
                    # This data shouldn't be known yet
                    clean_data.loc[idx, col] = None

    return clean_data.dropna(how='all')
