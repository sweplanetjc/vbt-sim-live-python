# Smart Data Loader - Usage Guide

The `data_loader.py` module provides intelligent data loading with automatic checking, validation, and helpful error messages.

---

## Quick Start

### 1. Check What Data You Have

```bash
# See all available data files
python data_loader.py check
```

**Output:**
```
============================================================
DATA AVAILABILITY CHECK
============================================================

✓ Found 3 data files:

  ES     | 432,000 bars | 2025-01-01 to 2025-11-13 | 15.2 MB
  NQ     | 432,000 bars | 2025-01-01 to 2025-11-13 | 15.1 MB
  GC     | 432,000 bars | 2025-01-01 to 2025-11-13 | 14.8 MB

============================================================
```

### 2. Load Data in Your Backtest

```python
from data_loader import load_futures_data
import vectorbtpro as vbt

# Smart loading with automatic checking
df = load_futures_data(
    symbol="ES",
    start_date="2025-06-01",
    end_date="2025-11-13",
    base_timeframe="1h"
)

# Convert to VectorBT data
data = vbt.Data.from_data(df)

# Ready to backtest!
```

---

## Usage Examples

### Example 1: Basic Loading

```python
from data_loader import load_futures_data

# Load ES data
df = load_futures_data("ES", "2025-06-01", "2025-11-13")

# Output:
# ✓ Found cached data: data/raw/ES_ohlcv_1m.parquet
#   Loaded 432,000 1-minute bars
#   Available range: 2025-01-01 to 2025-11-13
#   Filtered to 145,440 bars
#   Resampling from 1min to 1h...
#   Resampled to 3,024 1h bars
# 
# ✓ Data ready: 3,024 bars from 2025-06-01 to 2025-11-13
```

### Example 2: Data Doesn't Exist

```python
df = load_futures_data("ZB", "2025-06-01", "2025-11-13")

# Output:
# ❌ Data file not found: data/raw/ZB_ohlcv_1m.parquet
# 
# NEXT STEPS:
# 1. Fetch data for ZB:
#    python scripts/fetch_databento_data.py --symbol ZB
# 
# 2. Or fetch all common contracts:
#    python scripts/fetch_databento_data.py --all
# 
# Note: Check cost first with --check-cost flag

# Raises DataNotFoundError
```

### Example 3: Date Range Issues

```python
# Request dates that exceed available data
df = load_futures_data("ES", "2024-01-01", "2025-12-31")

# Output:
# ✓ Found cached data: data/raw/ES_ohlcv_1m.parquet
#   Loaded 432,000 1-minute bars
#   Available range: 2025-01-01 to 2025-11-13
# 
# ⚠️  WARNING: Requested start 2024-01-01 is before available data 2025-01-01
#    Using available start: 2025-01-01
# 
# ⚠️  WARNING: Requested end 2025-12-31 is after available data 2025-11-13
#    Using available end: 2025-11-13
# 
# ✓ Data ready: 6,504 bars from 2025-01-01 to 2025-11-13
```

### Example 4: Load Multiple Symbols

```python
from data_loader import load_multiple_symbols

# Load ES, NQ, and GC
data_dict = load_multiple_symbols(
    symbols=["ES", "NQ", "GC"],
    start_date="2025-06-01",
    end_date="2025-11-13",
    base_timeframe="1h",
    skip_missing=True  # Skip symbols without data
)

# Output shows each symbol loading...
# 
# ============================================================
# LOADING SUMMARY
# ============================================================
# ✓ Successfully loaded: 3 symbols
#   ['ES', 'NQ', 'GC']

# Use in backtest
for symbol, df in data_dict.items():
    data = vbt.Data.from_data(df)
    # Run optimization...
```

### Example 5: Error Handling

```python
from data_loader import load_futures_data, DataNotFoundError, InsufficientDataError

try:
    df = load_futures_data("ES", "2025-06-01", "2025-11-13")
    
    # Proceed with backtest
    data = vbt.Data.from_data(df)
    # ... run optimization
    
except DataNotFoundError as e:
    print(f"Data not available: {e}")
    print("Run fetch script first")
    exit(1)
    
except InsufficientDataError as e:
    print(f"Not enough data: {e}")
    print("Adjust date range or fetch more data")
    exit(1)
```

---

## CLI Usage

### Check All Data

```bash
python data_loader.py check
```

Shows all available data files with date ranges and sizes.

### Test Load Single Symbol

```bash
python data_loader.py load ES 2025-06-01 2025-11-13
```

Tests loading ES data for specified date range.

### Test Load Multiple Symbols

```bash
python data_loader.py load-multi ES,NQ,GC 2025-06-01 2025-11-13
```

Tests loading multiple symbols.

---

## Function Reference

### `load_futures_data()`

**Load data for single symbol with smart checking.**

```python
def load_futures_data(
    symbol: str,           # "ES", "NQ", etc.
    start_date: str,       # "2025-06-01"
    end_date: str,         # "2025-11-13"
    base_timeframe: str = "1h",  # Resample to this TF
    min_bars: int = 100,   # Minimum bars required
    verbose: bool = True   # Print status messages
) -> Optional[pd.DataFrame]:
```

**Returns:** DataFrame with OHLCV data, or None if unavailable

**Raises:**
- `DataNotFoundError`: File doesn't exist
- `InsufficientDataError`: Not enough bars

**What it checks:**
1. ✓ File exists
2. ✓ Date range coverage
3. ✓ Data quality (no NaNs)
4. ✓ Minimum bar count
5. ✓ Proper resampling

### `load_multiple_symbols()`

**Load data for multiple symbols.**

