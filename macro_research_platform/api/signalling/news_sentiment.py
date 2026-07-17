"""
News Sentiment Analyzer — NLP-Based Market Sentiment Extraction

Implements news sentiment analysis using FinBERT and VADER.
Combines transformer-based financial sentiment with rule-based
sentiment for robust sentiment scoring.

Models:
- FinBERT: BERT fine-tuned on financial news (Prosus AI)
- VADER: Valence Aware Dictionary and sEntiment Reasoner

Output:
- Sentiment scores (-1 to +1)
- Confidence metrics
- Entity extraction (companies, sectors mentioned)
- Trend analysis (sentiment momentum)
"""

import numpy as np
from dataclasses import dataclass
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import logging
import re

logger = logging.getLogger(__name__)

try:
    from transformers import pipeline
    TRANSFORMERS_AVAILABLE = True
except ImportError:
    TRANSFORMERS_AVAILABLE = False
    logger.warning("transformers not installed. FinBERT features disabled.")

try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    VADER_AVAILABLE = True
except ImportError:
    VADER_AVAILABLE = False
    logger.warning("vaderSentiment not installed. VADER features disabled.")


@dataclass
class SentimentResult:
    """Sentiment analysis result for a text."""
    text: str
    finbert_score: Optional[float]
    vader_score: Optional[float]
    composite_score: float
    confidence: float
    label: str  # "bullish", "bearish", "neutral"
    entities: List[str]
    timestamp: datetime


@dataclass
class SentimentAggregate:
    """Aggregate sentiment over multiple texts/time."""
    average_sentiment: float
    sentiment_std: float
    bullish_pct: float
    bearish_pct: float
    neutral_pct: float
    trend: str  # "improving", "deteriorating", "stable"
    volume: int
    top_entities: List[Dict[str, any]]


