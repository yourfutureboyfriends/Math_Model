"""Known-answer tests for headline sentiment scoring."""
from api.calculations.news_sentiment import score_headline, aggregate_sentiment


def test_positive_headline():
    assert score_headline("Stocks rally as profits surge and growth beats estimates") > 0.5


def test_negative_headline():
    assert score_headline("Markets plunge on recession fears as layoffs and losses mount") < -0.5


def test_neutral_headline():
    assert score_headline("Federal Reserve to meet next week") == 0.0


def test_mixed_nets_out():
    # one positive (gains) + one negative (fall) -> 0
    assert score_headline("Tech gains offset by energy fall") == 0.0


def test_aggregate_labels_and_counts():
    arts = [
        {"title": "Stocks surge to record highs on strong growth"},   # +
        {"title": "Bonds tumble as inflation fears spark selloff"},    # -
        {"title": "Fed officials to speak on Thursday"},               # 0
    ]
    agg = aggregate_sentiment(arts)
    assert agg["positive"] == 1 and agg["negative"] == 1 and agg["neutral"] == 1
    assert agg["overall"] in ("Bullish", "Bearish", "Neutral")
    assert len(agg["articles"]) == 3
    # most extreme article surfaces first
    assert abs(agg["articles"][0]["sentiment"]) >= abs(agg["articles"][-1]["sentiment"])


def test_aggregate_empty():
    agg = aggregate_sentiment([])
    assert agg["overall"] == "Neutral" and agg["articles"] == []
