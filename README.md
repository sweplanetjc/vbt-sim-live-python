# vbt_sim_bot - Live Trading System

A production-ready live trading system built on VectorBTPro that ingests real-time market data from Databento, evaluates trading strategies, and executes orders via CrossTrade API (NinjaTrader integration).

## Repository Structure

```
vbt_sim_bot_fork/
├── run_live_trading.py                # ENTRY POINT: Live trading system
├── logging_system.py                  # Core: Logging infrastructure
│
├── config/                            # Configuration files
│   └── live_trading_config.json       # Live trading configuration
│
├── scanner/                           # Core: Data ingestion & aggregation
│   ├── databento_live_feed.py         # Databento live feed integration
│   ├── second_to_minute_aggregator.py # 1s → 1m bar aggregation
│   ├── bar_aggregator.py              # Multi-timeframe bar aggregation
│   └── live_trading_orchestrator.py   # Multi-symbol trading orchestrator
│
├── execution/                         # Core: Order execution
│   ├── crosstrade_client.py           # CrossTrade API client
│   ├── order_manager.py               # High-level order interface
│   ├── models.py                      # Data models
│   ├── exceptions.py                  # Exception types
│   ├── rate_limiter.py                # API rate limiting
│   ├── market_data.py                 # Market data utilities
│   ├── signal_translator.py           # Signal translation
│   └── examples/
│       └── crosstrade_example.py      # API usage reference
│
├── strategies/                        # Core: Trading strategies
│   └── simple_bullish_cci.py          # Simple bullish CCI strategy
│
├── indicators/                        # Core: Technical indicators
│   ├── indicator_root.py              # Base indicator class
│   ├── indicator_basic.py             # Basic indicators
│   ├── indicator_cci.py               # Commodity Channel Index
│   ├── indicator_rsi.py               # Relative Strength Index
│   ├── indicator_mas.py               # Moving averages
│   ├── indicator_vwap.py              # VWAP
│   └── indicator_utils.py             # Indicator utilities
│
├── vbt_sim_live/                      # Core: Data structures
│   ├── generic_data.py                # Generic data containers
│   ├── live_data.py                   # Live data streaming
│   ├── sim_data.py                    # Simulation data
│   ├── tfs.py                         # Timeframe management
│   └── vectorbtpro_helpers.py         # VectorBTPro utilities
│
├── tests/                             # All tests
│   ├── unit/                          # Unit tests
│   │   ├── test_bar_aggregator.py
│   │   ├── test_config_validation.py
│   │   ├── test_databento_live_feed.py
│   │   ├── test_indicator_cci.py
│   │   ├── test_live_trading_orchestrator.py
│   │   ├── test_run_live_trading.py
│   │   └── test_simple_bullish_cci.py
│   └── integration/                   # Integration tests
│       ├── test_cci_with_replay.py
│       ├── test_databento_feed.py
│       ├── test_databento_feed_simple.py
│       ├── test_symbol_fix.py
│       └── test_symbol_mapping.py
│
├── scripts/                           # Development utilities
│   ├── README.md                      # Scripts documentation
│   ├── backtest/                      # Backtesting tools
│   │   ├── backtest_macd_bb_strategy.py
│   │   └── data_loader.py
│   ├── data/                          # Data fetching utilities
│   │   ├── fetch_databento_data.py
│   │   └── databento_safe_download.py
│   ├── debug/                         # Debugging tools
│   │   ├── debug_databento.py
│   │   └── debug_parquet_structure.py
│   └── monitoring/                    # Monitoring tools
│       └── monitor_live.py
│
├── archive/                           # Archived legacy code
│   └── examples/                      # Early POC scripts
│
├── data/                              # Runtime data (gitignored)
│   └── raw/                           # Raw market data
│
├── results/                           # Backtest results (gitignored)
│
└── Docs/                              # Documentation
    ├── README.md                      # Documentation index
    ├── ARCHITECTURE.md                # System architecture
    ├── WORKFLOWS.md                   # Usage workflows
    ├── API.md                         # API documentation
    ├── STRATEGY_REGISTRY.md           # Strategy documentation
    └── plans/                         # Implementation plans
        ├── 2025-11-16-replay-strategy-warmup.md
        └── 2025-11-17-repository-reorganization.md
```