class NewsSentimentAnalyzer:
    """
    Analyze financial news sentiment using FinBERT + VADER.

    Features:
    - FinBERT for financial-domain sentiment
    - VADER as fallback / ensemble component
    - Entity extraction (basic regex-based)
    - Sentiment trend analysis
    """

    def __init__(self):
        self.finbert = None
        self.vader = None

        if TRANSFORMERS_AVAILABLE:
            try:
                self.finbert = pipeline(
                    "sentiment-analysis",
                    model="ProsusAI/finbert",
                    tokenizer="ProsusAI/finbert",
                )
                logger.info("FinBERT model loaded")
            except Exception as e:
                logger.warning(f"Failed to load FinBERT: {e}")

        if VADER_AVAILABLE:
            self.vader = SentimentIntensityAnalyzer()

    def analyze(self, text: str) -> SentimentResult:
        """
        Analyze sentiment of a single text.

        Returns combined FinBERT + VADER scores.
        """
        text = text[:512]  # Truncate for FinBERT limit

        # FinBERT scoring
        finbert_score = None
        if self.finbert:
            try:
                result = self.finbert(text)[0]
                # Map to -1 to +1 scale
                label_map = {"positive": 1, "negative": -1, "neutral": 0}
                finbert_score = label_map.get(result["label"], 0) * result["score"]
            except Exception as e:
                logger.debug(f"FinBERT analysis failed: {e}")

        # VADER scoring
        vader_score = None
        if self.vader:
            scores = self.vader.polarity_scores(text)
            vader_score = scores["compound"]  # -1 to +1

        # Composite score (average of available scores)
        scores = [s for s in [finbert_score, vader_score] if s is not None]
        composite = np.mean(scores) if scores else 0.0

        # Confidence based on agreement
        if len(scores) >= 2:
            agreement = 1 - abs(scores[0] - scores[1]) / 2
            confidence = agreement
        else:
            confidence = 0.5

        # Label
        if composite > 0.2:
            label = "bullish"
        elif composite < -0.2:
            label = "bearish"
        else:
            label = "neutral"

        # Basic entity extraction (ticker symbols)
        entities = self._extract_entities(text)

        return SentimentResult(
            text=text[:100] + "..." if len(text) > 100 else text,
            finbert_score=round(finbert_score, 3) if finbert_score else None,
            vader_score=round(vader_score, 3) if vader_score else None,
            composite_score=round(composite, 3),
            confidence=round(confidence, 3),
            label=label,
            entities=entities,
            timestamp=datetime.now(),
        )

    def _extract_entities(self, text: str) -> List[str]:
        """Extract ticker symbols and company mentions from text."""
        # Pattern for $TICKER or TICKER (common formats)
        ticker_pattern = r'\$([A-Z]{1,5})|\b([A-Z]{2,5})\b'
        matches = re.findall(ticker_pattern, text)
        tickers = [m[0] or m[1] for m in matches if len(m[0] or m[1]) >= 1]

        # Common sector keywords
        sectors = [
            "technology", "tech", "financials", "healthcare", "energy",
            "utilities", "consumer", "materials", "industrials",
            "REITs", "real estate", "communication", "staples", "discretionary"
        ]
        found_sectors = [s for s in sectors if s.lower() in text.lower()]

        return tickers + found_sectors

    def analyze_batch(self, texts: List[str]) -> List[SentimentResult]:
        """Analyze sentiment for a batch of texts."""
        return [self.analyze(text) for text in texts]

    def aggregate_sentiment(
        self,
        results: List[SentimentResult],
        lookback_days: Optional[int] = None,
    ) -> SentimentAggregate:
        """
        Aggregate sentiment results over time.

        Args:
            results: List of SentimentResult objects
            lookback_days: Optional filter for recent results only
        """
        if not results:
            return SentimentAggregate(
                average_sentiment=0.0,
                sentiment_std=0.0,
                bullish_pct=0.0,
                bearish_pct=0.0,
                neutral_pct=100.0,
                trend="stable",
                volume=0,
                top_entities=[],
            )

        # Filter by date if specified
        if lookback_days:
            cutoff = datetime.now() - timedelta(days=lookback_days)
            results = [r for r in results if r.timestamp > cutoff]

        scores = [r.composite_score for r in results]

        # Calculate distribution
        n = len(scores)
        bullish = sum(1 for s in scores if s > 0.2)
        bearish = sum(1 for s in scores if s < -0.2)
        neutral = n - bullish - bearish

        # Trend detection (simple: compare first/second half)
        mid = n // 2
        if n >= 4:
            first_half = np.mean(scores[:mid])
            second_half = np.mean(scores[mid:])
            diff = second_half - first_half
            if diff > 0.1:
                trend = "improving"
            elif diff < -0.1:
                trend = "deteriorating"
            else:
                trend = "stable"
        else:
            trend = "insufficient_data"

        # Entity aggregation
        entity_counts = {}
        for r in results:
            for e in r.entities:
                entity_counts[e] = entity_counts.get(e, 0) + 1

        top_entities = [
            {"entity": e, "mentions": c}
            for e, c in sorted(entity_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        ]

        return SentimentAggregate(
            average_sentiment=round(np.mean(scores), 3),
            sentiment_std=round(np.std(scores), 3),
            bullish_pct=round(bullish / n * 100, 1),
            bearish_pct=round(bearish / n * 100, 1),
            neutral_pct=round(neutral / n * 100, 1),
            trend=trend,
            volume=n,
            top_entities=top_entities,
        )


def get_market_sentiment_summary(
    analyzer: NewsSentimentAnalyzer,
    news_items: List[str],
) -> Dict:
    """
    Convenience function: analyze news and return summary.
    """
    results = analyzer.analyze_batch(news_items)
    aggregate = analyzer.aggregate_sentiment(results)

    return {
        "sentiment": {
            "average": aggregate.average_sentiment,
            "trend": aggregate.trend,
            "distribution": {
                "bullish_pct": aggregate.bullish_pct,
                "bearish_pct": aggregate.bearish_pct,
                "neutral_pct": aggregate.neutral_pct,
            },
        },
        "volume": aggregate.volume,
        "top_entities": aggregate.top_entities,
        "latest_signals": [
            {
                "text": r.text[:50],
                "score": r.composite_score,
                "label": r.label,
            }
            for r in results[-5:]  # Last 5
        ],
    }


def detect_sentiment_extremes(
    aggregate: SentimentAggregate,
    threshold: float = 0.7,
) -> Optional[Dict]:
    """
    Detect extreme sentiment conditions (contrarian signals).
    """
    if aggregate.bullish_pct > threshold * 100:
        return {
            "extreme": "excessive_optimism",
            "contrarian_signal": "bearish",
            "confidence": aggregate.bullish_pct / 100,
            "rationale": f"{aggregate.bullish_pct:.0f}% bullish sentiment suggests crowded positioning",
        }
    elif aggregate.bearish_pct > threshold * 100:
        return {
            "extreme": "excessive_pessimism",
            "contrarian_signal": "bullish",
            "confidence": aggregate.bearish_pct / 100,
            "rationale": f"{aggregate.bearish_pct:.0f}% bearish sentiment suggests capitulation",
        }
    return None
