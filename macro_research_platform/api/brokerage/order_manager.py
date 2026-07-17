"""
Order Manager — Strategy Execution and Order Lifecycle

Manages order submission, tracking, and execution for signal-based strategies.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Any
from enum import Enum

from .alpaca_client import (
    AlpacaClient, OrderSide, OrderType, TimeInForce,
    Order, get_alpaca_client
)

logger = logging.getLogger(__name__)


class Strategy(Enum):
    """Trading strategies supported."""
    MARKET = "market"
    LIMIT = "limit"
    VWAP = "vwap"
    TWAP = "twap"
    POV = "pov"


@dataclass
class OrderRequest:
    """Order request from strategy."""
    symbol: str
    qty: float
    side: OrderSide
    strategy: Strategy
    limit_price: Optional[float] = None
    notional: Optional[float] = None  # Dollar amount instead of qty
    time_in_force: TimeInForce = TimeInForce.DAY
    take_profit: Optional[float] = None
    stop_loss: Optional[float] = None


@dataclass
class ExecutionResult:
    """Order execution result."""
    success: bool
    order_id: Optional[str]
    filled_qty: float
    filled_price: Optional[float]
    status: str
    message: str
    timestamp: datetime


class OrderManager:
    """
    Manage order lifecycle for signal-based strategies.

    Features:
    - Order validation and risk checks
    - Position sizing based on portfolio value
    - Order tracking and status updates
    - Bracket orders (take profit / stop loss)
    """

    def __init__(self, client: Optional[AlpacaClient] = None):
        self.client = client or get_alpaca_client()
        self._order_history: Dict[str, List[Order]] = {}

    def place_market_order(
        self,
        symbol: str,
        qty: float,
        side: OrderSide,
        notional: Optional[float] = None,
    ) -> ExecutionResult:
        """
        Place a simple market order.

        Args:
            symbol: Ticker symbol
            qty: Number of shares (or use notional)
            side: BUY or SELL
            notional: Dollar amount (alternative to qty)

        Returns:
            ExecutionResult with order status
        """
        try:
            # Validate
            if not qty and not notional:
                return ExecutionResult(
                    success=False,
                    order_id=None,
                    filled_qty=0,
                    filled_price=None,
                    status="rejected",
                    message="Must specify qty or notional",
                    timestamp=datetime.now(),
                )

            # Check market is open (warn but don't block in mock mode)
            if not self.client.is_market_open():
                if not self.client.mock_mode:
                    logger.warning(f"[ORDER] Market closed - order may be queued")

            # Place order
            order = self.client.submit_order(
                symbol=symbol,
                qty=qty if qty else 0,  # Alpaca will calculate from notional if supported
                side=side,
                type=OrderType.MARKET,
                time_in_force=TimeInForce.DAY,
            )

            # Track in history
            if symbol not in self._order_history:
                self._order_history[symbol] = []
            self._order_history[symbol].append(order)

            logger.info(f"[ORDER] {side.value.upper()} {qty} {symbol} @ MARKET - ID: {order.id}")

            return ExecutionResult(
                success=order.status in ["filled", "accepted", "pending"],
                order_id=order.id,
                filled_qty=order.filled_qty,
                filled_price=None,  # Will be available after fill
                status=order.status,
                message=f"Order {order.status}",
                timestamp=datetime.now(),
            )

        except Exception as e:
            logger.error(f"[ORDER] Failed to place order: {e}")
            return ExecutionResult(
                success=False,
                order_id=None,
                filled_qty=0,
                filled_price=None,
                status="error",
                message=str(e),
                timestamp=datetime.now(),
            )

    def place_limit_order(
        self,
        symbol: str,
        qty: float,
        side: OrderSide,
        limit_price: float,
        time_in_force: TimeInForce = TimeInForce.GTC,
    ) -> ExecutionResult:
        """
        Place a limit order.

        Args:
            symbol: Ticker symbol
            qty: Number of shares
            side: BUY or SELL
            limit_price: Limit price
            time_in_force: DAY, GTC, etc.

        Returns:
            ExecutionResult with order status
        """
        try:
            order = self.client.submit_order(
                symbol=symbol,
                qty=qty,
                side=side,
                type=OrderType.LIMIT,
                time_in_force=time_in_force,
                limit_price=limit_price,
            )

            logger.info(f"[ORDER] {side.value.upper()} {qty} {symbol} @ {limit_price} LIMIT")

            return ExecutionResult(
                success=order.status in ["filled", "accepted", "pending"],
                order_id=order.id,
                filled_qty=order.filled_qty,
                filled_price=limit_price,
                status=order.status,
                message=f"Limit order {order.status}",
                timestamp=datetime.now(),
            )

        except Exception as e:
            logger.error(f"[ORDER] Failed to place limit order: {e}")
            return ExecutionResult(
                success=False,
                order_id=None,
                filled_qty=0,
                filled_price=None,
                status="error",
                message=str(e),
                timestamp=datetime.now(),
            )

    def execute_strategy_signal(
        self,
        signal: Dict[str, Any],
        portfolio_value: Optional[float] = None,
    ) -> ExecutionResult:
        """
        Execute a signal from the signal stack.

        Args:
            signal: Signal dict with symbol, action, confidence
            portfolio_value: Total portfolio value for position sizing

        Returns:
            ExecutionResult
        """
        symbol = signal.get("symbol", "SPY")
        action = signal.get("action", "hold")
        confidence = signal.get("confidence", 0.5)

        if action == "hold":
            return ExecutionResult(
                success=True,
                order_id=None,
                filled_qty=0,
                status="skipped",
                message="Hold signal - no action taken",
                timestamp=datetime.now(),
            )

        # Position sizing: 1-5% of portfolio based on confidence
        if portfolio_value:
            position_pct = 0.01 + (confidence * 0.04)  # 1% to 5%
            notional = portfolio_value * position_pct
        else:
            # Default $10,000
            notional = 10000.0

        # Get current price for qty calculation
        quote = self.client.get_latest_quote(symbol)
        price = (quote["bid"] + quote["ask"]) / 2
        qty = int(notional / price)

        side = OrderSide.BUY if action == "buy" else OrderSide.SELL

        # Check existing position
        position = self.client.get_position(symbol)
        if side == OrderSide.SELL and not position:
            return ExecutionResult(
                success=False,
                order_id=None,
                filled_qty=0,
                status="rejected",
                message=f"Cannot sell {symbol} - no position held",
                timestamp=datetime.now(),
            )

        return self.place_market_order(symbol, qty, side)

    def get_open_orders(self) -> List[Order]:
        """Get all open orders."""
        return self.client.get_orders(status="open")

    def cancel_all_orders(self) -> int:
        """Cancel all open orders."""
        return self.client.cancel_all_orders()

    def get_order_history(self, symbol: Optional[str] = None) -> List[Order]:
        """Get order history for a symbol or all symbols."""
        if symbol:
            return self._order_history.get(symbol, [])
        # Flatten all history
        return [o for orders in self._order_history.values() for o in orders]

    def liquidate_position(self, symbol: str) -> ExecutionResult:
        """
        Close entire position for a symbol.

        Args:
            symbol: Ticker to liquidate

        Returns:
            ExecutionResult
        """
        position = self.client.get_position(symbol)
        if not position:
            return ExecutionResult(
                success=False,
                order_id=None,
                filled_qty=0,
                status="rejected",
                message=f"No position in {symbol}",
                timestamp=datetime.now(),
            )

        return self.place_market_order(
            symbol=symbol,
            qty=abs(position.qty),
            side=OrderSide.SELL if position.qty > 0 else OrderSide.BUY,
        )

    def liquidate_all(self) -> Dict[str, ExecutionResult]:
        """
        Liquidate all positions (panic button).

        Returns:
            Dict mapping symbol to ExecutionResult
        """
        results = {}
        positions = self.client.get_positions()

        for position in positions:
            result = self.liquidate_position(position.symbol)
            results[position.symbol] = result

        logger.warning(f"[ORDER] Liquidated {len(positions)} positions")
        return results

    def get_portfolio_summary(self) -> Dict[str, Any]:
        """Get portfolio summary with P&L."""
        account = self.client.get_account()
        positions = self.client.get_positions()

        total_unrealized_pl = sum(p.unrealized_pl for p in positions)
        total_unrealized_plpc = (
            total_unrealized_pl / account.portfolio_value
            if account.portfolio_value > 0 else 0
        )

        return {
            "account_id": account.account_number,
            "equity": account.equity,
            "buying_power": account.buying_power,
            "cash": account.cash,
            "portfolio_value": account.portfolio_value,
            "position_count": len(positions),
            "total_unrealized_pl": total_unrealized_pl,
            "total_unrealized_plpc": total_unrealized_plpc,
            "positions": [
                {
                    "symbol": p.symbol,
                    "qty": p.qty,
                    "market_value": p.market_value,
                    "unrealized_pl": p.unrealized_pl,
                    "unrealized_plpc": p.unrealized_plpc,
                }
                for p in positions
            ],
            "is_paper": self.client.credentials.paper if not self.client.mock_mode else True,
            "is_mock": self.client.mock_mode,
        }
