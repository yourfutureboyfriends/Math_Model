
# Position Management Module (Phase 11B)
# Live position tracking with P&L attribution


import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Any, Optional, List
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from database.models import Position, PositionPnlHistory, PortfolioSnapshot, PositionStatus
from audit import log_trade_executed

logger = logging.getLogger(__name__)


class PositionManager:
    """
    Manage trading positions with P&L attribution.
    Tracks open positions, calculates P&L, and maintains attribution.
    """

    @staticmethod
    async def open_position(
        session: AsyncSession,
        symbol: str,
        user_id: UUID,
        side: str,  # LONG or SHORT
        quantity: int,
        entry_price: float,
        entry_signal_id: Optional[UUID] = None,
        tags: Optional[List[str]] = None,
        notes: Optional[str] = None,
    ) -> Position:
        """Open a new position"""
        try:
            notional = Decimal(entry_price) * quantity

            position = Position(
                id=uuid4(),
                symbol=symbol,
                user_id=user_id,
                entry_timestamp=datetime.utcnow(),
                entry_price=Decimal(entry_price),
                entry_signal_id=entry_signal_id,
                quantity=quantity,
                side=side,
                notional=notional,
                status=PositionStatus.OPEN,
                current_price=Decimal(entry_price),
                unrealized_pnl=Decimal(0),
                unrealized_pnl_pct=0.0,
                tags=tags or [],
                notes=notes,
            )

            session.add(position)
            await session.commit()

            # Log trade in audit
            await log_trade_executed(
                session=session,
                position_id=str(position.id),
                symbol=symbol,
                side=side,
                quantity=quantity,
                price=entry_price,
                user_id=user_id,
                details={"position_id": str(position.id)},
            )

            logger.info(f"Position opened: {symbol} {side} {quantity} @ {entry_price}")
            return position

        except Exception as e:
            await session.rollback()
            logger.error(f"Failed to open position: {e}")
            raise

    @staticmethod
    async def close_position(
        session: AsyncSession,
        position_id: UUID,
        exit_price: float,
        exit_reason: str,  # signal_flip, stop_loss, take_profit, manual
        notes: Optional[str] = None,
    ) -> Position:
        """Close an open position"""
        try:
            stmt = select(Position).where(
                Position.id == position_id,
                Position.status == PositionStatus.OPEN
            )
            result = await session.execute(stmt)
            position = result.scalar_one_or_none()

            if not position:
                raise ValueError(f"Open position not found: {position_id}")

            # Calculate realized P&L
            price_diff = Decimal(exit_price) - position.entry_price
            if position.side == "SHORT":
                price_diff = -price_diff

            realized_pnl = price_diff * position.quantity
            realized_pnl_pct = float(price_diff / position.entry_price * 100)

            # Update position
            position.status = PositionStatus.CLOSED
            position.exit_timestamp = datetime.utcnow()
            position.exit_price = Decimal(exit_price)
            position.realized_pnl = realized_pnl
            position.realized_pnl_pct = realized_pnl_pct
            position.exit_reason = exit_reason

            if notes:
                position.notes = f"{position.notes or ''}\nClose: {notes}"

            # Calculate P&L attribution
            await PositionManager._calculate_attribution(session, position)

            await session.commit()

            logger.info(
                f"Position closed: {position.symbol} {position.side} "
                f"P&L: ${realized_pnl:.2f} ({realized_pnl_pct:.2f}%)"
            )

            return position

        except Exception as e:
            await session.rollback()
            logger.error(f"Failed to close position: {e}")
            raise

    @staticmethod
    async def update_position_prices(
        session: AsyncSession,
        prices: Dict[str, float],  # symbol -> price
    ) -> List[Position]:
        """
        Update current prices for all open positions.
        Creates P&L history snapshots.
        """
        updated = []

        try:
            stmt = select(Position).where(Position.status == PositionStatus.OPEN)
            result = await session.execute(stmt)
            positions = result.scalars().all()

            timestamp = datetime.utcnow()
            spy_price = prices.get("SPY", 0)
            vix_level = prices.get("^VIX", 0)

            for position in positions:
                if position.symbol not in prices:
                    continue

                current_price = Decimal(prices[position.symbol])

                # Calculate unrealized P&L
                price_diff = current_price - position.entry_price
                if position.side == "SHORT":
                    price_diff = -price_diff

                position.current_price = current_price
                position.unrealized_pnl = price_diff * position.quantity
                position.unrealized_pnl_pct = float(price_diff / position.entry_price * 100)

                # Create P&L history entry
                pnl_history = PositionPnlHistory(
                    timestamp=timestamp,
                    position_id=position.id,
                    market_price=current_price,
                    unrealized_pnl=position.unrealized_pnl,
                    unrealized_pnl_pct=position.unrealized_pnl_pct,
                    spy_return_1d=0.0,  # Would calculate from historical data
                    vix_level=vix_level,
                )
                session.add(pnl_history)
                updated.append(position)

            await session.commit()
            return updated

        except Exception as e:
            await session.rollback()
            logger.error(f"Failed to update position prices: {e}")
            raise

    @staticmethod
    async def _calculate_attribution(session: AsyncSession, position: Position):
        """Calculate P&L attribution components"""
        # This would use historical data to attribute P&L to:
        # - Signal contribution (entry timing quality)
        # - Regime contribution (alignment with macro regime)
        # - Timing contribution (exit timing quality)

        # Placeholder implementation
        position.signal_contrib = 0.4
        position.regime_contrib = 0.3
        position.timing_contrib = 0.3

    @staticmethod
    async def get_open_positions(
        session: AsyncSession,
        user_id: Optional[UUID] = None,
        symbol: Optional[str] = None,
    ) -> List[Position]:
        """Get open positions with optional filters"""
        stmt = select(Position).where(Position.status == PositionStatus.OPEN)

        if user_id:
            stmt = stmt.where(Position.user_id == user_id)
        if symbol:
            stmt = stmt.where(Position.symbol == symbol)

        stmt = stmt.order_by(desc(Position.entry_timestamp))
        result = await session.execute(stmt)
        return result.scalars().all()

    @staticmethod
    async def get_position_summary(
        session: AsyncSession,
        user_id: UUID,
    ) -> Dict[str, Any]:
        """Get summary of positions for a user"""
        # Open positions
        open_stmt = select(Position).where(
            Position.user_id == user_id,
            Position.status == PositionStatus.OPEN
        )
        open_result = await session.execute(open_stmt)
        open_positions = open_result.scalars().all()

        # Closed positions (today)
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        closed_stmt = select(Position).where(
            Position.user_id == user_id,
            Position.status == PositionStatus.CLOSED,
            Position.exit_timestamp >= today
        )
        closed_result = await session.execute(closed_stmt)
        closed_positions = closed_result.scalars().all()

        # Calculate totals
        total_unrealized = sum(p.unrealized_pnl or 0 for p in open_positions)
        total_realized = sum(p.realized_pnl or 0 for p in closed_positions)
        gross_exposure = sum(p.notional for p in open_positions)

        longs = [p for p in open_positions if p.side == "LONG"]
        shorts = [p for p in open_positions if p.side == "SHORT"]

        return {
            "open_positions": len(open_positions),
            "num_longs": len(longs),
            "num_shorts": len(shorts),
            "total_unrealized_pnl": float(total_unrealized),
            "total_realized_pnl_today": float(total_realized),
            "gross_exposure": float(gross_exposure),
            "net_exposure": sum(p.unrealized_pnl_pct or 0 for p in longs) - sum(p.unrealized_pnl_pct or 0 for p in shorts),
            "positions": open_positions,
        }


