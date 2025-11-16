"""
CrossTrade Integration Example for Futures-Algo
Demonstrates how to use crosstrade module for order execution
"""

import json
import logging
from datetime import datetime
from typing import Dict, Optional

# CrossTrade imports (from execution/ directory)
from execution.crosstrade_client import CrossTradeClient
from execution.models import Order, OrderAction
from execution.order_manager import OrderManager
from execution.signal_translator import SignalTranslator, SignalType

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class SimpleExecutor:
    """
    Minimal example of how to use CrossTrade for execution.

    This shows the three-step process:
    1. Initialize CrossTrade components
    2. Receive signals from scanner
    3. Execute trades via NinjaTrader
    """

    def __init__(self, config_path="config/execution_config.json"):
        """Initialize CrossTrade components."""

        # Load configuration
        with open(config_path) as f:
            config = json.load(f)

        # Step 1: Create CrossTrade client
        self.client = CrossTradeClient(
            base_url=config.get("crosstrade_url", "http://localhost:8080"),
            account=config.get("nt8_account", "Sim101"),
        )

        # Step 2: Create order manager
        self.order_manager = OrderManager(
            client=self.client, account=config.get("nt8_account")
        )

        # Step 3: Create signal translator
        self.signal_translator = SignalTranslator(
            order_manager=self.order_manager,
            default_quantity=config.get("default_quantity", 1),
            use_market_orders=config.get("use_market_orders", True),
        )

        logger.info("SimpleExecutor initialized successfully")

        # Verify connection
        self._verify_connection()

    def _verify_connection(self):
        """Verify NT8 connection is working."""
        try:
            accounts = self.client.get_accounts()
            logger.info(f"Connected to NT8. Available accounts: {accounts}")
        except Exception as e:
            logger.error(f"Failed to connect to NT8: {e}")
            raise

    def execute_signal(self, signal: Dict) -> Optional[Order]:
        """
        Execute a trading signal.

        Args:
            signal: Dict with keys:
                - signal_type: "LONG_ENTRY", "SHORT_ENTRY", or "EXIT"
                - instrument: e.g. "ES 03-25"
                - price: Current market price
                - timestamp: ISO format timestamp

        Returns:
            Order object if successful, None otherwise
        """
        logger.info(f"Processing signal: {signal}")

        try:
            # Use signal translator to convert signal → order
            order = self.signal_translator.process_signal(signal)

            if order:
                logger.info(
                    f"Order submitted successfully:\n"
                    f"  Order ID: {order.orderId}\n"
                    f"  Action: {order.action}\n"
                    f"  Quantity: {order.quantity}\n"
                    f"  Instrument: {order.instrument}\n"
                    f"  State: {order.state}"
                )
                return order
            else:
                logger.warning(f"Signal not executed: {signal}")
                return None

        except Exception as e:
            logger.exception(f"Failed to execute signal: {e}")
            return None

    def get_current_positions(self):
        """Get current positions from NT8."""
        try:
            positions = self.client.get_positions()
            logger.info(f"Current positions: {len(positions)}")
            for pos in positions:
                logger.info(
                    f"  {pos.instrument}: {pos.quantity} contracts, "
                    f"Avg Price: {pos.averagePrice}"
                )
            return positions
        except Exception as e:
            logger.exception(f"Failed to get positions: {e}")
            return []

    def close_all_positions(self):
        """Emergency: Close all open positions."""
        try:
            positions = self.client.get_positions()
            for pos in positions:
                logger.warning(f"Closing position: {pos.instrument}")
                order = self.order_manager.flatten_position(pos.instrument)
                logger.info(f"Exit order submitted: {order.orderId}")
        except Exception as e:
            logger.exception(f"Failed to close positions: {e}")


# ==================== USAGE EXAMPLES ====================


