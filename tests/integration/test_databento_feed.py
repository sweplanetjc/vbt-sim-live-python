"""Quick test script to verify Databento feed is working."""

import os
import sys

# Add project root to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from scanner.databento_live_feed import DatabentoLiveFeed

bar_count = 0
minute_bar_count = 0


def on_bar(bar):
    """Callback for 1-minute bars."""
    global minute_bar_count
    minute_bar_count += 1
    if minute_bar_count % 10 == 0:
        print(
            f"Received {minute_bar_count} 1-minute bars (latest: {bar['symbol']} @ {bar['close']:.2f})"
        )


# Get API key from environment
api_key = os.getenv("DATABENTO_API_KEY")
if not api_key:
    print("ERROR: DATABENTO_API_KEY environment variable not set")
    sys.exit(1)

# Configure feed with just ES and NQ
config = {
    "api_key": api_key,
    "dataset": "GLBX.MDP3",
    "symbols": ["ES.c.0", "NQ.c.0"],  # Continuous symbols (like old implementation)
    "schema": "ohlcv-1s",
    "replay_hours": 24,
}

print("Starting Databento feed test...")
print(f"Symbols: {config['symbols']}")
print(f"Schema: {config['schema']}")
print("=" * 80)

try:
    feed = DatabentoLiveFeed(config, on_bar_callback=on_bar)
    feed.start()
except KeyboardInterrupt:
    print(f"\n\nTest stopped. Received {minute_bar_count} 1-minute bars total.")
except Exception as e:
    print(f"Error: {e}")
    import traceback

    traceback.print_exc()
