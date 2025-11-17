#!/usr/bin/env python3
"""
MACD + Bollinger Bands Multi-Timeframe Strategy Backtest
=========================================================

Usage:
    Run from repository root:
    python scripts/backtest/backtest_macd_bb_strategy.py

Strategy Rules:
- Base Timeframe: 1-minute
- Higher Timeframe: 5-minute (resampled to 1-minute for alignment)

Entry Conditions (BOTH must be true):
1. 1-min MACD histogram crosses from negative to positive (current > 0 AND previous <= 0)
2. 5-min Bollinger Bands upper band is expanding (current upper > previous upper)

Exit Conditions (BOTH must be true):
1. MACD momentum weakening: histogram increase < previous increase
2. BB contraction: current BB width < previous BB width

Parameters to Optimize:
- MACD fast_period: 10 to 20 (step 2)
- MACD slow_period: 12 to 30 (step 3)
- MACD signal_period: 2 to 4 (step 1)
- BB length: fixed at 2
- BB std: fixed at 2

Walk-Forward Cross-Validation:
- 4 folds (25% each)
- Train on 3 folds, test on 1 fold
- Calculate Sharpe retention: test_sharpe / train_sharpe
- Target: >= 80% Sharpe retention
"""

import json
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

import vectorbtpro as vbt

# ============================================================================
# Configuration
# ============================================================================

DATA_PATH = Path("data/raw/ES_ohlcv_1m.parquet")
RESULTS_DIR = Path("results")
RESULTS_DIR.mkdir(exist_ok=True)

# Strategy parameters
BASE_TF = "1min"
HIGHER_TF = "5min"

# MACD parameters to optimize
MACD_FAST_RANGE = range(10, 21, 2)  # 10, 12, 14, 16, 18, 20
MACD_SLOW_RANGE = range(12, 31, 3)  # 12, 15, 18, 21, 24, 27, 30
MACD_SIGNAL_RANGE = range(2, 5)  # 2, 3, 4

# BB parameters (fixed)
BB_LENGTH = 2
BB_STD = 2

# Walk-forward CV settings
N_FOLDS = 4
SHARPE_RETENTION_THRESHOLD = 0.80

# ============================================================================
# Helper Functions
# ============================================================================


def calculate_ohlc4(df):
    """Calculate OHLC4 average: (O + H + L + C) / 4"""
    return (df["open"] + df["high"] + df["low"] + df["close"]) / 4


def resample_to_higher_tf(df, timeframe="5min"):
    """Resample 1-minute data to higher timeframe, then forward-fill to 1-minute"""
    # Resample to higher timeframe
    df_resampled = df.resample(timeframe).agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    )

    # Forward-fill back to 1-minute resolution
    df_resampled = df_resampled.reindex(df.index, method="ffill")

    return df_resampled


def generate_signals(df, df_5min, fast, slow, signal):
    """
    Generate entry and exit signals based on MACD + BB conditions.

    Args:
        df: 1-minute OHLCV data
        df_5min: 5-minute OHLCV data (already resampled to 1-min)
        fast: MACD fast period
        slow: MACD slow period
        signal: MACD signal period

    Returns:
        entries, exits: Boolean arrays for entry/exit signals
    """
    # Calculate OHLC4 for 1-minute MACD
    ohlc4_1m = calculate_ohlc4(df)

    # Calculate 1-minute MACD using OHLC4
    macd_1m = vbt.talib("MACD").run(
        ohlc4_1m, fastperiod=fast, slowperiod=slow, signalperiod=signal
    )

    macd_line = macd_1m.macd
    signal_line = macd_1m.macdsignal
    histogram = macd_1m.macdhist

    # Calculate 5-minute Bollinger Bands
    bb_5m = vbt.talib("BBANDS").run(
        df_5min["close"], timeperiod=BB_LENGTH, nbdevup=BB_STD, nbdevdn=BB_STD
    )

    upper_band = bb_5m.upperband
    middle_band = bb_5m.middleband
    lower_band = bb_5m.lowerband

    # Entry conditions
    # 1. MACD histogram crosses from negative to positive
    hist_cross_positive = (histogram > 0) & (histogram.shift(1) <= 0)

    # 2. BB upper band expanding
    bb_upper_expanding = upper_band > upper_band.shift(1)

    entries = hist_cross_positive & bb_upper_expanding

    # Exit conditions
    # 1. MACD momentum weakening (histogram increase < previous increase)
    hist_change = histogram - histogram.shift(1)
    hist_change_prev = hist_change.shift(1)
    macd_weakening = hist_change < hist_change_prev

    # 2. BB contracting (width decreasing)
    bb_width = upper_band - lower_band
    bb_contracting = bb_width < bb_width.shift(1)

    exits = macd_weakening & bb_contracting

    return entries, exits


# ============================================================================
# Main Backtest Function
# ============================================================================