def example_1_simple_execution():
    """Example 1: Execute a single long entry signal."""

    print("\n" + "=" * 60)
    print("Example 1: Simple Long Entry")
    print("=" * 60 + "\n")

    # Initialize executor
    executor = SimpleExecutor()

    # Signal from scanner (your live_scanner.py would generate this)
    signal = {
        "signal_type": "LONG_ENTRY",
        "instrument": "ES 03-25",
        "price": 5850.0,
        "timestamp": datetime.now().isoformat(),
    }

    # Execute
    order = executor.execute_signal(signal)

    if order:
        print(f"\n✅ Order submitted: {order.orderId}")
        print(f"   Status: {order.state}")
    else:
        print("\n❌ Order failed")


def example_2_with_position_check():
    """Example 2: Check existing position before entry."""

    print("\n" + "=" * 60)
    print("Example 2: Entry with Position Check")
    print("=" * 60 + "\n")

    executor = SimpleExecutor()

    # Check if we already have a position
    existing = executor.signal_translator.check_existing_position("ES 03-25")

    if existing:
        print(f"⚠️  Position exists: {existing} contracts")
        print("   Skipping entry signal")
        return

    # No position, proceed with entry
    signal = {
        "signal_type": "LONG_ENTRY",
        "instrument": "ES 03-25",
        "price": 5850.0,
        "timestamp": datetime.now().isoformat(),
    }

    order = executor.execute_signal(signal)
    print(f"✅ New position opened: {order.orderId}")


def example_3_full_round_trip():
    """Example 3: Complete trade cycle (entry → exit)."""

    print("\n" + "=" * 60)
    print("Example 3: Full Round Trip (Entry + Exit)")
    print("=" * 60 + "\n")

    executor = SimpleExecutor()

    # ENTRY
    entry_signal = {
        "signal_type": "LONG_ENTRY",
        "instrument": "ES 03-25",
        "price": 5850.0,
        "timestamp": datetime.now().isoformat(),
    }

    print("1. Entering long position...")
    entry_order = executor.execute_signal(entry_signal)

    if not entry_order:
        print("❌ Entry failed")
        return

    print(f"✅ Entry order: {entry_order.orderId}\n")

    # CHECK POSITION
    print("2. Checking current position...")
    positions = executor.get_current_positions()

    # Simulate: wait for signal to exit (in real system, scanner would detect)
    input("\nPress Enter when ready to exit position...")

    # EXIT
    exit_signal = {
        "signal_type": "EXIT",
        "instrument": "ES 03-25",
        "timestamp": datetime.now().isoformat(),
    }

    print("\n3. Exiting position...")
    exit_order = executor.execute_signal(exit_signal)

    if exit_order:
        print(f"✅ Exit order: {exit_order.orderId}")
    else:
        print("❌ Exit failed")


def example_4_batch_signals():
    """Example 4: Process multiple signals (multi-instrument)."""

    print("\n" + "=" * 60)
    print("Example 4: Batch Signal Processing")
    print("=" * 60 + "\n")

    executor = SimpleExecutor()

    # Multiple signals from scanner (ES and NQ)
    signals = [
        {
            "signal_type": "LONG_ENTRY",
            "instrument": "ES 03-25",
            "price": 5850.0,
            "timestamp": datetime.now().isoformat(),
        },
        {
            "signal_type": "LONG_ENTRY",
            "instrument": "NQ 03-25",
            "price": 20500.0,
            "timestamp": datetime.now().isoformat(),
        },
    ]

    # Process batch
    orders = executor.signal_translator.process_signals_batch(signals)

    # Report results
    successful = sum(1 for o in orders if o is not None)
    print(f"\n✅ Processed {successful}/{len(signals)} signals")

    for i, order in enumerate(orders):
        if order:
            print(f"   Signal {i + 1}: {order.orderId} ({order.state})")
        else:
            print(f"   Signal {i + 1}: Failed")


