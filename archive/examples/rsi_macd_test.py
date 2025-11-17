"""
Phase 2: Multi-indicator with real-time incomplete bars (CORRECTED)
Combines RSI + MACD, checks at every base timeframe bar

CORRECTIONS:
- Loads from Parquet files
- Uses correct VectorBT Pro API (window parameters, .rsi/.macd attributes)
"""

import os

import pandas as pd
import vectorbtpro as vbt
from dotenv import load_dotenv

load_dotenv()

# ===== CONFIGURATION =====
SYMBOL = "ES"
DATA_DIR = "data/raw"
START_DATE = "2025-01-01"
END_DATE = "2025-10-31"
BASE_TF = "1h"
HIGHER_TF = "4h"

# ===== DATA LOADING =====
print("Loading data from Parquet...")
try:
    parquet_file = f"{DATA_DIR}/{SYMBOL}_ohlcv_1m.parquet"
    df = pd.read_parquet(parquet_file)
    print(f"✓ Loaded {len(df)} rows from {parquet_file}")

    # Resample to base timeframe
    if BASE_TF != "1m":
        print(f"Resampling to {BASE_TF}...")
        df = (
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

    # Filter date range
    df = df.loc[START_DATE:END_DATE]
    print(f"✓ {len(df)} bars from {START_DATE} to {END_DATE}")

    # Convert to VectorBT
    data = vbt.Data.from_data(df)
    print(f"✓ Ready for optimization\n")

except FileNotFoundError:
    print(f"✗ Error: {parquet_file} not found")
    print("   Run fetch_databento_data.py first")
    exit(1)


# ===== STRATEGY DEFINITION =====
@vbt.parameterized(merge_func="concat")
def backtest_rsi_macd_mtf(
    data,
    rsi_window,
    macd_fast_window,
    macd_slow_window,
    macd_signal_window,
    rsi_threshold_low,
    rsi_threshold_high,
    macd_threshold,
):
    """
    Multi-indicator strategy with real-time incomplete higher timeframe

    Entry conditions (ALL must be true):
    - 1h RSI < threshold_low (base TF oversold)
    - 4h RSI < threshold_low (higher TF also oversold)
    - 4h MACD positive (higher TF bullish momentum)

    Exit conditions (ANY can trigger):
    - 1h RSI > threshold_high (base TF overbought)
    - 4h RSI > threshold_high (higher TF overbought)
    - 4h MACD negative (higher TF bearish momentum)
    """

    close_base = data.close

    # === Step 1: Upsample to higher timeframe ===
    close_high = close_base.vbt.resample_apply(HIGHER_TF, vbt.nb.last_reduce_nb)

    # === Step 2: Calculate indicators ===
    # Base timeframe (1h)
    rsi_base = vbt.RSI.run(close_base, window=rsi_window).rsi

    # Higher timeframe (4h) - INCOMPLETE bars
    rsi_high = vbt.RSI.run(close_high, window=rsi_window).rsi

    macd_high = vbt.MACD.run(
        close_high,
        fast_window=macd_fast_window,
        slow_window=macd_slow_window,
        signal_window=macd_signal_window,
    )
    macd_line = macd_high.macd

    # === Step 3: Realign higher TF to base TF (NO .fshift) ===
    resampler = vbt.Resampler(
        source_index=rsi_high.index,
        target_index=close_base.index,
        source_freq=HIGHER_TF,
        target_freq=BASE_TF,
    )

    rsi_high_aligned = rsi_high.vbt.realign_opening(resampler)
    macd_aligned = macd_line.vbt.realign_opening(resampler)

    # === Step 4: Entry/Exit signals ===
    entries = (
        (rsi_base < rsi_threshold_low)
        & (rsi_high_aligned < rsi_threshold_low)
        & (macd_aligned > macd_threshold)
    )

    exits = (
        (rsi_base > rsi_threshold_high)
        | (rsi_high_aligned > rsi_threshold_high)
        | (macd_aligned < -macd_threshold)
    )

    # === Step 5: Backtest ===
    pf = vbt.Portfolio.from_signals(
        close_base, entries, exits, direction="both", freq=BASE_TF
    )

    return pf.total_return


# ===== RUN OPTIMIZATION =====
print("=" * 80)
print(f"MULTI-INDICATOR OPTIMIZATION: {SYMBOL} ({BASE_TF} base, {HIGHER_TF} MTF)")
print("=" * 80)

print("\nParameter ranges:")
print("  RSI window: [10, 12, 14, 16]")
print("  MACD fast: [5, 8, 12]")
print("  MACD slow: [26, 28, 30]")
print("  MACD signal: [8, 9, 10]")
print("  RSI threshold low: [20, 25, 30]")
print("  RSI threshold high: [65, 70, 75]")
print("  MACD threshold: [0.0, 0.0001]")

total_combos = 4 * 3 * 3 * 3 * 3 * 3 * 2
print(f"\nTotal combinations: {total_combos}")
print("Running optimization (5-10 minutes)...\n")

results = backtest_rsi_macd_mtf(
    data,
    rsi_window=vbt.Param([10, 12, 14, 16]),
    macd_fast_window=vbt.Param([5, 8, 12]),
    macd_slow_window=vbt.Param([26, 28, 30]),
    macd_signal_window=vbt.Param([8, 9, 10]),
    rsi_threshold_low=vbt.Param([20, 25, 30]),
    rsi_threshold_high=vbt.Param([65, 70, 75]),
    macd_threshold=vbt.Param([0.0, 0.0001]),
)

print(f"✓ Optimization complete!\n")

# ===== RESULTS ANALYSIS =====
print("=" * 80)
print("TOP 15 RESULTS (by total return)")
print("=" * 80)

top_results = results.nlargest(15)
print(top_results)

# ===== SAVE RESULTS =====
results_sorted = results.sort_values(ascending=False)
results_sorted.to_csv(f"optimization_{SYMBOL}_{BASE_TF}_{HIGHER_TF}.csv")

print(f"\n✓ Full results saved to optimization_{SYMBOL}_{BASE_TF}_{HIGHER_TF}.csv")

# ===== SUMMARY STATS =====
print("\n" + "=" * 80)
print("SUMMARY STATISTICS")
print("=" * 80)

print(f"Mean return: {results.mean():.4f}")
print(f"Median return: {results.median():.4f}")
print(f"Std deviation: {results.std():.4f}")
print(f"Min return: {results.min():.4f}")
print(f"Max return: {results.max():.4f}")
print(f"% Positive: {(results > 0).mean() * 100:.1f}%")

print("\n✓ PHASE 2 COMPLETE")
