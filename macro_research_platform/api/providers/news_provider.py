"""
News Provider — Raw news and sentiment data access.

Fetches news from RSS feeds and other sources.
No business logic, no caching, no fallbacks.
"""

import logging
from typing import List, Optional, Dict, Any
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

    DEFAULT_FEEDS = {
        "reuters": "https://www.reutersagency.com/feed/?taxonomy=markets",
        "bloomberg": "https://www.bloomberg.com/feeds/news",
        "ft": "https://www.ft.com/?format=rss",
    }

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

        for feed_name in self.feeds.keys():
            result = self.fetch_feed(feed_name)
            if result.success:
                all_articles.extend(result.articles)
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
