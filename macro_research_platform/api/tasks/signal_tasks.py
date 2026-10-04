# ═══════════════════════════════════════════════════════════════════════════════
# Celery Signal Tasks — Signal generation and regime classification
# ═══════════════════════════════════════════════════════════════════════════════

import logging
import os
from datetime import datetime
from typing import Dict, Any, List, Optional
import uuid

import numpy as np
import pandas as pd
from api.celery_app import app
from lightgbm import LGBMClassifier
from sklearn.model_selection import TimeSeriesSplit

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL")   # required; no credentials in source


@app.task(bind=True, max_retries=3, default_retry_delay=60)
def generate_all_signals(self) -> Dict[str, Any]:
    """
    Generate all ensemble signals with confidence intervals
    Runs every 30 minutes
    """
    results = {
        "timestamp": datetime.utcnow().isoformat(),
        "signals_generated": [],
        "errors": [],
    }

    try:
        # Signal types to generate
        signal_types = [
            "master_signal",      # composite (ensemble) score
            "growth_signal",
            "inflation_signal",
            "liquidity_signal",
            "risk_signal",
        ]

        for signal_type in signal_types:
            try:
                # Generate signal with confidence intervals
                signal = generate_signal_with_ci(signal_type)

                # Store in database
                store_signal(signal)

                results["signals_generated"].append({
                    "type": signal_type,
                    "value": signal["value"],
                    "direction": signal["direction"],
                    "confidence": signal["confidence_level"],
                })

            except Exception as e:
                logger.error(f"Failed to generate {signal_type}: {e}")
                results["errors"].append(f"{signal_type}: {str(e)}")

        # Publish signal event if significant change
        publish_signal_events(results["signals_generated"])

        return results

    except Exception as exc:
        logger.error(f"Signal generation failed: {exc}")
        raise self.retry(exc=exc)


def _live_dashboard():
    """The dashboard's live computation (the same numbers the terminal shows)."""
    import asyncio
    from api.handlers.dashboard_handler import get_dashboard_data
    return asyncio.run(get_dashboard_data(mode="live"))


def generate_signal_with_ci(signal_type: str) -> Dict[str, Any]:
    """Read a live signal from the dashboard computation, mapped to [-1, 1].

    This used to draw a random value and a random "bootstrap" interval ("Placeholder for
    demonstration") and publish it as a signal event. Confidence intervals are not modelled,
    so they are None.
    """
    d = _live_dashboard()
    raw = {
        "master_signal": d.ensemble.score if d.ensemble else None,
        "growth_signal": d.scores.growth / 100 if d.scores else None,
        "inflation_signal": d.scores.inflation / 100 if d.scores else None,
        "liquidity_signal": d.scores.liquidity / 100 if d.scores else None,
        "risk_signal": d.scores.risk / 100 if d.scores else None,
    }.get(signal_type)
    if raw is None:
        raise ValueError(f"{signal_type} unavailable")
    value = float(np.clip(2 * raw - 1, -1, 1))       # 0-1 score -> -1..+1
    direction = "bullish" if value > 0.2 else "bearish" if value < -0.2 else "neutral"
    return {
        "id": str(uuid.uuid4()),
        "type": signal_type,
        "timestamp": datetime.utcnow(),
        "value": value,
        "direction": direction,
        "confidence_level": "unrated",
        "confidence_lower_80": None, "confidence_upper_80": None,
        "confidence_lower_95": None, "confidence_upper_95": None,
        "model_version": "dashboard",
    }


def store_signal(signal: Dict[str, Any]):
    """Store signal in database"""
    # Implementation would use SQLAlchemy async session
    logger.info(f"Storing signal: {signal['type']} = {signal['value']:.3f} [{signal['direction']}]")


def publish_signal_events(signals: List[Dict[str, Any]]):
    """Publish signal events to Redis for WebSocket distribution"""
    try:
        import redis
        import json

        r = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))

        for signal in signals:
            event = {
                "type": "signal_update",
                "timestamp": datetime.utcnow().isoformat(),
                "data": signal,
            }
            r.publish("signal_events", json.dumps(event))

        logger.info(f"Published {len(signals)} signal events to Redis")

    except Exception as e:
        logger.error(f"Failed to publish signal events: {e}")


