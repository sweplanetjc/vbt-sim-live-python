"""
Data Loader for Futures-Algo Backtesting

Smart data loading with existence checking, date validation, and quality checks.
Used by backtest_runner.py and weekly_backtest.py.
"""

import pandas as pd
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict
import logging

logger = logging.getLogger(__name__)


class DataNotFoundError(Exception):
    """Raised when requested data file doesn't exist."""
    pass


class InsufficientDataError(Exception):
    """Raised when available data is insufficient for backtesting."""
    pass


def check_data_availability(symbol: str) -> bool:
    """
    Quick check if data file exists for symbol.
    
    Args:
        symbol: Futures symbol (e.g., "ES", "NQ")
    
    Returns:
        True if file exists, False otherwise
    """
    data_file = Path(f"data/raw/{symbol}_ohlcv_1m.parquet")
    return data_file.exists()


def get_available_symbols() -> List[str]:
    """
    Get list of symbols with cached data.
    
    Returns:
        List of symbol names (e.g., ["ES", "NQ", "GC"])
    """
    data_dir = Path("data/raw")
    if not data_dir.exists():
        return []
    
    symbols = []
    for file in data_dir.glob("*_ohlcv_1m.parquet"):
        # Extract symbol from filename (e.g., "ES_ohlcv_1m.parquet" -> "ES")
        symbol = file.stem.split("_")[0]
        symbols.append(symbol)
    
    return sorted(symbols)


def get_data_date_range(symbol: str) -> Optional[tuple]:
    """
    Get available date range for symbol without loading full data.
    
    Args:
        symbol: Futures symbol
    
    Returns:
        (start_date, end_date) tuple or None if file doesn't exist
    """
    data_file = Path(f"data/raw/{symbol}_ohlcv_1m.parquet")
    
    if not data_file.exists():
        return None
    
    try:
        # Read just the index to get date range (fast)
        df = pd.read_parquet(data_file, columns=[])
        return (df.index[0], df.index[-1])
    except Exception as e:
        logger.error(f"Error reading date range for {symbol}: {e}")
        return None


