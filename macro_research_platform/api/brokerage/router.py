"""
Brokerage API Router — Alpaca Paper Trading Endpoints
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from datetime import datetime

from .alpaca_client import (
    AlpacaClient, get_alpaca_client, OrderSide, OrderType, TimeInForce
)
from .order_manager import OrderManager
from .portfolio_sync import PortfolioSync, run_daily_sync

router = APIRouter(prefix="/brokerage", tags=["brokerage"])


class PlaceOrderRequest(BaseModel):
    """Request to place an order."""
    symbol: str
    qty: Optional[float] = None
    notional: Optional[float] = None
    side: str  # "buy" or "sell"
    order_type: str = "market"  # "market", "limit", "stop", "stop_limit"
    limit_price: Optional[float] = None
    time_in_force: str = "day"  # "day", "gtc", "opg", "ioc", "fok", "cls"


class OrderResponse(BaseModel):
    """Order response."""
    success: bool
    order_id: Optional[str] = None
    status: str
    message: str
    filled_qty: float = 0.0
    timestamp: str


class PositionResponse(BaseModel):
    """Position information."""
    symbol: str
    qty: float
    market_value: float
    avg_entry_price: float
    current_price: float
    unrealized_pl: float
    unrealized_plpc: float


class AccountResponse(BaseModel):
    """Account information."""
    account_number: str
    status: str
    equity: float
    buying_power: float
    cash: float
    portfolio_value: float
    long_market_value: float
    short_market_value: float
    is_paper: bool
    is_mock: bool


class PortfolioSummaryResponse(BaseModel):
    """Portfolio summary response."""
    account_id: str
    equity: float
    buying_power: float
    cash: float
    portfolio_value: float
    position_count: int
    total_unrealized_pl: float
    total_unrealized_plpc: float
    positions: List[Dict[str, Any]]
    is_paper: bool
    is_mock: bool


@router.get("/health")
async def brokerage_health():
    """
    Check brokerage connection status.

    Returns:
        Connection status and mode
    """
    client = get_alpaca_client()

    return {
        "status": "connected" if not client.mock_mode else "mock_mode",
        "mock_mode": client.mock_mode,
        "paper_trading": client.credentials.paper if not client.mock_mode else True,
        "api_key_configured": bool(client.credentials.api_key) and len(client.credentials.api_key) > 10,
    }


@router.get("/account", response_model=AccountResponse)
async def get_account():
    """
    Get Alpaca account information.

    Returns:
        Account details including equity, buying power, positions
    """
    try:
        client = get_alpaca_client()
        account = client.get_account()

        return AccountResponse(
            account_number=account.account_number,
            status=account.status,
            equity=account.equity,
            buying_power=account.buying_power,
            cash=account.cash,
            portfolio_value=account.portfolio_value,
            long_market_value=account.long_market_value,
            short_market_value=account.short_market_value,
            is_paper=client.credentials.paper if not client.mock_mode else True,
            is_mock=client.mock_mode,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get account: {str(e)}")


@router.get("/positions", response_model=List[PositionResponse])
async def get_positions():
    """
    Get all open positions.

    Returns:
        List of positions with P&L
    """
    try:
        client = get_alpaca_client()
        positions = client.get_positions()

        return [
            PositionResponse(
                symbol=p.symbol,
                qty=p.qty,
                market_value=p.market_value,
                avg_entry_price=p.avg_entry_price,
                current_price=p.current_price,
                unrealized_pl=p.unrealized_pl,
                unrealized_plpc=p.unrealized_plpc,
            )
            for p in positions
        ]

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get positions: {str(e)}")


@router.get("/positions/{symbol}", response_model=PositionResponse)
async def get_position(symbol: str):
    """
    Get specific position.

    Args:
        symbol: Ticker symbol

    Returns:
        Position details
    """
    try:
        client = get_alpaca_client()
        position = client.get_position(symbol)

        if not position:
            raise HTTPException(status_code=404, detail=f"No position found for {symbol}")

        return PositionResponse(
            symbol=position.symbol,
            qty=position.qty,
            market_value=position.market_value,
            avg_entry_price=position.avg_entry_price,
            current_price=position.current_price,
            unrealized_pl=position.unrealized_pl,
            unrealized_plpc=position.unrealized_plpc,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get position: {str(e)}")


@router.post("/orders", response_model=OrderResponse)
async def place_order(request: PlaceOrderRequest):
    """
    Place a new order.

    Args:
        request: Order details

    Returns:
        Order execution result
    """
    try:
        manager = OrderManager()

        # Map string to enum
        side = OrderSide.BUY if request.side.lower() == "buy" else OrderSide.SELL

        result = manager.place_market_order(
            symbol=request.symbol,
            qty=request.qty or 0,
            side=side,
            notional=request.notional,
        )

        return OrderResponse(
            success=result.success,
            order_id=result.order_id,
            status=result.status,
            message=result.message,
            filled_qty=result.filled_qty,
            timestamp=result.timestamp.isoformat(),
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to place order: {str(e)}")


@router.get("/orders")
async def get_orders(status: Optional[str] = None, limit: int = 100):
    """
    Get order history.

    Args:
        status: Filter by status (open, closed, all)
        limit: Maximum number of orders to return

    Returns:
        List of orders
    """
    try:
        client = get_alpaca_client()
        orders = client.get_orders(status=status, limit=limit)

        return [
            {
                "id": o.id,
                "symbol": o.symbol,
                "side": o.side.value,
                "type": o.type.value,
                "qty": o.qty,
                "filled_qty": o.filled_qty,
                "status": o.status,
                "created_at": o.created_at.isoformat() if o.created_at else None,
                "filled_at": o.filled_at.isoformat() if o.filled_at else None,
            }
            for o in orders
        ]

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get orders: {str(e)}")


@router.delete("/orders/{order_id}")
async def cancel_order(order_id: str):
    """
    Cancel an open order.

    Args:
        order_id: Order ID to cancel

    Returns:
        Cancellation result
    """
    try:
        client = get_alpaca_client()
        success = client.cancel_order(order_id)

        return {
            "success": success,
            "order_id": order_id,
            "message": "Order canceled" if success else "Order not found or already filled",
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to cancel order: {str(e)}")


@router.delete("/orders")
async def cancel_all_orders():
    """
    Cancel all open orders.

    Returns:
        Number of orders canceled
    """
    try:
        manager = OrderManager()
        count = manager.cancel_all_orders()

        return {
            "canceled_count": count,
            "message": f"Canceled {count} orders",
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to cancel orders: {str(e)}")


@router.get("/portfolio/summary", response_model=PortfolioSummaryResponse)
async def get_portfolio_summary():
    """
    Get portfolio summary with P&L.

    Returns:
        Portfolio summary including all positions
    """
    try:
        manager = OrderManager()
        summary = manager.get_portfolio_summary()

        return PortfolioSummaryResponse(**summary)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get portfolio summary: {str(e)}")


@router.post("/portfolio/liquidate/{symbol}")
async def liquidate_position(symbol: str):
    """
    Liquidate a specific position (market order to close).

    Args:
        symbol: Symbol to liquidate

    Returns:
        Liquidation result
    """
    try:
        manager = OrderManager()
        result = manager.liquidate_position(symbol)

        return {
            "success": result.success,
            "order_id": result.order_id,
            "status": result.status,
            "message": result.message,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to liquidate: {str(e)}")


@router.post("/portfolio/liquidate-all")
async def liquidate_all_positions():
    """
    Liquidate ALL positions (panic button).

    Returns:
        Dict of liquidation results per symbol
    """
    try:
        manager = OrderManager()
        results = manager.liquidate_all()

        return {
            "liquidated_count": len(results),
            "results": {
                symbol: {
                    "success": r.success,
                    "status": r.status,
                    "message": r.message,
                }
                for symbol, r in results.items()
            },
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to liquidate all: {str(e)}")


@router.get("/market/status")
async def get_market_status():
    """
    Get market open/closed status.

    Returns:
        Market status
    """
    try:
        client = get_alpaca_client()
        is_open = client.is_market_open()

        return {
            "is_open": is_open,
            "status": "open" if is_open else "closed",
            "next_open": "Tomorrow 09:30" if not is_open else "Now",
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get market status: {str(e)}")


@router.get("/market/quote/{symbol}")
async def get_quote(symbol: str):
    """
    Get latest quote for a symbol.

    Args:
        symbol: Ticker symbol

    Returns:
        Quote data
    """
    try:
        client = get_alpaca_client()
        quote = client.get_latest_quote(symbol)

        return quote

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get quote: {str(e)}")


@router.get("/sync/status")
async def get_sync_status():
    """
    Get portfolio sync status.

    Returns:
        Sync status and last sync times
    """
    try:
        sync = PortfolioSync()

        # Try to get some data to verify sync is working
        returns = sync.get_portfolio_returns(days=7)

        return {
            "status": "healthy",
            "records_available": len(returns),
            "latest_record": returns[0] if returns else None,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get sync status: {str(e)}")


@router.post("/sync/run")
async def run_sync(background_tasks: BackgroundTasks):
    """
    Manually trigger portfolio sync.

    Returns:
        Sync result
    """
    try:
        results = run_daily_sync()

        return {
            "success": all(results.values()),
            "results": results,
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to run sync: {str(e)}")


@router.get("/performance")
async def get_performance(days: int = 30):
    """
    Get trading performance metrics.

    Args:
        days: Number of days to analyze

    Returns:
        Performance metrics
    """
    try:
        sync = PortfolioSync()

        # Get returns history
        returns = sync.get_portfolio_returns(days=days)

        # Calculate metrics
        if returns:
            total_return = sum(r.get("daily_pnl_pct", 0) for r in returns)
            avg_daily = total_return / len(returns) if returns else 0
        else:
            total_return = 0
            avg_daily = 0

        return {
            "period_days": days,
            "total_return_pct": round(total_return * 100, 2),
            "avg_daily_return_pct": round(avg_daily * 100, 2),
            "data_points": len(returns),
            "returns_history": returns[:10],  # Last 10 days
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get performance: {str(e)}")