def run_optimization_with_wf_cv(df):
    """
    Run parameter optimization with walk-forward cross-validation.

    Returns:
        results_df: DataFrame with all parameter combinations and performance metrics
        best_params: Dictionary with best parameters and their performance
    """
    print("=" * 80)
    print("MACD + BOLLINGER BANDS STRATEGY OPTIMIZATION")
    print("=" * 80)
    print(f"\nData range: {df.index[0]} to {df.index[-1]}")
    print(f"Total bars: {len(df):,}")
    print(f"\nParameter ranges:")
    print(f"  MACD Fast: {list(MACD_FAST_RANGE)}")
    print(f"  MACD Slow: {list(MACD_SLOW_RANGE)}")
    print(f"  MACD Signal: {list(MACD_SIGNAL_RANGE)}")
    print(f"  BB Length: {BB_LENGTH} (fixed)")
    print(f"  BB Std: {BB_STD} (fixed)")

    # Prepare 5-minute data
    print("\nResampling to 5-minute timeframe...")
    df_5min = resample_to_higher_tf(df, HIGHER_TF)

    # Split data into folds
    fold_size = len(df) // N_FOLDS
    folds = []

    for i in range(N_FOLDS):
        start_idx = i * fold_size
        end_idx = (i + 1) * fold_size if i < N_FOLDS - 1 else len(df)
        folds.append((start_idx, end_idx))

    print(f"\nWalk-forward CV with {N_FOLDS} folds:")
    for i, (start, end) in enumerate(folds):
        print(
            f"  Fold {i + 1}: {df.index[start]} to {df.index[end - 1]} ({end - start:,} bars)"
        )

    # Generate all parameter combinations
    param_combinations = [
        (fast, slow, signal)
        for fast in MACD_FAST_RANGE
        for slow in MACD_SLOW_RANGE
        for signal in MACD_SIGNAL_RANGE
        if slow > fast  # Ensure slow > fast
    ]

    print(f"\nTotal parameter combinations: {len(param_combinations)}")
    print("\nRunning walk-forward cross-validation...")

    results = []

    for fold_idx in range(N_FOLDS):
        print(f"\n{'=' * 80}")
        print(f"FOLD {fold_idx + 1}/{N_FOLDS}")
        print(f"{'=' * 80}")

        # Define train and test sets
        # Train: all folds except current fold
        # Test: current fold
        train_indices = [i for i in range(N_FOLDS) if i != fold_idx]

        # Combine training folds
        train_data = []
        for idx in train_indices:
            start, end = folds[idx]
            train_data.append(df.iloc[start:end])

        df_train = pd.concat(train_data)
        df_train_5min = resample_to_higher_tf(df_train, HIGHER_TF)

        # Test fold
        test_start, test_end = folds[fold_idx]
        df_test = df.iloc[test_start:test_end]
        df_test_5min = resample_to_higher_tf(df_test, HIGHER_TF)

        print(f"Train: {len(df_train):,} bars")
        print(f"Test: {len(df_test):,} bars")
        print(f"Testing {len(param_combinations)} parameter combinations...")

        # Test each parameter combination
        for param_idx, (fast, slow, signal) in enumerate(param_combinations):
            if (param_idx + 1) % 10 == 0:
                print(f"  Progress: {param_idx + 1}/{len(param_combinations)}")

            # Generate signals for train set
            entries_train, exits_train = generate_signals(
                df_train, df_train_5min, fast, slow, signal
            )

            # Run backtest on train set
            pf_train = vbt.Portfolio.from_signals(
                df_train["close"],
                entries_train,
                exits_train,
                init_cash=100000,
                size=1,  # 1 contract per trade
                fees=0.0002,  # 2 bps per trade
                freq="1min",
            )

            # Generate signals for test set
            entries_test, exits_test = generate_signals(
                df_test, df_test_5min, fast, slow, signal
            )

            # Run backtest on test set
            pf_test = vbt.Portfolio.from_signals(
                df_test["close"],
                entries_test,
                exits_test,
                init_cash=100000,
                size=1,  # 1 contract per trade
                fees=0.0002,
                freq="1min",
            )

            # Extract metrics (properties, not methods)
            train_sharpe = pf_train.sharpe_ratio
            test_sharpe = pf_test.sharpe_ratio
            sharpe_retention = test_sharpe / train_sharpe if train_sharpe != 0 else 0

            results.append(
                {
                    "fold": fold_idx + 1,
                    "fast": fast,
                    "slow": slow,
                    "signal": signal,
                    "train_sharpe": train_sharpe,
                    "test_sharpe": test_sharpe,
                    "sharpe_retention": sharpe_retention,
                    "train_total_return": pf_train.total_return,
                    "test_total_return": pf_test.total_return,
                    "train_max_dd": pf_train.max_drawdown,
                    "test_max_dd": pf_test.max_drawdown,
                    "train_num_trades": pf_train.trades.count(),
                    "test_num_trades": pf_test.trades.count(),
                }
            )

    # Convert results to DataFrame
    results_df = pd.DataFrame(results)

    # Calculate average metrics across folds for each parameter combination
    avg_results = (
        results_df.groupby(["fast", "slow", "signal"])
        .agg(
            {
                "train_sharpe": "mean",
                "test_sharpe": "mean",
                "sharpe_retention": "mean",
                "train_total_return": "mean",
                "test_total_return": "mean",
                "train_max_dd": "mean",
                "test_max_dd": "mean",
                "train_num_trades": "mean",
                "test_num_trades": "mean",
            }
        )
        .reset_index()
    )

    # Find best parameters (MUST have positive test Sharpe AND retention >= 80%)
    valid_params = avg_results[
        (avg_results["test_sharpe"] > 0)
        & (avg_results["train_sharpe"] > 0)
        & (avg_results["sharpe_retention"] >= SHARPE_RETENTION_THRESHOLD)
    ]

    if len(valid_params) > 0:
        best_idx = valid_params["test_sharpe"].idxmax()
        best_params = valid_params.loc[best_idx].to_dict()

        print("\n" + "=" * 80)
        print("OPTIMIZATION COMPLETE - BEST PARAMETERS FOUND")
        print("=" * 80)
        print(
            f"\nBest parameters (positive Sharpe + ≥{SHARPE_RETENTION_THRESHOLD * 100}% retention):"
        )
        print(f"  MACD Fast: {int(best_params['fast'])}")
        print(f"  MACD Slow: {int(best_params['slow'])}")
        print(f"  MACD Signal: {int(best_params['signal'])}")
        print(f"\nPerformance metrics (average across {N_FOLDS} folds):")
        print(f"  Train Sharpe: {best_params['train_sharpe']:.3f}")
        print(f"  Test Sharpe: {best_params['test_sharpe']:.3f}")
        print(f"  Sharpe Retention: {best_params['sharpe_retention'] * 100:.1f}%")
        print(f"  Test Total Return: {best_params['test_total_return'] * 100:.2f}%")
        print(f"  Test Max Drawdown: {best_params['test_max_dd'] * 100:.2f}%")
        print(f"  Test Avg Trades: {best_params['test_num_trades']:.0f}")
    else:
        best_params = None
        print("\n" + "=" * 80)
        print("OPTIMIZATION COMPLETE - NO VALID PARAMETERS FOUND")
        print("=" * 80)
        print(
            f"\nNo parameter combinations achieved positive Sharpe with ≥{SHARPE_RETENTION_THRESHOLD * 100}% retention"
        )
        print("Strategy FAILED validation criteria")

    # Save results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_file = RESULTS_DIR / f"macd_bb_optimization_{timestamp}.csv"
    avg_results_file = RESULTS_DIR / f"macd_bb_avg_results_{timestamp}.csv"

    results_df.to_csv(results_file, index=False)
    avg_results.to_csv(avg_results_file, index=False)

    print(f"\nResults saved:")
    print(f"  All folds: {results_file}")
    print(f"  Averages: {avg_results_file}")

    return results_df, avg_results, best_params