class PortfolioSnapshotManager:
    """Manage portfolio snapshots for performance tracking"""

    @staticmethod
    async def create_snapshot(
        session: AsyncSession,
        user_id: UUID,
        total_value: float,
        cash: float,
        positions: List[Position],
    ) -> PortfolioSnapshot:
        """Create a new portfolio snapshot"""
        try:
            market_value = sum(
                (p.current_price or p.entry_price) * p.quantity
                for p in positions
            )

            longs = [p for p in positions if p.side == "LONG"]
            shorts = [p for p in positions if p.side == "SHORT"]

            snapshot = PortfolioSnapshot(
                timestamp=datetime.utcnow(),
                user_id=user_id,
                total_value=Decimal(total_value),
                cash=Decimal(cash),
                market_value=Decimal(market_value),
                day_pnl=Decimal(0),  # Would calculate from previous snapshot
                day_pnl_pct=0.0,
                mtd_pnl=Decimal(0),
                ytd_pnl=Decimal(0),
                gross_exposure=sum(p.notional for p in positions),
                net_exposure=sum(p.notional for p in longs) - sum(p.notional for p in shorts),
                beta_to_spy=1.0,  # Would calculate
                num_positions=len(positions),
                num_long=len(longs),
                num_short=len(shorts),
            )

            session.add(snapshot)
            await session.commit()

            return snapshot

        except Exception as e:
            await session.rollback()
            logger.error(f"Failed to create portfolio snapshot: {e}")
            raise

    @staticmethod
    async def get_portfolio_history(
        session: AsyncSession,
        user_id: UUID,
        days: int = 30,
    ) -> List[PortfolioSnapshot]:
        """Get portfolio history for a user"""
        cutoff = datetime.utcnow() - timedelta(days=days)

        stmt = select(PortfolioSnapshot).where(
            PortfolioSnapshot.user_id == user_id,
            PortfolioSnapshot.timestamp >= cutoff
        ).order_by(PortfolioSnapshot.timestamp)

        result = await session.execute(stmt)
        return result.scalars().all()


# Convenience functions
async def get_position(
    session: AsyncSession,
    position_id: UUID,
) -> Optional[Position]:
    """Get a position by ID"""
    stmt = select(Position).where(Position.id == position_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_position_pnl_history(
    session: AsyncSession,
    position_id: UUID,
    hours: int = 24,
) -> List[PositionPnlHistory]:
    """Get P&L history for a position"""
    cutoff = datetime.utcnow() - timedelta(hours=hours)

    stmt = select(PositionPnlHistory).where(
        PositionPnlHistory.position_id == position_id,
        PositionPnlHistory.timestamp >= cutoff
    ).order_by(PositionPnlHistory.timestamp)

    result = await session.execute(stmt)
    return result.scalars().all()
