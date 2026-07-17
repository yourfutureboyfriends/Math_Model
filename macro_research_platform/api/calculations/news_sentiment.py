"""
Lightweight headline sentiment — pure, tested.

No pre-scored provider is available keyless, so sentiment is computed from real headline text
with a finance-tuned lexicon (Loughran-McDonald-style word lists, trimmed). Fast, dependency-
free, deterministic. Score is in [-1, +1] per headline; the panel aggregates across articles.
"""
from __future__ import annotations

import re
from typing import Dict, List, Sequence

# Finance-oriented sentiment lexicon (lower-case stems matched as whole words).
POSITIVE = {
    "rally", "rallies", "surge", "surges", "surged", "gain", "gains", "gained", "jump", "jumps",
    "rise", "rises", "rose", "soar", "soars", "beat", "beats", "upgrade", "upgraded", "growth",
    "grow", "optimism", "optimistic", "record", "strong", "strength", "boost", "boosts", "profit",
    "profits", "bullish", "recover", "recovery", "rebound", "outperform", "higher",
    "expand", "expansion", "win", "wins", "ease", "eases", "eased", "cooling", "resilient",
}
NEGATIVE = {
    "plunge", "plunges", "plunged", "crash", "crashes", "fall", "falls", "fell", "drop", "drops",
    "slump", "slumps", "sink", "sinks", "tumble", "tumbles", "miss", "misses", "downgrade",
    "downgraded", "recession", "fear", "fears", "selloff", "sell-off", "weak", "weakness", "cut",
    "cuts", "layoff", "layoffs", "default", "crisis", "bearish", "loss", "losses", "warn", "warns",
    "warning", "slow", "slowdown", "decline", "declines", "declined", "lower",
    "concern", "concerns", "turmoil", "volatile", "volatility", "hike", "hikes",
}

_WORD = re.compile(r"[a-z][a-z\-']+")


def score_headline(text: str) -> float:
    """Sentiment of a headline in [-1, +1]: (pos - neg) / (pos + neg). 0 if no signal words."""
    if not text:
        return 0.0
    words = _WORD.findall(text.lower())
    pos = sum(1 for w in words if w in POSITIVE)
    neg = sum(1 for w in words if w in NEGATIVE)
    if pos + neg == 0:
        return 0.0
    return round((pos - neg) / (pos + neg), 3)


def _label(score: float) -> str:
    if score > 0.15:
        return "Bullish"
    if score < -0.15:
        return "Bearish"
    return "Neutral"


def aggregate_sentiment(articles: Sequence[Dict]) -> Dict:
    """Score each article (by title, falling back to summary) and aggregate.

    `articles` items need at least a `title`. Returns overall label + mean score + trend and
    the per-article scores (most extreme first), so the panel shows headline-level detail.
    """
    scored: List[Dict] = []
    for a in articles:
        title = a.get("title") or ""
        s = score_headline(title) if title else score_headline(a.get("summary") or "")
        scored.append({**a, "sentiment": s, "label": _label(s)})
    if not scored:
        return {"overall": "Neutral", "score": 0.0, "trend": "Stable",
                "positive": 0, "negative": 0, "neutral": 0, "articles": []}
    mean = round(sum(x["sentiment"] for x in scored) / len(scored), 3)
    pos = sum(1 for x in scored if x["sentiment"] > 0.15)
    neg = sum(1 for x in scored if x["sentiment"] < -0.15)
    neu = len(scored) - pos - neg
    scored.sort(key=lambda x: abs(x["sentiment"]), reverse=True)
    return {
        "overall": _label(mean),
        "score": mean,
        "trend": "Improving" if mean > 0.05 else "Declining" if mean < -0.05 else "Stable",
        "positive": pos, "negative": neg, "neutral": neu,
        "articles": scored,
    }
