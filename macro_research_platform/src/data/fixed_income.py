"""
Fixed Income Terminal for Macro Research Platform.

Section C: Fixed Income Dashboard
- 6-country yield curves
- Credit spreads (HY, IG, EM, TED)
- Recession probabilities (Estrella-Mishkin)
- Real yields (TIPS)
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class YieldCurvePoint:
    """Single point on yield curve."""
    tenor_years: float
    yield_pct: Optional[float]


@dataclass
class YieldCurve:
    """Complete yield curve for a country."""
    country: str
    points: List[YieldCurvePoint] = field(default_factory=list)
    # Key spreads
    spread_2s10s: Optional[float] = None
    spread_3m10y: Optional[float] = None
    spread_5s30s: Optional[float] = None
    real_yield_10y: Optional[float] = None
    # Shape classification
    shape: str = "NORMAL"
    # Recession probability
    recession_prob: Optional[float] = None
    # Term premium
    term_premium: Optional[float] = None


@dataclass
class CreditSpread:
    """Credit spread data."""
    name: str
    spread_bps: Optional[float]
    change_1d_bps: Optional[float] = None
    change_1w_bps: Optional[float] = None
    change_1m_bps: Optional[float] = None
    signal: str = "NEUTRAL"


class FixedIncomeTerminal:
    """
    Fixed income market data aggregator.

    Sources:
    - FRED for US Treasury yields, credit spreads
    - Various APIs for international yields
    """

    # US Treasury yield curve FRED series
    US_YIELD_CURVE = {
        "1M": "DGS1MO",
        "3M": "DGS3MO",
        "6M": "DGS6MO",
        "1Y": "DGS1",
        "2Y": "DGS2",
        "3Y": "DGS3",
        "5Y": "DGS5",
        "7Y": "DGS7",
        "10Y": "DGS10",
        "20Y": "DGS20",
        "30Y": "DGS30",
    }

    # Credit spread FRED series
    CREDIT_SPREADS = {
        "HY_OAS": "BAMLH0A0HYM2",
        "IG_OAS": "BAMLC0A0CM",
        "EUR_HY_OAS": "BAMLHE00EHYIOAS",
        "BBB_SPREAD": "BAMLC0A4CBBBEY",
        "AAA_SPREAD": "BAMLC0A1CAAAEY",
        "TED_SPREAD": "TEDRATE",
        "EM_SOVEREIGN_OAS": "BAMLVZ0A0JNKSTAS",
    }

    # TIPS real yields
    TIPS_YIELDS = {
        "5Y": "DFII5",
        "10Y": "DFII10",
    }

    # International yields (FRED where available)
    INTERNATIONAL_YIELDS = {
        "UK": {"10Y": "IRLTLT01GBM156N"},
        "JP": {"10Y": "IRLTLT01JPM156N"},
        "DE": {"10Y": "IRLTLT01DEM156N"},
        "CA": {"10Y": "IRLTLT01CAM156N"},
        "AU": {"10Y": "IRLTLT01AUM156N"},
    }

    def __init__(self):
        self._cache: Optional[Dict[str, Any]] = None
        self._cache_time: Optional[datetime] = None
        self.cache_duration = timedelta(hours=1)

    def _is_cache_valid(self) -> bool:
        """Check if cached data is still valid."""
        if self._cache_time is None or not self._cache:
            return False
        return (datetime.now() - self._cache_time) < self.cache_duration

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

    def _fetch_fred_history(self, series_id: str, days: int = 30) -> List[float]:
        """Fetch historical values from FRED."""
        try:
            import requests
            import os
            from datetime import datetime, timedelta

            api_key = os.getenv("FRED_API_KEY")
            if not api_key:
                return []

            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)

            url = "https://api.stlouisfed.org/fred/series/observations"
            params = {
                "series_id": series_id,
                "api_key": api_key,
                "file_type": "json",
                "observation_start": start_date.strftime("%Y-%m-%d"),
                "observation_end": end_date.strftime("%Y-%m-%d"),
            }

            response = requests.get(url, params=params, timeout=10)
            data = response.json()

            values = []
            if "observations" in data:
                for obs in data["observations"]:
                    val = obs.get("value")
                    if val and val != ".":
                        values.append(float(val))
            return values

        except Exception as e:
            logger.warning(f"Failed to fetch FRED history {series_id}: {e}")
            return []

    def _build_us_yield_curve(self) -> YieldCurve:
        """Build US Treasury yield curve."""
        curve = YieldCurve(country="US")

        # Fetch all tenors
        tenor_years = {
            "1M": 0.083, "3M": 0.25, "6M": 0.5,
            "1Y": 1, "2Y": 2, "3Y": 3, "5Y": 5, "7Y": 7,
            "10Y": 10, "20Y": 20, "30Y": 30,
        }

        yields = {}
        for tenor, fred_code in self.US_YIELD_CURVE.items():
            val = self._fetch_fred_latest(fred_code)
            if val is not None:
                yields[tenor] = val
                curve.points.append(YieldCurvePoint(
                    tenor_years=tenor_years[tenor],
                    yield_pct=val
                ))

        # Sort by tenor
        curve.points.sort(key=lambda x: x.tenor_years)

        # Calculate spreads
        if "10Y" in yields and "2Y" in yields:
            curve.spread_2s10s = yields["10Y"] - yields["2Y"]

        if "10Y" in yields and "3M" in yields:
            curve.spread_3m10y = yields["10Y"] - yields["3M"]

        if "30Y" in yields and "5Y" in yields:
            curve.spread_5s30s = yields["30Y"] - yields["5Y"]

        # Classify shape
        if curve.spread_2s10s is not None:
            if curve.spread_2s10s < 0:
                curve.shape = "INVERTED"
            elif curve.spread_2s10s < 0.25:
                curve.shape = "FLAT"
            elif curve.spread_2s10s > 1.5:
                curve.shape = "STEEP"
            else:
                curve.shape = "NORMAL"

        # Calculate recession probability (Estrella-Mishkin 1998)
        if curve.spread_3m10y is not None:
            # prob = 1 / (1 + exp(0.6566 + 0.6109 * spread))
            try:
                prob = 1 / (1 + np.exp(0.6566 + 0.6109 * curve.spread_3m10y))
                curve.recession_prob = prob
            except:
                pass

        # Real yield from TIPS
        curve.real_yield_10y = self._fetch_fred_latest("DFII10")

        # Term premium estimate
        if "10Y" in yields and "1Y" in yields and "2Y" in yields:
            expected_short = (yields["1Y"] + yields["2Y"]) / 2
            curve.term_premium = yields["10Y"] - expected_short

        return curve

    def _build_international_yield_curve(self, country: str) -> YieldCurve:
        """Build international yield curve (limited data)."""
        curve = YieldCurve(country=country)

        config = self.INTERNATIONAL_YIELDS.get(country, {})
        for tenor, fred_code in config.items():
            val = self._fetch_fred_latest(fred_code)
            if val is not None:
                if tenor == "10Y":
                    curve.points.append(YieldCurvePoint(tenor_years=10, yield_pct=val))

        return curve

    def _fetch_credit_spreads(self) -> List[CreditSpread]:
        """Fetch all credit spreads."""
        spreads = []

        # HY OAS
        hy_val = self._fetch_fred_latest(self.CREDIT_SPREADS["HY_OAS"])
        if hy_val:
            # FRED returns as percentage, convert to bps
            hy_bps = hy_val * 100 if hy_val < 1 else hy_val

            # Get historical for changes
            hist = self._fetch_fred_history(self.CREDIT_SPREADS["HY_OAS"], days=30)
            change_1d = None
            change_1w = None
            change_1m = None

            if len(hist) >= 2:
                change_1d = (hist[-1] - hist[-2]) * 100
            if len(hist) >= 6:
                change_1w = (hist[-1] - hist[-6]) * 100
            if len(hist) >= 22:
                change_1m = (hist[-1] - hist[-22]) * 100

            # Determine signal
            if hy_bps < 300:
                signal = "COMPRESSION"
            elif hy_bps > 500:
                signal = "STRESS"
            else:
                signal = "NEUTRAL"

            spreads.append(CreditSpread(
                name="US HY OAS",
                spread_bps=round(hy_bps, 1),
                change_1d_bps=round(change_1d, 1) if change_1d else None,
                change_1w_bps=round(change_1w, 1) if change_1w else None,
                change_1m_bps=round(change_1m, 1) if change_1m else None,
                signal=signal,
            ))

        # IG OAS
        ig_val = self._fetch_fred_latest(self.CREDIT_SPREADS["IG_OAS"])
        if ig_val:
            ig_bps = ig_val * 100 if ig_val < 1 else ig_val
            spreads.append(CreditSpread(
                name="US IG OAS",
                spread_bps=round(ig_bps, 1),
            ))

        # TED Spread
        ted_val = self._fetch_fred_latest(self.CREDIT_SPREADS["TED_SPREAD"])
        if ted_val:
            spreads.append(CreditSpread(
                name="TED Spread",
                spread_bps=round(ted_val * 100, 1) if ted_val < 1 else round(ted_val, 1),
            ))

        # EM Sovereign
        em_val = self._fetch_fred_latest(self.CREDIT_SPREADS["EM_SOVEREIGN_OAS"])
        if em_val:
            em_bps = em_val * 100 if em_val < 1 else em_val
            spreads.append(CreditSpread(
                name="EM Sovereign OAS",
                spread_bps=round(em_bps, 1),
            ))

        return spreads

    def _calculate_yield_curve_history(self) -> Dict[str, List[Dict]]:
        """Get historical yield curves for charting."""
        history = {
            "current": [],
            "oneMonthAgo": [],
            "oneYearAgo": [],
        }

        # Fetch current
        for tenor, fred_code in self.US_YIELD_CURVE.items():
            val = self._fetch_fred_latest(fred_code)
            if val:
                tenor_map = {"1M": 0.083, "3M": 0.25, "6M": 0.5, "1Y": 1, "2Y": 2, "3Y": 3, "5Y": 5, "7Y": 7, "10Y": 10, "20Y": 20, "30Y": 30}
                history["current"].append({"tenor": tenor, "years": tenor_map[tenor], "yield": val})

        # Sort by tenor
        history["current"].sort(key=lambda x: x["years"])

        return history

    def calculate_fixed_income(self) -> Dict[str, Any]:
        """
        Calculate complete fixed income terminal data.

        Returns:
            Dictionary with yield curves, credit spreads, and analytics.
        """
        if self._is_cache_valid() and self._cache:
            return self._cache

        # Build yield curves
        us_curve = self._build_us_yield_curve()
        uk_curve = self._build_international_yield_curve("UK")
        jp_curve = self._build_international_yield_curve("JP")
        de_curve = self._build_international_yield_curve("DE")
        ca_curve = self._build_international_yield_curve("CA")
        au_curve = self._build_international_yield_curve("AU")

        yield_curves = {
            "US": {
                "country": "US",
                "points": [{"tenor": p.tenor_years, "yield": p.yield_pct} for p in us_curve.points],
                "spread2s10s": round(us_curve.spread_2s10s, 2) if us_curve.spread_2s10s else None,
                "spread3m10y": round(us_curve.spread_3m10y, 2) if us_curve.spread_3m10y else None,
                "spread5s30s": round(us_curve.spread_5s30s, 2) if us_curve.spread_5s30s else None,
                "realYield10y": round(us_curve.real_yield_10y, 2) if us_curve.real_yield_10y else None,
                "shape": us_curve.shape,
                "recessionProb": round(us_curve.recession_prob * 100, 1) if us_curve.recession_prob else None,
                "termPremium": round(us_curve.term_premium, 2) if us_curve.term_premium else None,
            },
            "UK": {"country": "UK", "points": [{"tenor": p.tenor_years, "yield": p.yield_pct} for p in uk_curve.points]},
            "JP": {"country": "JP", "points": [{"tenor": p.tenor_years, "yield": p.yield_pct} for p in jp_curve.points]},
            "DE": {"country": "DE", "points": [{"tenor": p.tenor_years, "yield": p.yield_pct} for p in de_curve.points]},
            "CA": {"country": "CA", "points": [{"tenor": p.tenor_years, "yield": p.yield_pct} for p in ca_curve.points]},
            "AU": {"country": "AU", "points": [{"tenor": p.tenor_years, "yield": p.yield_pct} for p in au_curve.points]},
        }

        # Fetch credit spreads
        credit_spreads = self._fetch_credit_spreads()

        # Calculate HY-IG basis
        hy_ig_basis = None
        hy = next((s for s in credit_spreads if s.name == "US HY OAS"), None)
        ig = next((s for s in credit_spreads if s.name == "US IG OAS"), None)
        if hy and ig and hy.spread_bps and ig.spread_bps:
            hy_ig_basis = round(hy.spread_bps - ig.spread_bps, 1)

        # Real yield signal
        real_yield_signal = "NEUTRAL"
        if us_curve.real_yield_10y is not None:
            if us_curve.real_yield_10y > 2.0:
                real_yield_signal = "RESTRICTIVE"
            elif us_curve.real_yield_10y < 0:
                real_yield_signal = "ACCOMMODATIVE"

        # Breakeven inflation
        be_10y = self._fetch_fred_latest("T10YIE")
        be_5y5y = self._fetch_fred_latest("T5YIFRM")

        result = {
            "yieldCurves": yield_curves,
            "creditSpreads": [
                {
                    "name": s.name,
                    "spreadBps": s.spread_bps,
                    "change1d": s.change_1d_bps,
                    "change1w": s.change_1w_bps,
                    "change1m": s.change_1m_bps,
                    "signal": s.signal,
                }
                for s in credit_spreads
            ],
            "hyIgBasis": hy_ig_basis,
            "realYieldSignal": real_yield_signal,
            "breakevenInflation": {
                "tenYear": round(be_10y, 2) if be_10y else None,
                "fiveYearFiveYear": round(be_5y5y, 2) if be_5y5y else None,
            },
            "ratesTable": self._build_rates_table(us_curve, yield_curves),
            "timestamp": datetime.now().isoformat(),
        }

        self._cache = result
        self._cache_time = datetime.now()

        return result

    def _build_rates_table(self, us_curve: YieldCurve, all_curves: Dict) -> List[Dict]:
        """Build rates table for display."""
        table = []

        # US Treasuries
        for point in us_curve.points:
            if point.tenor_years in [0.25, 2, 10, 30]:
                tenor_name = {0.25: "3M", 2: "2Y", 10: "10Y", 30: "30Y"}.get(point.tenor_years, f"{point.tenor_years}Y")
                table.append({
                    "instrument": f"US {tenor_name} Treasury",
                    "yield": round(point.yield_pct, 2) if point.yield_pct else None,
                    "signal": "─",
                })

        # Spreads
        if us_curve.spread_2s10s:
            table.append({
                "instrument": "US 2s10s Spread",
                "yield": round(us_curve.spread_2s10s, 2),
                "signal": us_curve.shape,
            })

        # International 10Y
        for country, curve_data in all_curves.items():
            if country != "US":
                points = curve_data.get("points", [])
                if points:
                    table.append({
                        "instrument": f"{country} 10Y Govt",
                        "yield": round(points[0]["yield"], 2),
                        "signal": "─",
                    })

        # US-Germany spread
        if us_curve.points and len(us_curve.points) >= 8:
            us_10y = next((p for p in us_curve.points if p.tenor_years == 10), None)
            de_curve = all_curves.get("DE", {})
            de_points = de_curve.get("points", [])
            if us_10y and de_points:
                spread = us_10y.yield_pct - de_points[0]["yield"]
                table.append({
                    "instrument": "US-Germany 10Y Spread",
                    "yield": round(spread, 2),
                    "signal": "USD PREMIUM" if spread > 0 else "EUR PREMIUM",
                })

        return table


# Singleton instance
_fi_instance: Optional[FixedIncomeTerminal] = None


def get_fixed_income_terminal() -> FixedIncomeTerminal:
    """Get or create fixed income terminal singleton."""
    global _fi_instance
    if _fi_instance is None:
        _fi_instance = FixedIncomeTerminal()
    return _fi_instance


def calculate_fixed_income() -> Dict[str, Any]:
    """Public API for fixed income data."""
    terminal = get_fixed_income_terminal()
    return terminal.calculate_fixed_income()
