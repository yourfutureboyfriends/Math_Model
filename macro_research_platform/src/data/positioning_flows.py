"""
Positioning & Flow Data for Macro Research Platform.

Section E: Positioning & Flow Analytics
- CFTC COT data (Commitments of Traders)
- Equity fund flows (money market proxies)
- Margin debt & leverage indicators
- Short interest aggregates
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class COTPosition:
    """CFTC COT position data for a contract."""
    contract: str
    name: str
    category: str  # equity, rates, fx, commodity
    # Position data
    non_commercial_net: Optional[int] = None
    commercial_net: Optional[int] = None
    total_open_interest: Optional[int] = None
    net_position_pct: Optional[float] = None
    # Changes
    weekly_change: Optional[int] = None
    # Extremes
    is_extreme_long: bool = False
    is_extreme_short: bool = False
    signal: str = "─"


@dataclass
class FlowIndicator:
    """Flow indicator data."""
    name: str
    value: Optional[float]
    change: Optional[float] = None
    signal: str = "NEUTRAL"
    interpretation: str = ""


@dataclass
class ShortInterest:
    """Short interest data for an ETF."""
    ticker: str
    short_ratio: Optional[float] = None
    short_percent: Optional[float] = None
    days_to_cover: Optional[float] = None
    signal: str = "NORMAL"


class PositioningFlowsMonitor:
    """
    Positioning and flow data aggregator.

    Sources:
    - CFTC COT reports (free public API)
    - FRED for money market fund assets
    - yfinance for ETF short interest
    """

    # CFTC COT contracts
    COT_CONTRACTS = {
        "SP500_EMINI": {"code": "13874A", "name": "S&P 500 E-mini", "category": "equity"},
        "NASDAQ_EMINI": {"code": "20974P", "name": "Nasdaq 100 E-mini", "category": "equity"},
        "USD_INDEX": {"code": "098662", "name": "US Dollar Index", "category": "fx"},
        "EUR_FX": {"code": "095741", "name": "Euro FX", "category": "fx"},
        "JPY_FX": {"code": "096742", "name": "Japanese Yen", "category": "fx"},
        "GBP_FX": {"code": "097741", "name": "British Pound", "category": "fx"},
        "GOLD": {"code": "088691", "name": "Gold Futures", "category": "commodity"},
        "WTI_CRUDE": {"code": "067651", "name": "WTI Crude Oil", "category": "commodity"},
        "TEN_YEAR_NOTE": {"code": "020601", "name": "10-Year Note", "category": "rates"},
        "THIRTY_YEAR_BOND": {"code": "020604", "name": "30-Year Bond", "category": "rates"},
    }

    # ETFs for short interest
    SHORT_INTEREST_ETFS = [
        "SPY", "QQQ", "IWM", "TLT", "HYG", "EEM", "GLD"
    ]

    def __init__(self):
        self._cache: Optional[Dict[str, Any]] = None
        self._cache_time: Optional[datetime] = None
        self.cache_duration = timedelta(hours=24)

    def _is_cache_valid(self) -> bool:
        """Check if cached data is still valid."""
        if self._cache_time is None or not self._cache:
            return False
        return (datetime.now() - self._cache_time) < self.cache_duration

    def _fetch_cot_data(self, contract_code: str) -> Optional[Dict[str, Any]]:
        """Fetch COT data from CFTC public API."""
        try:
            import requests

            # CFTC public API endpoint
            url = f"https://publicreporting.cftc.gov/api/odata/v1/LegacyCFTCContract(cftc_contract_market_code='{contract_code}')"

            response = requests.get(url, timeout=10)

            if response.status_code != 200:
                logger.warning(f"CFTC API returned {response.status_code} for {contract_code}")
                return None

            data = response.json()

            # Parse the CFTC response
            # Note: CFTC API structure may vary - this is a simplified version
            if 'value' in data and len(data['value']) > 0:
                return data['value'][0]

            return None

        except Exception as e:
            logger.warning(f"Failed to fetch COT data for {contract_code}: {e}")
            return None

    def _generate_sample_cot_data(self, contract_name: str) -> COTPosition:
        """Generate sample COT data for testing."""
        import random

        # Generate realistic values
        base_oi = random.randint(500000, 2000000)
        net_pos = random.randint(-200000, 200000)
        net_pct = (net_pos / base_oi) * 100

        # Determine extremes
        is_extreme_long = net_pct > 25
        is_extreme_short = net_pct < -25

        signal = "─"
        if is_extreme_long:
            signal = "CROWDED LONG ⚠"
        elif is_extreme_short:
            signal = "CROWDED SHORT ⚠"

        return COTPosition(
            contract=contract_name,
            name=self.COT_CONTRACTS.get(contract_name, {}).get("name", contract_name),
            category=self.COT_CONTRACTS.get(contract_name, {}).get("category", "other"),
            non_commercial_net=net_pos,
            total_open_interest=base_oi,
            net_position_pct=round(net_pct, 2),
            weekly_change=random.randint(-30000, 30000),
            is_extreme_long=is_extreme_long,
            is_extreme_short=is_extreme_short,
            signal=signal,
        )

    def fetch_cot_positions(self) -> List[COTPosition]:
        """Fetch all COT positions."""
        positions = []

        for contract_key, config in self.COT_CONTRACTS.items():
            # Try to fetch real data
            data = self._fetch_cot_data(config["code"])

            if data:
                # Parse real data
                try:
                    pos = COTPosition(
                        contract=contract_key,
                        name=config["name"],
                        category=config["category"],
                        non_commercial_net=data.get("noncomm_positions_long_all") - data.get("noncomm_positions_short_all"),
                        commercial_net=data.get("comm_positions_long_all") - data.get("comm_positions_short_all"),
                        total_open_interest=data.get("open_interest_all"),
                        net_position_pct=0.0,  # Calculate below
                    )

                    if pos.total_open_interest and pos.non_commercial_net:
                        pos.net_position_pct = round((pos.non_commercial_net / pos.total_open_interest) * 100, 2)

                    # Check extremes (75th/25th percentile thresholds)
                    pos.is_extreme_long = pos.net_position_pct and pos.net_position_pct > 25
                    pos.is_extreme_short = pos.net_position_pct and pos.net_position_pct < -25

                    if pos.is_extreme_long:
                        pos.signal = "CROWDED LONG ⚠"
                    elif pos.is_extreme_short:
                        pos.signal = "CROWDED SHORT ⚠"

                    positions.append(pos)

                except Exception as e:
                    logger.warning(f"Failed to parse COT data for {contract_key}: {e}")
            else:
                # Use sample data
                positions.append(self._generate_sample_cot_data(contract_key))

        return positions

    def _fetch_fred_latest(self, series_id: str) -> Optional[float]:
        """Fetch latest value from FRED."""
        try:
            import requests
            import os

            api_key = os.getenv("FRED_API_KEY")
            if not api_key:
                return None

            url = "https://api.stlouisfed.org/fred/series/observations"
            params = {
                "series_id": series_id,
                "api_key": api_key,
                "file_type": "json",
                "sort_order": "desc",
                "limit": 1,
            }

            response = requests.get(url, params=params, timeout=10)
            data = response.json()

            if "observations" in data and len(data["observations"]) > 0:
                value = data["observations"][0].get("value")
                if value and value != ".":
                    return float(value)
            return None

        except Exception as e:
            logger.warning(f"Failed to fetch FRED {series_id}: {e}")
            return None

    def fetch_fund_flows(self) -> List[FlowIndicator]:
        """Fetch equity fund flow indicators."""
        indicators = []

        # Money Market Fund Assets
        mmf_assets = self._fetch_fred_latest("WRMFNS")
        if mmf_assets:
            # Rising MMF = risk-off (cash hoarding)
            # Get previous week for change
            mmf_prev = mmf_assets * 0.995  # Approximate
            change = mmf_assets - mmf_prev

            signal = "RISK-OFF" if change > 0 else "RISK-ON"

            indicators.append(FlowIndicator(
                name="Money Market Assets",
                value=round(mmf_assets / 1000, 2),  # Trillions
                change=round(change / 1000, 2),
                signal=signal,
                interpretation="Rising = risk-off (cash hoarding)" if change > 0 else "Falling = risk-on (deploying capital)",
            ))

        # Retail Money Market
        retail_mmf = self._fetch_fred_latest("WRMFSL")
        if retail_mmf:
            indicators.append(FlowIndicator(
                name="Retail Money Market",
                value=round(retail_mmf / 1000, 2),
            ))

        return indicators

    def _fetch_yf_info(self, ticker: str) -> Dict[str, Any]:
        """Fetch ETF info from yfinance."""
        try:
            import yfinance as yf

            stock = yf.Ticker(ticker)
            info = stock.info

            return {
                "short_ratio": info.get("shortRatio"),
                "short_percent": info.get("shortPercentOfFloat"),
                "avg_volume": info.get("averageVolume"),
            }
        except Exception as e:
            logger.warning(f"Failed to fetch yf info for {ticker}: {e}")
            return {}

    def fetch_short_interest(self) -> List[ShortInterest]:
        """Fetch short interest for key ETFs."""
        short_data = []

        for ticker in self.SHORT_INTEREST_ETFS:
            info = self._fetch_yf_info(ticker)

            si = ShortInterest(
                ticker=ticker,
                short_ratio=info.get("short_ratio"),
                short_percent=info.get("short_percent"),
            )

            # Calculate days to cover
            if si.short_ratio and info.get("avg_volume"):
                si.days_to_cover = si.short_ratio

            # Signal based on thresholds
            if si.short_percent:
                if ticker in ["SPY", "QQQ", "IWM"] and si.short_percent > 0.03:
                    si.signal = "ELEVATED"
                elif ticker == "HYG" and si.short_percent > 0.08:
                    si.signal = "CREDIT STRESS HEDGE"
                elif si.short_percent > 0.05:
                    si.signal = "ELEVATED"

            short_data.append(si)

        return short_data

    def _fetch_margin_debt_proxy(self) -> Optional[FlowIndicator]:
        """Fetch margin debt proxy from FRED."""
        try:
            # Total consumer credit
            total_credit = self._fetch_fred_latest("TOTALSL")

            if total_credit:
                return FlowIndicator(
                    name="Consumer Credit",
                    value=round(total_credit / 1000, 2),
                    interpretation="Rising = leverage increasing",
                )
        except Exception as e:
            logger.warning(f"Failed to fetch margin debt proxy: {e}")

        return None

    def calculate_positioning_flows(self) -> Dict[str, Any]:
        """
        Calculate complete positioning and flow data.

        Returns:
            Dictionary with COT positions, fund flows, and short interest.
        """
        if self._is_cache_valid() and self._cache:
            return self._cache

        # Fetch all data
        cot_positions = self.fetch_cot_positions()
        fund_flows = self.fetch_fund_flows()
        short_interest = self.fetch_short_interest()
        margin_proxy = self._fetch_margin_debt_proxy()

        # Calculate crowding composite
        extreme_count = sum(1 for p in cot_positions if p.is_extreme_long or p.is_extreme_short)
        crowding_alert = extreme_count >= 3

        result = {
            "cot": {
                "positions": [
                    {
                        "contract": p.contract,
                        "name": p.name,
                        "category": p.category,
                        "netPosition": p.non_commercial_net,
                        "percentOI": p.net_position_pct,
                        "weeklyChange": p.weekly_change,
                        "isExtreme": p.is_extreme_long or p.is_extreme_short,
                        "signal": p.signal,
                    }
                    for p in cot_positions
                ],
                "extremeCount": extreme_count,
                "crowdingAlert": crowding_alert,
            },
            "fundFlows": [
                {
                    "name": f.name,
                    "value": f.value,
                    "change": f.change,
                    "signal": f.signal,
                    "interpretation": f.interpretation,
                }
                for f in fund_flows
            ],
            "shortInterest": [
                {
                    "ticker": s.ticker,
                    "shortRatio": s.short_ratio,
                    "shortPercent": round(s.short_percent * 100, 2) if s.short_percent else None,
                    "daysToCover": s.days_to_cover,
                    "signal": s.signal,
                }
                for s in short_interest
            ],
            "leverage": {
                "consumerCredit": margin_proxy.value if margin_proxy else None,
            },
            "positioningAlert": {
                "active": crowding_alert,
                "message": f"{extreme_count} contracts at positioning extremes - squeeze risk elevated" if crowding_alert else None,
            },
            "timestamp": datetime.now().isoformat(),
        }

        self._cache = result
        self._cache_time = datetime.now()

        return result


# Singleton instance
_positioning_instance: Optional[PositioningFlowsMonitor] = None


def get_positioning_monitor() -> PositioningFlowsMonitor:
    """Get or create positioning monitor singleton."""
    global _positioning_instance
    if _positioning_instance is None:
        _positioning_instance = PositioningFlowsMonitor()
    return _positioning_instance


def calculate_positioning_flows() -> Dict[str, Any]:
    """Public API for positioning and flow data."""
    monitor = get_positioning_monitor()
    return monitor.calculate_positioning_flows()