def example_5_scanner_integration():
    """Example 5: How live_scanner.py would use executor."""

    print("\n" + "=" * 60)
    print("Example 5: Scanner Integration Pattern")
    print("=" * 60 + "\n")

    # This is pseudocode showing how your live_scanner.py would work

    print("Pseudocode for live_scanner.py integration:\n")

    code = """
# In live_scanner.py

from execution.simple_executor import SimpleExecutor

# Initialize once at startup
executor = SimpleExecutor()

while True:
    # 1. Fetch latest data (from Databento or other source)
    current_data = fetch_realtime_bars(["ES 03-25", "NQ 03-25"])

    # 2. Calculate indicators with best parameters
    for symbol, df in current_data.items():
        rsi = calculate_rsi(df, window=config["rsi_window"])
        macd = calculate_macd(df, ...)

        # 3. Check entry conditions
        if check_long_entry(rsi, macd, config):
            signal = {
                "signal_type": "LONG_ENTRY",
                "instrument": symbol,
                "price": df['close'].iloc[-1],
                "timestamp": df.index[-1].isoformat()
            }

            # 4. Execute via CrossTrade
            executor.execute_signal(signal)

            # 5. Log signal
            log_signal(signal)

        # Check exit conditions
        elif check_exit(current_position, rsi, macd):
            exit_signal = {
                "signal_type": "EXIT",
                "instrument": symbol,
                "timestamp": df.index[-1].isoformat()
            }
            executor.execute_signal(exit_signal)

    # Wait before next scan (1-3 minutes)
    time.sleep(180)
"""

    print(code)


def example_6_error_handling():
    """Example 6: Proper error handling."""

    print("\n" + "=" * 60)
    print("Example 6: Error Handling Best Practices")
    print("=" * 60 + "\n")

    try:
        executor = SimpleExecutor()
    except Exception as e:
        print(f"❌ Failed to initialize executor: {e}")
        print("\nTroubleshooting steps:")
        print("1. Check NT8 is running")
        print("2. Verify CrossTrade plugin is enabled")
        print("3. Confirm config/execution_config.json exists")
        print("4. Test connection: curl http://localhost:8080/accounts")
        return

    # Test with invalid signal (missing required fields)
    invalid_signal = {
        "signal_type": "LONG_ENTRY",
        # Missing "instrument" and "price"
    }

    print("Testing with invalid signal...")
    order = executor.execute_signal(invalid_signal)

    if not order:
        print("✅ Invalid signal correctly rejected")

    # Test with valid signal
    valid_signal = {
        "signal_type": "LONG_ENTRY",
        "instrument": "ES 03-25",
        "price": 5850.0,
        "timestamp": datetime.now().isoformat(),
    }

    print("\nTesting with valid signal...")
    order = executor.execute_signal(valid_signal)

    if order:
        print(f"✅ Valid signal executed: {order.orderId}")


def main():
    """Run all examples."""

    print("\n" + "=" * 60)
    print("CROSSTRADE INTEGRATION EXAMPLES")
    print("=" * 60)

    examples = [
        ("Simple Execution", example_1_simple_execution),
        ("With Position Check", example_2_with_position_check),
        ("Full Round Trip", example_3_full_round_trip),
        ("Batch Processing", example_4_batch_signals),
        ("Scanner Integration", example_5_scanner_integration),
        ("Error Handling", example_6_error_handling),
    ]

    print("\nAvailable examples:")
    for i, (name, func) in enumerate(examples, 1):
        print(f"  {i}. {name}")

    print("\nNote: These examples require:")
    print("  - NinjaTrader 8 running with CrossTrade plugin")
    print("  - Sim account configured")
    print("  - execution_config.json in config/ directory")

    choice = input("\nRun which example (1-6, or 'all')? ")

    if choice.lower() == "all":
        for name, func in examples:
            func()
    elif choice.isdigit() and 1 <= int(choice) <= len(examples):
        examples[int(choice) - 1][1]()
    else:
        print("Invalid choice")


if __name__ == "__main__":
    main()