def load_futures_data(
    symbol: str,
    start_date: str,
    end_date: str,
    base_timeframe: str = "1h",
    min_bars: int = 100,
    verbose: bool = True
) -> Optional[pd.DataFrame]:
    """
    Load historical futures data with smart checking.
    
    Args:
        symbol: Futures symbol (e.g., "ES", "NQ")
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        base_timeframe: Resample to this timeframe (default: "1h")
        min_bars: Minimum bars required (default: 100)
        verbose: Print detailed status messages (default: True)
    
    Returns:
        DataFrame with OHLCV data, or None if data unavailable
    
    Raises:
        DataNotFoundError: If data file doesn't exist
        InsufficientDataError: If available data is below min_bars
    """
    
    data_file = Path(f"data/raw/{symbol}_ohlcv_1m.parquet")
    
    # ============================================================
    # STEP 1: Check file exists
    # ============================================================
    if not data_file.exists():
        msg = (
            f"Data file not found: {data_file}\n"
            f"\n"
            f"NEXT STEPS:\n"
            f"1. Fetch data for {symbol}:\n"
            f"   python scripts/fetch_databento_data.py --symbol {symbol}\n"
            f"\n"
            f"2. Or fetch all common contracts:\n"
            f"   python scripts/fetch_databento_data.py --all\n"
            f"\n"
            f"Note: Check cost first with --check-cost flag"
        )
        if verbose:
            print(f"\n❌ {msg}")
        raise DataNotFoundError(msg)
    
    if verbose:
        print(f"✓ Found cached data: {data_file}")
    
    # ============================================================
    # STEP 2: Load and validate
    # ============================================================
    try:
        df = pd.read_parquet(data_file)
        
        if verbose:
            print(f"  Loaded {len(df):,} 1-minute bars")
        
        # Get available date range
        data_start = df.index[0]
        data_end = df.index[-1]
        
        if verbose:
            print(f"  Available range: {data_start.date()} to {data_end.date()}")
        
    except Exception as e:
        msg = (
            f"Error loading data from {data_file}: {e}\n"
            f"\n"
            f"File may be corrupted. Try:\n"
            f"1. Delete file: rm {data_file}\n"
            f"2. Re-fetch: python scripts/fetch_databento_data.py --symbol {symbol}"
        )
        if verbose:
            print(f"\n❌ {msg}")
        raise DataNotFoundError(msg)
    
    # ============================================================
    # STEP 3: Check date coverage
    # ============================================================
    req_start = pd.to_datetime(start_date)
    req_end = pd.to_datetime(end_date)
    
    # Adjust if requested dates exceed available data
    actual_start = req_start
    actual_end = req_end
    
    if data_start > req_start:
        if verbose:
            print(f"\n⚠️  WARNING: Requested start {req_start.date()} "
                  f"is before available data {data_start.date()}")
            print(f"   Using available start: {data_start.date()}")
        actual_start = data_start
    
    if data_end < req_end:
        if verbose:
            print(f"\n⚠️  WARNING: Requested end {req_end.date()} "
                  f"is after available data {data_end.date()}")
            print(f"   Using available end: {data_end.date()}")
        actual_end = data_end
    
    # ============================================================
    # STEP 4: Filter to date range
    # ============================================================
    df_filtered = df.loc[actual_start:actual_end]
    
    if len(df_filtered) == 0:
        msg = (
            f"No data available for date range\n"
            f"  Requested: {req_start.date()} to {req_end.date()}\n"
            f"  Available: {data_start.date()} to {data_end.date()}"
        )
        if verbose:
            print(f"\n❌ {msg}")
        raise InsufficientDataError(msg)
    
    if verbose:
        print(f"  Filtered to {len(df_filtered):,} bars")
    
    # ============================================================
    # STEP 5: Resample to base timeframe
    # ============================================================
    if base_timeframe != "1min":
        if verbose:
            print(f"  Resampling from 1min to {base_timeframe}...")
        
        df_resampled = df_filtered.resample(base_timeframe).agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum'
        }).dropna()
        
        if verbose:
            print(f"  Resampled to {len(df_resampled):,} {base_timeframe} bars")
    else:
        df_resampled = df_filtered
    
    # ============================================================
    # STEP 6: Quality checks
    # ============================================================
    
    # Check minimum bars
    if len(df_resampled) < min_bars:
        msg = (
            f"Insufficient data: {len(df_resampled)} bars "
            f"(minimum {min_bars} required)"
        )
        if verbose:
            print(f"\n❌ {msg}")
        raise InsufficientDataError(msg)
    
    # Check for missing values
    missing = df_resampled.isnull().sum()
    if missing.any():
        if verbose:
            print(f"\n⚠️  WARNING: Missing values detected:")
            for col, count in missing[missing > 0].items():
                print(f"   {col}: {count} missing")
    
    # Final summary
    if verbose:
        print(f"\n✓ Data ready: {len(df_resampled):,} bars "
              f"from {df_resampled.index[0].date()} to {df_resampled.index[-1].date()}")
    
    return df_resampled


def load_multiple_symbols(
    symbols: List[str],
    start_date: str,
    end_date: str,
    base_timeframe: str = "1h",
    min_bars: int = 100,
    skip_missing: bool = True
) -> Dict[str, pd.DataFrame]:
    """
    Load data for multiple symbols with smart checking.
    
    Args:
        symbols: List of futures symbols
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        base_timeframe: Resample to this timeframe
        min_bars: Minimum bars required per symbol
        skip_missing: If True, skip symbols with missing data; if False, raise error
    
    Returns:
        Dict mapping symbol to DataFrame
    
    Raises:
        DataNotFoundError: If skip_missing=False and any data is missing
    """
    
    data_dict = {}
    failed_symbols = []
    
    for symbol in symbols:
        print(f"\n{'='*60}")
        print(f"Loading {symbol}...")
        print('='*60)
        
        try:
            df = load_futures_data(
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
                base_timeframe=base_timeframe,
                min_bars=min_bars,
                verbose=True
            )
            data_dict[symbol] = df
            
        except (DataNotFoundError, InsufficientDataError) as e:
            if skip_missing:
                print(f"⚠️  Skipping {symbol} - {e}")
                failed_symbols.append(symbol)
            else:
                raise
    
    # Summary
    print(f"\n{'='*60}")
    print(f"LOADING SUMMARY")
    print('='*60)
    print(f"✓ Successfully loaded: {len(data_dict)} symbols")
    if data_dict:
        print(f"  {list(data_dict.keys())}")
    
    if failed_symbols:
        print(f"\n⚠️  Failed to load: {len(failed_symbols)} symbols")
        print(f"  {failed_symbols}")
        print(f"\nTo fetch missing data:")
        for symbol in failed_symbols:
            print(f"  python scripts/fetch_databento_data.py --symbol {symbol}")
    
    if not data_dict:
        raise DataNotFoundError(
            "No data available for any symbols. "
            "Run: python scripts/fetch_databento_data.py --all"
        )
    
    return data_dict


