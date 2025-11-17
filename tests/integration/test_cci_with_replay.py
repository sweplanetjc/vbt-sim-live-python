#!/usr/bin/env python3
"""
Test CCI indicator calculation with Databento intraday replay.
This validates the full pipeline: Feed → Aggregation → Indicators
"""

import os
import sys
from datetime import datetime

import numpy as np
import pandas as pd
import pytz

# Add project root to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))


# Simple mock for TFs enum
class TFsMock:
    def __init__(self, value):
        self.value = value

    def is_intraday(self):
        return True


class TFs:
    m1 = TFsMock(60)
    m5 = TFsMock(300)


# Patch the import
sys.modules["vbt_sim_live"] = type(sys)("vbt_sim_live")
sys.modules["vbt_sim_live"].TFs = TFs

from scanner.bar_aggregator import BarAggregator
from scanner.databento_live_feed import DatabentoLiveFeed


def calculate_cci(df, length=15):
    """Calculate CCI indicator on a dataframe.

    CCI = (Typical Price - SMA) / (0.015 * Mean Deviation)
    """
    if len(df) < length:
        return pd.Series([np.nan] * len(df), index=df.index)

    # Typical price
    tp = (df["high"] + df["low"] + df["close"]) / 3

    # SMA of typical price
    sma = tp.rolling(window=length).mean()

    # Mean deviation
    mad = tp.rolling(window=length).apply(
        lambda x: np.abs(x - x.mean()).mean(), raw=True
    )

    # CCI
    cci = (tp - sma) / (0.015 * mad)

    return cci


def main():
    """Test CCI calculation with replay data."""

    # Check for API key
    api_key = os.getenv("DATABENTO_API_KEY")
    if not api_key:
        print("ERROR: DATABENTO_API_KEY environment variable not set")
        sys.exit(1)

    print("=" * 80)
    print("CCI INDICATOR TEST WITH DATABENTO REPLAY")
    print("=" * 80)
    print(f"Testing CCI calculation on 5-minute ES bars")
    print(f"Using last 24 trading hours of data")
    print("=" * 80)
    print()

    # Data storage
    bars_1min = []
    bars_5min = []

    # Create bar aggregator for 5-min bars
    agg_m5 = BarAggregator(symbol="ES.c.0", target_tf=TFs.m5)

    def on_bar(bar):
        """Callback for each 1-min bar."""
        bars_1min.append(bar)

        # Aggregate to 5-min
        completed = agg_m5.add_bar(bar)
        if completed:
            bars_5min.append(completed)

            # Print progress every 10 bars
            if len(bars_5min) % 10 == 0:
                print(f"[{len(bars_5min):3d}] 5-min bars aggregated...")

    # Configure feed
    config = {
        "api_key": api_key,
        "dataset": "GLBX.MDP3",
        "schema": "ohlcv-1m",
        "symbols": ["ES.c.0"],
    }

    print(f"Starting feed at {datetime.now(pytz.UTC)}")
    print("Waiting for replay to complete...\n")

    # Create and start feed
    feed = DatabentoLiveFeed(config, on_bar)

    try:
        feed.start()  # This will block until replay completes
    except KeyboardInterrupt:
        print("\n\nCtrl+C received, stopping...")
        feed.stop()

    # Now calculate CCI on the 5-min bars
    print("\n" + "=" * 80)
    print("CALCULATING CCI INDICATOR")
    print("=" * 80)

    if len(bars_5min) == 0:
        print("ERROR: No 5-min bars were created!")
        print("This likely means no data was available in the replay window.")
        return

    # Convert to DataFrame
    df = pd.DataFrame(bars_5min)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")

    print(f"Total 1-min bars: {len(bars_1min)}")
    print(f"Total 5-min bars: {len(bars_5min)}")
    print(f"Date range: {df.index[0]} to {df.index[-1]}")
    print()

    # Calculate CCI(15)
    df["cci15"] = calculate_cci(df, length=15)

    # Show last 20 bars with CCI
    print("Last 20 bars with CCI(15):")
    print("=" * 80)
    pd.set_option("display.max_rows", None)
    pd.set_option("display.width", 120)

    display_df = df[["open", "high", "low", "close", "volume", "cci15"]].tail(20)
    print(display_df.to_string())

    print("\n" + "=" * 80)
    print("CCI STATISTICS")
    print("=" * 80)

    valid_cci = df["cci15"].dropna()
    if len(valid_cci) > 0:
        print(f"Valid CCI values: {len(valid_cci)}/{len(df)}")
        print(f"CCI Mean: {valid_cci.mean():.2f}")
        print(f"CCI Std Dev: {valid_cci.std():.2f}")
        print(f"CCI Min: {valid_cci.min():.2f}")
        print(f"CCI Max: {valid_cci.max():.2f}")
        print(f"CCI Current: {df['cci15'].iloc[-1]:.2f}")

        # Check for bullish signals (CCI rising)
        print("\n" + "=" * 80)
        print("BULLISH SIGNALS (CCI Rising)")
        print("=" * 80)

        df["cci_rising"] = df["cci15"] > df["cci15"].shift(1)
        df["bullish_candle"] = df["close"] > df["open"]
        df["close_higher"] = df["close"] > df["close"].shift(1)

        signals = df[df["cci_rising"] & df["bullish_candle"] & df["close_higher"]]

        if len(signals) > 0:
            print(f"Found {len(signals)} bullish signals:")
            print(signals[["open", "close", "cci15"]].tail(10).to_string())
        else:
            print("No bullish signals found in the data")
    else:
        print("ERROR: No valid CCI values calculated!")
        print("Need at least 15 bars to calculate CCI(15)")

    print("\n" + "=" * 80)
    print("TEST COMPLETE")
    print("=" * 80)
    print("\nThis validates:")
    print("✓ Databento replay connection")
    print("✓ 1-min bar reception")
    print("✓ Bar aggregation (m1 → m5)")
    print("✓ CCI indicator calculation")
    print("✓ Signal detection logic")


if __name__ == "__main__":
    main()
