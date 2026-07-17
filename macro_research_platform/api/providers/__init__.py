"""
Providers Layer — Raw external data access only.

Rules:
- No business logic
- No endpoint logic
- No formatting for UI
- No hardcoded fake fallback values
- Clear logging on failure
"""

from .yahoo_provider import YahooFinanceProvider
from .fred_provider import FREDProvider
from .news_provider import NewsProvider

__all__ = ["YahooFinanceProvider", "FREDProvider", "NewsProvider"]
