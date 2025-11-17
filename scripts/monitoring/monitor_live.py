"""Live monitoring script - shows real-time bars and prices."""

import os
import sys
from datetime import datetime

# Add project root to path for module imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from scanner.databento_live_feed import DatabentoLiveFeed

# Track latest values
latest_1min_bars = {}
bar_counts = {"1s": 0, "1m": 0}


def on_1min_bar(bar):
    """Callback for 1-minute bars."""
    bar_counts["1m"] += 1
    symbol = bar["symbol"]
    latest_1min_bars[symbol] = bar

    # Print every 1-minute bar
    print(f"\n{'=' * 80}")
    print(f"⏰ 1-MINUTE BAR #{bar_counts['1m']}")
    print(f"{'=' * 80}")
    print(f"Symbol:     {symbol}")
    print(f"Time:       {bar['date']}")
    print(f"Open:       {bar['open']:.2f}")
    print(f"High:       {bar['high']:.2f}")
    print(f"Low:        {bar['low']:.2f}")
    print(f"Close:      {bar['close']:.2f}")
    print(f"Volume:     {bar['volume']}")
    print(f"{'=' * 80}")


# Get API key from environment
api_key = os.environ.get("DATABENTO_API_KEY")
if not api_key:
    raise ValueError(
        "DATABENTO_API_KEY environment variable not set. "
        "Please set it before running: export DATABENTO_API_KEY='your-key'"
    )

# Configure symbols - just ES and NQ for clarity
symbols = ["ES.c.0", "NQ.c.0"]
dataset = "GLBX.MDP3"
replay_hours = 24

print("=" * 80)
print("LIVE MARKET DATA MONITOR")
print("=" * 80)
print(f"Symbols: {symbols}")
print(f"Started: {datetime.now()}")
print("=" * 80)
print("\nWaiting for 1-minute bars...\n")

try:
    feed = DatabentoLiveFeed(
        api_key=api_key,
        dataset=dataset,
        symbols=symbols,
        schema="ohlcv-1s",
        replay_hours=replay_hours,
        on_1min_bar=on_1min_bar,
    )
    feed.start()  # Blocking
except KeyboardInterrupt:
    print(f"\n\n{'=' * 80}")
    print("STOPPED - Summary:")
    print(f"  Total 1-minute bars received: {bar_counts['1m']}")
    print(f"{'=' * 80}")
