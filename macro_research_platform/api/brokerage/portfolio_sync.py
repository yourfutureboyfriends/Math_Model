"""
Portfolio Sync — Keep local state synchronized with Alpaca

Syncs positions, orders, and account data to local database
for tracking and reporting.
"""

import logging
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from pathlib import Path

from .alpaca_client import AlpacaClient, Position, Order, Account, get_alpaca_client

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent.parent.parent / "macro_terminal.db"


class PortfolioSync:
    """
    Synchronize Alpaca portfolio data to local database.

    Tracks:
    - Position history over time
    - Order fills and execution quality
    - Daily P&L snapshots
    - Trade statistics
    """

    def __init__(self, client: Optional[AlpacaClient] = None):
        self.client = client or get_alpaca_client()
        self._ensure_tables_exist()

    def _ensure_tables_exist(self):
        """Create portfolio tracking tables."""
        try:
            with sqlite3.connect(DB_PATH) as conn:
                # Position snapshots
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS position_snapshots (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT,
                        symbol TEXT,
                        qty REAL,
                        market_value REAL,
                        avg_entry_price REAL,
                        current_price REAL,
                        unrealized_pl REAL,
                        unrealized_plpc REAL
                    )
                """)

                # Order history
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS order_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT,
                        order_id TEXT UNIQUE,
                        symbol TEXT,
                        side TEXT,
                        type TEXT,
                        qty REAL,
                        filled_qty REAL,
                        status TEXT,
                        limit_price REAL,
                        stop_price REAL,
                        filled_price REAL,
                        commission REAL DEFAULT 0.0
                    )
                """)

                # Daily P&L
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS daily_pnl (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        date TEXT UNIQUE,
                        equity REAL,
                        cash REAL,
                        portfolio_value REAL,
                        daily_pnl REAL,
                        daily_pnl_pct REAL
                    )
                """)

                # Trade statistics
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS trade_stats (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        date TEXT,
                        symbol TEXT,
                        total_trades INTEGER,
                        winning_trades INTEGER,
                        losing_trades INTEGER,
                        win_rate REAL,
                        avg_win REAL,
                        avg_loss REAL,
                        profit_factor REAL
                    )
                """)

                conn.commit()
                logger.info("[PORTFOLIO_SYNC] Tables ensured")
        except Exception as e:
            logger.error(f"[PORTFOLIO_SYNC] Failed to create tables: {e}")

    def sync_positions(self) -> bool:
        """
        Sync current positions to database.

        Returns:
            True if successful
        """
        try:
            positions = self.client.get_positions()
            timestamp = datetime.now().isoformat()

            with sqlite3.connect(DB_PATH) as conn:
                for pos in positions:
                    conn.execute("""
                        INSERT INTO position_snapshots
                        (timestamp, symbol, qty, market_value, avg_entry_price,
                         current_price, unrealized_pl, unrealized_plpc)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        timestamp, pos.symbol, pos.qty, pos.market_value,
                        pos.avg_entry_price, pos.current_price,
                        pos.unrealized_pl, pos.unrealized_plpc
                    ))
                conn.commit()

            logger.info(f"[PORTFOLIO_SYNC] Synced {len(positions)} positions")
            return True

        except Exception as e:
            logger.error(f"[PORTFOLIO_SYNC] Failed to sync positions: {e}")
            return False

    def sync_orders(self, limit: int = 100) -> bool:
        """
        Sync recent orders to database.

        Args:
            limit: Number of orders to sync

        Returns:
            True if successful
        """
        try:
            orders = self.client.get_orders(limit=limit)
            timestamp = datetime.now().isoformat()

            with sqlite3.connect(DB_PATH) as conn:
                for order in orders:
                    conn.execute("""
                        INSERT OR REPLACE INTO order_history
                        (timestamp, order_id, symbol, side, type, qty,
                         filled_qty, status, limit_price, stop_price)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        timestamp, order.id, order.symbol, order.side.value,
                        order.type.value, order.qty, order.filled_qty,
                        order.status, order.limit_price, order.stop_price
                    ))
                conn.commit()

            logger.info(f"[PORTFOLIO_SYNC] Synced {len(orders)} orders")
            return True

        except Exception as e:
            logger.error(f"[PORTFOLIO_SYNC] Failed to sync orders: {e}")
            return False

    def sync_daily_pnl(self) -> bool:
        """
        Record daily P&L snapshot.

        Returns:
            True if successful
        """
        try:
            account = self.client.get_account()
            today = datetime.now().strftime("%Y-%m-%d")

            # Get yesterday's value for daily P&L calculation
            with sqlite3.connect(DB_PATH) as conn:
                yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
                row = conn.execute(
                    "SELECT portfolio_value FROM daily_pnl WHERE date = ?",
                    (yesterday,)
                ).fetchone()
                yesterday_value = row[0] if row else account.portfolio_value

                daily_pnl = account.portfolio_value - yesterday_value
                daily_pnl_pct = daily_pnl / yesterday_value if yesterday_value > 0 else 0

                conn.execute("""
                    INSERT OR REPLACE INTO daily_pnl
                    (date, equity, cash, portfolio_value, daily_pnl, daily_pnl_pct)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    today, account.equity, account.cash, account.portfolio_value,
                    daily_pnl, daily_pnl_pct
                ))
                conn.commit()

            logger.info(f"[PORTFOLIO_SYNC] Daily P&L: ${daily_pnl:.2f} ({daily_pnl_pct*100:.2f}%)")
            return True

        except Exception as e:
            logger.error(f"[PORTFOLIO_SYNC] Failed to sync daily P&L: {e}")
            return False

    def sync_all(self) -> Dict[str, bool]:
        """
        Run full sync of all data.

        Returns:
            Dict with sync status for each component
        """
        return {
            "positions": self.sync_positions(),
            "orders": self.sync_orders(),
            "daily_pnl": self.sync_daily_pnl(),
        }

    def get_position_history(
        self,
        symbol: str,
        days: int = 30
    ) -> List[Dict[str, Any]]:
        """
        Get position history for a symbol.

        Args:
            symbol: Ticker symbol
            days: Number of days of history

        Returns:
            List of position snapshots
        """
        try:
            cutoff = (datetime.now() - timedelta(days=days)).isoformat()

            with sqlite3.connect(DB_PATH) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute("""
                    SELECT * FROM position_snapshots
                    WHERE symbol = ? AND timestamp > ?
                    ORDER BY timestamp DESC
                """, (symbol, cutoff)).fetchall()

                return [dict(row) for row in rows]

        except Exception as e:
            logger.error(f"[PORTFOLIO_SYNC] Failed to get position history: {e}")
            return []

    def get_trade_performance(
        self,
        days: int = 30
    ) -> Dict[str, Any]:
        """
        Get trade performance statistics.

        Args:
            days: Analysis period in days

        Returns:
            Performance metrics
        """
        try:
            cutoff = (datetime.now() - timedelta(days=days)).isoformat()

            with sqlite3.connect(DB_PATH) as conn:
                # Get filled orders
                rows = conn.execute("""
                    SELECT * FROM order_history
                    WHERE status = 'filled' AND timestamp > ?
                """, (cutoff,)).fetchall()

                if not rows:
                    return {"message": "No trades in period"}

                # Calculate statistics
                total_trades = len(rows)

                return {
                    "period_days": days,
                    "total_trades": total_trades,
                    "avg_trade_size": sum(r[5] for r in rows) / total_trades if total_trades > 0 else 0,
                    "most_traded_symbol": max(set(r[3] for r in rows), key=lambda x: sum(1 for r in rows if r[3] == x)) if rows else None,
                }

        except Exception as e:
            logger.error(f"[PORTFOLIO_SYNC] Failed to get trade performance: {e}")
            return {"error": str(e)}

    def get_portfolio_returns(
        self,
        days: int = 30
    ) -> List[Dict[str, Any]]:
        """
        Get daily portfolio returns.

        Args:
            days: Number of days of history

        Returns:
            List of daily returns
        """
        try:
            with sqlite3.connect(DB_PATH) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute("""
                    SELECT * FROM daily_pnl
                    ORDER BY date DESC
                    LIMIT ?
                """, (days,)).fetchall()

                return [dict(row) for row in rows]

        except Exception as e:
            logger.error(f"[PORTFOLIO_SYNC] Failed to get portfolio returns: {e}")
            return []


# Scheduler entry point
def run_daily_sync():
    """Entry point for daily sync job."""
    logger.info("[PORTFOLIO_SYNC] Starting daily sync")
    sync = PortfolioSync()
    results = sync.sync_all()
    logger.info(f"[PORTFOLIO_SYNC] Results: {results}")
    return results
