"""
Alpaca API Client — Paper Trading Integration

Supports both paper trading and live trading (when keys available).
Falls back to mock mode for development without keys.

Documentation: https://alpaca.markets/docs/
"""

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from enum import Enum

logger = logging.getLogger(__name__)


class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class TimeInForce(Enum):
    DAY = "day"
    GTC = "gtc"
    OPG = "opg"
    IOC = "ioc"
    FOK = "fok"
    CLS = "cls"


@dataclass
class AlpacaCredentials:
    """Alpaca API credentials."""
    api_key: str
    api_secret: str
    paper: bool = True  # Default to paper trading


@dataclass
class Position:
    """Portfolio position."""
    symbol: str
    qty: float
    market_value: float
    avg_entry_price: float
    current_price: float
    unrealized_pl: float
    unrealized_plpc: float


@dataclass
class Order:
    """Order details."""
    id: str
    symbol: str
    side: OrderSide
    type: OrderType
    qty: float
    filled_qty: float
    status: str
    created_at: datetime
    submitted_at: Optional[datetime] = None
    filled_at: Optional[datetime] = None
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None


@dataclass
class Account:
    """Account information."""
    id: str
    account_number: str
    status: str
    equity: float
    buying_power: float
    cash: float
    portfolio_value: float
    long_market_value: float
    short_market_value: float


