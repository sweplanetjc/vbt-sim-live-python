"""
Phase 1 PoC: RSI with real-time incomplete higher timeframe bars

CORRECTED VERSION:
- Loads from Parquet files (Databento data)
- Uses correct VectorBT Pro API (window instead of timeperiod)
"""

import os

import numpy as np
import pandas as pd
import vectorbtpro as vbt
from dotenv import load_dotenv

load_dotenv()

# ===== CONFIGURATION =====
SYMBOL = "ES"
DATA_DIR = "data/raw"  # Directory with Parquet files
START_DATE = "2025-01-01"
END_DATE = "2025-10-31"
BASE_TF = "1h"  # Base data frequency (check signals here)
HIGHER_TF = "4h"  # Higher timeframe for trend confirmation

# ===== DATA LOADING FROM PARQUET =====
print("Loading data from Parquet...")
try:
    # Load Parquet file
    parquet_file = f"{DATA_DIR}/{SYMBOL}_ohlcv_1m.parquet"
    df = pd.read_parquet(parquet_file)

    print(f"✓ Loaded {len(df)} rows from {parquet_file}")

    # Resample to base timeframe if needed (1m -> 1h)
    if BASE_TF != "1m":
        print(f"Resampling from 1m to {BASE_TF}...")
        df_resampled = (
            df.resample(BASE_TF)
            .agg(
                {
                    "open": "first",
                    "high": "max",
                    "low": "min",
                    "close": "last",
                    "volume": "sum",
                }
            )
            .dropna()
        )
        df = df_resampled
        print(f"✓ Resampled to {len(df)} {BASE_TF} bars")

    # Filter date range
    df = df.loc[START_DATE:END_DATE]
    print(f"✓ Filtered to {len(df)} bars ({START_DATE} to {END_DATE})")

    # Convert to VectorBT data format
    data = vbt.Data.from_data(df)
    print(f"✓ Converted to VectorBT format\n")

except FileNotFoundError:
    print(f"✗ Error: Could not find {parquet_file}")
    print(f"   Please run the Databento fetch script first")
    exit(1)
except Exception as e:
    print(f"✗ Error loading data: {e}")
    exit(1)


# ===== BASELINE: Single Timeframe RSI =====
@vbt.parameterized(merge_func="concat")
def backtest_rsi_single_tf(data, rsi_window, threshold_low, threshold_high):
    """
    Baseline: RSI only on base timeframe (1h)
    No multi-timeframe confirmation

    Note: VectorBT Pro uses 'window' parameter, not 'timeperiod'
    """
    close = data.close

    # Calculate RSI on 1h (using window parameter)
    rsi = vbt.RSI.run(close, window=rsi_window).rsi

    # Signals
    entries = rsi < threshold_low
    exits = rsi > threshold_high

    # Backtest
    pf = vbt.Portfolio.from_signals(
        close, entries, exits, direction="both", freq=BASE_TF
    )

    return pf.total_return


print("=" * 80)
print("BASELINE TEST: RSI on 1h timeframe only")
print("=" * 80)

baseline_results = backtest_rsi_single_tf(
    data,
    rsi_window=vbt.Param([10, 12, 14, 16]),
    threshold_low=vbt.Param([20, 25, 30]),
    threshold_high=vbt.Param([65, 70, 75]),
)

print(f"\nTotal combos tested: {len(baseline_results)}")
print(f"Best 5 results:")
print(baseline_results.nlargest(5))

baseline_results.to_csv("baseline_1h_only.csv")
print("\n✓ Baseline results saved\n")


# ===== MULTI-TIMEFRAME: Real-Time Incomplete Bars =====
@vbt.parameterized(merge_func="concat")
def backtest_rsi_mtf_realtime(data, rsi_window, threshold_low, threshold_high):
    """
    Multi-timeframe with REAL-TIME incomplete 4h bars

    Key principle:
    - Check at EVERY 1h bar close
    - Use current 4h RSI value (incomplete/forming)
    - NO .fshift(1) - immediate action when conditions align
    """
    close_1h = data.close

    # === Step 1: Upsample to 4h (INCOMPLETE bars) ===
    # last_reduce_nb = use current close price (forming bar)
    close_4h = close_1h.vbt.resample_apply(HIGHER_TF, vbt.nb.last_reduce_nb)

    # === Step 2: Calculate indicators ===
    # 1h RSI (normal)
    rsi_1h = vbt.RSI.run(close_1h, window=rsi_window).rsi

    # 4h RSI (on incomplete bars - updates every hour!)
    rsi_4h = vbt.RSI.run(close_4h, window=rsi_window).rsi

    # === Step 3: Realign 4h to 1h (NO .fshift) ===
    # We want the CURRENT 4h value at each 1h bar
    resampler = vbt.Resampler(
        source_index=rsi_4h.index,
        target_index=close_1h.index,
        source_freq=HIGHER_TF,
        target_freq=BASE_TF,
    )
    rsi_4h_on_1h = rsi_4h.vbt.realign_opening(resampler)

    # === Step 4: Entry logic - Both must be bullish ===
    # At every 1h bar, check if:
    # - 1h RSI < threshold (short-term oversold)
    # - Current 4h RSI < threshold (higher TF also oversold)
    # === Step 4: Entry logic - REVISED ===
    # Entry: 1h oversold + 4h not extreme
    entries = (rsi_1h < threshold_low) & (rsi_4h_on_1h < 65)

    # Exit: Either overbought
    exits = (rsi_1h > threshold_high) | (rsi_4h_on_1h > 75)

    # === Step 5: Backtest ===
    pf = vbt.Portfolio.from_signals(
        close_1h, entries, exits, direction="both", freq=BASE_TF
    )

    return pf.total_return


print("=" * 80)
print("MULTI-TIMEFRAME TEST: Real-time incomplete 4h bars")
print("=" * 80)
print(f"Strategy: Check at EVERY {BASE_TF} bar using current {HIGHER_TF} value")
print("Processing...\n")

mtf_results = backtest_rsi_mtf_realtime(
    data,
    rsi_window=vbt.Param([10, 12, 14, 16]),
    threshold_low=vbt.Param([20, 25, 30]),
    threshold_high=vbt.Param([65, 70, 75]),
)

print(f"Total combos tested: {len(mtf_results)}")
print(f"Best 5 results:")
print(mtf_results.nlargest(5))

mtf_results.to_csv("mtf_4h_realtime.csv")
print("\n✓ MTF results saved\n")

# ===== COMPARISON =====
print("=" * 80)
print("COMPARISON: Baseline vs Multi-Timeframe")
print("=" * 80)

baseline_best = baseline_results.max()
mtf_best = mtf_results.max()

print(f"\nBaseline (1h only) best: {baseline_best:.4f}")
print(f"MTF (real-time 4h) best: {mtf_best:.4f}")
print(f"Improvement: {(mtf_best - baseline_best):.4f}")

if mtf_best > baseline_best:
    print("\n✓ Multi-timeframe confirmation improves results!")
else:
    print("\n⚠ Baseline performs better - review signal logic")

print("\n" + "=" * 80)
print("PHASE 1 COMPLETE")
print("=" * 80)
