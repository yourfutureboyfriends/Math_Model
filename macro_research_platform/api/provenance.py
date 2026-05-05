
# Data Provenance Tracking Module (Phase 10A)
# Tracks data lineage, source stamps, and revision history


import hashlib
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from database.models import DataProvenance, DataSource

logger = logging.getLogger(__name__)


class ProvenanceTracker:
    """Track data provenance with revision history"""

    @staticmethod
    def compute_hash(data: Dict[str, Any]) -> str:
        """Compute SHA-256 hash of data content"""
        content = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(content.encode()).hexdigest()

    @staticmethod
    async def record_data(
        session: AsyncSession,
        data_type: str,
        data_key: str,
        value: Optional[float],
        value_json: Optional[Dict[str, Any]],
        source: DataSource,
        source_url: Optional[str] = None,
        source_api_version: Optional[str] = None,
        data_timestamp: Optional[datetime] = None,
        created_by: Optional[UUID] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> DataProvenance:
        """
        Record new data point with provenance tracking.
        If data with same key exists, creates new revision.
        """
        try:
            # Check for existing data
            stmt = select(DataProvenance).where(
                DataProvenance.data_type == data_type,
                DataProvenance.data_key == data_key,
                DataProvenance.valid_until.is_(None)
            ).order_by(desc(DataProvenance.revision_number))
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()

            # Compute revision number and hash
            revision_number = 1
            previous_revision_id = None

            if existing:
                revision_number = existing.revision_number + 1
                previous_revision_id = existing.id
                # Close previous revision
                existing.valid_until = datetime.utcnow()

            # Create new revision
            data_content = {
                "value": value,
                "value_json": value_json,
                "metadata": metadata or {},
            }
            revision_hash = ProvenanceTracker.compute_hash(data_content)

            provenance = DataProvenance(
                data_type=data_type,
                data_key=data_key,
                source=source,
                source_url=source_url,
                source_api_version=source_api_version,
                revision_number=revision_number,
                revision_hash=revision_hash,
                previous_revision_id=previous_revision_id,
                value=value,
                value_json=value_json,
                data_timestamp=data_timestamp or datetime.utcnow(),
                metadata=metadata or {},
                created_by=created_by,
            )

            session.add(provenance)
            await session.commit()

            logger.info(
                f"Recorded data provenance: {data_type}/{data_key} "
                f"rev={revision_number} from {source.value}"
            )

            return provenance

        except Exception as e:
            await session.rollback()
            logger.error(f"Failed to record data provenance: {e}")
            raise

    @staticmethod
    async def get_revision_history(
        session: AsyncSession,
        data_type: str,
        data_key: str,
        limit: int = 100
    ) -> List[DataProvenance]:
        """Get revision history for a data point"""
        stmt = select(DataProvenance).where(
            DataProvenance.data_type == data_type,
            DataProvenance.data_key == data_key
        ).order_by(desc(DataProvenance.revision_number)).limit(limit)

        result = await session.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def get_data_at_time(
        session: AsyncSession,
        data_type: str,
        data_key: str,
        timestamp: datetime
    ) -> Optional[DataProvenance]:
        """Get data as it existed at a specific time"""
        stmt = select(DataProvenance).where(
            DataProvenance.data_type == data_type,
            DataProvenance.data_key == data_key,
            DataProvenance.valid_from <= timestamp,
            (DataProvenance.valid_until.is_(None) | (DataProvenance.valid_until > timestamp))
        ).order_by(desc(DataProvenance.revision_number))

        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def validate_data(
        session: AsyncSession,
        data_type: str,
        data_key: str,
        revision_number: int
    ) -> bool:
        """Validate data integrity by checking hash"""
        stmt = select(DataProvenance).where(
            DataProvenance.data_type == data_type,
            DataProvenance.data_key == data_key,
            DataProvenance.revision_number == revision_number
        )

        result = await session.execute(stmt)
        provenance = result.scalar_one_or_none()

        if not provenance:
            return False

        # Recompute hash
        data_content = {
            "value": provenance.value,
            "value_json": provenance.value_json,
            "metadata": provenance.metadata,
        }
        computed_hash = ProvenanceTracker.compute_hash(data_content)

        return computed_hash == provenance.revision_hash


# Convenience functions for common operations
async def record_market_data(
    session: AsyncSession,
    symbol: str,
    price: float,
    source: DataSource,
    timestamp: Optional[datetime] = None,
    **kwargs
) -> DataProvenance:
    """Record market data with provenance"""
    return await ProvenanceTracker.record_data(
        session=session,
        data_type="market_price",
        data_key=symbol,
        value=price,
        value_json=kwargs,
        source=source,
        data_timestamp=timestamp,
    )


async def record_economic_indicator(
    session: AsyncSession,
    series_id: str,
    value: float,
    source: DataSource,
    timestamp: Optional[datetime] = None,
    **kwargs
) -> DataProvenance:
    """Record economic indicator with provenance"""
    return await ProvenanceTracker.record_data(
        session=session,
        data_type="economic_indicator",
        data_key=series_id,
        value=value,
        value_json=kwargs,
        source=source,
        data_timestamp=timestamp,
    )


async def record_signal(
    session: AsyncSession,
    signal_type: str,
    signal_value: float,
    source: DataSource = DataSource.CALCULATED,
    timestamp: Optional[datetime] = None,
    **kwargs
) -> DataProvenance:
    """Record signal with provenance"""
    return await ProvenanceTracker.record_data(
        session=session,
        data_type="signal",
        data_key=signal_type,
        value=signal_value,
        value_json=kwargs,
        source=source,
        data_timestamp=timestamp,
    )