## Quick Start

### 1. Setup Environment

```bash
# Clone repository
git clone <repository-url>
cd vbt_sim_bot_fork

# Create virtual environment
python3.12 -m venv venv312
source venv312/bin/activate  # On Windows: venv312\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
# Edit .env and add your API keys:
#   DATABENTO_API_KEY=your_databento_key
#   CROSSTRADE_API_KEY=your_crosstrade_key
```

### 2. Configure Live Trading

Edit `config/live_trading_config.json`:

```json
{
  "databento": {
    "symbols": ["ES.c.0", "NQ.c.0"],
    "schema": "ohlcv-1s",
    "replay_hours": 24
  },
  "strategies": [
    {
      "name": "simple_bullish_cci",
      "module": "strategies.simple_bullish_cci",
      "symbols": ["ES.c.0"],
      "timeframes": ["m5"],
      "params": {
        "cci_period": 15,
        "entry_threshold": -100,
        "exit_threshold": 100
      }
    }
  ],
  "execution": {
    "account": "Sim101",
    "dry_run": true
  }
}
```

### 3. Run Live Trading

```bash
# Start live trading (dry run mode)
python run_live_trading.py config/live_trading_config.json --log-level INFO

# Monitor in separate terminal
python scripts/monitoring/monitor_live.py
```

### 4. Run Tests

```bash
# All tests
pytest tests/ -v

# Unit tests only
pytest tests/unit/ -v

# Integration tests only
pytest tests/integration/ -v

# With coverage
pytest --cov=scanner --cov=execution --cov=strategies --cov=indicators --cov-report=html
```

### 5. Backtest a Strategy

```bash
# Fetch historical data
python scripts/data/fetch_databento_data.py \
    --symbols ES.c.0 NQ.c.0 \
    --start 2025-01-01 \
    --end 2025-11-17 \
    --schema ohlcv-1m

# Run backtest
cd scripts/backtest
python backtest_macd_bb_strategy.py
```

## Key Features

- **Real-time Data Ingestion:** Databento live feeds with 24-hour historical replay
- **Multi-Timeframe Bar Aggregation:** 1s → 1m → 5m, 15m, 30m, 1h, 4h
- **Strategy Framework:** Modular strategy system with technical indicators
- **Order Execution:** CrossTrade API integration (NinjaTrader)
- **Comprehensive Testing:** Unit and integration tests
- **Production-Ready Logging:** Structured logging with configurable levels

## System Architecture

### Data Flow

```
Databento Feed (1s OHLCV)
    ↓
Second-to-Minute Aggregator (1s → 1m)
    ↓
Bar Aggregator (1m → 5m, 15m, etc.)
    ↓
Live Trading Orchestrator
    ↓
Strategy Evaluation (per symbol/timeframe)
    ↓
Order Manager
    ↓
CrossTrade Client
    ↓
NinjaTrader
```

### Key Components

