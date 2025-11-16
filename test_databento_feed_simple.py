#!/usr/bin/env python3
"""
Simple test script for Databento live feed without VectorBT dependency.
Tests just the feed and bar aggregation.
"""

import os
import sys
from datetime import datetime

import pytz


# Simple mock for TFs enum since we can't import vbt_sim_live
class TFsMock:
    def __init__(self, value):
        self.value = value

    def is_intraday(self):
        return True


class TFs:
    m1 = TFsMock(60)
    m5 = TFsMock(300)


# Patch the import before loading our modules
sys.modules["vbt_sim_live"] = type(sys)("vbt_sim_live")
sys.modules["vbt_sim_live"].TFs = TFs

# Now we can import our modules
from scanner.bar_aggregator import BarAggregator
from scanner.databento_live_feed import DatabentoLiveFeed


def main():
    """Test Databento feed with historical replay."""

    # Check for API key
    api_key = os.getenv("DATABENTO_API_KEY")
    if not api_key:
        print("ERROR: DATABENTO_API_KEY environment variable not set")
        print("\nSet it with:")
        print("  export DATABENTO_API_KEY='your_key_here'")
        sys.exit(1)

    print("=" * 80)
    print("DATABENTO LIVE FEED TEST")
    print("=" * 80)
    print(f"API Key: {api_key[:8]}...{api_key[-4:]}")
    print(f"Testing with last 96 hours (4 days) of ES.c.0 trading data")
    print("=" * 80)
    print()

    # Stats tracking
    bar_count = 0
    symbol_bars = {}
    aggregated_bars = {}

    # Create bar aggregator for ES 5-min bars
    agg_es_m5 = BarAggregator(symbol="ES.c.0", target_tf=TFs.m5)

    def on_bar(bar):
        """Callback for each 1-min bar."""
        nonlocal bar_count, symbol_bars, aggregated_bars

        bar_count += 1
        symbol = bar["symbol"]
        symbol_bars[symbol] = symbol_bars.get(symbol, 0) + 1

        # Print every 10th bar
        if bar_count % 10 == 0:
            print(
                f"[{bar_count:4d}] {bar['date']} | {symbol:8s} | "
                f"O:{bar['open']:7.2f} H:{bar['high']:7.2f} "
                f"L:{bar['low']:7.2f} C:{bar['close']:7.2f} V:{bar['volume']:6d}"
            )

        # Test bar aggregation for ES
        if symbol == "ES.c.0":
            completed = agg_es_m5.add_bar(bar)
            if completed:
                aggregated_bars["m5"] = aggregated_bars.get("m5", 0) + 1
                print(f"\n>>> COMPLETED 5-MIN BAR:")
                print(f"    Date: {completed['date']}")
                print(
                    f"    O:{completed['open']:7.2f} H:{completed['high']:7.2f} "
                    f"L:{completed['low']:7.2f} C:{completed['close']:7.2f} "
                    f"V:{completed['volume']:6d}\n"
                )

    # Configure feed
    config = {
        "api_key": api_key,
        "dataset": "GLBX.MDP3",
        "schema": "ohlcv-1m",
        "symbols": ["ES.c.0"],  # Just ES for quick test
        "replay_hours": 96,  # 96 hours (4 days) to go back past weekend
    }

    print(f"Starting feed at {datetime.now(pytz.UTC)}")
    print("Press Ctrl+C to stop\n")

    # Create and start feed
    feed = DatabentoLiveFeed(config, on_bar)

    try:
        feed.start()  # Blocking call
    except KeyboardInterrupt:
        print("\n\nCtrl+C received, stopping...")
        feed.stop()

    # Print summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total 1-min bars: {bar_count}")
    print(f"Bars per symbol:")
    for sym, count in symbol_bars.items():
        print(f"  {sym}: {count}")
    print(f"\nAggregated bars:")
    for tf, count in aggregated_bars.items():
        print(f"  {tf}: {count}")
    print("=" * 80)


if __name__ == "__main__":
    main()
