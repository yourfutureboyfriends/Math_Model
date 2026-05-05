"""
Celery tasks for universe refresh and trade recommendation generation.
"""

import logging
from datetime import datetime

try:
    from celery import Celery
    celery_available = True
except ImportError:
    celery_available = False
    Celery = None

from ..signalling.universe_builder import build_universe
from ..signalling.trade_engine import generate_all_recommendations

logger = logging.getLogger(__name__)

# Initialize Celery if available
if celery_available:
    app = Celery('macro_research')
    app.conf.update(
        broker_url='redis://localhost:6379/0',
        result_backend='redis://localhost:6379/0',
        task_serializer='json',
        accept_content=['json'],
        result_serializer='json',
        timezone='UTC',
        enable_utc=True,
    )
else:
    app = None


def refresh_universe_task(force_refresh: bool = True) -> dict:
    """
    Refresh the tradeable universe cache.
    Can be called directly or via Celery.
    """
    try:
        logger.info("Starting universe refresh...")
        start_time = datetime.utcnow()

        universe = build_universe(force_refresh=force_refresh)

        end_time = datetime.utcnow()
        duration = (end_time - start_time).total_seconds()

        result = {
            "status": "success",
            "assets_count": len(universe),
            "duration_seconds": duration,
            "completed_at": end_time.isoformat(),
        }

        logger.info(f"Universe refresh completed: {len(universe)} assets in {duration:.1f}s")
        return result

    except Exception as e:
        logger.error(f"Universe refresh failed: {e}")
        return {
            "status": "error",
            "error": str(e),
            "completed_at": datetime.utcnow().isoformat(),
        }


if celery_available and app:
    @app.task(bind=True, max_retries=3)
    def refresh_universe(self, force_refresh: bool = True):
        """Celery task wrapper for universe refresh."""
        try:
            return refresh_universe_task(force_refresh)
        except Exception as exc:
            logger.error(f"Celery universe refresh failed: {exc}")
            raise self.retry(exc=exc, countdown=60)


def generate_recommendations_task(
    regime: str,
    macro_score: float,
    regime_probs: dict = None,
    df=None,
) -> dict:
    """
    Generate trade recommendations for the current regime using v2.0 engine.
    Can be called directly or via Celery.

    Args:
        regime: Modal regime classification
        macro_score: Overall macro score
        regime_probs: Dict of regime probabilities (optional)
        df: DataFrame with economic data (optional)
    """
    try:
        logger.info(f"Generating recommendations for {regime} regime (v2.0)...")
        start_time = datetime.utcnow()

        # Default regime probabilities if not provided
        if regime_probs is None:
            regime_probs = {
                regime: 0.70,
                "Goldilocks": 0.10,
                "Reflation": 0.10,
                "Slowdown": 0.05,
                "Stagflation": 0.05,
            }

        # Default scores from macro_score
        growth_score = macro_score
        inflation_score = macro_score * 0.5
        liquidity_score = macro_score * 0.3
        risk_score = -macro_score

        # Import pandas if df not provided
        if df is None:
            try:
                import pandas as pd
                df = pd.DataFrame()  # Empty DataFrame as placeholder
            except ImportError:
                df = None

        # Generate recommendations using v2.0 engine
        recommendations = generate_all_recommendations(
            regime_probs=regime_probs,
            modal_regime=regime,
            growth_score=growth_score,
            inflation_score=inflation_score,
            liquidity_score=liquidity_score,
            risk_score=risk_score,
            df=df,
            fed_funds=5.25,
            max_longs=20,
            max_shorts=12,
        )

        end_time = datetime.utcnow()
        duration = (end_time - start_time).total_seconds()

        recommendations["duration_seconds"] = duration

        logger.info(f"Recommendations generated in {duration:.1f}s")
        return recommendations

    except Exception as e:
        logger.error(f"Recommendation generation failed: {e}")
        return {
            "regime": regime,
            "macro_score": macro_score,
            "status": "error",
            "error": str(e),
            "generated_at": datetime.utcnow().isoformat(),
        }


if celery_available and app:
    @app.task(bind=True, max_retries=2)
    def generate_recommendations_async(self, regime: str, macro_score: float):
        """Celery task wrapper for recommendation generation."""
        try:
            return generate_recommendations_task(regime, macro_score)
        except Exception as exc:
            logger.error(f"Celery recommendation generation failed: {exc}")
            raise self.retry(exc=exc, countdown=30)


# Schedule periodic tasks
if celery_available and app:
    app.conf.beat_schedule = {
        'refresh-universe-every-6-hours': {
            'task': 'api.tasks.universe_tasks.refresh_universe',
            'schedule': 6 * 60 * 60.0,  # 6 hours in seconds
            'args': (True,),
        },
    }
