"""
News Provider — Raw news and sentiment data access.

Fetches news from RSS feeds and other sources.
No business logic, no caching, no fallbacks.
"""

import logging
from typing import List, Optional
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class NewsArticle:
    """Raw news article data."""
    title: str
    source: str
    published: datetime
    url: Optional[str] = None
    summary: Optional[str] = None
    raw_content: Optional[str] = None


@dataclass
class NewsResult:
    """Result of news fetch."""
    success: bool
    articles: List[NewsArticle]
    error: Optional[str] = None
    latency_ms: float = 0.0


class NewsProvider:
    """
    Provider for news and sentiment data.

    Responsibilities:
    - Fetch raw news from RSS feeds
    - Parse feed data
    - Log failures clearly

    Does NOT:
    - Cache data
    - Apply sentiment analysis
    - Filter by relevance
    """

    # Markets/economics feeds that answer keyless (checked 2026-10). The former Reuters agency
    # and bloomberg.com/feeds/news URLs return 404, and the FT home feed is general news.
    DEFAULT_FEEDS = {
        "Bloomberg Markets": "https://feeds.bloomberg.com/markets/news.rss",
        "Bloomberg Economics": "https://feeds.bloomberg.com/economics/news.rss",
        "FT Markets": "https://www.ft.com/markets?format=rss",
        "CNBC": "https://www.cnbc.com/id/100003114/device/rss/rss.html",
        "MarketWatch": "https://feeds.content.dowjones.io/public/rss/mw_marketpulse",
    }
    MAX_AGE_DAYS = 3

    def __init__(self):
        self.feeds = self.DEFAULT_FEEDS.copy()

    def fetch_feed(self, feed_name: str) -> NewsResult:
        """
        Fetch news from a specific RSS feed.

        Args:
            feed_name: Name of configured feed

        Returns:
            NewsResult with articles or error
        """
        import time
        start_time = time.time()

        feed_url = self.feeds.get(feed_name)
        if not feed_url:
            return NewsResult(
                success=False,
                articles=[],
                error=f"Unknown feed: {feed_name}"
            )

        try:
            import feedparser
        except ImportError:
            return NewsResult(
                success=False,
                articles=[],
                error="feedparser not installed"
            )

        try:
            feed = feedparser.parse(feed_url)
            articles = []

            for entry in feed.get("entries", [])[:50]:  # Limit to 50
                try:
                    # Parse published date
                    published = entry.get("published_parsed") or entry.get("updated_parsed")
                    if published:
                        published_dt = datetime(*published[:6])
                    else:
                        published_dt = datetime.utcnow()

                    articles.append(NewsArticle(
                        title=entry.get("title", ""),
                        source=feed_name,
                        published=published_dt,
                        url=entry.get("link"),
                        summary=entry.get("summary", ""),
                        raw_content=entry.get("content", [{}])[0].get("value") if entry.get("content") else None
                    ))
                except Exception as e:
                    logger.debug(f"Failed to parse article: {e}")
                    continue

            latency_ms = (time.time() - start_time) * 1000
            return NewsResult(
                success=True,
                articles=articles,
                latency_ms=latency_ms
            )

        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            error_msg = f"Feed fetch failed: {e}"
            logger.warning(error_msg)
            return NewsResult(
                success=False,
                articles=[],
                error=error_msg,
                latency_ms=latency_ms
            )

    def fetch_all(self) -> NewsResult:
        """Fetch from all configured feeds and merge."""
        import time
        start_time = time.time()

        all_articles = []
        errors = []

        from concurrent.futures import ThreadPoolExecutor
        from datetime import timedelta
        with ThreadPoolExecutor(max_workers=len(self.feeds) or 1) as pool:
            results = list(pool.map(self.fetch_feed, self.feeds.keys()))
        cutoff = datetime.utcnow() - timedelta(days=self.MAX_AGE_DAYS)
        seen = set()
        for feed_name, result in zip(self.feeds.keys(), results):
            if result.success:
                for a in result.articles:
                    key = (a.title or "").strip().lower()
                    if a.published >= cutoff and key and key not in seen:   # recent, de-duplicated
                        seen.add(key)
                        all_articles.append(a)
            else:
                errors.append(f"{feed_name}: {result.error}")

        # Sort by published date
        all_articles.sort(key=lambda x: x.published, reverse=True)

        latency_ms = (time.time() - start_time) * 1000

        if not all_articles and errors:
            return NewsResult(
                success=False,
                articles=[],
                error="; ".join(errors),
                latency_ms=latency_ms
            )

        return NewsResult(
            success=True,
            articles=all_articles[:100],  # Return top 100
            latency_ms=latency_ms
        )

    def add_feed(self, name: str, url: str) -> None:
        """Add a custom RSS feed."""
        self.feeds[name] = url
