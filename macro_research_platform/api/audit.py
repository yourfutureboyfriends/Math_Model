
# Immutable Audit Logging Module (Phase 10B)
# TimescaleDB hypertable for append-only audit logs


import logging
from datetime import datetime
from typing import Dict, Any, Optional
from uuid import UUID

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func

from database.models import AuditLog, AuditAction

logger = logging.getLogger(__name__)


class AuditLogger:
    """
    Immutable audit logging system.
    All entries are append-only and cannot be modified or deleted.
    Uses TimescaleDB hypertable for time-series data.
    """

    @staticmethod
    async def log(
        session: AsyncSession,
        action: AuditAction,
        resource_type: str,
        resource_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        user_id: Optional[UUID] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> AuditLog:
        """
        Create an immutable audit log entry.
        This action cannot be undone - logs are append-only.
        """
        try:
            audit_entry = AuditLog(
                timestamp=datetime.utcnow(),
                user_id=user_id,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                details=details or {},
                ip_address=ip_address,
                user_agent=user_agent,
            )

            session.add(audit_entry)
            await session.commit()

            logger.debug(
                f"Audit log: {action.value} on {resource_type}"
                f"{f'/{resource_id}' if resource_id else ''} by {user_id}"
            )

            return audit_entry

        except Exception as e:
            await session.rollback()
            logger.error(f"Failed to create audit log: {e}")
            raise

    @staticmethod
    async def log_from_request(
        session: AsyncSession,
        request: Request,
        action: AuditAction,
        resource_type: str,
        resource_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        user_id: Optional[UUID] = None,
    ) -> AuditLog:
        """Create audit log entry with request metadata"""

        # Extract IP address
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            ip_address = forwarded.split(',')[0].strip()
        else:
            ip_address = request.client.host if request.client else None

        # Extract user agent
        user_agent = request.headers.get("User-Agent")

        return await AuditLogger.log(
            session=session,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
            user_id=user_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )

    @staticmethod
    async def get_audit_trail(
        session: AsyncSession,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        user_id: Optional[UUID] = None,
        action: Optional[AuditAction] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> tuple[list[AuditLog], int]:
        """
        Query audit trail with filters.
        Returns (logs, total_count).
        """
        # Build query
        stmt = select(AuditLog)

        if resource_type:
            stmt = stmt.where(AuditLog.resource_type == resource_type)
        if resource_id:
            stmt = stmt.where(AuditLog.resource_id == resource_id)
        if user_id:
            stmt = stmt.where(AuditLog.user_id == user_id)
        if action:
            stmt = stmt.where(AuditLog.action == action)
        if start_time:
            stmt = stmt.where(AuditLog.timestamp >= start_time)
        if end_time:
            stmt = stmt.where(AuditLog.timestamp <= end_time)

        # Get total count
        count_stmt = select(func.count()).select_from(stmt.subquery())
        count_result = await session.execute(count_stmt)
        total = count_result.scalar()

        # Get paginated results
        stmt = stmt.order_by(desc(AuditLog.timestamp)).offset(offset).limit(limit)
        result = await session.execute(stmt)
        logs = result.scalars().all()

        return logs, total

    @staticmethod
    async def get_user_activity(
        session: AsyncSession,
        user_id: UUID,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
    ) -> list[AuditLog]:
        """Get activity log for a specific user"""
        stmt = select(AuditLog).where(AuditLog.user_id == user_id)

        if start_time:
            stmt = stmt.where(AuditLog.timestamp >= start_time)
        if end_time:
            stmt = stmt.where(AuditLog.timestamp <= end_time)

        stmt = stmt.order_by(desc(AuditLog.timestamp)).limit(limit)
        result = await session.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def get_recent_signals(
        session: AsyncSession,
        hours: int = 24,
    ) -> list[AuditLog]:
        """Get recent signal generation events"""
        cutoff = datetime.utcnow() - __import__('datetime').timedelta(hours=hours)

        stmt = select(AuditLog).where(
            AuditLog.action == AuditAction.SIGNAL_GENERATED,
            AuditLog.timestamp >= cutoff
        ).order_by(desc(AuditLog.timestamp))

        result = await session.execute(stmt)
        return result.scalars().all()


# Convenience functions
async def log_login(
    session: AsyncSession,
    user_id: UUID,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> AuditLog:
    """Log user login"""
    return await AuditLogger.log(
        session=session,
        action=AuditAction.LOGIN,
        resource_type="user",
        resource_id=str(user_id),
        user_id=user_id,
        ip_address=ip_address,
        user_agent=user_agent,
    )


async def log_logout(
    session: AsyncSession,
    user_id: UUID,
    ip_address: Optional[str] = None,
) -> AuditLog:
    """Log user logout"""
    return await AuditLogger.log(
        session=session,
        action=AuditAction.LOGOUT,
        resource_type="user",
        resource_id=str(user_id),
        user_id=user_id,
        ip_address=ip_address,
    )


async def log_signal_generated(
    session: AsyncSession,
    signal_type: str,
    signal_value: float,
    user_id: Optional[UUID] = None,
    details: Optional[Dict[str, Any]] = None,
) -> AuditLog:
    """Log signal generation"""
    return await AuditLogger.log(
        session=session,
        action=AuditAction.SIGNAL_GENERATED,
        resource_type="signal",
        resource_id=signal_type,
        details={
            "signal_value": signal_value,
            **(details or {})
        },
        user_id=user_id,
    )


async def log_trade_executed(
    session: AsyncSession,
    position_id: str,
    symbol: str,
    side: str,
    quantity: int,
    price: float,
    user_id: UUID,
    details: Optional[Dict[str, Any]] = None,
) -> AuditLog:
    """Log trade execution"""
    return await AuditLogger.log(
        session=session,
        action=AuditAction.TRADE_EXECUTED,
        resource_type="position",
        resource_id=position_id,
        details={
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "price": price,
            **(details or {})
        },
        user_id=user_id,
    )
