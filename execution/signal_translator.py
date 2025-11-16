"""
Signal Translator for Vector Bot

Translates Vector Bot trading signals to CrossTrade order submissions.
Handles position sizing, risk management, and order type selection.
"""

from enum import Enum
from typing import Any, Dict, Optional

from logging_system import get_logger

from .exceptions import OrderError
from .models import Order, OrderAction, OrderType, TimeInForce
from .order_manager import OrderManager

logger = get_logger(__name__)


class SignalType(str, Enum):
    LONG_ENTRY = "LONG_ENTRY"
    SHORT_ENTRY = "SHORT_ENTRY"
    EXIT = "EXIT"
    EXIT_LONG = "EXIT_LONG"
    EXIT_SHORT = "EXIT_SHORT"


class SignalTranslator:
    """Translates trading signals to CrossTrade orders.

    Converts Vector Bot scanner signals into executable orders, handling:
    - Position sizing
    - Order type selection
    - Risk management
    - Position tracking

    Args:
        order_manager: OrderManager instance
        default_quantity: Default position size (contracts)
        use_market_orders: Use market orders (True) or limit orders (False)

    Usage:
        translator = SignalTranslator(order_manager, default_quantity=1)
        order = translator.process_signal({
            "signal_type": "LONG_ENTRY",
            "instrument": "ES 03-25",
            "price": 5850.0
        })
    """

    # Futures contract multipliers (dollar value per 1-point move)
    INSTRUMENT_MULTIPLIERS = {
        # E-mini Equity Indices
        "ES": 50.0,  # E-mini S&P 500: $50 per point
        "NQ": 20.0,  # E-mini NASDAQ-100: $20 per point
        "YM": 5.0,  # E-mini Dow: $5 per point
        "RTY": 50.0,  # E-mini Russell 2000: $50 per point
        # Metals
        "GC": 100.0,  # Gold: $100 per troy ounce
        "SI": 5000.0,  # Silver: $5000 per 5000 troy ounces
        "HG": 25000.0,  # Copper: $25,000 per contract
        # Energy
        "CL": 1000.0,  # Crude Oil: $1000 per contract
        "NG": 10000.0,  # Natural Gas: $10,000 per contract
        # Currencies
        "6E": 125000.0,  # Euro FX: $125,000 per contract
        "6J": 12500000.0,  # Japanese Yen: ¥12,500,000 per contract
        "6B": 62500.0,  # British Pound: £62,500 per contract
        # Treasuries
        "ZB": 1000.0,  # 30-Year T-Bond: $1000 per point
        "ZN": 1000.0,  # 10-Year T-Note: $1000 per point
        "ZF": 1000.0,  # 5-Year T-Note: $1000 per point
    }

    def __init__(
        self,
        order_manager: OrderManager,
        default_quantity: int = 1,
        use_market_orders: bool = True,
    ):
        """Initialize signal translator.

        Args:
            order_manager: OrderManager for order execution
            default_quantity: Default position size (contracts)
            use_market_orders: Use market orders (default: True)
        """
        self.order_manager = order_manager
        self.default_quantity = default_quantity
        self.use_market_orders = use_market_orders

        logger.info(
            f"SignalTranslator initialized "
            f"(default_qty: {default_quantity}, market_orders: {use_market_orders})"
        )

    # ===================================================================
    # Signal Processing
    # ===================================================================

    def _normalize_signal_type(self, signal_type: Any) -> SignalType:
        """Normalize signal_type to SignalType enum.

        Args:
            signal_type: SignalType enum or string value

        Returns:
            SignalType enum member

        Raises:
            OrderError: If signal_type is invalid
        """
        if isinstance(signal_type, SignalType):
            return signal_type

        if isinstance(signal_type, str):
            try:
                return SignalType(signal_type)
            except ValueError:
                raise OrderError(f"Invalid signal_type: {signal_type}")

        raise OrderError(f"Invalid signal_type type: {type(signal_type)}")

    def process_signal(
        self, signal: Dict[str, Any], quantity: Optional[int] = None
    ) -> Optional[Order]:
        """Process trading signal and submit order.

        Args:
            signal: Signal dictionary with keys:
                - signal_type: SignalType enum or string (LONG_ENTRY, SHORT_ENTRY, EXIT, etc.)
                - instrument: Instrument name (e.g., "ES 03-25")
                - price: Signal price (for limit orders)
                - stop_price: Optional stop price (for stop orders)
                - quantity: Optional quantity override
            quantity: Quantity override (uses signal.quantity or default if None)

        Returns:
            Order object if submitted, None if signal filtered

        Raises:
            OrderError: If order submission fails or signal_type is invalid

        Example:
            >>> signal = {
            ...     "signal_type": "LONG_ENTRY",
            ...     "instrument": "ES 03-25",
            ...     "price": 5850.0
            ... }
            >>> order = translator.process_signal(signal)
        """
        # Extract and normalize signal fields
        signal_type = self._normalize_signal_type(signal.get("signal_type"))
        instrument = signal.get("instrument")
        price = signal.get("price")
        stop_price = signal.get("stop_price")

        # Determine quantity
        qty = quantity or signal.get("quantity") or self.default_quantity

        logger.info(
            f"Processing signal: {signal_type} {qty} {instrument} "
            f"@ {price if price else 'MARKET'}"
        )

        # Route to appropriate handler
        if signal_type == SignalType.LONG_ENTRY:
            return self._handle_long_entry(instrument, qty, price, stop_price)
        elif signal_type == SignalType.SHORT_ENTRY:
            return self._handle_short_entry(instrument, qty, price, stop_price)
        elif signal_type == SignalType.EXIT:
            return self._handle_exit(instrument)
        elif signal_type == SignalType.EXIT_LONG:
            return self._handle_exit_long(instrument, qty)
        elif signal_type == SignalType.EXIT_SHORT:
            return self._handle_exit_short(instrument, qty)
        else:
            logger.warning(f"Unknown signal type: {signal_type}")
            return None

    # ===================================================================
    # Entry Signals
    # ===================================================================

    def _handle_long_entry(
        self,
        instrument: str,
        quantity: int,
        price: Optional[float] = None,
        stop_price: Optional[float] = None,
    ) -> Order:
        """Handle long entry signal.

        Args:
            instrument: Instrument name
            quantity: Position size (contracts)
            price: Limit price (uses market if None)
            stop_price: Stop price for stop market orders

        Returns:
            Order object
        """
        logger.info(f"Long entry: {quantity} {instrument}")

        # Stop market order
        if stop_price is not None:
            return self.order_manager.submit_stop_market_order(
                instrument=instrument,
                action=OrderAction.BUY,
                quantity=quantity,
                stop_price=stop_price,
            )

        # Market order
        elif self.use_market_orders or price is None:
            return self.order_manager.submit_market_order(
                instrument=instrument, action=OrderAction.BUY, quantity=quantity
            )

        # Limit order
        else:
            return self.order_manager.submit_limit_order(
                instrument=instrument,
                action=OrderAction.BUY,
                quantity=quantity,
                limit_price=price,
            )

    def _handle_short_entry(
        self,
        instrument: str,
        quantity: int,
        price: Optional[float] = None,
        stop_price: Optional[float] = None,
    ) -> Order:
        """Handle short entry signal.

        Args:
            instrument: Instrument name
            quantity: Position size (contracts)
            price: Limit price (uses market if None)
            stop_price: Stop price for stop market orders

        Returns:
            Order object
        """
        logger.info(f"Short entry: {quantity} {instrument}")

        # Stop market order
        if stop_price is not None:
            return self.order_manager.submit_stop_market_order(
                instrument=instrument,
                action=OrderAction.SELL_SHORT,
                quantity=quantity,
                stop_price=stop_price,
            )

        # Market order
        elif self.use_market_orders or price is None:
            return self.order_manager.submit_market_order(
                instrument=instrument, action=OrderAction.SELL_SHORT, quantity=quantity
            )

        # Limit order
        else:
            return self.order_manager.submit_limit_order(
                instrument=instrument,
                action=OrderAction.SELL_SHORT,
                quantity=quantity,
                limit_price=price,
            )

    # ===================================================================
    # Exit Signals
    # ===================================================================

    def _handle_exit(self, instrument: str) -> Order:
        """Handle general exit signal (flatten position).

        Args:
            instrument: Instrument name

        Returns:
            Order object for closing order
        """
        logger.info(f"Exit signal: {instrument}")
        return self.order_manager.flatten_position(instrument)

    def _handle_exit_long(self, instrument: str, quantity: int) -> Order:
        """Handle exit long signal (sell to close).

        Args:
            instrument: Instrument name
            quantity: Quantity to close

        Returns:
            Order object
        """
        logger.info(f"Exit long: {quantity} {instrument}")

        return self.order_manager.submit_market_order(
            instrument=instrument, action=OrderAction.SELL, quantity=quantity
        )

    def _handle_exit_short(self, instrument: str, quantity: int) -> Order:
        """Handle exit short signal (buy to cover).

        Args:
            instrument: Instrument name
            quantity: Quantity to close

        Returns:
            Order object
        """
        logger.info(f"Exit short: {quantity} {instrument}")

        return self.order_manager.submit_market_order(
            instrument=instrument, action=OrderAction.BUY_TO_COVER, quantity=quantity
        )

    # ===================================================================
    # Batch Processing
    # ===================================================================

    def process_signals_batch(
        self, signals: list[Dict[str, Any]]
    ) -> list[Optional[Order]]:
        """Process multiple signals in batch.

        Args:
            signals: List of signal dictionaries

        Returns:
            List of Order objects (None for filtered signals)

        Example:
            >>> signals = [
            ...     {"signal_type": "LONG_ENTRY", "instrument": "ES 03-25"},
            ...     {"signal_type": "SHORT_ENTRY", "instrument": "NQ 03-25"}
            ... ]
            >>> orders = translator.process_signals_batch(signals)
        """
        logger.info(f"Processing batch of {len(signals)} signals")

        orders = []
        for signal in signals:
            try:
                order = self.process_signal(signal)
                orders.append(order)
            except (OrderError, ValueError) as e:
                logger.error(f"Failed to process signal {signal}: {e}", exc_info=True)
                orders.append(None)
            except Exception as e:
                logger.error(
                    f"Unexpected error processing signal {signal}: {e}", exc_info=True
                )
                raise

        successful = sum(1 for o in orders if o is not None)
        logger.info(f"Processed {successful}/{len(signals)} signals successfully")

        return orders

    # ===================================================================
    # Risk Management
    # ===================================================================

    def calculate_position_size(
        self, signal: Dict[str, Any], account_value: float, risk_percent: float = 0.01
    ) -> int:
        """Calculate position size based on risk parameters.

        Accounts for futures contract multipliers to prevent over-leverage.

        Args:
            signal: Signal dictionary with stop_loss, price, and instrument
            account_value: Account value (USD)
            risk_percent: Risk per trade (default: 1% = 0.01)

        Returns:
            Position size in contracts

        Example:
            >>> signal = {
            ...     "price": 5850.0,
            ...     "stop_loss": 5800.0,
            ...     "instrument": "ES 03-25"
            ... }
            >>> qty = translator.calculate_position_size(signal, 100000, 0.01)
            >>> # Risk $1000 (1% of $100k), ES multiplier $50, 50pt stop
            >>> # risk_per_contract = 50 * $50 = $2500, position = 0 contracts (capped to 1)
        """
        price = signal.get("price")
        stop_loss = signal.get("stop_loss")
        instrument = signal.get("instrument", "")

        if price is None or stop_loss is None:
            logger.warning("Cannot calculate position size without price and stop_loss")
            return self.default_quantity

        # Extract base instrument (e.g., "ES 03-25" → "ES")
        base_instrument = instrument.split()[0] if instrument else ""

        # Get contract multiplier (default to 1.0 if not found)
        multiplier = self.INSTRUMENT_MULTIPLIERS.get(base_instrument, 1.0)

        # Calculate risk per contract (price difference * multiplier)
        price_diff = abs(price - stop_loss)
        risk_per_contract = price_diff * multiplier

        # Guard against zero risk
        if risk_per_contract == 0:
            logger.warning(
                f"Zero risk per contract for {instrument} "
                f"(price_diff={price_diff}, multiplier={multiplier})"
            )
            return self.default_quantity

        # Calculate maximum risk amount
        max_risk_amount = account_value * risk_percent

        # Calculate position size
        position_size = int(max_risk_amount / risk_per_contract)

        # Ensure at least 1 contract
        position_size = max(1, position_size)

        logger.info(
            f"Position size: {position_size} contracts for {instrument} "
            f"(risk ${max_risk_amount:.2f} / ${risk_per_contract:.2f} per contract, "
            f"multiplier: ${multiplier})"
        )

        return position_size

    def validate_signal(self, signal: Dict[str, Any]) -> bool:
        """Validate signal has required fields.

        Args:
            signal: Signal dictionary to validate

        Returns:
            True if valid, False otherwise
        """
        required_fields = ["signal_type", "instrument"]

        for field in required_fields:
            if field not in signal:
                logger.error(f"Invalid signal: missing field '{field}'")
                return False

        # Validate signal type
        signal_type = signal.get("signal_type")
        if signal_type not in [s.value for s in SignalType]:
            logger.error(f"Invalid signal_type: {signal_type}")
            return False

        return True

    # ===================================================================
    # Position Management
    # ===================================================================

    def check_existing_position(self, instrument: str) -> Optional[int]:
        """Check if position exists for instrument.

        Args:
            instrument: Instrument name

        Returns:
            Position quantity (positive for long, negative for short, None if flat)
        """
        positions = self.order_manager.client.get_positions()

        for position in positions:
            if position.instrument == instrument:
                return position.quantity

        return None

    def should_enter_trade(
        self, signal: Dict[str, Any], allow_reversals: bool = False
    ) -> bool:
        """Determine if trade should be entered.

        Args:
            signal: Signal dictionary
            allow_reversals: Allow position reversals (default: False)

        Returns:
            True if should enter, False if should skip
        """
        instrument = signal.get("instrument")
        signal_type = self._normalize_signal_type(signal.get("signal_type"))

        # Check existing position
        current_qty = self.check_existing_position(instrument)

        # Flat position - can enter
        if current_qty is None or current_qty == 0:
            return True

        # Long position
        if current_qty > 0:
            if signal_type == SignalType.LONG_ENTRY:
                logger.info(f"Already long {instrument}, skipping long entry")
                return False
            elif signal_type == SignalType.SHORT_ENTRY:
                if allow_reversals:
                    logger.info(f"Reversing from long to short: {instrument}")
                    # Flatten existing long position first to ensure correct net position
                    self.order_manager.flatten_position(instrument)
                    return True
                else:
                    logger.info(
                        f"Already long {instrument}, skipping short entry (reversals disabled)"
                    )
                    return False

        # Short position
        if current_qty < 0:
            if signal_type == SignalType.SHORT_ENTRY:
                logger.info(f"Already short {instrument}, skipping short entry")
                return False
            elif signal_type == SignalType.LONG_ENTRY:
                if allow_reversals:
                    logger.info(f"Reversing from short to long: {instrument}")
                    # Flatten existing short position first to ensure correct net position
                    self.order_manager.flatten_position(instrument)
                    return True
                else:
                    logger.info(
                        f"Already short {instrument}, skipping long entry (reversals disabled)"
                    )
                    return False

        return True