1. **scanner/databento_live_feed.py** - Ingests real-time and historical data from Databento
2. **scanner/bar_aggregator.py** - Aggregates bars across multiple timeframes
3. **scanner/live_trading_orchestrator.py** - Orchestrates strategy evaluation and order execution
4. **strategies/** - Trading strategy implementations
5. **execution/crosstrade_client.py** - CrossTrade API client with rate limiting and error handling

## Documentation

- **[Docs/README.md](Docs/README.md)** - Documentation index
- **[Docs/ARCHITECTURE.md](Docs/ARCHITECTURE.md)** - Detailed system architecture
- **[Docs/WORKFLOWS.md](Docs/WORKFLOWS.md)** - Common workflows (live trading, backtesting, testing)
- **[Docs/STRATEGY_REGISTRY.md](Docs/STRATEGY_REGISTRY.md)** - Available strategies and parameters
- **[scripts/README.md](scripts/README.md)** - Development scripts documentation

## Migration Notes (2025-11-17 Reorganization)

The repository was reorganized on 2025-11-17 to improve maintainability and discoverability. Here's what changed:

### Test Scripts Moved
- **Before:** Test files scattered in repository root
- **After:** All tests organized in `tests/` directory
  - Unit tests: `tests/unit/`
  - Integration tests: `tests/integration/`

**Migration:** Update any test discovery scripts to use `tests/` directory:
```bash
# Old
pytest test_*.py

# New
pytest tests/
```

### Utility Scripts Reorganized
- **Backtest scripts:** Moved to `scripts/backtest/`
  - `backtest_macd_bb_strategy.py`
  - `data_loader.py`
- **Data utilities:** Moved to `scripts/data/`
  - `fetch_databento_data.py`
  - `databento_safe_download.py`
- **Debug scripts:** Moved to `scripts/debug/`
  - `debug_databento.py`
  - `debug_parquet_structure.py`
- **Monitoring:** Moved to `scripts/monitoring/`
  - `monitor_live.py`

**Migration:** Update script paths in any automation or documentation:
```bash
# Old
python monitor_live.py

# New
python scripts/monitoring/monitor_live.py
```

### Examples Archived
Early POC and example files moved from `examples/` to `archive/examples/` for historical reference. These files are not maintained and may not work with the current codebase.

**Active example:** `execution/examples/crosstrade_example.py` remains as an API reference.

### Import Paths
**No changes to core module imports.** All core modules remain in their original locations:
- `scanner/`
- `execution/`
- `strategies/`
- `indicators/`
- `vbt_sim_live/`

Python imports continue to work as before:
```python
from scanner.databento_live_feed import DatabentoLiveFeed
from execution.crosstrade_client import CrossTradeClient
from strategies.simple_bullish_cci import SimpleBullishCCIStrategy
```

### Directory Structure Changes
- **Created:** `scripts/` with subdirectories (backtest, data, debug, monitoring)
- **Created:** `tests/integration/` for integration tests
- **Created:** `archive/` for legacy code
- **Removed:** `examples/` (moved to `archive/examples/`)
- **Removed:** `debug_scripts/` (moved to `scripts/debug/`)
- **Removed:** `Databento/` (moved to `scripts/data/`)

### Running Scripts After Reorganization
All scripts should work from repository root:
```bash
# Live trading (unchanged)
python run_live_trading.py config/live_trading_config.json

# Monitoring (new location)
python scripts/monitoring/monitor_live.py

# Backtesting (new location)
cd scripts/backtest
python backtest_macd_bb_strategy.py

# Tests (new organization)
pytest tests/ -v
```

### .gitignore Updates
Enhanced `.gitignore` to properly exclude:
- Python artifacts (`__pycache__/`, `*.pyc`)
- Virtual environments (`venv/`, `venv312/`)
- Data and results (`data/`, `results/`, `*.parquet`)
- Environment files (`.env`)
- IDE files (`.vscode/`, `.idea/`)

## Contributing

### Adding a New Strategy

1. Create strategy file in `strategies/`:
```bash
touch strategies/my_new_strategy.py
```

2. Implement strategy (inherit from base strategy class)

3. Add to `config/live_trading_config.json`:
```json
{
  "strategies": [
    {
      "name": "my_new_strategy",
      "module": "strategies.my_new_strategy",
      "symbols": ["ES.c.0"],
      "timeframes": ["m5"],
      "params": {}
    }
  ]
}
```

4. Add unit tests in `tests/unit/test_my_new_strategy.py`

5. Test with dry run:
```bash
python run_live_trading.py config/live_trading_config.json --log-level DEBUG
```

### Development Workflow

1. **Make changes** to core modules (`scanner/`, `execution/`, `strategies/`, `indicators/`)
2. **Write tests** in `tests/unit/` or `tests/integration/`
3. **Run tests:** `pytest tests/ -v`
4. **Test live (dry run):** `python run_live_trading.py config/live_trading_config.json`
5. **Commit changes** with descriptive message
6. **Push** to feature branch
7. **Create PR** for review

## License

[Add license information here]

## Support

For questions, issues, or contributions:
- Create an issue in the repository
- See [Docs/README.md](Docs/README.md) for detailed documentation
- Review [Docs/WORKFLOWS.md](Docs/WORKFLOWS.md) for common usage patterns