```python
def load_multiple_symbols(
    symbols: List[str],    # ["ES", "NQ", "GC"]
    start_date: str,
    end_date: str,
    base_timeframe: str = "1h",
    min_bars: int = 100,
    skip_missing: bool = True  # Skip or error on missing data
) -> Dict[str, pd.DataFrame]:
```

**Returns:** Dict mapping symbol → DataFrame

**Raises:** `DataNotFoundError` if skip_missing=False and any data missing

### `check_data_availability()`

**Quick check if data exists.**

```python
def check_data_availability(symbol: str) -> bool:
```

**Returns:** True if file exists, False otherwise

### `get_available_symbols()`

**Get list of symbols with cached data.**

```python
def get_available_symbols() -> List[str]:
```

**Returns:** List of symbol names (e.g., ["ES", "NQ", "GC"])

### `get_data_date_range()`

**Get available date range without loading full data.**

```python
def get_data_date_range(symbol: str) -> Optional[tuple]:
```

**Returns:** (start_date, end_date) or None if file doesn't exist

---

## Integration with Backtest Skill

The backtest skill uses this loader automatically:

```python
# In backtest_runner.py

from data_loader import load_futures_data

# User says: "Test RSI on ES from June to November"
df = load_futures_data(
    symbol="ES",
    start_date="2025-06-01",
    end_date="2025-11-13",
    base_timeframe="1h"
)

if df is None:
    print("Cannot proceed without data")
    exit(1)

# Convert to VectorBT
data = vbt.Data.from_data(df)

# Run optimization
results = backtest_rsi_mtf(data, ...)
```

---

## Decision Flow

```
User requests backtest
    ↓
Load data with load_futures_data()
    ↓
Does file exist?
├─ No → Print clear instructions → Exit with error
└─ Yes → Load file
    ↓
Does date range cover request?
├─ Partial → Adjust + warning → Continue
└─ Yes → Filter to range
    ↓
Enough bars? (>100)
├─ No → Error with explanation
└─ Yes → Return DataFrame
    ↓
Ready for backtest!
```

---

## Best Practices

### 1. Always Use the Loader

```python
# ✅ GOOD - Smart checking
from data_loader import load_futures_data
df = load_futures_data("ES", start, end)

# ❌ BAD - No checking
df = pd.read_parquet("data/raw/ES_ohlcv_1m.parquet")
```

### 2. Handle Errors Gracefully

```python
try:
    df = load_futures_data("ES", start, end)
except DataNotFoundError:
    print("Fetch data first")
    exit(1)
```

### 3. Check Before Batch Processing

```python
# Check what's available first
symbols = get_available_symbols()
print(f"Available: {symbols}")

# Then load
data_dict = load_multiple_symbols(symbols, start, end)
```

### 4. Use verbose=False in Production

```python
# Development - show everything
df = load_futures_data("ES", start, end, verbose=True)

# Production - suppress messages
df = load_futures_data("ES", start, end, verbose=False)
```

---

## Common Scenarios

### Scenario 1: First Time Setup

```bash
# 1. Check what you have
python data_loader.py check

# Output: "No data files found"

# 2. Fetch data
python scripts/fetch_databento_data.py --all

# 3. Check again
python data_loader.py check

# Output: Shows ES, NQ, GC available

# 4. Ready to backtest!
```

### Scenario 2: Missing One Symbol

```bash
# Try to backtest ES, NQ, ZB
python backtest_runner.py --symbols ES,NQ,ZB

# Output:
# ✓ ES loaded
# ✓ NQ loaded
# ❌ ZB not found - fetch with:
#    python scripts/fetch_databento_data.py --symbol ZB
```

### Scenario 3: Stale Data

```bash
# Backtest fails because data is old
python data_loader.py check

# Output:
# ES | 2025-01-01 to 2025-06-01  ← Old!

# Update data
python scripts/fetch_databento_data.py --symbol ES --update

# Check again
python data_loader.py check

# Output:
# ES | 2025-01-01 to 2025-11-13  ← Fresh!
```

---

## Error Messages Explained

### "Data file not found"

**Cause:** Parquet file doesn't exist in data/raw/

**Solution:** Run `python scripts/fetch_databento_data.py --symbol SYMBOL`

### "No data available for date range"

**Cause:** Requested dates don't overlap with available data

**Solution:** Check available range with `python data_loader.py check`

### "Insufficient data: X bars (minimum 100 required)"

**Cause:** After filtering and resampling, not enough bars

**Solution:** Expand date range or use shorter timeframe

### "File may be corrupted"

**Cause:** Can't read Parquet file

**Solution:** Delete and re-fetch:
```bash
rm data/raw/ES_ohlcv_1m.parquet
python scripts/fetch_databento_data.py --symbol ES
```

---

## Summary

**Key Benefits:**

✅ **Automatic checking** - Knows if data exists before trying to load  
✅ **Clear errors** - Tells you exactly what to do if data is missing  
✅ **Date validation** - Handles date range issues gracefully  
✅ **Quality checks** - Validates data before returning  
✅ **Multi-symbol** - Easy batch loading with skip_missing  
✅ **CLI testing** - Test data availability from command line

**Usage in Backtest Workflow:**

```
1. Check data availability
   ↓
2. Load with smart checking
   ↓
3. Handle errors gracefully
   ↓
4. Convert to VectorBT
   ↓
5. Run optimization
```

**Integration:**

- Used by: `backtest_runner.py`, `weekly_backtest.py`
- Replaces: Manual `pd.read_parquet()` calls
- Benefits: No more silent failures or cryptic errors!
