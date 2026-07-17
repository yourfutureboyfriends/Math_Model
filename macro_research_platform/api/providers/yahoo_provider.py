"""
Yahoo Finance Provider — Raw market data access.

Fetches prices from yfinance. No business logic, no caching, no fallbacks.
Returns raw data or None on failure.
"""

import logging
from typing import Dict, Optional, Any, List
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class PriceRecord:
    """Raw price data from Yahoo Finance."""
    symbol: str
    price: float
    timestamp: datetime
    currency: str = "USD"
    source: str = "yfinance"


@dataclass
class PriceFetchResult:
    """Result of a price fetch operation."""
    success: bool
    data: Optional[Dict[str, PriceRecord]]
    error: Optional[str] = None
    latency_ms: float = 0.0
    records_fetched: int = 0


class YahooFinanceProvider:
    """
    Provider for Yahoo Finance market data.

    Responsibilities:
    - Fetch raw price data
    - Handle symbol mapping (canonical -> yfinance)
    - Handle FX inversion (yfinance returns inverted for some pairs)
    - Log failures clearly

    Does NOT:
    - Cache data
    - Apply business logic
    - Format for display
    - Provide fallback values
    """

    # Symbol mapping: canonical name -> yfinance ticker
    SYMBOL_MAP = {
        'SPX': '^GSPC',
        'NDX': '^NDX',
        'VIX': '^VIX',
        'TENYR': '^TNX',
        'TWYR': '^FVX',
        'DXY': 'DX-Y.NYB',
        'EURUSD': 'EURUSD=X',
        'GBPUSD': 'GBPUSD=X',
        'USDJPY': 'JPY=X',      # yfinance returns JPY/USD, we need USD/JPY
        'USDCAD': 'CAD=X',      # Same - yfinance returns CAD/USD
        'USDCHF': 'CHF=X',      # Same - yfinance returns CHF/USD
        'AUDUSD': 'AUDUSD=X',
        'NZDUSD': 'NZDUSD=X',
        'GLD': 'GC=F',
        'WTI': 'CL=F',
        'SPY': 'SPY',
        'TLT': 'TLT',
        'GLD_ETF': 'GLD',
        'HYG': 'HYG',
        'DBC': 'DBC',
        'TIP': 'TIP',
        'VVIX': '^VVIX',
        'SKEW': '^SKEW',
    }

    # Symbols that need inversion (yfinance returns quote/base)
    INVERT_SYMBOLS = {'USDJPY', 'USDCAD', 'USDCHF'}

    def __init__(self):
        self._last_error: Optional[str] = None

    def fetch_latest(
        self,
        symbols: List[str],
        period: str = "2d"
    ) -> PriceFetchResult:
        """
        Fetch latest prices for given symbols.

        Args:
            symbols: List of canonical symbol names (e.g., ['SPX', 'VIX'])
            period: yfinance period string

        Returns:
            PriceFetchResult with data or error
        """
        import time
        start_time = time.time()

        try:
            import yfinance as yf
        except ImportError:
            return PriceFetchResult(
                success=False,
                data=None,
                error="yfinance not installed",
                latency_ms=0.0
            )

        # Map canonical symbols to yfinance tickers
        yf_symbols = []
        symbol_map_reverse = {}
        for sym in symbols:
            yf_sym = self.SYMBOL_MAP.get(sym, sym)
            yf_symbols.append(yf_sym)
            symbol_map_reverse[yf_sym] = sym

        try:
            # Batch download — timeout=5 prevents indefinite hang when proxy blocks
            data = yf.download(
                yf_symbols,
                period=period,
                interval='1d',
                progress=False,
                threads=False,
                timeout=5,
            )

            if data.empty:
                return PriceFetchResult(
                    success=False,
                    data=None,
                    error="Empty response from yfinance",
                    latency_ms=(time.time() - start_time) * 1000
                )

            # Process results
            results: Dict[str, PriceRecord] = {}
            timestamp = datetime.utcnow()

            for canonical, yf_sym in self.SYMBOL_MAP.items():
                if canonical not in symbols:
                    continue

                try:
                    # Extract close price
                    if 'Close' in data.columns.get_level_values(0):
                        if yf_sym in data['Close'].columns:
                            close_series = data['Close'][yf_sym]
                        else:
                            continue
                    elif yf_sym in data.columns:
                        close_series = data[yf_sym]['Close']
                    else:
                        continue

                    if close_series is None or close_series.empty:
                        continue

                    # Drop NaN values and get the last valid price
                    close_series_valid = close_series.dropna()
                    if close_series_valid.empty:
                        logger.warning(f"No valid close price for {canonical}")
                        continue

                    latest = float(close_series_valid.iloc[-1])

                    # Apply inversion if needed
                    if canonical in self.INVERT_SYMBOLS and latest != 0:
                        latest = 1.0 / latest

                    results[canonical] = PriceRecord(
                        symbol=canonical,
                        price=latest,
                        timestamp=timestamp,
                        source="yfinance"
                    )

                except Exception as e:
                    logger.warning(f"Failed to process {canonical}: {e}")
                    continue

            latency_ms = (time.time() - start_time) * 1000

            if not results:
                return PriceFetchResult(
                    success=False,
                    data=None,
                    error="No valid prices extracted",
                    latency_ms=latency_ms
                )

            return PriceFetchResult(
                success=True,
                data=results,
                latency_ms=latency_ms,
                records_fetched=len(results)
            )

        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            error_msg = f"yfinance fetch failed: {e}"
            logger.error(error_msg)
            return PriceFetchResult(
                success=False,
                data=None,
                error=error_msg,
                latency_ms=latency_ms
            )

    def fetch_history(
        self,
        symbol: str,
        period: str = "1y",
        interval: str = "1d"
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch historical price data for a single symbol.

        Args:
            symbol: Canonical symbol name
            period: yfinance period
            interval: yfinance interval

        Returns:
            Dict with history data or None
        """
        try:
            import yfinance as yf
        except ImportError:
            return None

        yf_sym = self.SYMBOL_MAP.get(symbol, symbol)

        try:
            ticker = yf.Ticker(yf_sym)
            hist = ticker.history(period=period, interval=interval)

            if hist.empty:
                return None

            # Apply inversion if needed
            if symbol in self.INVERT_SYMBOLS:
                hist['Close'] = 1.0 / hist['Close']
                hist['Open'] = 1.0 / hist['Open']
                hist['High'] = 1.0 / hist['High']
                hist['Low'] = 1.0 / hist['Low']

            return {
                'symbol': symbol,
                'timestamps': hist.index.tolist(),
                'open': hist['Open'].tolist(),
                'high': hist['High'].tolist(),
                'low': hist['Low'].tolist(),
                'close': hist['Close'].tolist(),
                'volume': hist['Volume'].tolist() if 'Volume' in hist else [],
            }

        except Exception as e:
            logger.warning(f"History fetch failed for {symbol}: {e}")
            return None

    def fetch_single(self, symbol: str) -> Optional[PriceRecord]:
        """Fetch a single price (convenience method)."""
        result = self.fetch_latest([symbol])
        if result.success and result.data:
            return result.data.get(symbol)

    async def fetch_latest_async(
        self,
        symbols: list,
        timeout: float = 8.0,
    ) -> "PriceFetchResult":
        """
        Async wrapper for fetch_latest — runs the blocking yf.download() call
        in a thread-pool executor so it never blocks the FastAPI event loop.
        Falls back to an empty-success result on timeout or error.
        """
        import asyncio
        import concurrent.futures

        loop = asyncio.get_event_loop()
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                result = await asyncio.wait_for(
                    loop.run_in_executor(pool, self.fetch_latest, symbols),
                    timeout=timeout,
                )
            return result
        except asyncio.TimeoutError:
            logger.warning(
                f"[yahoo_provider] fetch_latest timed out after {timeout}s for {symbols} — returning empty"
            )
            return PriceFetchResult(success=False, data=None, error="timeout")
        except Exception as exc:
            logger.error(f"[yahoo_provider] fetch_latest_async error: {exc}")
            return PriceFetchResult(success=False, data=None, error=str(exc))
        return None
