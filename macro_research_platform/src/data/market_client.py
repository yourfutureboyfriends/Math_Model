"""
Market data client for non-FRED data sources.

Provides access to:
- VIX term structure (^VIX, ^VIX3M, ^VIX6M) via yfinance
- AAII Sentiment Survey via XLS download
- Shiller CAPE via XLS download

All data cached to Parquet alongside FRED data.
"""

import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import requests
import yfinance as yf

from .base_client import BaseDataClient, SeriesMetadata, logger

# Cache directory
CACHE_DIR = Path(__file__).parent.parent.parent / "data" / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


class MarketDataClient:
    """
    Client for market data (yfinance) and web-scraped sentiment data.

    This is a simpler client than FRED as it doesn't need API keys,
    but follows similar caching patterns.
    """

    def __init__(self, cache_duration_hours: int = 24):
        self.cache_duration_hours = cache_duration_hours
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })

    def _get_cache_path(self, name: str) -> Path:
        """Get cache file path."""
        return CACHE_DIR / f"market_{name}.parquet"

    def _is_cache_valid(self, cache_path: Path) -> bool:
        """Check if cached data is still valid."""
        if not cache_path.exists():
            return False
        cache_age = datetime.now() - datetime.fromtimestamp(cache_path.stat().st_mtime)
        return cache_age < timedelta(hours=self.cache_duration_hours)

    def fetch_vix_term_structure(self) -> Optional[pd.DataFrame]:
        """
        Fetch VIX term structure (^VIX, ^VIX3M, ^VIX6M).

        Returns DataFrame with columns: VIX, VIX3M, VIX6M, term_structure_ratio
        """
        cache_path = self._get_cache_path("vix_term_structure")

        if self._is_cache_valid(cache_path):
            logger.info("Loading VIX term structure from cache")
            return pd.read_parquet(cache_path)

        try:
            # Fetch VIX futures proxies
            symbols = {
                'VIX': '^VIX',
                'VIX3M': '^VIX3M',
                'VIX6M': '^VIX6M'
            }

            data = {}
            for name, symbol in symbols.items():
                ticker = yf.Ticker(symbol)
                hist = ticker.history(period="6mo")
                if not hist.empty:
                    data[name] = hist['Close']

            if not data:
                logger.error("No VIX data fetched")
                return None

            df = pd.DataFrame(data)
            df = df.dropna()

            # Calculate term structure ratio (VIX3M/VIX - 1)
            if 'VIX' in df.columns and 'VIX3M' in df.columns:
                df['term_structure_ratio'] = (df['VIX3M'] / df['VIX']) - 1

            # Save to cache
            df.to_parquet(cache_path, compression="zstd")
            logger.info(f"Fetched VIX term structure: {len(df)} observations")

            return df

        except Exception as e:
            logger.error(f"Failed to fetch VIX term structure: {e}")
            return None

    def fetch_aaii_sentiment(self) -> Optional[pd.DataFrame]:
        """
        Fetch AAII Sentiment Survey from XLS file.

        Returns DataFrame with columns: date, bull, bear, neutral, bull_bear_spread
        """
        cache_path = self._get_cache_path("aaii_sentiment")

        if self._is_cache_valid(cache_path):
            logger.info("Loading AAII sentiment from cache")
            return pd.read_parquet(cache_path)

        try:
            url = "https://www.aaii.com/files/surveys/sentiment.xls"
            response = self.session.get(url, timeout=30)
            response.raise_for_status()

            # Read Excel file
            df = pd.read_excel(pd.io.BytesIO(response.content))

            # Parse based on AAII format
            # Columns typically: Date, Bullish, Neutral, Bearish
            df.columns = [c.lower().strip() for c in df.columns]

            # Find date column
            date_col = None
            for col in df.columns:
                if 'date' in col:
                    date_col = col
                    break

            if date_col is None:
                logger.error("Could not find date column in AAII data")
                return None

            df[date_col] = pd.to_datetime(df[date_col])
            df = df.set_index(date_col)

            # Standardize column names
            col_map = {}
            for col in df.columns:
                if 'bull' in col:
                    col_map[col] = 'bull'
                elif 'bear' in col:
                    col_map[col] = 'bear'
                elif 'neutral' in col:
                    col_map[col] = 'neutral'

            df = df.rename(columns=col_map)

            # Calculate bull-bear spread
            if 'bull' in df.columns and 'bear' in df.columns:
                df['bull_bear_spread'] = df['bull'] - df['bear']

            # Save to cache
            df.to_parquet(cache_path, compression="zstd")
            logger.info(f"Fetched AAII sentiment: {len(df)} observations")

            return df

        except Exception as e:
            logger.error(f"Failed to fetch AAII sentiment: {e}")
            return None

    def fetch_shiller_cape(self) -> Optional[pd.DataFrame]:
        """
        Fetch Shiller CAPE data from Yale.

        Returns DataFrame with columns: date, cape, cyclically_adjusted_price
        """
        cache_path = self._get_cache_path("shiller_cape")

        if self._is_cache_valid(cache_path):
            logger.info("Loading Shiller CAPE from cache")
            return pd.read_parquet(cache_path)

        try:
            url = "http://www.econ.yale.edu/~shiller/data/ie_data.xls"
            response = self.session.get(url, timeout=60)
            response.raise_for_status()

            # Read Excel file
            df = pd.read_excel(pd.io.BytesIO(response.content), sheet_name="Data")

            # Parse based on Shiller format
            # Typically has Date, P, D, E, CPI, CAPE columns
            df.columns = [c.lower().strip() for c in df.columns]

            # Find date column
            date_col = None
            for col in df.columns:
                if 'date' in col:
                    date_col = col
                    break

            if date_col is None:
                # Try to construct date from year/month if available
                if 'year' in df.columns:
                    df['date'] = pd.to_datetime(df[['year']].assign(month=1, day=1))
                    date_col = 'date'

            if date_col is None:
                logger.error("Could not find date column in Shiller data")
                return None

            df[date_col] = pd.to_datetime(df[date_col])
            df = df.set_index(date_col)

            # Standardize column names
            col_map = {}
            for col in df.columns:
                if 'cape' in col and 'tr' not in col:  # Regular CAPE, not total return
                    col_map[col] = 'cape'
                elif 'price' in col and 'cyclical' not in col:
                    col_map[col] = 'price'

            df = df.rename(columns=col_map)

            # Keep only relevant columns
            keep_cols = ['cape', 'price'] if 'cape' in df.columns else ['cape']
            df = df[keep_cols]

            # Save to cache
            df.to_parquet(cache_path, compression="zstd")
            logger.info(f"Fetched Shiller CAPE: {len(df)} observations")

            return df

        except Exception as e:
            logger.error(f"Failed to fetch Shiller CAPE: {e}")
            return None

    def fetch_etf_prices(self, symbols: List[str], period: str = "2y") -> Optional[pd.DataFrame]:
        """
        Fetch ETF price data for momentum/correlation calculations.

        Args:
            symbols: List of ETF symbols (e.g., ['SPY', 'TLT', 'GLD', 'DBC', 'UUP'])
            period: Period to fetch (e.g., '1y', '2y')

        Returns DataFrame with adjusted close prices for each symbol
        """
        cache_key = f"etf_prices_{'_'.join(symbols)}_{period}"
        cache_path = self._get_cache_path(cache_key)

        if self._is_cache_valid(cache_path):
            logger.info(f"Loading ETF prices from cache: {symbols}")
            return pd.read_parquet(cache_path)

        try:
            data = {}
            for symbol in symbols:
                ticker = yf.Ticker(symbol)
                hist = ticker.history(period=period)
                if not hist.empty:
                    data[symbol] = hist['Close']
                else:
                    logger.warning(f"No data for {symbol}")

            if not data:
                logger.error("No ETF data fetched")
                return None

            df = pd.DataFrame(data)
            df = df.dropna(how='all')

            # Save to cache
            df.to_parquet(cache_path, compression="zstd")
            logger.info(f"Fetched ETF prices: {len(df)} observations for {len(symbols)} symbols")

            return df

        except Exception as e:
            logger.error(f"Failed to fetch ETF prices: {e}")
            return None


def get_market_client() -> MarketDataClient:
    """Get a configured market data client."""
    return MarketDataClient()
