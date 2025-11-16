"""
CrossTrade Order Manager

Manages order lifecycle: submission, tracking, cancellation, and status updates.
Provides high-level interface for order execution with Vector Bot.
"""

from datetime import datetime
from threading import Lock
from typing import Any, Dict, List, Optional

from logging_system import get_logger

from .crosstrade_client import CrossTradeClient
from .exceptions import InsufficientMarginError, OrderError
from .models import (
    Order,
    OrderAction,
    OrderRequest,
    OrderState,
    OrderType,
    TimeInForce,
)

logger = get_logger(__name__)


class OrderManager:
    """Manages order lifecycle and tracking.

    Provides high-level interface for submitting, tracking, and managing orders.
    Maintains in-memory order cache for quick status lookups.

    Args:
        client: CrossTradeClient instance
        account: Default account name (uses client default if None)

    Usage:
        manager = OrderManager(client)
        order = manager.submit_market_order("ES 03-25", OrderAction.BUY, 1)
        print(f"Order ID: {order.orderId}, State: {order.state}")
    """

    def __init__(self, client: CrossTradeClient, account: Optional[str] = None):
        """Initialize order manager.

        Args:
            client: CrossTradeClient for API access
            account: Default account (uses client default if None)
        """
        self.client = client
        self.account = account or client.account

        # Order cache: {order_id: Order}
        self._orders: Dict[str, Order] = {}
        self._lock = Lock()

        logger.info(f"OrderManager initialized (account: {self.account})")

    # ===================================================================
    # Order Submission
    # ===================================================================

    def submit_market_order(
        self,
        instrument: str,
        action: OrderAction,
        quantity: int,
        account: Optional[str] = None,
    ) -> Order:
        """Submit market order.

        Args:
            instrument: Instrument name (e.g., "ES 03-25")
            action: Order action (BUY, SELL, BUY_TO_COVER, SELL_SHORT)
            quantity: Order quantity (contracts)
            account: Account name (uses default if None)

        Returns:
            Order object with orderId and state

        Raises:
            OrderError: If order submission fails
            InsufficientMarginError: If insufficient margin

        Example:
            >>> order = manager.submit_market_order("ES 03-25", OrderAction.BUY, 1)
            >>> print(f"Submitted: {order.orderId}")
        """
        order_request = OrderRequest(
            instrument=instrument,
            action=action,
            quantity=quantity,
            orderType=OrderType.MARKET,
            timeInForce=TimeInForce.DAY,
        )

        logger.info(f"Submitting market order: {action.value} {quantity} {instrument}")

        order = self.client.submit_order(order_request, account or self.account)

        # Cache order
        with self._lock:
            self._orders[order.orderId] = order

        logger.info(f"Market order submitted: {order.orderId} ({order.state.value})")
        return order

    def submit_limit_order(
        self,
        instrument: str,
        action: OrderAction,
        quantity: int,
        limit_price: float,
        time_in_force: TimeInForce = TimeInForce.DAY,
        account: Optional[str] = None,
    ) -> Order:
        """Submit limit order.

        Args:
            instrument: Instrument name (e.g., "ES 03-25")
            action: Order action (BUY, SELL, BUY_TO_COVER, SELL_SHORT)
            quantity: Order quantity (contracts)
            limit_price: Limit price
            time_in_force: Time in force (DAY, GTC, IOC, FOK)
            account: Account name (uses default if None)

        Returns:
            Order object with orderId and state

        Example:
            >>> order = manager.submit_limit_order(
            ...     "ES 03-25", OrderAction.BUY, 1, limit_price=5850.0
            ... )
        """
        order_request = OrderRequest(
            instrument=instrument,
            action=action,
            quantity=quantity,
            orderType=OrderType.LIMIT,
            limitPrice=limit_price,
            timeInForce=time_in_force,
        )

        logger.info(
            f"Submitting limit order: {action.value} {quantity} {instrument} @ {limit_price}"
        )

        order = self.client.submit_order(order_request, account or self.account)

        # Cache order
        with self._lock:
            self._orders[order.orderId] = order

        logger.info(f"Limit order submitted: {order.orderId} ({order.state.value})")
        return order

    def submit_stop_market_order(
        self,
        instrument: str,
        action: OrderAction,
        quantity: int,
        stop_price: float,
        time_in_force: TimeInForce = TimeInForce.DAY,
        account: Optional[str] = None,
    ) -> Order:
        """Submit stop market order.

        Args:
            instrument: Instrument name (e.g., "ES 03-25")
            action: Order action (BUY, SELL, BUY_TO_COVER, SELL_SHORT)
            quantity: Order quantity (contracts)
            stop_price: Stop trigger price
            time_in_force: Time in force (DAY, GTC)
            account: Account name (uses default if None)

        Returns:
            Order object with orderId and state

        Example:
            >>> # Stop loss: Sell if price drops below 5800
            >>> order = manager.submit_stop_market_order(
            ...     "ES 03-25", OrderAction.SELL, 1, stop_price=5800.0
            ... )
        """
        order_request = OrderRequest(
            instrument=instrument,
            action=action,
            quantity=quantity,
            orderType=OrderType.STOP_MARKET,
            stopPrice=stop_price,
            timeInForce=time_in_force,
        )

        logger.info(
            f"Submitting stop market order: {action.value} {quantity} {instrument} @ {stop_price}"
        )

        order = self.client.submit_order(order_request, account or self.account)

        # Cache order
        with self._lock:
            self._orders[order.orderId] = order

        logger.info(
            f"Stop market order submitted: {order.orderId} ({order.state.value})"
        )
        return order

    # ===================================================================
    # Order Management
    # ===================================================================

    def cancel_order(self, order_id: str, account: Optional[str] = None) -> Order:
        """Cancel existing order.

        Args:
            order_id: Order ID to cancel
            account: Account name (uses default if None)

        Returns:
            Updated Order object with CANCELLED state

        Raises:
            OrderError: If cancellation fails

        Example:
            >>> order = manager.cancel_order("ORDER123")
            >>> assert order.state == OrderState.CANCELLED
        """
        logger.info(f"Cancelling order: {order_id}")

        order = self.client.cancel_order(order_id, account or self.account)

        # Update cache
        with self._lock:
            self._orders[order_id] = order

        logger.info(f"Order cancelled: {order_id}")
        return order

    def cancel_all_orders(
        self, instrument: Optional[str] = None, account: Optional[str] = None
    ) -> List[Order]:
        """Cancel all working orders.

        Args:
            instrument: Only cancel orders for this instrument (all if None)
            account: Account name (uses default if None)

        Returns:
            List of cancelled Order objects

        Example:
            >>> # Cancel all ES orders
            >>> cancelled = manager.cancel_all_orders(instrument="ES 03-25")
            >>> print(f"Cancelled {len(cancelled)} orders")
        """
        logger.info(f"Cancelling all orders (instrument: {instrument or 'all'})")

        # Get working orders
        orders = self.client.get_orders(account or self.account, active_only=True)

        # Filter by instrument if specified
        if instrument:
            orders = [o for o in orders if o.instrument == instrument]

        # Cancel each order
        cancelled = []
        for order in orders:
            try:
                cancelled_order = self.cancel_order(order.orderId, account)
                cancelled.append(cancelled_order)
            except Exception as e:
                logger.exception(f"Failed to cancel order {order.orderId}")

        logger.info(f"Cancelled {len(cancelled)}/{len(orders)} orders")
        return cancelled

    # ===================================================================
    # Order Tracking
    # ===================================================================

    def get_order(self, order_id: str, use_cache: bool = False) -> Optional[Order]:
        """Get order by ID.

        Args:
            order_id: Order ID to fetch
            use_cache: Use cached order if available (default: False)

        Returns:
            Order object or None if not found

        Example:
            >>> order = manager.get_order("ORDER123")
            >>> print(f"State: {order.state}, Filled: {order.filledQuantity}")
        """
        # Check cache if enabled
        if use_cache:
            with self._lock:
                if order_id in self._orders:
                    return self._orders[order_id]

        # Fetch from API (get all orders and find matching ID)
        orders = self.client.get_orders(self.account, active_only=False)
        for order in orders:
            if order.orderId == order_id:
                # Update cache
                with self._lock:
                    self._orders[order_id] = order
                return order

        return None

    def get_working_orders(
        self, instrument: Optional[str] = None, account: Optional[str] = None
    ) -> List[Order]:
        """Get all working orders.

        Args:
            instrument: Filter by instrument (all if None)
            account: Account name (uses default if None)

        Returns:
            List of working Order objects

        Example:
            >>> working = manager.get_working_orders(instrument="ES 03-25")
            >>> for order in working:
            ...     print(f"{order.orderId}: {order.action.value} {order.quantity}")
        """
        orders = self.client.get_orders(account or self.account, active_only=True)

        if instrument:
            orders = [o for o in orders if o.instrument == instrument]

        # Update cache
        with self._lock:
            for order in orders:
                self._orders[order.orderId] = order

        return orders

    def get_filled_orders(
        self, instrument: Optional[str] = None, account: Optional[str] = None
    ) -> List[Order]:
        """Get all filled orders.

        Args:
            instrument: Filter by instrument (all if None)
            account: Account name (uses default if None)

        Returns:
            List of filled Order objects
        """
        all_orders = self.client.get_orders(account or self.account, active_only=False)
        filled = [o for o in all_orders if o.state == OrderState.FILLED]

        if instrument:
            filled = [o for o in filled if o.instrument == instrument]

        return filled

    # ===================================================================
    # Position Management
    # ===================================================================

    def flatten_position(self, instrument: str, account: Optional[str] = None) -> Order:
        """Close specific position.

        Closes position by submitting opposite market order (BUY to close SHORT, SELL to close LONG).
        This approach is more reliable than the /close endpoint which has instrument encoding issues.

        Args:
            instrument: Instrument to flatten (e.g., "ES 03-25")
            account: Account name (uses default if None)

        Returns:
            Order object for closing order

        Raises:
            ValueError: If no position found for instrument

        Example:
            >>> order = manager.flatten_position("ES 03-25")
            >>> print(f"Flattening: {order.orderId}")
        """
        logger.info(f"Flattening position: {instrument}")

        # Get current position to determine direction and quantity
        positions = self.client.get_positions(account or self.account)
        target_position = None

        # Normalize instrument name for matching (API returns "ES DEC25" but we might pass "ES 12-25")
        def normalize_instrument(inst: str) -> str:
            """Extract base symbol (e.g., 'ES' from 'ES 12-25' or 'ES DEC25')."""
            return inst.split()[0].upper()

        instrument_base = normalize_instrument(instrument)

        for pos in positions:
            if (
                normalize_instrument(pos.instrument) == instrument_base
                and pos.quantity != 0
            ):
                target_position = pos
                break

        if not target_position:
            raise ValueError(f"No open position found for {instrument}")

        # Determine opposite action
        close_action = (
            OrderAction.SELL if target_position.quantity > 0 else OrderAction.BUY
        )
        close_quantity = abs(target_position.quantity)

        logger.info(
            f"Closing {target_position.instrument}: {close_action.value} {close_quantity} (current position: {target_position.quantity:+d})"
        )

        # Submit opposite market order to close position (use actual position's instrument name)
        order = self.submit_market_order(
            instrument=target_position.instrument,
            action=close_action,
            quantity=close_quantity,
            account=account,
        )

        logger.info(f"Position flattened: {instrument} (order: {order.orderId})")
        return order

    def flatten_all(self, account: Optional[str] = None) -> Dict[str, Any]:
        """Close all positions.

        Args:
            account: Account name (uses default if None)

        Returns:
            Dictionary with orderIds, closedPositions, and success flag

        Example:
            >>> result = manager.flatten_all()
            >>> print(f"Closed {len(result['closedPositions'])} positions")
        """
        logger.info("Flattening all positions")

        result = self.client.flatten_account(account or self.account)

        # Note: orderIds are returned but not full Order objects
        # We don't cache since we don't have full order details
        order_ids = result.get("orderIds", [])
        closed_positions = result.get("closedPositions", [])

        logger.info(
            f"All positions flattened ({len(closed_positions)} positions, {len(order_ids)} orders)"
        )
        return result

    # ===================================================================
    # Utilities
    # ===================================================================

    def clear_order_cache(self):
        """Clear cached orders.

        Example:
            >>> manager.clear_order_cache()
        """
        with self._lock:
            count = len(self._orders)
            self._orders.clear()
            logger.info(f"Cleared {count} cached orders")

    def get_order_stats(self) -> dict:
        """Get order statistics.

        Returns:
            Dictionary with order metrics:
                - total_cached: Number of cached orders
                - by_state: Orders grouped by state
                - by_instrument: Orders grouped by instrument
        """
        with self._lock:
            by_state = {}
            by_instrument = {}

            for order in self._orders.values():
                # Count by state
                state = order.state.value
                by_state[state] = by_state.get(state, 0) + 1

                # Count by instrument
                instrument = order.instrument
                by_instrument[instrument] = by_instrument.get(instrument, 0) + 1

            return {
                "total_cached": len(self._orders),
                "by_state": by_state,
                "by_instrument": by_instrument,
            }