@app.task(bind=True, max_retries=3, default_retry_delay=300)
def classify_regime(self) -> Dict[str, Any]:
    """
    Classify current macro regime with probabilities
    Runs hourly
    """
    results = {
        "timestamp": datetime.utcnow().isoformat(),
        "regime": None,
        "probabilities": {},
    }

    try:
        # Calculate regime probabilities based on economic indicators
        # This would use actual regime classification model

        # The dashboard's regime classifier (this used to draw random Dirichlet "probabilities").
        d = _live_dashboard()
        current_regime = d.regime.current
        results["regime"] = current_regime
        results["probabilities"] = {}            # the classifier does not produce a distribution
        results["confidence"] = d.regime.confidenceScore

        # Store in database
        store_regime_classification(results)

        # Publish regime event if changed
        publish_regime_event(results)

        logger.info(f"Regime classified: {current_regime} (confidence {results['confidence']})")
        return results

    except Exception as exc:
        logger.error(f"Regime classification failed: {exc}")
        raise self.retry(exc=exc)


def store_regime_classification(regime_data: Dict[str, Any]):
    """Store regime classification in database"""
    logger.info(f"Storing regime: {regime_data['regime']}")


def publish_regime_event(regime_data: Dict[str, Any]):
    """Publish regime event to Redis"""
    try:
        import redis
        import json

        r = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))

        event = {
            "type": "regime_update",
            "timestamp": datetime.utcnow().isoformat(),
            "data": regime_data,
        }
        r.publish("regime_events", json.dumps(event))

    except Exception as e:
        logger.error(f"Failed to publish regime event: {e}")


@app.task(bind=True, max_retries=3, default_retry_delay=300)
def forecast_regime_transition(self) -> Dict[str, Any]:
    """
    Forecast regime transition probabilities using Gradient Boosting
    Runs daily (Phase 13B)
    """
    results = {
        "timestamp": datetime.utcnow().isoformat(),
        "current_regime": None,
        "transition_probabilities": {},
    }

    try:
        # Load features for regime transition model
        features = load_regime_features()

        if features is not None and len(features) > 100:
            # Train or load GBM model
            model = train_regime_transition_model(features)

            # Predict transition probabilities
            current_regime = features['regime'].iloc[-1]
            X = features.drop(['regime', 'timestamp'], axis=1).iloc[-1:]

            # Predict probabilities for each regime
            probs = model.predict_proba(X)[0]
            classes = model.classes_

            transition_probs = dict(zip(classes, probs))

            results["current_regime"] = current_regime
            results["transition_probabilities"] = {k: float(v) for k, v in transition_probs.items()}

            # Store in database
            store_transition_forecast(results)

            logger.info(f"Regime transition forecast: {transition_probs}")
        else:
            results["status"] = "insufficient_data"
            logger.warning("Insufficient data for regime transition forecast")

        return results

    except Exception as exc:
        logger.error(f"Regime transition forecast failed: {exc}")
        raise self.retry(exc=exc)


def load_regime_features() -> Optional[pd.DataFrame]:
    """Load features for regime transition model"""
    # Implementation would load from database
    return None


def train_regime_transition_model(features: pd.DataFrame) -> LGBMClassifier:
    """Train Gradient Boosting model for regime transition"""

    # Prepare data
    X = features.drop(['regime', 'timestamp'], axis=1)
    y = features['regime']

    # Time series split for training
    tscv = TimeSeriesSplit(n_splits=5)

    model = LGBMClassifier(
        n_estimators=100,
        learning_rate=0.1,
        max_depth=6,
        objective='multiclass',
        class_weight='balanced',
        random_state=42,
    )

    # Fit on all data (in production, would use walk-forward validation)
    model.fit(X, y)

    return model


def store_transition_forecast(forecast: Dict[str, Any]):
    """Store regime transition forecast"""
    logger.info(f"Storing regime transition forecast")


@app.task
def snapshot_portfolio() -> Dict[str, Any]:
    """
    Take portfolio snapshot with P&L attribution
    Runs every 5 minutes during market hours
    """
    results = {
        "timestamp": datetime.utcnow().isoformat(),
        "snapshots_created": 0,
    }

    try:
        # Get all open positions
        # Calculate current P&L
        # Store snapshot in database
        # Publish to Redis

        logger.info("Portfolio snapshot created")
        results["snapshots_created"] = 1

        return results

    except Exception as exc:
        logger.error(f"Portfolio snapshot failed: {exc}")
        return {"error": str(exc)}
