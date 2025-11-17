"""Quick test to verify symbol mapping is working."""

import os
import sys

# Add project root to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from scanner.databento_live_feed import DatabentoLiveFeed

received_bars = []


def on_bar(bar):
    """Callback for 1-minute bars."""
    received_bars.append(bar)
    print(
        f"✓ Got 1-minute bar: {bar['symbol']} @ {bar['close']:.2f} (time: {bar['date']})"
    )


# Set API key
os.environ["DATABENTO_API_KEY"] = "db-i9rsBy5Wk96eJNHG6LfLGSHeba87Y"

# Configure feed
config = {
    "api_key": os.environ["DATABENTO_API_KEY"],
    "dataset": "GLBX.MDP3",
    "symbols": ["ES.c.0", "NQ.c.0"],
    "schema": "ohlcv-1s",
    "replay_hours": 24,
}

print("Testing symbol mapping fix...")
print("=" * 80)
print("Waiting for 1-minute bars (this takes at least 60 seconds)...")
print("=" * 80)

try:
    feed = DatabentoLiveFeed(config, on_bar_callback=on_bar)

    # Run for a limited time
    import threading
    import time

    def run_feed():
        try:
            feed.start()
        except:
            pass

    thread = threading.Thread(target=run_feed, daemon=True)
    thread.start()

    # Wait 2 minutes
    time.sleep(120)

    print("\n" + "=" * 80)
    print(f"Test complete! Received {len(received_bars)} 1-minute bars:")
    for bar in received_bars[:5]:  # Show first 5
        print(f"  - {bar['symbol']}: {bar['close']:.2f}")
    print("=" * 80)

except Exception as e:
    print(f"Error: {e}")
    import traceback

    traceback.print_exc()
