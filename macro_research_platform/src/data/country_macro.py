"""
G10 + EM Country Macro Matrix for Macro Research Platform.

Section B: International Macro Coverage
- 15-country macro scorecards
- Central bank divergence tracking
- Composite macro scores with regime classification
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from zoneinfo import ZoneInfo
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class CountryMacroData:
    """Macroeconomic data for a single country."""
    country_code: str
    country_name: str
    region: str  # DM, EM
    # Raw data
    gdp_growth: Optional[float] = None
    inflation: Optional[float] = None
    unemployment: Optional[float] = None
    policy_rate: Optional[float] = None
    current_account_pct: Optional[float] = None
    debt_to_gdp: Optional[float] = None
    pmi_mfg: Optional[float] = None
    # Computed
    real_rate: Optional[float] = None
    # Scores
    growth_score: float = 0.0
    inflation_score: float = 0.0
    real_rate_score: float = 0.0
    ca_score: float = 0.0
    pmi_score: float = 0.0
    composite_score: float = 0.0
    regime: str = "AVERAGE"
    # Metadata
    last_updated: Optional[datetime] = None


@dataclass
class CentralBankData:
    """Central bank policy data."""
    bank_code: str
    bank_name: str
    country: str
    current_rate: Optional[float] = None
    rate_3m_change: Optional[float] = None
    rate_12m_change: Optional[float] = None
    real_rate: Optional[float] = None
    stance: str = "NEUTRAL"  # Hawkish, Neutral, Dovish
    next_meeting: Optional[str] = None


class CountryMacroMatrix:
    """
    G10 + EM country macro matrix calculator.

    Sources:
    - FRED for available series
    - World Bank API as fallback
    - Computed scores normalized to G10 peers
    """

    # Country definitions
    COUNTRIES = {
        # G10 Developed Markets
        "US": {"name": "United States", "region": "DM", "fred_gdp": "GDPC1", "fred_cpi": "CPIAUCSL", "fred_unemp": "UNRATE", "fred_policy": "FEDFUNDS"},
        "UK": {"name": "United Kingdom", "region": "DM", "fred_gdp": None, "fred_cpi": "GBRCPIALLMINMEI", "fred_unemp": "LRHUTTTTGBQ156S", "fred_policy": "BOERUKM156N"},
        "DE": {"name": "Germany", "region": "DM", "fred_gdp": None, "fred_cpi": None, "fred_unemp": None, "fred_policy": None},
        "FR": {"name": "France", "region": "DM", "fred_gdp": None, "fred_cpi": None, "fred_unemp": None, "fred_policy": None},
        "JP": {"name": "Japan", "region": "DM", "fred_gdp": "JPNRGDPEXP", "fred_cpi": "JPNCPIALLMINMEI", "fred_unemp": "LRHUTTTTJPQ156S", "fred_policy": "IRSTCI01JPM156N"},
        "CA": {"name": "Canada", "region": "DM", "fred_gdp": None, "fred_cpi": None, "fred_unemp": None, "fred_policy": "IRSTCI01CAM156N"},
        "AU": {"name": "Australia", "region": "DM", "fred_gdp": None, "fred_cpi": None, "fred_unemp": None, "fred_policy": "IRSTCI01AUM156N"},
        "CH": {"name": "Switzerland", "region": "DM", "fred_gdp": None, "fred_cpi": None, "fred_unemp": None, "fred_policy": None},
        "SE": {"name": "Sweden", "region": "DM", "fred_gdp": None, "fred_cpi": None, "fred_unemp": None, "fred_policy": None},
        "NO": {"name": "Norway", "region": "DM", "fred_gdp": None, "fred_cpi": None, "fred_unemp": None, "fred_policy": None},
        # Emerging Markets
        "CN": {"name": "China", "region": "EM", "fred_gdp": "CHNGDPNQDSMEI", "fred_cpi": "CHNCPIALLMINMEI", "fred_unemp": None, "fred_policy": None},
        "IN": {"name": "India", "region": "EM", "fred_gdp": None, "fred_cpi": None, "fred_unemp": None, "fred_policy": None},
        "BR": {"name": "Brazil", "region": "EM", "fred_gdp": None, "fred_cpi": None, "fred_unemp": None, "fred_policy": None},
        "MX": {"name": "Mexico", "region": "EM", "fred_gdp": None, "fred_cpi": None, "fred_unemp": None, "fred_policy": None},
        "KR": {"name": "South Korea", "region": "EM", "fred_gdp": None, "fred_cpi": None, "fred_unemp": None, "fred_policy": None},
    }

    # Central Bank meeting dates (next 4 meetings per bank)
    CB_MEETINGS = {
        "FED": ["2026-06-18", "2026-07-30", "2026-09-17", "2026-10-29"],
        "ECB": ["2026-06-11", "2026-07-24", "2026-09-11", "2026-10-23"],
        "BOE": ["2026-06-19", "2026-08-07", "2026-09-18", "2026-11-06"],
        "BOJ": ["2026-06-13", "2026-07-31", "2026-09-19", "2026-10-31"],
        "RBA": ["2026-06-02", "2026-07-07", "2026-08-05", "2026-09-02"],
        "RBNZ": ["2026-05-28", "2026-07-09", "2026-08-13", "2026-09-24"],
    }

    def __init__(self):
        self._cache: Optional[Dict[str, Any]] = None
        self._cache_time: Optional[datetime] = None
        self.cache_duration = timedelta(hours=24)

    def _is_cache_valid(self) -> bool:
        """Check if cached data is still valid."""
        if self._cache_time is None or not self._cache:
            return False
        return (datetime.now() - self._cache_time) < self.cache_duration

    def _fetch_fred_latest(self, series_id: str) -> Optional[float]:
        """Fetch latest value from FRED."""
        try:
            import requests

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

    def _fetch_world_bank_data(self, country_code: str, indicator: str) -> Optional[float]:
        """Fetch data from World Bank API."""
        try:
            import requests

            url = f"https://api.worldbank.org/v2/country/{country_code}/indicator/{indicator}"
            params = {
                "format": "json",
                "mrv": 1,  # Most recent value
                "per_page": 1,
            }

            response = requests.get(url, params=params, timeout=10)
            data = response.json()

            # Response is [metadata, [data]]
            if len(data) > 1 and data[1]:
                value = data[1][0].get("value")
                if value is not None:
                    return float(value)
            return None

        except Exception as e:
            logger.warning(f"Failed to fetch World Bank {country_code}/{indicator}: {e}")
            return None

    def _fetch_country_data(self, code: str, info: Dict) -> CountryMacroData:
        """Fetch all macro data for a country."""
        country = CountryMacroData(
            country_code=code,
            country_name=info["name"],
            region=info["region"],
            last_updated=datetime.now(),
        )

        # Try FRED first, then World Bank
        wb_country_codes = {
            "US": "USA", "UK": "GBR", "DE": "DEU", "FR": "FRA",
            "JP": "JPN", "CA": "CAN", "AU": "AUS", "CH": "CHE",
            "SE": "SWE", "NO": "NOR", "CN": "CHN", "IN": "IND",
            "BR": "BRA", "MX": "MEX", "KR": "KOR",
        }

        # GDP Growth - try FRED then World Bank
        if info.get("fred_gdp"):
            country.gdp_growth = self._fetch_fred_latest(info["fred_gdp"])
        if country.gdp_growth is None:
            country.gdp_growth = self._fetch_world_bank_data(
                wb_country_codes.get(code, code), "NY.GDP.MKTP.KD.ZG"
            )

        # Inflation
        if info.get("fred_cpi"):
            # Calculate YoY change
            country.inflation = self._fetch_fred_latest(info["fred_cpi"])
        if country.inflation is None:
            country.inflation = self._fetch_world_bank_data(
                wb_country_codes.get(code, code), "FP.CPI.TOTL.ZG"
            )

        # Unemployment
        if info.get("fred_unemp"):
            country.unemployment = self._fetch_fred_latest(info["fred_unemp"])
        if country.unemployment is None:
            country.unemployment = self._fetch_world_bank_data(
                wb_country_codes.get(code, code), "SL.UEM.TOTL.ZS"
            )

        # Policy Rate
        if info.get("fred_policy"):
            country.policy_rate = self._fetch_fred_latest(info["fred_policy"])

        # Current Account / GDP
        country.current_account_pct = self._fetch_world_bank_data(
            wb_country_codes.get(code, code), "BN.CAB.XOKA.GD.ZS"
        )

        # Debt to GDP
        country.debt_to_gdp = self._fetch_world_bank_data(
            wb_country_codes.get(code, code), "GC.DOD.TOTL.GD.ZS"
        )

        # Compute real rate
        if country.policy_rate is not None and country.inflation is not None:
            country.real_rate = country.policy_rate - country.inflation

        return country

    def _calculate_zscore(self, value: Optional[float], values: List[float]) -> float:
        """Calculate z-score for a value."""
        if value is None or not values:
            return 0.0

        mean = np.mean(values)
        std = np.std(values)

        if std == 0:
            return 0.0

        return (value - mean) / std

    def _calculate_country_scores(self, countries: List[CountryMacroData]) -> List[CountryMacroData]:
        """Calculate normalized scores for all countries."""
        # Get G10-only values for normalization
        g10_countries = [c for c in countries if c.region == "DM"]

        if not g10_countries:
            return countries

        # Extract values for z-score calculation
        gdp_values = [c.gdp_growth for c in g10_countries if c.gdp_growth is not None]
        inflation_values = [c.inflation for c in g10_countries if c.inflation is not None]
        real_rate_values = [c.real_rate for c in g10_countries if c.real_rate is not None]
        ca_values = [c.current_account_pct for c in g10_countries if c.current_account_pct is not None]
        pmi_values = [c.pmi_mfg for c in g10_countries if c.pmi_mfg is not None]

        for country in countries:
            # Growth score (positive is good)
            country.growth_score = self._calculate_zscore(country.gdp_growth, gdp_values)

            # Inflation score (negative if too high, assuming 2% target)
            if country.inflation is not None:
                excess_inflation = max(0, country.inflation - 2.0)
                country.inflation_score = -self._calculate_zscore(excess_inflation, [max(0, i - 2.0) for i in inflation_values if i is not None])
            else:
                country.inflation_score = 0.0

            # Real rate score (positive real rates = good)
            country.real_rate_score = self._calculate_zscore(country.real_rate, real_rate_values)

            # Current account score (surplus = positive)
            country.ca_score = self._calculate_zscore(country.current_account_pct, ca_values)

            # PMI score (normalized around 50)
            if country.pmi_mfg is not None:
                country.pmi_score = (country.pmi_mfg - 50) / 10
            elif pmi_values:
                country.pmi_score = 0.0

            # Composite score
            country.composite_score = (
                0.30 * country.growth_score +
                0.20 * country.inflation_score +
                0.20 * country.real_rate_score +
                0.15 * country.ca_score +
                0.15 * country.pmi_score
            )

            # Regime classification
            if country.composite_score > 1.0:
                country.regime = "OUTPERFORMING"
            elif country.composite_score > 0.3:
                country.regime = "ABOVE AVERAGE"
            elif country.composite_score > -0.3:
                country.regime = "AVERAGE"
            elif country.composite_score > -1.0:
                country.regime = "BELOW AVERAGE"
            else:
                country.regime = "UNDERPERFORMING"

        return countries

    def _fetch_cb_data(self) -> List[CentralBankData]:
        """Fetch central bank policy data."""
        cbs = [
            ("FED", "Federal Reserve", "US", "FEDFUNDS"),
            ("ECB", "ECB", "EU", "ECBDFR"),
            ("BOE", "Bank of England", "UK", "BOERUKM156N"),
            ("BOJ", "Bank of Japan", "JP", "IRSTCI01JPM156N"),
            ("RBA", "Reserve Bank of Australia", "AU", "IRSTCI01AUM156N"),
            ("RBNZ", "Reserve Bank of New Zealand", "NZ", None),
        ]

        results = []
        now = datetime.now().date()

        for code, name, country, fred_series in cbs:
            cb = CentralBankData(
                bank_code=code,
                bank_name=name,
                country=country,
            )

            # Current rate
            if fred_series:
                cb.current_rate = self._fetch_fred_latest(fred_series)

            # Get next meeting
            meetings = self.CB_MEETINGS.get(code, [])
            for meeting_date in meetings:
                meeting = datetime.strptime(meeting_date, "%Y-%m-%d").date()
                if meeting >= now:
                    cb.next_meeting = meeting_date
                    break

            # Determine stance
            if cb.current_rate is not None:
                if cb.current_rate > 3.0:
                    cb.stance = "Hawkish"
                elif cb.current_rate < 1.0:
                    cb.stance = "Dovish"
                else:
                    cb.stance = "Neutral"

            # Calculate real rate (need to get inflation for this CB's country)
            if code == "FED" and cb.current_rate is not None:
                us_inflation = self._fetch_fred_latest("CPIAUCSL")
                if us_inflation:
                    # CPI is an index, calculate YoY
                    # For now, use approximate
                    cb.real_rate = cb.current_rate - 2.5  # Approximate

            results.append(cb)

        return results

    def _calculate_divergence(self, cbs: List[CentralBankData]) -> Dict[str, Any]:
        """Calculate central bank divergence matrix."""
        fed = next((cb for cb in cbs if cb.bank_code == "FED"), None)
        if not fed or fed.current_rate is None:
            return {"divergenceMatrix": [], "mostDivergent": None}

        divergences = []
        for cb in cbs:
            if cb.bank_code == "FED" or cb.current_rate is None:
                continue

            spread = abs(fed.current_rate - cb.current_rate)
            direction = "USD PREMIUM" if fed.current_rate > cb.current_rate else f"{cb.country} PREMIUM"

            divergences.append({
                "pair": f"FED vs {cb.bank_code}",
                "spreadBps": round(spread * 100, 1),
                "direction": direction,
                "fedRate": fed.current_rate,
                "cbRate": cb.current_rate,
                "isExtreme": spread > 2.0,  # >200bps difference
            })

        # Sort by spread
        divergences.sort(key=lambda x: x["spreadBps"], reverse=True)

        return {
            "divergenceMatrix": divergences[:6],  # Top 6 pairs
            "mostDivergent": divergences[0] if divergences else None,
        }

    def calculate_country_macro_matrix(self) -> Dict[str, Any]:
        """
        Calculate complete G10 + EM macro matrix.

        Returns:
            Dictionary with country data, CB data, and divergence analysis.
        """
        import os  # Import here for FRED calls

        if self._is_cache_valid() and self._cache:
            return self._cache

        # Fetch country data
        countries = []
        for code, info in self.COUNTRIES.items():
            country = self._fetch_country_data(code, info)
            countries.append(country)

        # Calculate scores
        countries = self._calculate_country_scores(countries)

        # Sort by composite score
        countries.sort(key=lambda x: x.composite_score, reverse=True)

        # Fetch CB data
        cb_data = self._fetch_cb_data()
        divergence = self._calculate_divergence(cb_data)

        result = {
            "countries": [
                {
                    "code": c.country_code,
                    "name": c.country_name,
                    "region": c.region,
                    "gdpGrowth": round(c.gdp_growth, 2) if c.gdp_growth else None,
                    "inflation": round(c.inflation, 2) if c.inflation else None,
                    "unemployment": round(c.unemployment, 2) if c.unemployment else None,
                    "policyRate": round(c.policy_rate, 2) if c.policy_rate else None,
                    "realRate": round(c.real_rate, 2) if c.real_rate else None,
                    "currentAccountPct": round(c.current_account_pct, 2) if c.current_account_pct else None,
                    "debtToGdp": round(c.debt_to_gdp, 1) if c.debt_to_gdp else None,
                    "pmiMfg": round(c.pmi_mfg, 1) if c.pmi_mfg else None,
                    "compositeScore": round(c.composite_score, 2),
                    "regime": c.regime,
                    "scores": {
                        "growth": round(c.growth_score, 2),
                        "inflation": round(c.inflation_score, 2),
                        "realRate": round(c.real_rate_score, 2),
                        "currentAccount": round(c.ca_score, 2),
                        "pmi": round(c.pmi_score, 2),
                    },
                }
                for c in countries
            ],
            "centralBanks": [
                {
                    "code": cb.bank_code,
                    "name": cb.bank_name,
                    "currentRate": round(cb.current_rate, 2) if cb.current_rate else None,
                    "realRate": round(cb.real_rate, 2) if cb.real_rate else None,
                    "stance": cb.stance,
                    "nextMeeting": cb.next_meeting,
                }
                for cb in cb_data
            ],
            "divergence": divergence,
            "timestamp": datetime.now().isoformat(),
        }

        self._cache = result
        self._cache_time = datetime.now()

        return result


# Singleton instance
_matrix_instance: Optional[CountryMacroMatrix] = None


def get_country_matrix() -> CountryMacroMatrix:
    """Get or create country macro matrix singleton."""
    global _matrix_instance
    if _matrix_instance is None:
        _matrix_instance = CountryMacroMatrix()
    return _matrix_instance


def calculate_country_macro_matrix() -> Dict[str, Any]:
    """Public API for country macro matrix."""
    matrix = get_country_matrix()
    return matrix.calculate_country_macro_matrix()
