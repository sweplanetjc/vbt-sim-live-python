# Development Scripts

This directory contains development utilities, debugging tools, and operational scripts.

## Directory Structure

### `backtest/`
Backtesting infrastructure and scripts.

- `backtest_macd_bb_strategy.py` - Example backtest script for MACD + Bollinger Bands strategy
- `data_loader.py` - Utilities for loading historical data for backtesting

**Usage:**
```bash
cd scripts/backtest
python backtest_macd_bb_strategy.py
```

### `data/`
Data fetching and management utilities.

- `fetch_databento_data.py` - Download historical data from Databento
- `databento_safe_download.py` - Safe data download with retry logic

**Usage:**
```bash
python scripts/data/fetch_databento_data.py --symbols ES.c.0 --start 2025-01-01
```

### `debug/`
Debugging and diagnostic tools.

- `debug_databento.py` - Debug Databento feed connections and data
- `debug_parquet_structure.py` - Inspect parquet file structure

**Usage:**
```bash
python scripts/debug/debug_databento.py
python scripts/debug/debug_parquet_structure.py data/raw/ES_2025-11-17.parquet
```

### `monitoring/`
Live system monitoring tools.

- `monitor_live.py` - Monitor live trading system in real-time

**Usage:**
```bash
python scripts/monitoring/monitor_live.py
```

## Guidelines

**Adding New Scripts:**
1. Place in appropriate subdirectory
2. Add docstring explaining purpose
3. Include usage example in this README
4. Make executable if it's a primary entry point: `chmod +x script.py`

**Script Requirements:**
- Use argparse for command-line arguments
- Import from core modules (scanner/, execution/, etc.)
- Handle errors gracefully with try/except
- Use logging_system for consistent logging