# ============================================================
# CLI Helper Functions
# ============================================================

def check_all_data(verbose: bool = True) -> None:
    """
    Check what data is available (for CLI use).
    
    Prints summary of all cached data files.
    """
    print("\n" + "="*60)
    print("DATA AVAILABILITY CHECK")
    print("="*60)
    
    data_dir = Path("data/raw")
    if not data_dir.exists():
        print("❌ Data directory not found: data/raw/")
        print("\nCreate it with: mkdir -p data/raw")
        return
    
    parquet_files = list(data_dir.glob("*_ohlcv_1m.parquet"))
    
    if not parquet_files:
        print("❌ No data files found in data/raw/")
        print("\nFetch data with:")
        print("  python scripts/fetch_databento_data.py --all")
        return
    
    print(f"\n✓ Found {len(parquet_files)} data files:\n")
    
    for file in sorted(parquet_files):
        symbol = file.stem.split("_")[0]
        
        try:
            # Get date range
            date_range = get_data_date_range(symbol)
            if date_range:
                start, end = date_range
                
                # Get file size
                size_mb = file.stat().st_size / (1024 * 1024)
                
                # Count bars
                df = pd.read_parquet(file)
                n_bars = len(df)
                
                print(f"  {symbol:6s} | {n_bars:,} bars | "
                      f"{start.date()} to {end.date()} | {size_mb:.1f} MB")
            else:
                print(f"  {symbol:6s} | ERROR reading file")
        except Exception as e:
            print(f"  {symbol:6s} | ERROR: {e}")
    
    print("\n" + "="*60)


# ============================================================
# Main (for testing)
# ============================================================

if __name__ == "__main__":
    import sys
    
    # Test: Check all available data
    if len(sys.argv) == 1 or sys.argv[1] == "check":
        check_all_data()
    
    # Test: Load specific symbol
    elif sys.argv[1] == "load":
        if len(sys.argv) < 3:
            print("Usage: python data_loader.py load SYMBOL [START] [END]")
            print("Example: python data_loader.py load ES 2025-06-01 2025-11-13")
            sys.exit(1)
        
        symbol = sys.argv[2]
        start = sys.argv[3] if len(sys.argv) > 3 else "2025-06-01"
        end = sys.argv[4] if len(sys.argv) > 4 else "2025-11-13"
        
        try:
            df = load_futures_data(symbol, start, end, base_timeframe="1h")
            print("\n✓ SUCCESS - Data loaded and ready for backtesting")
        except Exception as e:
            print(f"\n❌ FAILED - {e}")
            sys.exit(1)
    
    # Test: Load multiple symbols
    elif sys.argv[1] == "load-multi":
        symbols = sys.argv[2].split(",") if len(sys.argv) > 2 else ["ES", "NQ"]
        start = sys.argv[3] if len(sys.argv) > 3 else "2025-06-01"
        end = sys.argv[4] if len(sys.argv) > 4 else "2025-11-13"
        
        try:
            data_dict = load_multiple_symbols(
                symbols=symbols,
                start_date=start,
                end_date=end,
                skip_missing=True
            )
            print("\n✓ SUCCESS - All data loaded and ready")
        except Exception as e:
            print(f"\n❌ FAILED - {e}")
            sys.exit(1)
    
    else:
        print("Usage:")
        print("  python data_loader.py check                           # Check all available data")
        print("  python data_loader.py load SYMBOL [START] [END]      # Test load single symbol")
        print("  python data_loader.py load-multi SYM1,SYM2 [START] [END]  # Test load multiple")
