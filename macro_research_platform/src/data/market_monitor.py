"""
Global Market Monitor for Macro Research Platform.

Section A: Global Market Data
- 21+ equity indices (DM + EM)
- VIX complex (6 volatility indices)
- Real-time market clock
- Momentum signals and breadth analysis
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from zoneinfo import ZoneInfo
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class MarketIndex:
    """Single market index data."""
    ticker: str
    name: str
    region: str  # US, EU, Asia, EM
    price: Optional[float] = None
    change_1d: Optional[float] = None
    change_1w: Optional[float] = None
    change_1m: Optional[float] = None
    week_52_high: Optional[float] = None
    week_52_low: Optional[float] = None
    week_52_percentile: Optional[float] = None
    momentum_signal: str = "NEUTRAL"
    is_open: bool = False
    last_updated: Optional[datetime] = None


@dataclass
class MarketClock:
    """Market open/closed status."""
    exchange: str
    status: str  # OPEN, PRE_MARKET, POST_MARKET, CLOSED, WEEKEND
    local_time: str
    time_to_open_minutes: Optional[int] = None
    time_to_close_minutes: Optional[int] = None
    next_session: str = ""


@dataclass
class GlobalMarketData:
    """Complete global market monitor data."""
    indices: List[MarketIndex] = field(default_factory=list)
    dm_average_1m: Optional[float] = None
    em_average_1m: Optional[float] = None
    dm_em_spread: Optional[float] = None
    global_risk_on_score: Optional[float] = None
    fear_composite: Optional[float] = None
    fear_status: str = "NORMAL"
    market_clock: List[MarketClock] = field(default_factory=list)
    timestamp: Optional[datetime] = None


class GlobalMarketMonitor:
    """
    Global equity market monitor with real-time data.

    Sources:
    - yfinance for live index prices
    - Computed metrics for momentum and breadth
    """

    # Developed Market Indices
    DM_INDICES = [
        ("^GSPC", "S&P 500", "US"),
        ("^NDX", "Nasdaq 100", "US"),
        ("^DJI", "Dow Jones", "US"),
        ("^RUT", "Russell 2000", "US"),
        ("^FTSE", "FTSE 100", "UK"),
        ("^GDAXI", "DAX", "DE"),
        ("^FCHI", "CAC 40", "FR"),
        ("^STOXX50E", "Euro Stoxx 50", "EU"),
        ("^N225", "Nikkei 225", "JP"),
        ("^HSI", "Hang Seng", "HK"),
        ("^AXJO", "ASX 200", "AU"),
        ("^GSPTSE", "TSX Composite", "CA"),
        ("^SMI", "SMI", "CH"),
    ]

    # Emerging Market Indices
    EM_INDICES = [
        ("EEM", "EM ETF", "EM"),
        ("^BSESN", "Sensex", "IN"),
        ("^BVSP", "Bovespa", "BR"),
        ("^MXX", "IPC", "MX"),
        ("000001.SS", "Shanghai Comp", "CN"),
        ("^KS11", "KOSPI", "KR"),
        ("^TWII", "TAIEX", "TW"),
    ]

    # VIX Complex
    VIX_INDICES = [
        ("^VIX", "VIX", "Equity Volatility"),
        ("^VXN", "VXN", "Nasdaq Volatility"),
        ("^RVX", "RVX", "Russell 2000 Volatility"),
        ("^OVX", "OVX", "Oil Volatility"),
        ("^GVZ", "GVZ", "Gold Volatility"),
        ("^EVZ", "EVZ", "Euro Currency Volatility"),
    ]

    # Market hours by exchange
    MARKET_HOURS = {
        "NYSE/NASDAQ": {
            "tz": "America/New_York",
            "open": "09:30",
            "close": "16:00",
            "pre_market": "04:00",
            "post_market": "20:00",
        },
        "LSE": {
            "tz": "Europe/London",
            "open": "08:00",
            "close": "16:30",
        },
        "Xetra/Euronext": {
            "tz": "Europe/Paris",
            "open": "09:00",
            "close": "17:30",
        },
        "TSE": {
            "tz": "Asia/Tokyo",
            "open": "09:00",
            "close": "15:00",
            "break_start": "11:30",
            "break_end": "12:30",
        },
        "HKEx": {
            "tz": "Asia/Hong_Kong",
            "open": "09:30",
            "close": "16:00",
            "break_start": "12:00",
            "break_end": "13:00",
        },
        "SGX": {
            "tz": "Asia/Singapore",
            "open": "09:00",
            "close": "17:00",
            "break_start": "12:00",
            "break_end": "13:00",
        },
        "ASX": {
            "tz": "Australia/Sydney",
            "open": "10:00",
            "close": "16:00",
        },
    }

    def __init__(self):
        self._yf_cache: Dict[str, Any] = {}
        self._cache_time: Optional[datetime] = None
        self.cache_duration = timedelta(minutes=5)

    def _is_cache_valid(self) -> bool:
        """Check if cached data is still valid."""
        if self._cache_time is None or not self._yf_cache:
            return False
        return (datetime.now() - self._cache_time) < self.cache_duration

    def _fetch_yf_data(self, ticker: str) -> Dict[str, Any]:
        """Fetch data from yfinance with caching."""
        try:
            import yfinance as yf

            if ticker in self._yf_cache and self._is_cache_valid():
                return self._yf_cache[ticker]

            stock = yf.Ticker(ticker)
            hist = stock.history(period="1y")
            info = stock.info

            if hist.empty:
                return {}

            current = hist["Close"].iloc[-1]
            prev = hist["Close"].iloc[-2] if len(hist) > 1 else current
            week_ago = hist["Close"].iloc[-6] if len(hist) > 5 else prev
            month_ago = hist["Close"].iloc[-22] if len(hist) > 21 else prev

            week_52_high = hist["High"].max()
            week_52_low = hist["Low"].min()

            data = {
                "price": current,
                "change_1d": ((current - prev) / prev) * 100 if prev != 0 else 0,
                "change_1w": ((current - week_ago) / week_ago) * 100 if week_ago != 0 else 0,
                "change_1m": ((current - month_ago) / month_ago) * 100 if month_ago != 0 else 0,
                "week_52_high": week_52_high,
                "week_52_low": week_52_low,
                "last_updated": datetime.now(),
            }

            self._yf_cache[ticker] = data
            return data

        except Exception as e:
            logger.warning(f"Failed to fetch {ticker}: {e}")
            return {}

    def _calculate_52w_percentile(self, price: float, high: float, low: float) -> float:
        """Calculate 52-week percentile position."""
        if high == low:
            return 50.0
        return ((price - low) / (high - low)) * 100

    def _calculate_momentum_signal(self, change_1m: float) -> str:
        """Calculate momentum signal based on 1M change."""
        if change_1m > 5:
            return "UPTREND"
        elif change_1m < -5:
            return "DOWNTREND"
        return "NEUTRAL"

    def fetch_equity_indices(self) -> List[MarketIndex]:
        """Fetch all equity indices with metrics."""
        indices = []

        # Fetch DM indices
        for ticker, name, region in self.DM_INDICES:
            data = self._fetch_yf_data(ticker)
            if not data:
                continue

            percentile = self._calculate_52w_percentile(
                data.get("price", 0),
                data.get("week_52_high", 1),
                data.get("week_52_low", 0)
            )

            index = MarketIndex(
                ticker=ticker,
                name=name,
                region=region,
                price=data.get("price"),
                change_1d=round(data.get("change_1d", 0), 2),
                change_1w=round(data.get("change_1w", 0), 2),
                change_1m=round(data.get("change_1m", 0), 2),
                week_52_high=data.get("week_52_high"),
                week_52_low=data.get("week_52_low"),
                week_52_percentile=round(percentile, 1),
                momentum_signal=self._calculate_momentum_signal(data.get("change_1m", 0)),
                last_updated=data.get("last_updated"),
            )
            indices.append(index)

        # Fetch EM indices
        for ticker, name, region in self.EM_INDICES:
            data = self._fetch_yf_data(ticker)
            if not data:
                continue

            percentile = self._calculate_52w_percentile(
                data.get("price", 0),
                data.get("week_52_high", 1),
                data.get("week_52_low", 0)
            )

            index = MarketIndex(
                ticker=ticker,
                name=name,
                region=region,
                price=data.get("price"),
                change_1d=round(data.get("change_1d", 0), 2),
                change_1w=round(data.get("change_1w", 0), 2),
                change_1m=round(data.get("change_1m", 0), 2),
                week_52_high=data.get("week_52_high"),
                week_52_low=data.get("week_52_low"),
                week_52_percentile=round(percentile, 1),
                momentum_signal=self._calculate_momentum_signal(data.get("change_1m", 0)),
                last_updated=data.get("last_updated"),
            )
            indices.append(index)

        self._cache_time = datetime.now()
        return indices

    def fetch_vix_complex(self) -> Dict[str, Any]:
        """Fetch VIX and related volatility indices."""
        vol_data = {}
        values = []

        for ticker, name, desc in self.VIX_INDICES:
            data = self._fetch_yf_data(ticker)
            if data and data.get("price"):
                vol_data[name] = {
                    "price": round(data["price"], 2),
                    "change_1d": round(data.get("change_1d", 0), 2),
                    "description": desc,
                }
                values.append(data["price"])

        # Calculate fear composite
        if values:
            # Normalize VIX-like values to 0-100 scale
            normalized = []
            for v in values:
                # Map 10-40 range to 0-100
                norm = ((v - 10) / 30) * 100 if v > 10 else 0
                norm = min(max(norm, 0), 100)  # Clamp
                normalized.append(norm)

            fear_composite = np.mean(normalized) if normalized else 50

            # Determine status
            if fear_composite > 70:
                fear_status = "FEAR ELEVATED"
            elif fear_composite > 80:
                fear_status = "SYSTEMIC FEAR"
            elif fear_composite < 30:
                fear_status = "COMPLACENT"
            else:
                fear_status = "NORMAL"
        else:
            fear_composite = None
            fear_status = "UNAVAILABLE"

        return {
            "indices": vol_data,
            "fear_composite": round(fear_composite, 1) if fear_composite else None,
            "fear_status": fear_status,
        }

    def get_market_clock(self) -> List[MarketClock]:
        """Get real-time market status for all exchanges."""
        now_utc = datetime.now(ZoneInfo("UTC"))
        clocks = []

        for exchange, hours in self.MARKET_HOURS.items():
            try:
                tz = ZoneInfo(hours["tz"])
                local_time = now_utc.astimezone(tz)

                # Parse hours
                open_time = datetime.strptime(hours["open"], "%H:%M").time()
                close_time = datetime.strptime(hours["close"], "%H:%M").time()

                open_dt = datetime.combine(local_time.date(), open_time, tz)
                close_dt = datetime.combine(local_time.date(), close_time, tz)

                # Check if weekend
                if local_time.weekday() >= 5:  # Saturday=5, Sunday=6
                    status = "WEEKEND"
                    next_open = open_dt + timedelta(days=(7 - local_time.weekday()))
                    time_to_open = int((next_open - local_time).total_seconds() / 60)
                    clocks.append(MarketClock(
                        exchange=exchange,
                        status=status,
                        local_time=local_time.strftime("%H:%M"),
                        time_to_open_minutes=time_to_open,
                        next_session=next_open.strftime("%a %H:%M"),
                    ))
                    continue

                # Check pre/post market (US only)
                if "pre_market" in hours and "post_market" in hours:
                    pre_time = datetime.strptime(hours["pre_market"], "%H:%M").time()
                    post_time = datetime.strptime(hours["post_market"], "%H:%M").time()
                    pre_dt = datetime.combine(local_time.date(), pre_time, tz)
                    post_dt = datetime.combine(local_time.date(), post_time, tz)

                    if pre_dt <= local_time < open_dt:
                        status = "PRE_MARKET"
                        time_to_open = int((open_dt - local_time).total_seconds() / 60)
                        clocks.append(MarketClock(
                            exchange=exchange,
                            status=status,
                            local_time=local_time.strftime("%H:%M"),
                            time_to_open_minutes=time_to_open,
                            next_session="Open " + open_time.strftime("%H:%M"),
                        ))
                        continue
                    elif close_dt <= local_time < post_dt:
                        status = "POST_MARKET"
                        time_to_close = int((post_dt - local_time).total_seconds() / 60)
                        clocks.append(MarketClock(
                            exchange=exchange,
                            status=status,
                            local_time=local_time.strftime("%H:%M"),
                            time_to_close_minutes=time_to_close,
                        ))
                        continue

                # Regular hours
                if open_dt <= local_time <= close_dt:
                    status = "OPEN"
                    time_to_close = int((close_dt - local_time).total_seconds() / 60)
                    clocks.append(MarketClock(
                        exchange=exchange,
                        status=status,
                        local_time=local_time.strftime("%H:%M"),
                        time_to_close_minutes=time_to_close,
                    ))
                else:
                    status = "CLOSED"
                    next_open = open_dt + timedelta(days=1)
                    time_to_open = int((next_open - local_time).total_seconds() / 60)
                    clocks.append(MarketClock(
                        exchange=exchange,
                        status=status,
                        local_time=local_time.strftime("%H:%M"),
                        time_to_open_minutes=time_to_open,
                        next_session=next_open.strftime("%a %H:%M"),
                    ))

            except Exception as e:
                logger.warning(f"Failed to get clock for {exchange}: {e}")
                continue

        return clocks

    def calculate_global_markets(self) -> Dict[str, Any]:
        """
        Calculate complete global market monitor data.

        Returns:
            Dictionary with indices, aggregates, VIX complex, and market clock.
        """
        # Fetch equity indices
        indices = self.fetch_equity_indices()

        # Calculate aggregates
        dm_returns = [idx.change_1m for idx in indices if idx.region != "EM" and idx.change_1m is not None]
        em_returns = [idx.change_1m for idx in indices if idx.region == "EM" and idx.change_1m is not None]

        dm_average_1m = np.mean(dm_returns) if dm_returns else None
        em_average_1m = np.mean(em_returns) if em_returns else None
        dm_em_spread = (dm_average_1m - em_average_1m) if dm_average_1m and em_average_1m else None

        # Global risk-on score (% of indices with positive 1M return)
        all_returns = [idx.change_1m for idx in indices if idx.change_1m is not None]
        positive_count = sum(1 for r in all_returns if r and r > 0)
        global_risk_on_score = (positive_count / len(all_returns) * 100) if all_returns else None

        # Fetch VIX complex
        vix_data = self.fetch_vix_complex()

        # Get market clock
        market_clock = self.get_market_clock()

        return {
            "indices": [
                {
                    "ticker": idx.ticker,
                    "name": idx.name,
                    "region": idx.region,
                    "price": idx.price,
                    "change1d": idx.change_1d,
                    "change1w": idx.change_1w,
                    "change1m": idx.change_1m,
                    "week52High": idx.week_52_high,
                    "week52Low": idx.week_52_low,
                    "week52Percentile": idx.week_52_percentile,
                    "momentumSignal": idx.momentum_signal,
                }
                for idx in indices
            ],
            "dmAverage1m": round(dm_average_1m, 2) if dm_average_1m else None,
            "emAverage1m": round(em_average_1m, 2) if em_average_1m else None,
            "dmEmSpread": round(dm_em_spread, 2) if dm_em_spread else None,
            "globalRiskOnScore": round(global_risk_on_score, 1) if global_risk_on_score else None,
            "vixComplex": vix_data,
            "marketClock": [
                {
                    "exchange": c.exchange,
                    "status": c.status,
                    "localTime": c.local_time,
                    "timeToOpenMinutes": c.time_to_open_minutes,
                    "timeToCloseMinutes": c.time_to_close_minutes,
                    "nextSession": c.next_session,
                }
                for c in market_clock
            ],
            "timestamp": datetime.now().isoformat(),
        }


# Singleton instance
_monitor_instance: Optional[GlobalMarketMonitor] = None


def get_market_monitor() -> GlobalMarketMonitor:
    """Get or create global market monitor singleton."""
    global _monitor_instance
    if _monitor_instance is None:
        _monitor_instance = GlobalMarketMonitor()
    return _monitor_instance


def calculate_global_markets() -> Dict[str, Any]:
    """Public API for global market data."""
    monitor = get_market_monitor()
    return monitor.calculate_global_markets()