class AlpacaClient:
    """
    Alpaca API client with paper trading support.

    Automatically falls back to mock mode when API keys are not available.
    Set ALPACA_API_KEY and ALPACA_SECRET_KEY environment variables for live mode.
    """

    def __init__(self, credentials: Optional[AlpacaCredentials] = None):
        self.credentials = credentials or self._load_credentials()
        self.mock_mode = not self._has_valid_credentials()
        self._mock_positions: Dict[str, Position] = {}
        self._mock_orders: List[Order] = []
        self._mock_account: Optional[Account] = None
        self._init_mock_data()

        if self.mock_mode:
            logger.warning("[ALPACA] Running in MOCK MODE - no real trades will be executed")
            logger.warning("[ALPACA] Set ALPACA_API_KEY and ALPACA_SECRET_KEY for live trading")
        else:
            logger.info(f"[ALPACA] Initialized {'PAPER' if self.credentials.paper else 'LIVE'} trading mode")
            self._init_real_client()

    def _load_credentials(self) -> AlpacaCredentials:
        """Load credentials from environment variables."""
        return AlpacaCredentials(
            api_key=os.getenv("ALPACA_API_KEY", ""),
            api_secret=os.getenv("ALPACA_SECRET_KEY", ""),
            paper=os.getenv("ALPACA_PAPER", "true").lower() == "true",
        )

    def _has_valid_credentials(self) -> bool:
        """Check if valid credentials are available."""
        return bool(
            self.credentials.api_key
            and self.credentials.api_secret
            and len(self.credentials.api_key) > 10
            and len(self.credentials.api_secret) > 10
        )

    def _init_real_client(self):
        """Initialize real Alpaca client."""
        try:
            import alpaca_trade_api as tradeapi

            base_url = (
                "https://paper-api.alpaca.markets"
                if self.credentials.paper
                else "https://api.alpaca.markets"
            )

            self.api = tradeapi.REST(
                self.credentials.api_key,
                self.credentials.api_secret,
                base_url,
                api_version="v2",
            )
            logger.info("[ALPACA] Real client initialized successfully")
        except ImportError:
            logger.error("[ALPACA] alpaca-trade-api not installed. Run: pip install alpaca-trade-api")
            self.mock_mode = True
        except Exception as e:
            logger.error(f"[ALPACA] Failed to initialize real client: {e}")
            self.mock_mode = True

    def _init_mock_data(self):
        """Initialize mock portfolio data for development."""
        self._mock_account = Account(
            id="mock-account-001",
            account_number="PAPER-12345678",
            status="ACTIVE",
            equity=100000.0,
            buying_power=100000.0,
            cash=25000.0,
            portfolio_value=75000.0,
            long_market_value=75000.0,
            short_market_value=0.0,
        )

        # Sample mock positions
        self._mock_positions = {
            "SPY": Position(
                symbol="SPY",
                qty=100.0,
                market_value=45000.0,
                avg_entry_price=420.0,
                current_price=450.0,
                unrealized_pl=3000.0,
                unrealized_plpc=0.0714,
            ),
            "TLT": Position(
                symbol="TLT",
                qty=150.0,
                market_value=15000.0,
                avg_entry_price=98.0,
                current_price=100.0,
                unrealized_pl=300.0,
                unrealized_plpc=0.0204,
            ),
            "GLD": Position(
                symbol="GLD",
                qty=80.0,
                market_value=15000.0,
                avg_entry_price=180.0,
                current_price=187.5,
                unrealized_pl=600.0,
                unrealized_plpc=0.0417,
            ),
        }

    # ============ Account Operations ============

    def get_account(self) -> Account:
        """Get account information."""
        if self.mock_mode:
            return self._mock_account

        try:
            acc = self.api.get_account()
            return Account(
                id=acc.id,
                account_number=acc.account_number,
                status=acc.status,
                equity=float(acc.equity),
                buying_power=float(acc.buying_power),
                cash=float(acc.cash),
                portfolio_value=float(acc.portfolio_value),
                long_market_value=float(acc.long_market_value),
                short_market_value=float(acc.short_market_value),
            )
        except Exception as e:
            logger.error(f"[ALPACA] Failed to get account: {e}")
            raise

    # ============ Position Operations ============

    def get_positions(self) -> List[Position]:
        """Get all open positions."""
        if self.mock_mode:
            return list(self._mock_positions.values())

        try:
            positions = self.api.list_positions()
            return [
                Position(
                    symbol=p.symbol,
                    qty=float(p.qty),
                    market_value=float(p.market_value),
                    avg_entry_price=float(p.avg_entry_price),
                    current_price=float(p.current_price),
                    unrealized_pl=float(p.unrealized_pl),
                    unrealized_plpc=float(p.unrealized_plpc),
                )
                for p in positions
            ]
        except Exception as e:
            logger.error(f"[ALPACA] Failed to get positions: {e}")
            raise

    def get_position(self, symbol: str) -> Optional[Position]:
        """Get specific position."""
        if self.mock_mode:
            return self._mock_positions.get(symbol)

        try:
            p = self.api.get_position(symbol)
            return Position(
                symbol=p.symbol,
                qty=float(p.qty),
                market_value=float(p.market_value),
                avg_entry_price=float(p.avg_entry_price),
                current_price=float(p.current_price),
                unrealized_pl=float(p.unrealized_pl),
                unrealized_plpc=float(p.unrealized_plpc),
            )
        except Exception as e:
            if "position does not exist" in str(e).lower():
                return None
            raise

    # ============ Order Operations ============

    def submit_order(
        self,
        symbol: str,
        qty: float,
        side: OrderSide,
        type: OrderType = OrderType.MARKET,
        time_in_force: TimeInForce = TimeInForce.DAY,
        limit_price: Optional[float] = None,
        stop_price: Optional[float] = None,
    ) -> Order:
        """Submit a new order."""
        if self.mock_mode:
            return self._mock_submit_order(
                symbol, qty, side, type, time_in_force, limit_price, stop_price
            )

        try:
            order = self.api.submit_order(
                symbol=symbol,
                qty=qty,
                side=side.value,
                type=type.value,
                time_in_force=time_in_force.value,
                limit_price=limit_price,
                stop_price=stop_price,
            )
            return self._convert_order(order)
        except Exception as e:
            logger.error(f"[ALPACA] Failed to submit order: {e}")
            raise

    def _mock_submit_order(
        self,
        symbol: str,
        qty: float,
        side: OrderSide,
        type: OrderType,
        time_in_force: TimeInForce,
        limit_price: Optional[float],
        stop_price: Optional[float],
    ) -> Order:
        """Mock order submission for development."""
        order_id = f"mock-order-{len(self._mock_orders) + 1:04d}"

        order = Order(
            id=order_id,
            symbol=symbol,
            side=side,
            type=type,
            qty=qty,
            filled_qty=qty if type == OrderType.MARKET else 0.0,
            status="filled" if type == OrderType.MARKET else "pending",
            created_at=datetime.now(),
            submitted_at=datetime.now(),
            filled_at=datetime.now() if type == OrderType.MARKET else None,
            limit_price=limit_price,
            stop_price=stop_price,
        )

        self._mock_orders.append(order)

        # Update mock position
        if type == OrderType.MARKET:
            current_price = self._get_mock_price(symbol)
            if side == OrderSide.BUY:
                self._mock_positions[symbol] = Position(
                    symbol=symbol,
                    qty=qty,
                    market_value=qty * current_price,
                    avg_entry_price=current_price,
                    current_price=current_price,
                    unrealized_pl=0.0,
                    unrealized_plpc=0.0,
                )
                self._mock_account.cash -= qty * current_price
            else:
                if symbol in self._mock_positions:
                    del self._mock_positions[symbol]
                self._mock_account.cash += qty * current_price

        logger.info(f"[ALPACA MOCK] Order submitted: {side.value} {qty} {symbol}")
        return order

    def _get_mock_price(self, symbol: str) -> float:
        """Get mock price for a symbol."""
        mock_prices = {
            "SPY": 450.0,
            "TLT": 100.0,
            "GLD": 187.5,
            "QQQ": 380.0,
            "IWM": 200.0,
            "HYG": 75.0,
            "LQD": 110.0,
            "VNQ": 85.0,
            "DBC": 22.0,
            "AAPL": 175.0,
            "MSFT": 420.0,
            "GOOGL": 140.0,
            "AMZN": 180.0,
        }
        return mock_prices.get(symbol, 100.0)

    def get_orders(
        self,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> List[Order]:
        """Get orders with optional filtering."""
        if self.mock_mode:
            orders = self._mock_orders
            if status:
                orders = [o for o in orders if o.status == status]
            return orders[-limit:]

        try:
            orders = self.api.list_orders(status=status, limit=limit)
            return [self._convert_order(o) for o in orders]
        except Exception as e:
            logger.error(f"[ALPACA] Failed to get orders: {e}")
            raise

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order."""
        if self.mock_mode:
            for order in self._mock_orders:
                if order.id == order_id and order.status == "pending":
                    order.status = "canceled"
                    return True
            return False

        try:
            self.api.cancel_order(order_id)
            return True
        except Exception as e:
            logger.error(f"[ALPACA] Failed to cancel order: {e}")
            return False

    def cancel_all_orders(self) -> int:
        """Cancel all open orders."""
        if self.mock_mode:
            canceled = 0
            for order in self._mock_orders:
                if order.status == "pending":
                    order.status = "canceled"
                    canceled += 1
            return canceled

        try:
            return self.api.cancel_all_orders()
        except Exception as e:
            logger.error(f"[ALPACA] Failed to cancel all orders: {e}")
            raise

    def _convert_order(self, order) -> Order:
        """Convert Alpaca order to our Order dataclass."""
        return Order(
            id=order.id,
            symbol=order.symbol,
            side=OrderSide(order.side),
            type=OrderType(order.type),
            qty=float(order.qty),
            filled_qty=float(order.filled_qty),
            status=order.status,
            created_at=order.created_at,
            submitted_at=getattr(order, "submitted_at", None),
            filled_at=getattr(order, "filled_at", None),
            limit_price=float(order.limit_price) if order.limit_price else None,
            stop_price=float(order.stop_price) if order.stop_price else None,
        )

    # ============ Market Data ============

    def get_latest_quote(self, symbol: str) -> Dict[str, Any]:
        """Get latest quote for a symbol."""
        if self.mock_mode:
            price = self._get_mock_price(symbol)
            return {
                "symbol": symbol,
                "bid": price - 0.01,
                "ask": price + 0.01,
                "bid_size": 100,
                "ask_size": 100,
                "timestamp": datetime.now().isoformat(),
            }

        try:
            quote = self.api.get_latest_quote(symbol)
            return {
                "symbol": symbol,
                "bid": quote.bidprice,
                "ask": quote.askprice,
                "bid_size": quote.bidsize,
                "ask_size": quote.asksize,
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.error(f"[ALPACA] Failed to get quote: {e}")
            raise

    def get_bars(
        self,
        symbol: str,
        timeframe: str = "1Day",
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Get historical bars."""
        if self.mock_mode:
            # Generate mock bars
            bars = []
            base_price = self._get_mock_price(symbol)
            start = start or datetime.now() - timedelta(days=limit)

            for i in range(limit):
                date = start + timedelta(days=i)
                noise = (i % 5 - 2) * 0.01
                bars.append({
                    "timestamp": date.isoformat(),
                    "open": base_price * (1 + noise - 0.005),
                    "high": base_price * (1 + noise + 0.01),
                    "low": base_price * (1 + noise - 0.01),
                    "close": base_price * (1 + noise),
                    "volume": 1000000 + i * 1000,
                })
            return bars

        try:
            bars = self.api.get_bars(
                symbol, timeframe, start=start.isoformat() if start else None,
                end=end.isoformat() if end else None, limit=limit
            )
            return [
                {
                    "timestamp": bar.timestamp.isoformat(),
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                    "volume": bar.volume,
                }
                for bar in bars
            ]
        except Exception as e:
            logger.error(f"[ALPACA] Failed to get bars: {e}")
            raise

    def is_market_open(self) -> bool:
        """Check if market is currently open."""
        if self.mock_mode:
            # Mock: market open 9:30-16:00 ET, Mon-Fri
            now = datetime.now()
            if now.weekday() >= 5:  # Weekend
                return False
            hour = now.hour
            return 9 <= hour < 16

        try:
            clock = self.api.get_clock()
            return clock.is_open
        except Exception as e:
            logger.error(f"[ALPACA] Failed to get market status: {e}")
            return False


def get_alpaca_client() -> AlpacaClient:
    """Get or create Alpaca client singleton."""
    if not hasattr(get_alpaca_client, "_instance"):
        get_alpaca_client._instance = AlpacaClient()
    return get_alpaca_client._instance