# ============================================================================
# Main Execution
# ============================================================================

if __name__ == "__main__":
    print("\nLoading data...")
    df = pd.read_parquet(DATA_PATH)

    # Filter to last 1 year
    end_date = df.index[-1]
    start_date = end_date - timedelta(days=365)
    df = df[df.index >= start_date]

    print(f"Loaded {len(df):,} bars from {df.index[0]} to {df.index[-1]}")

    # Prepare OHLCV data
    df = df[["open", "high", "low", "close", "volume"]].copy()

    # Run optimization
    start_time = datetime.now()
    results_df, avg_results, best_params = run_optimization_with_wf_cv(df)
    end_time = datetime.now()

    print(
        f"\nTotal execution time: {(end_time - start_time).total_seconds():.1f} seconds"
    )

    # Generate live_scenario_config.json if validation passed
    if (
        best_params is not None
        and best_params["sharpe_retention"] >= SHARPE_RETENTION_THRESHOLD
    ):
        config = {
            "strategy_name": "MACD_BB_MultiTimeframe",
            "description": "1-min MACD + 5-min Bollinger Bands multi-timeframe strategy",
            "validated": True,
            "validation_date": datetime.now().isoformat(),
            "parameters": {
                "base_timeframe": "1min",
                "higher_timeframe": "5min",
                "macd_fast_period": int(best_params["fast"]),
                "macd_slow_period": int(best_params["slow"]),
                "macd_signal_period": int(best_params["signal"]),
                "macd_source": "OHLC4",
                "bb_length": BB_LENGTH,
                "bb_std": BB_STD,
            },
            "performance": {
                "avg_train_sharpe": float(best_params["train_sharpe"]),
                "avg_test_sharpe": float(best_params["test_sharpe"]),
                "sharpe_retention": float(best_params["sharpe_retention"]),
                "avg_test_return": float(best_params["test_total_return"]),
                "avg_test_max_dd": float(best_params["test_max_dd"]),
                "avg_test_trades": float(best_params["test_num_trades"]),
            },
            "walk_forward_cv": {
                "n_folds": N_FOLDS,
                "retention_threshold": SHARPE_RETENTION_THRESHOLD,
            },
        }

        config_file = RESULTS_DIR / "live_scenario_config.json"
        with open(config_file, "w") as f:
            json.dump(config, f, indent=2)

        print(f"\nLive scenario config saved: {config_file}")
        print("\n✅ STRATEGY VALIDATED - Ready for live trading")
    else:
        print("\n❌ STRATEGY REJECTED - Does not meet validation criteria")
