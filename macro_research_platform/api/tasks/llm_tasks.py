# ═══════════════════════════════════════════════════════════════════════════════
# Celery LLM Tasks — Phase 13A
# Ollama integration for news sentiment analysis
# ═══════════════════════════════════════════════════════════════════════════════

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

import feedparser
import requests
from bs4 import BeautifulSoup
from celery_app import app

logger = logging.getLogger(__name__)

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")


@app.task(bind=True, max_retries=3, default_retry_delay=60)
def analyze_recent_news(self, sources: Optional[List[str]] = None, hours: int = 1) -> Dict[str, Any]:
    """
    Fetch and analyze recent financial news using Ollama LLM
    Runs every 30 minutes
    Degrades gracefully if Ollama is unavailable
    """
    if sources is None:
        sources = [
            "https://feeds.bloomberg.com/markets/news.rss",
            "https://feeds.reuters.com/reuters/businessNews",
            "https://feeds.marketwatch.com/marketwatch/topstories/",
            "https://www.ft.com/?format=rss",
        ]

    results = {
        "timestamp": datetime.utcnow().isoformat(),
        "articles_analyzed": 0,
        "articles_failed": 0,
        "aggregate_sentiment": None,
        "errors": [],
    }

    # Check if Ollama is available
    if not check_ollama_available():
        logger.warning("Ollama not available, skipping LLM analysis")
        results["status"] = "ollama_unavailable"
        return results

    articles = []

    # Fetch news from RSS feeds
    for source in sources:
        try:
            feed = feedparser.parse(source)
            for entry in feed.entries[:10]:  # Top 10 articles per source
                # Parse published date
                published = entry.get('published_parsed') or entry.get('updated_parsed')
                if published:
                    published_dt = datetime(*published[:6])
                    cutoff = datetime.utcnow() - timedelta(hours=hours)

                    if published_dt > cutoff:
                        article = {
                            "headline": entry.title,
                            "url": entry.link,
                            "source": feed.feed.title if hasattr(feed.feed, 'title') else source,
                            "published_at": published_dt.isoformat(),
                            "summary": entry.get('summary', ''),
                        }
                        articles.append(article)

        except Exception as e:
            logger.error(f"Failed to fetch from {source}: {e}")
            results["errors"].append(f"{source}: {str(e)}")

    # Analyze articles in batch
    if articles:
        try:
            analyzed = analyze_sentiment_batch(articles)
            results["articles_analyzed"] = len(analyzed)

            # Calculate aggregate sentiment
            if analyzed:
                sentiments = [a.get("sentiment_score", 0) for a in analyzed if a.get("sentiment_score")]
                if sentiments:
                    avg_sentiment = sum(sentiments) / len(sentiments)
                    results["aggregate_sentiment"] = {
                        "score": round(avg_sentiment, 3),
                        "direction": "bullish" if avg_sentiment > 0.2 else "bearish" if avg_sentiment < -0.2 else "neutral",
                        "confidence": len(sentiments),
                    }

            # Store analyzed articles
            for article in analyzed:
                store_news_article(article)

        except Exception as e:
            logger.error(f"LLM analysis failed: {e}")
            results["errors"].append(f"Analysis: {str(e)}")

    return results


@app.task
def analyze_sentiment_batch(articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Analyze sentiment of news articles using Ollama LLM
    Processes in batches for efficiency
    """
    if not articles:
        return []

    analyzed = []

    for article in articles:
        try:
            # Prepare prompt for LLM
            prompt = f"""Analyze the sentiment of this financial news headline:

Headline: {article['headline']}
Summary: {article.get('summary', 'N/A')}

Provide your analysis in this exact JSON format:
{{
  "sentiment_score": <number between -1 (very bearish) and 1 (very bullish)>,
  "sentiment_category": "<bullish|bearish|neutral>",
  "macro_topics": [<list of relevant macro topics like "Fed", "inflation", "recession", "earnings">],
  "key_entities": [<list of mentioned companies, indices, or assets>],
  "explanation": "<brief explanation of sentiment reasoning>",
  "confidence": <0-1 scale>
}}

Respond ONLY with the JSON, no other text."""

            # Call Ollama API
            response = requests.post(
                f"{OLLAMA_HOST}/api/generate",
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.3,
                        "num_predict": 500,
                    },
                },
                timeout=30,
            )

            if response.status_code == 200:
                result = response.json()
                response_text = result.get("response", "")

                # Parse JSON from response
                try:
                    # Try to find JSON in response
                    json_start = response_text.find('{')
                    json_end = response_text.rfind('}') + 1

                    if json_start >= 0 and json_end > json_start:
                        json_str = response_text[json_start:json_end]
                        analysis = json.loads(json_str)
                    else:
                        analysis = json.loads(response_text)

                    # Merge with article data
                    article.update({
                        "sentiment_score": analysis.get("sentiment_score"),
                        "sentiment_category": analysis.get("sentiment_category"),
                        "macro_topics": analysis.get("macro_topics", []),
                        "key_entities": analysis.get("key_entities", []),
                        "sentiment_explanation": analysis.get("explanation"),
                        "analysis_confidence": analysis.get("confidence"),
                        "llm_model": OLLAMA_MODEL,
                        "analyzed_at": datetime.utcnow().isoformat(),
                    })

                    analyzed.append(article)

                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse LLM response JSON: {e}")
                    article["analysis_error"] = f"JSON parse error: {str(e)}"
                    analyzed.append(article)

            else:
                logger.warning(f"Ollama returned status {response.status_code}")
                article["analysis_error"] = f"HTTP {response.status_code}"
                analyzed.append(article)

        except requests.exceptions.Timeout:
            logger.warning(f"Ollama timeout analyzing article: {article['headline'][:50]}...")
            article["analysis_error"] = "timeout"
            analyzed.append(article)

        except Exception as e:
            logger.error(f"Failed to analyze article: {e}")
            article["analysis_error"] = str(e)
            analyzed.append(article)

    return analyzed


def check_ollama_available() -> bool:
    """Check if Ollama service is available"""
    try:
        response = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=5)
        return response.status_code == 200
    except Exception:
        return False


def store_news_article(article: Dict[str, Any]):
    """Store analyzed news article in database"""
    logger.info(f"Storing article: {article['headline'][:50]}... [{article.get('sentiment_category', 'unprocessed')}]")
    # Implementation would use SQLAlchemy async session to store in news_articles table


@app.task
def pull_ollama_model(model: str = OLLAMA_MODEL) -> Dict[str, Any]:
    """
    Pull/update Ollama model
    Run manually when setting up or updating model
    """
    try:
        response = requests.post(
            f"{OLLAMA_HOST}/api/pull",
            json={"name": model},
            timeout=300,
        )

        if response.status_code == 200:
            logger.info(f"Successfully pulled Ollama model: {model}")
            return {"status": "success", "model": model}
        else:
            return {"status": "error", "code": response.status_code}

    except Exception as e:
        logger.error(f"Failed to pull Ollama model: {e}")
        return {"status": "error", "error": str(e)}
