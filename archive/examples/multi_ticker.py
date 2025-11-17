"""
Phase 3: Multi-symbol optimization (CORRECTED)
Find parameters that work across ES and NQ (avoid overfitting)

CORRECTIONS:
- Loads from Parquet files
- Uses correct VectorBT Pro API
"""

import json
import os

import pandas as pd
import vectorbtpro as vbt
from dotenv import load_dotenv

load_dotenv()


# ===== HELPER FUNCTION =====
def load_symbol_data(symbol, data_dir, base_tf, start_date, end_date):
    """Load and prepare symbol data from Parquet"""
    parquet_file = f"{data_dir}/{symbol}_ohlcv_1m.parquet"
    df = pd.read_parquet(parquet_file)

    if base_tf != "1m":
        df = (
            df.resample(base_tf)
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

    df = df.loc[start_date:end_date]
    return vbt.Data.from_data(df)


# ===== STRATEGY DEFINITION =====
def get_strategy_function(base_tf, higher_tf):
    """Returns the multi-indicator strategy function"""

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
        close_base = data.close

        # Upsample (incomplete bars)
        close_high = close_base.vbt.resample_apply(higher_tf, vbt.nb.last_reduce_nb)

        # Indicators
        rsi_base = vbt.RSI.run(close_base, window=rsi_window).rsi
        rsi_high = vbt.RSI.run(close_high, window=rsi_window).rsi

        macd_high = vbt.MACD.run(
            close_high,
            fast_window=macd_fast_window,
            slow_window=macd_slow_window,
            signal_window=macd_signal_window,
        )
        macd_line = macd_high.macd

        # Realign (NO .fshift)
        resampler = vbt.Resampler(
            source_index=rsi_high.index,
            target_index=close_base.index,
            source_freq=higher_tf,
            target_freq=base_tf,
        )

        rsi_high_aligned = rsi_high.vbt.realign_opening(resampler)
        macd_aligned = macd_line.vbt.realign_opening(resampler)

        # Signals
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

        # Backtest
        pf = vbt.Portfolio.from_signals(
            close_base, entries, exits, direction="both", freq=base_tf
        )

        return pf.total_return

    return backtest_rsi_macd_mtf


# ===== CONFIGURATION =====
SYMBOLS = ["ES", "NQ"]
DATA_DIR = "data/raw"
START_DATE = "2025-01-01"
END_DATE = "2025-10-31"
BASE_TF = "1h"
HIGHER_TF = "4h"

PARAM_RANGES = {
    "rsi_window": [10, 12, 14, 16],
    "macd_fast_window": [5, 8, 12],
    "macd_slow_window": [26, 28, 30],
    "macd_signal_window": [8, 9, 10],
    "rsi_threshold_low": [20, 25, 30],
    "rsi_threshold_high": [65, 70, 75],
    "macd_threshold": [0.0, 0.0001],
}

all_results = {}

# ===== OPTIMIZE EACH SYMBOL =====
for symbol in SYMBOLS:
    print("=" * 80)
    print(f"OPTIMIZING {symbol}")
    print("=" * 80)

    print(f"\nLoading {symbol} data...")
    try:
        data = load_symbol_data(symbol, DATA_DIR, BASE_TF, START_DATE, END_DATE)
        print(f"✓ Loaded {len(data.close)} bars\n")
    except FileNotFoundError:
        print(f"✗ Error: {DATA_DIR}/{symbol}_ohlcv_1m.parquet not found")
        print("   Run fetch_databento_data.py first")
        exit(1)

    print(f"Running optimization for {symbol}...")

    backtest_func = get_strategy_function(BASE_TF, HIGHER_TF)

    results = backtest_func(
        data,
        rsi_window=vbt.Param(PARAM_RANGES["rsi_window"]),
        macd_fast_window=vbt.Param(PARAM_RANGES["macd_fast_window"]),
        macd_slow_window=vbt.Param(PARAM_RANGES["macd_slow_window"]),
        macd_signal_window=vbt.Param(PARAM_RANGES["macd_signal_window"]),
        rsi_threshold_low=vbt.Param(PARAM_RANGES["rsi_threshold_low"]),
        rsi_threshold_high=vbt.Param(PARAM_RANGES["rsi_threshold_high"]),
        macd_threshold=vbt.Param(PARAM_RANGES["macd_threshold"]),
    )

    all_results[symbol] = results

    # Save individual symbol results (sorted)
    results_sorted = results.sort_values(ascending=False)
    results_sorted.to_csv(f"optimization_{symbol}_{BASE_TF}_{HIGHER_TF}.csv")
    print(f"✓ {symbol} optimization complete")
    print(f"  Best: {results.max():.4f}")
    print(f"  Mean: {results.mean():.4f}\n")

# ===== COMPARISON =====
print("=" * 80)
print("CROSS-SYMBOL COMPARISON")
print("=" * 80)

for symbol, results in all_results.items():
    print(f"{symbol} - Best: {results.max():.4f}, Mean: {results.mean():.4f}")

print("\n" + "-" * 80)
print("Top 10 for each symbol:")
print("-" * 80)

for symbol in SYMBOLS:
    print(f"\n{symbol} Top 10:")
    print(all_results[symbol].nlargest(10))

# ===== ROBUSTNESS ANALYSIS =====
print("\n" + "=" * 80)
print("ROBUSTNESS ANALYSIS")
print("=" * 80)

# Load as DataFrames for easier manipulation
es_df = pd.read_csv(f"optimization_ES_{BASE_TF}_{HIGHER_TF}.csv", index_col=0)
nq_df = pd.read_csv(f"optimization_NQ_{BASE_TF}_{HIGHER_TF}.csv", index_col=0)

# Average results across symbols (most robust parameters)
combined = (es_df + nq_df) / 2
# Get the column name (should be the first/only column with return values)
col_name = combined.columns[0]
combined_sorted = combined.sort_values(by=col_name, ascending=False)

print("\nBest 10 AVERAGED across ES and NQ (most robust):")
print(combined_sorted.head(10))

# Save combined results
combined_sorted.to_csv(f"optimization_combined_{BASE_TF}_{HIGHER_TF}.csv")
print(f"\n✓ Combined results saved to optimization_combined_{BASE_TF}_{HIGHER_TF}.csv")

# ===== EXTRACT BEST PARAMETERS =====
print("\n" + "=" * 80)
print("BEST PARAMETERS EXTRACTION")
print("=" * 80)

# Get best parameter set (averaged across symbols)
best_row = combined_sorted.iloc[0]
best_idx = combined_sorted.index[0]

print("\nBest parameter combination (robust across ES and NQ):")
print(f"  Combined return: {best_row.values[0]:.4f}")

# Extract parameter names from index
param_names = [
    "rsi_window",
    "macd_fast_window",
    "macd_slow_window",
    "macd_signal_window",
    "rsi_threshold_low",
    "rsi_threshold_high",
    "macd_threshold",
]

print("\nParameter values:")
# Check if best_idx is a tuple (MultiIndex) or needs parsing
if isinstance(best_idx, tuple):
    for i, name in enumerate(param_names):
        print(f"  {name}: {best_idx[i]}")
else:
    # Index might be a string representation, just print it
    print(f"  Index: {best_idx}")
    print("  Note: Check the CSV file structure to extract individual parameter values")

# Save to JSON for live trading
best_params_json = {
    "description": "Best parameters from multi-symbol optimization (ES + NQ)",
    "base_timeframe": BASE_TF,
    "higher_timeframe": HIGHER_TF,
    "symbols_tested": SYMBOLS,
    "date_range": f"{START_DATE} to {END_DATE}",
    "combined_return": float(best_row.values[0]),
}

# Only add parameters if index is a tuple
if isinstance(best_idx, tuple):
    best_params_json["parameters"] = {
        "rsi_window": int(best_idx[0]),
        "macd_fast_window": int(best_idx[1]),
        "macd_slow_window": int(best_idx[2]),
        "macd_signal_window": int(best_idx[3]),
        "rsi_threshold_low": int(best_idx[4]),
        "rsi_threshold_high": int(best_idx[5]),
        "macd_threshold": float(best_idx[6]),
    }
else:
    best_params_json["parameters"] = "Check CSV file for parameter structure"

with open("best_params.json", "w") as f:
    json.dump(best_params_json, f, indent=2)

print("\n✓ Best parameters saved to best_params.json")

# ===== TOP 5 ALTERNATIVES =====
print("\n" + "=" * 80)
print("TOP 5 ALTERNATIVE PARAMETER SETS")
print("=" * 80)

top_5 = combined_sorted.head(5)
for i, (idx, row) in enumerate(top_5.iterrows(), 1):
    print(f"\nRank {i}: Return = {row.iloc[0]:.4f}")
    if isinstance(idx, tuple):
        for j, name in enumerate(param_names):
            print(f"  {name}: {idx[j]}")
    else:
        print(f"  Index: {idx}")

print("\n" + "=" * 80)
print("✓ PHASE 3 COMPLETE")
print("=" * 80)
print("\nNext steps:")
print("1. Review best_params.json")
print("2. Implement live scanner with these parameters")
print("3. Paper trade for 2-4 weeks before going live")
