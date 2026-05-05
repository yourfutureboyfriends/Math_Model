"""
FX & Commodities Terminal for Macro Research Platform.

Section D: FX & Commodities Dashboard
- G10 FX pairs with carry and trend signals
- EM FX monitoring
- Commodities complex (energy, metals, agriculture)
- Cross-asset heatmap
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class FXPair:
    """FX pair data."""
    pair: str
    spot: Optional[float] = None
    change_1d: Optional[float] = None
    change_1w: Optional[float] = None
    change_1m: Optional[float] = None
    change_3m: Optional[float] = None
    vol_1m: Optional[float] = None
    week_52_high: Optional[float] = None
    week_52_low: Optional[float] = None
    week_52_percentile: Optional[float] = None
    trend_signal: str = "NEUTRAL"
    carry: Optional[float] = None


@dataclass
class Commodity:
    """Commodity futures data."""
    symbol: str
    name: str
    category: str  # energy, metal, agriculture
    spot: Optional[float] = None
    change_1d: Optional[float] = None
    change_1w: Optional[float] = None
    change_1m: Optional[float] = None
    change_3m: Optional[float] = None
    change_1y: Optional[float] = None
    vol_20d: Optional[float] = None
    week_52_high: Optional[float] = None
    week_52_low: Optional[float] = None
    week_52_percentile: Optional[float] = None


class FXCommoditiesTerminal:
    """
    FX and commodities market data aggregator.

    Sources:
    - yfinance for spot prices and historical data
    - Computed signals for trend, carry, volatility
    """

    # G10 FX pairs
    G10_FX_PAIRS = [
        ("EURUSD=X", "EUR/USD", "G10"),
        ("GBPUSD=X", "GBP/USD", "G10"),
        ("USDJPY=X", "USD/JPY", "G10"),
        ("USDCHF=X", "USD/CHF", "G10"),
        ("AUDUSD=X", "AUD/USD", "G10"),
        ("NZDUSD=X", "NZD/USD", "G10"),
        ("USDCAD=X", "USD/CAD", "G10"),
        ("USDSEK=X", "USD/SEK", "G10"),
        ("USDNOK=X", "USD/NOK", "G10"),
        ("EURGBP=X", "EUR/GBP", "G10"),
        ("EURJPY=X", "EUR/JPY", "G10"),
        ("GBPJPY=X", "GBP/JPY", "G10"),
    ]

    # EM FX pairs
    EM_FX_PAIRS = [
        ("USDCNY=X", "USD/CNY", "CN", "China"),
        ("USDBRL=X", "USD/BRL", "BR", "Brazil"),
        ("USDINR=X", "USD/INR", "IN", "India"),
        ("USDMXN=X", "USD/MXN", "MX", "Mexico"),
        ("USDKRW=X", "USD/KRW", "KR", "Korea"),
        ("USDTRY=X", "USD/TRY", "TR", "Turkey"),
        ("USDZAR=X", "USD/ZAR", "ZA", "South Africa"),
        ("USDSGD=X", "USD/SGD", "SG", "Singapore"),
    ]

    # Commodities
    COMMODITIES = {
        # Energy
        "energy": [
            ("CL=F", "WTI Crude Oil"),
            ("BZ=F", "Brent Crude"),
            ("NG=F", "Natural Gas"),
            ("HO=F", "Heating Oil"),
            ("RB=F", "RBOB Gasoline"),
        ],
        # Metals
        "metals": [
            ("GC=F", "Gold"),
            ("SI=F", "Silver"),
            ("HG=F", "Copper"),
            ("PL=F", "Platinum"),
            ("PA=F", "Palladium"),
            ("ALI=F", "Aluminum"),
        ],
        # Agriculture
        "agriculture": [
            ("ZC=F", "Corn"),
            ("ZW=F", "Wheat"),
            ("ZS=F", "Soybeans"),
            ("CC=F", "Cocoa"),
            ("KC=F", "Coffee"),
            ("CT=F", "Cotton"),
            ("SB=F", "Sugar"),
        ],
    }

    # Cross-asset heatmap assets
    HEATMAP_ASSETS = [
        ("SPY", "S&P 500"),
        ("TLT", "20+Y Treasury"),
        ("GLD", "Gold"),
        ("USO", "Crude Oil"),
        ("DBC", "Commodities"),
        ("UUP", "USD"),
        ("EEM", "EM Equity"),
        ("HYG", "High Yield"),
        ("TIP", "TIPS"),
        ("VNQ", "Real Estate"),
    ]

    def __init__(self):
        self._cache: Optional[Dict[str, Any]] = None
        self._cache_time: Optional[datetime] = None
        self.cache_duration = timedelta(minutes=5)

    def _is_cache_valid(self) -> bool:
        """Check if cached data is still valid."""
        if self._cache_time is None or not self._cache:
            return False
        return (datetime.now() - self._cache_time) < self.cache_duration

    def _fetch_yf_data(self, ticker: str, period: str = "1y") -> Dict[str, Any]:
        """Fetch data from yfinance."""
        try:
            import yfinance as yf

            stock = yf.Ticker(ticker)
            hist = stock.history(period=period)

            if hist.empty:
                return {}

            current = hist["Close"].iloc[-1]

            # Calculate returns
            returns = {}
            periods = {
                "1d": 2,
                "1w": 6,
                "1m": 22,
                "3m": 66,
                "1y": len(hist),
            }

            for name, days in periods.items():
                if len(hist) >= days:
                    prev = hist["Close"].iloc[-days]
                    returns[f"change_{name}"] = ((current - prev) / prev) * 100
                else:
                    returns[f"change_{name}"] = None

            # Calculate volatility (20-day)
            vol = None
            if len(hist) >= 21:
                daily_returns = hist["Close"].pct_change().dropna().tail(21)
                vol = daily_returns.std() * np.sqrt(252) * 100  # Annualized

            # 52-week range
            week_52_high = hist["High"].tail(252).max() if len(hist) >= 252 else hist["High"].max()
            week_52_low = hist["Low"].tail(252).min() if len(hist) >= 252 else hist["Low"].min()

            return {
                "price": current,
                **returns,
                "vol_20d": vol,
                "week_52_high": week_52_high,
                "week_52_low": week_52_low,
            }

        except Exception as e:
            logger.warning(f"Failed to fetch {ticker}: {e}")
            return {}

    def _calculate_trend_signal(self, change_1m: Optional[float], change_3m: Optional[float]) -> str:
        """Calculate trend signal using TSMOM logic."""
        if change_1m is None or change_3m is None:
            return "NEUTRAL"

        # Time Series Momentum: positive 1M and 3M = LONG
        if change_1m > 0 and change_3m > 0:
            return "LONG"
        elif change_1m < 0 and change_3m < 0:
            return "SHORT"
        return "NEUTRAL"

    def _calculate_week_52_percentile(self, price: float, high: float, low: float) -> float:
        """Calculate position in 52-week range."""
        if high == low:
            return 50.0
        return ((price - low) / (high - low)) * 100

    def fetch_g10_fx(self) -> List[FXPair]:
        """Fetch G10 FX pairs."""
        fx_data = []

        for ticker, pair_name, region in self.G10_FX_PAIRS:
            data = self._fetch_yf_data(ticker)
            if not data:
                continue

            percentile = self._calculate_week_52_percentile(
                data.get("price", 0),
                data.get("week_52_high", 1),
                data.get("week_52_low", 0)
            )

            fx = FXPair(
                pair=pair_name,
                spot=data.get("price"),
                change_1d=round(data.get("change_1d"), 2) if data.get("change_1d") else None,
                change_1w=round(data.get("change_1w"), 2) if data.get("change_1w") else None,
                change_1m=round(data.get("change_1m"), 2) if data.get("change_1m") else None,
                change_3m=round(data.get("change_3m"), 2) if data.get("change_3m") else None,
                vol_1m=round(data.get("vol_20d"), 2) if data.get("vol_20d") else None,
                week_52_high=data.get("week_52_high"),
                week_52_low=data.get("week_52_low"),
                week_52_percentile=round(percentile, 1),
                trend_signal=self._calculate_trend_signal(
                    data.get("change_1m"), data.get("change_3m")
                ),
            )
            fx_data.append(fx)

        return fx_data

    def fetch_em_fx(self) -> List[FXPair]:
        """Fetch EM FX pairs."""
        fx_data = []

        for ticker, pair_name, country, country_name in self.EM_FX_PAIRS:
            data = self._fetch_yf_data(ticker)
            if not data:
                continue

            percentile = self._calculate_week_52_percentile(
                data.get("price", 0),
                data.get("week_52_high", 1),
                data.get("week_52_low", 0)
            )

            fx = FXPair(
                pair=pair_name,
                spot=data.get("price"),
                change_1d=round(data.get("change_1d"), 2) if data.get("change_1d") else None,
                change_1m=round(data.get("change_1m"), 2) if data.get("change_1m") else None,
                change_3m=round(data.get("change_3m"), 2) if data.get("change_3m") else None,
                week_52_percentile=round(percentile, 1),
                trend_signal=self._calculate_trend_signal(
                    data.get("change_1m"), data.get("change_3m")
                ),
            )
            fx_data.append(fx)

        return fx_data

    def fetch_dxy(self) -> Optional[Dict[str, Any]]:
        """Fetch US Dollar Index."""
        data = self._fetch_yf_data("DX-Y.NYB")
        if not data:
            return None

        return {
            "spot": round(data["price"], 2),
            "change1d": round(data.get("change_1d"), 2) if data.get("change_1d") else None,
            "change1m": round(data.get("change_1m"), 2) if data.get("change_1m") else None,
        }

    def fetch_commodities(self) -> Dict[str, List[Commodity]]:
        """Fetch all commodities data."""
        result = {}

        for category, commodities in self.COMMODITIES.items():
            category_data = []
            for ticker, name in commodities:
                data = self._fetch_yf_data(ticker)
                if not data:
                    continue

                percentile = self._calculate_week_52_percentile(
                    data.get("price", 0),
                    data.get("week_52_high", 1),
                    data.get("week_52_low", 0)
                )

                comm = Commodity(
                    symbol=ticker,
                    name=name,
                    category=category,
                    spot=data.get("price"),
                    change_1d=round(data.get("change_1d"), 2) if data.get("change_1d") else None,
                    change_1w=round(data.get("change_1w"), 2) if data.get("change_1w") else None,
                    change_1m=round(data.get("change_1m"), 2) if data.get("change_1m") else None,
                    change_3m=round(data.get("change_3m"), 2) if data.get("change_3m") else None,
                    change_1y=round(data.get("change_1y"), 2) if data.get("change_1y") else None,
                    vol_20d=round(data.get("vol_20d"), 2) if data.get("vol_20d") else None,
                    week_52_high=data.get("week_52_high"),
                    week_52_low=data.get("week_52_low"),
                    week_52_percentile=round(percentile, 1),
                )
                category_data.append(comm)

            result[category] = category_data

        return result

    def calculate_macro_signals(self, commodities: Dict[str, List[Commodity]]) -> Dict[str, Any]:
        """Calculate macro signals from commodities."""
        signals = {}

        # Copper/Gold ratio
        gold = next((c for c in commodities.get("metals", []) if c.name == "Gold"), None)
        copper = next((c for c in commodities.get("metals", []) if c.name == "Copper"), None)

        if gold and copper and gold.spot and copper.spot:
            ratio = copper.spot / gold.spot

            # Trend signal
            if copper.change_3m and gold.change_3m:
                ratio_change = copper.change_3m - gold.change_3m
                if ratio_change > 5:
                    signals["copperGoldRatio"] = {
                        "value": round(ratio, 4),
                        "signal": "RISK-ON",
                        "description": "Copper outperforming gold - growth expectations rising",
                    }
                elif ratio_change < -5:
                    signals["copperGoldRatio"] = {
                        "value": round(ratio, 4),
                        "signal": "RISK-OFF",
                        "description": "Gold outperforming copper - growth fears / risk-off",
                    }
                else:
                    signals["copperGoldRatio"] = {
                        "value": round(ratio, 4),
                        "signal": "NEUTRAL",
                    }
            else:
                signals["copperGoldRatio"] = {"value": round(ratio, 4), "signal": "NEUTRAL"}

        # Oil trend signal
        wti = next((c for c in commodities.get("energy", []) if "WTI" in c.name), None)
        if wti and wti.change_3m:
            if wti.change_3m > 10:
                signals["oilTrend"] = {
                    "direction": "RISING",
                    "interpretation": "INFLATIONARY",
                    "description": "Demand-driven oil rally = inflationary pressure",
                }
            elif wti.change_3m < -10:
                signals["oilTrend"] = {
                    "direction": "FALLING",
                    "interpretation": "DEFLATIONARY",
                    "description": "Demand destruction / recession fear",
                }
            else:
                signals["oilTrend"] = {"direction": "NEUTRAL", "interpretation": "NEUTRAL"}

        # Commodity inflation index
        inflation_commodities = [
            next((c for c in commodities.get("energy", []) if "WTI" in c.name), None),
            next((c for c in commodities.get("metals", []) if c.name == "Copper"), None),
            next((c for c in commodities.get("agriculture", []) if c.name == "Wheat"), None),
            next((c for c in commodities.get("metals", []) if c.name == "Gold"), None),
        ]

        changes_1m = [c.change_1m for c in inflation_commodities if c and c.change_1m]
        if changes_1m:
            avg_change = np.mean(changes_1m)
            signals["commodityInflationIndex"] = {
                "score": round(avg_change, 2),
                "signal": "RISING" if avg_change > 2 else "FALLING" if avg_change < -2 else "STABLE",
            }

        return signals

    def calculate_cross_asset_heatmap(self) -> List[List[Dict[str, Any]]]:
        """Calculate cross-asset return heatmap."""
        timeframes = ["1D", "1W", "1M", "3M", "6M", "1Y"]
        days_map = {"1D": 2, "1W": 6, "1M": 22, "3M": 66, "6M": 132, "1Y": 252}

        heatmap = []

        for ticker, name in self.HEATMAP_ASSETS:
            data = self._fetch_yf_data(ticker, period="1y")
            if not data:
                continue

            row = {"asset": name, "ticker": ticker}

            for tf in timeframes:
                key = f"change_{tf.lower()}"
                val = data.get(key)
                if val is not None:
                    row[tf] = round(val, 2)
                else:
                    row[tf] = None

            heatmap.append(row)

        return heatmap

    def calculate_fx_commodities(self) -> Dict[str, Any]:
        """
        Calculate complete FX & commodities data.

        Returns:
            Dictionary with FX pairs, commodities, and macro signals.
        """
        if self._is_cache_valid() and self._cache:
            return self._cache

        # Fetch data
        g10_fx = self.fetch_g10_fx()
        em_fx = self.fetch_em_fx()
        dxy = self.fetch_dxy()
        commodities = self.fetch_commodities()
        macro_signals = self.calculate_macro_signals(commodities)
        heatmap = self.calculate_cross_asset_heatmap()

        result = {
            "fx": {
                "g10": [
                    {
                        "pair": f.pair,
                        "spot": round(f.spot, 4) if f.spot else None,
                        "change1d": f.change_1d,
                        "change1w": f.change_1w,
                        "change1m": f.change_1m,
                        "change3m": f.change_3m,
                        "vol1m": f.vol_1m,
                        "week52Percentile": f.week_52_percentile,
                        "trendSignal": f.trend_signal,
                    }
                    for f in g10_fx
                ],
                "em": [
                    {
                        "pair": f.pair,
                        "spot": round(f.spot, 4) if f.spot else None,
                        "change1d": f.change_1d,
                        "change1m": f.change_1m,
                        "change3m": f.change_3m,
                        "week52Percentile": f.week_52_percentile,
                        "trendSignal": f.trend_signal,
                    }
                    for f in em_fx
                ],
                "dxy": dxy,
            },
            "commodities": {
                category: [
                    {
                        "symbol": c.symbol,
                        "name": c.name,
                        "spot": round(c.spot, 2) if c.spot else None,
                        "change1d": c.change_1d,
                        "change1w": c.change_1w,
                        "change1m": c.change_1m,
                        "change3m": c.change_3m,
                        "change1y": c.change_1y,
                        "vol20d": c.vol_20d,
                        "week52Percentile": c.week_52_percentile,
                    }
                    for c in commodities_list
                ]
                for category, commodities_list in commodities.items()
            },
            "macroSignals": macro_signals,
            "crossAssetHeatmap": heatmap,
            "timestamp": datetime.now().isoformat(),
        }

        self._cache = result
        self._cache_time = datetime.now()

        return result


# Singleton instance
_fx_comm_instance: Optional[FXCommoditiesTerminal] = None


def get_fx_commodities_terminal() -> FXCommoditiesTerminal:
    """Get or create FX/commodities terminal singleton."""
    global _fx_comm_instance
    if _fx_comm_instance is None:
        _fx_comm_instance = FXCommoditiesTerminal()
    return _fx_comm_instance


def calculate_fx_commodities() -> Dict[str, Any]:
    """Public API for FX and commodities data."""
    terminal = get_fx_commodities_terminal()
    return terminal.calculate_fx_commodities()
