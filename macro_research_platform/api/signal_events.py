
# Signal Events Module (Phase 11A)
# Event publishing system for signal state changes


import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
from uuid import UUID, uuid4

import redis
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from database.models import SignalEvent, SignalDirection

logger = logging.getLogger(__name__)

REDIS_URL = __import__('os').getenv("REDIS_URL", "redis://localhost:6379/0")


class SignalEventPublisher:
    """
    Publish signal events to Redis and database.
    Enables real-time notifications and event sourcing.
    """

    def __init__(self):
        self._redis = None

    def _get_redis(self) -> Optional[redis.Redis]:
        """Get Redis connection"""
        if self._redis is None:
            try:
                self._redis = redis.from_url(REDIS_URL, decode_responses=True)
            except Exception as e:
                logger.error(f"Failed to connect to Redis: {e}")
                return None
        return self._redis

    async def publish_event(
        self,
        session: AsyncSession,
        event_type: str,
        previous_state: Optional[str],
        new_state: str,
        previous_signal: Optional[float],
        current_signal: float,
        severity: str = "info",
        description: str = "",
        affected_assets: Optional[List[str]] = None,
    ) -> SignalEvent:
        """
        Publish a signal event to database and Redis.
        """
        try:
            # Create event in database
            event = SignalEvent(
                timestamp=datetime.utcnow(),
                event_id=uuid4(),
                event_type=event_type,
                previous_state=previous_state,
                new_state=new_state,
                previous_signal=previous_signal,
                current_signal=current_signal,
                severity=severity,
                description=description,
                affected_assets=affected_assets or [],
                published_to_redis=False,
                notifications_sent=False,
            )

            session.add(event)
            await session.commit()

            # Publish to Redis
            redis_conn = self._get_redis()
            if redis_conn:
                message = {
                    "type": "signal_event",
                    "timestamp": datetime.utcnow().isoformat(),
                    "data": {
                        "event_id": str(event.event_id),
                        "event_type": event_type,
                        "previous_state": previous_state,
                        "new_state": new_state,
                        "previous_signal": previous_signal,
                        "current_signal": current_signal,
                        "severity": severity,
                        "description": description,
                        "affected_assets": affected_assets or [],
                    },
                }

                redis_conn.publish("signal_events", json.dumps(message))

                # Update event as published
                event.published_to_redis = True
                await session.commit()

            logger.info(f"Signal event published: {event_type} - {new_state}")
            return event

        except Exception as e:
            await session.rollback()
            logger.error(f"Failed to publish signal event: {e}")
            raise

    async def check_signal_flip(
        self,
        session: AsyncSession,
        signal_type: str,
        new_signal: float,
        threshold: float = 0.0,
    ) -> Optional[SignalEvent]:
        """
        Check if signal has flipped across threshold and publish event if so.
        """
        # Get previous signal
        from database.models import SignalPrediction

        stmt = select(SignalPrediction).where(
            SignalPrediction.timestamp < datetime.utcnow()
        ).order_by(desc(SignalPrediction.timestamp)).limit(1)

        result = await session.execute(stmt)
        previous = result.scalar_one_or_none()

        if previous is None:
            return None

        # Check for threshold crossing
        prev_direction = "above" if previous.signal_value > threshold else "below"
        new_direction = "above" if new_signal > threshold else "below"

        if prev_direction != new_direction:
            # Signal has flipped
            event_type = "signal_flip"
            description = f"{signal_type} signal flipped from {prev_direction} to {new_direction} threshold"
            severity = "warning" if new_direction == "below" else "info"

            return await self.publish_event(
                session=session,
                event_type=event_type,
                previous_state=prev_direction,
                new_state=new_direction,
                previous_signal=previous.signal_value,
                current_signal=new_signal,
                severity=severity,
                description=description,
            )

        return None

    async def check_regime_change(
        self,
        session: AsyncSession,
        new_regime: str,
        confidence: float,
    ) -> Optional[SignalEvent]:
        """
        Check if regime has changed and publish event if so.
        """
        from database.models import RegimeClassification

        # Get previous regime
        stmt = select(RegimeClassification).order_by(desc(RegimeClassification.timestamp)).limit(1)
        result = await session.execute(stmt)
        previous = result.scalar_one_or_none()

        if previous is None or previous.current_regime == new_regime:
            return None

        # Regime has changed
        severity = "critical" if confidence > 0.7 else "warning"

        return await self.publish_event(
            session=session,
            event_type="regime_change",
            previous_state=previous.current_regime.value if hasattr(previous.current_regime, 'value') else str(previous.current_regime),
            new_state=new_regime,
            previous_signal=None,
            current_signal=confidence,
            severity=severity,
            description=f"Macro regime changed from {previous.current_regime} to {new_regime}",
        )


class SignalEventConsumer:
    """
    Consume signal events from Redis for real-time processing.
    """

    def __init__(self, redis_url: str = REDIS_URL):
        self.redis_url = redis_url
        self._redis = None
        self._pubsub = None

    async def connect(self):
        """Connect to Redis"""
        self._redis = redis.from_url(self.redis_url, decode_responses=True)
        self._pubsub = self._redis.pubsub()
        await self._pubsub.subscribe("signal_events")
        logger.info("Signal event consumer connected to Redis")

    async def listen(self, callback):
        """Listen for events and call callback"""
        if self._pubsub is None:
            await self.connect()

        async for message in self._pubsub.listen():
            if message["type"] == "message":
                try:
                    data = json.loads(message["data"])
                    await callback(data)
                except Exception as e:
                    logger.error(f"Error processing signal event: {e}")

    async def disconnect(self):
        """Disconnect from Redis"""
        if self._pubsub:
            await self._pubsub.unsubscribe()
            await self._pubsub.close()
        if self._redis:
            await self._redis.close()


# Global publisher instance
event_publisher = SignalEventPublisher()


# Convenience functions
async def publish_signal_flip(
    session: AsyncSession,
    signal_type: str,
    previous_signal: float,
    current_signal: float,
    threshold: float = 0.0,
) -> Optional[SignalEvent]:
    """Publish a signal flip event"""
    return await event_publisher.check_signal_flip(
        session, signal_type, current_signal, threshold
    )


async def publish_regime_change(
    session: AsyncSession,
    new_regime: str,
    confidence: float,
) -> Optional[SignalEvent]:
    """Publish a regime change event"""
    return await event_publisher.check_regime_change(session, new_regime, confidence)


async def get_recent_events(
    session: AsyncSession,
    hours: int = 24,
    event_types: Optional[List[str]] = None,
    severity: Optional[str] = None,
) -> List[SignalEvent]:
    """Get recent signal events"""
    from datetime import timedelta

    cutoff = datetime.utcnow() - timedelta(hours=hours)

    stmt = select(SignalEvent).where(SignalEvent.timestamp >= cutoff)

    if event_types:
        stmt = stmt.where(SignalEvent.event_type.in_(event_types))
    if severity:
        stmt = stmt.where(SignalEvent.severity == severity)

    stmt = stmt.order_by(desc(SignalEvent.timestamp))
    result = await session.execute(stmt)
    return result.scalars().all()
