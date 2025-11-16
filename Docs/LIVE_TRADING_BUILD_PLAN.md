# Live Trading System - Build Plan & File Structure

**Project:** Futures Algo Trading System (Live Phase)  
**Date:** November 2025  
**Status:** Planning Phase

---

## Overview

This document outlines the complete build plan for the live trading system with dynamic strategy loading, multi-timeframe analysis, and real-time signal generation.

**Core Architecture:**
```
Databento Live Feed (1-min OHLCV)
    ↓
BarAggregator (resample to multi-timeframe)
    ↓
VBTIndicatorCalculator (compute indicators from config)
    ↓
StrategyLoader + SignalGenerator (evaluate conditions)
    ↓
CrossTradeExecutor (submit orders)
    ↓
logs/ (signals, errors, audit trail)
```

---

## Complete File Structure

```
futures-algo/
│
├── README.md
├── requirements.txt
├── .env                              # API keys (NEVER commit)
├── .gitignore
│
│
├── config/
│   ├── __init__.py
│   ├── live_trading_config.json      # Main config (strategies, parameters, timeframes)
│   └── config_loader.py              # Validates and loads config from JSON
│
│
├── scanner/                          # Core live trading logic
│   ├── __init__.py
│   ├── databento_live_feed.py        # Streams 1-min OHLCV data from Databento
│   ├── bar_aggregator.py             # Resamples 1-min → 3/6/15/27-min bars
│   ├── vbt_indicator_calculator.py   # Calculates indicators (MACD, CCI, RSI, etc.)
│   ├── strategy_loader.py            # Dynamically loads/reloads strategies from JSON
│   ├── signal_generator.py           # Evaluates entry/exit conditions
│   ├── live_trading_system.py        # Main orchestrator (ties all components)
│   └── start_live_trading.py         # Entry point script
│
│
├── strategies/                       # Strategy implementations
│   ├── __init__.py
│   ├── base.py                       # BaseStrategy abstract class
│   ├── macd_cci_27min.py             # Example: MACD+CCI on 27-min
│   ├── future_strategy_v2.py         # Placeholder for next strategy
│   └── yet_another.py                # Placeholder for another strategy
│
│
├── execution/                        # Order execution (copied from vector_bot)
│   ├── __init__.py
│   ├── crosstrade_client.py          # HTTP client for CrossTrade API
│   ├── order_manager.py              # Order lifecycle management
│   ├── signal_translator.py          # Convert signals → NT8 orders
│   └── executor.py                   # High-level execution wrapper
│
│
├── data/
│   ├── __init__.py
│   ├── data_adapter.py               # Converts Databento format → standard format
│   └── validation.py                 # Validates OHLCV data integrity
│
│
├── utils/
│   ├── __init__.py
│   ├── logging_system.py             # Centralized logging (ticks, bars, signals, orders)
│   ├── config_validator.py           # Validates JSON structure
│   ├── time_utils.py                 # Session awareness, timezone handling
│   └── errors.py                     # Custom exception classes
│
│
├── tests/
│   ├── __init__.py
│   ├── unit/
│   │   ├── __init__.py
│   │   ├── test_bar_aggregator.py
│   │   ├── test_vbt_indicator_calculator.py
│   │   ├── test_strategy_loader.py
│   │   ├── test_signal_generator.py
│   │   └── test_config_loader.py
│   ├── integration/
│   │   ├── __init__.py
│   │   ├── test_databento_to_bars.py
│   │   ├── test_bars_to_signals.py
│   │   └── test_full_pipeline.py
│   └── fixtures/
│       ├── sample_bars.py            # Test data
│       └── sample_indicators.py      # Test data
│
│
├── logs/
│   ├── .gitkeep                      # Git won't track empty dir otherwise
│   ├── live_trading_2025-11-16.log   # Daily log file
│   ├── signals.log                   # All signals generated
│   └── executions.log                # All orders submitted
│
│
├── scripts/
│   ├── start_live_trading.sh         # Bash wrapper (systemd-friendly)
│   ├── validate_config.py            # Pre-flight check
│   ├── test_databento_connection.py  # Verify Databento works
│   └── graceful_shutdown.py          # Clean shutdown handler
│
│
├── docs/
│   ├── ARCHITECTURE.md               # System design overview
│   ├── API_REFERENCE.md              # Component APIs
│   ├── DEPLOYMENT.md                 # Production deployment guide
│   ├── TROUBLESHOOTING.md            # Common issues & fixes
│   └── CONFIG_GUIDE.md               # How to configure strategies
│
│
└── venv/                             # Python virtual environment
    └── (ignore in git)
```

---

## Build Tasks Breakdown

### **Phase 1: Foundation Components** (4-5 hours)

These are the core data pipeline components that have no dependencies on each other.

#### **Task 1.1: DatabentoLiveFeed** 
**File:** `scanner/databento_live_feed.py`

**Description:** Connects to Databento WebSocket, receives 1-minute OHLCV bars, emits callbacks.

**Dependencies:**
- `databento` library
- `logging_system.py`
- `errors.py`

**Key Functions:**
```python
class DatabentoLiveFeed:
    def __init__(api_key, symbols, on_bar_callback, schema='ohlcv-1m')
    def connect() -> None
    def subscribe() -> None
    def stream() -> None  # Blocking
    def shutdown() -> None
    def _convert_message(msg) -> dict
```

**Testing:** Unit test with mock Databento client

**Output:** Working live feed that emits 1-min bars

---

#### **Task 1.2: BarAggregator**
**File:** `scanner/bar_aggregator.py`

**Description:** Takes 1-min OHLCV bars, resamples to multiple timeframes (3/6/15/27-min).

**Dependencies:**
- `pandas`
- `numpy`
- `logging_system.py`

**Key Functions:**
```python
class BarAggregator:
    def __init__(timeframes: list)
    def process_bar(symbol: str, bar_1min: dict) -> dict  # Returns {3: {...}, 27: {...}}
    def get_available_timeframes() -> list
    def add_timeframes(new_tfs: list) -> None  # Dynamic addition
    def get_bars(symbol: str, timeframe: int, n: int = 100) -> list
```

**Key Logic:**
- Session-aware resampling (respects market open/close)
- Tracks "incomplete" bars (currently being built for each TF)
- Returns only COMPLETED bars when timeframe boundary crossed
- Efficient: O(1) per bar processed

**Testing:** Unit tests with synthetic bar sequence

**Output:** Clean bar resampling with proper boundary detection

---

#### **Task 1.3: Configuration System**
**Files:** `config/live_trading_config.json` + `config/config_loader.py`

**Description:** JSON-based strategy/parameter configuration with validation.

**Dependencies:**
- `json`
- `utils/config_validator.py`
- `logging_system.py`

**Key Functions:**
```python
def load_config(path: str) -> dict
def validate_config(config: dict) -> bool
def get_strategy_config(config: dict, strategy_name: str) -> dict
```

**Config Structure (JSON):**
```json
{
  "databento": {
    "symbols": ["ES.c.0", "NQ.c.0"],
    "schema": "ohlcv-1m"
  },
  "strategies": {
    "macd_cci_27min": {
      "enabled": true,
      "class": "strategies.macd_cci_27min.MACDCCIStrategy",
      "timeframes": [1, 6, 27],
      "indicators_by_timeframe": {
        "27min": {
          "macd": {
            "parameters": {
              "fast": 12,
              "slow": 26,
              "signal": 9
            }
          }
        },
        "6min": {
          "cci": {
            "parameters": {
              "length": 35,
              "threshold": -100
            }
          }
        }
      }
    }
  },
  "execution": {
    "crosstrade_api_key": "${CROSSTRADE_API_KEY}",
    "crosstrade_base_url": "https://app.crosstrade.io/v1/api"
  }
}
```

**Validation Checks:**
- All required fields present
- Symbol format valid (e.g., ES.c.0)
- Strategy class exists and is importable
- Timeframes are positive integers
- Parameters are valid (no NaN, inf)
- No duplicate strategy names

**Output:** Validated config dict ready for system

---

### **Phase 2: Indicator & Signal Components** (3-4 hours)

#### **Task 2.1: VBT Indicator Calculator**
**File:** `scanner/vbt_indicator_calculator.py`

**Description:** Calculates indicators (MACD, CCI, RSI, etc.) based on strategy config. Uses vbt-sim-live patterns for consistency with backtests.

**Dependencies:**
- `vbt_sim_live` framework (from project)
- `pandas`
- `numpy`
- `talib` or similar
- `logging_system.py`

**Key Functions:**
```python
class VBTIndicatorCalculator:
    def __init__(symbol: str, strategy_config: dict)
    def update_bar(timeframe: int, bar: dict) -> dict
    def get_indicators(timeframe: int) -> dict
    def is_ready() -> bool
    def reset() -> None
```

**Behavior:**
- Maintains rolling windows of bars per timeframe (numpy arrays for speed)
- Updates only the LAST indicator value (not recalculating entire history)
- Returns indicators in format: `{'macd': 0.45, 'macd_signal': 0.38, 'cci': -102, ...}`
- Knows when it has enough bars to start generating signals (`is_ready()`)

**Testing:** Unit tests with synthetic bar sequences

**Output:** Fast, incremental indicator updates

---

#### **Task 2.2: Base Strategy Class**
**File:** `strategies/base.py`

**Description:** Abstract base class that all strategies inherit from.

**Dependencies:**
- `logging_system.py`

**Key Functions:**
```python
class BaseStrategy(ABC):
    def __init__(symbol: str, config: dict)
    @abstractmethod
    def check_conditions(indicators: dict) -> Optional[str]
    def update_parameters(new_config: dict) -> None
    def get_position() -> str  # 'FLAT', 'LONG', 'SHORT'
    def set_position(side: str) -> None
    def get_metadata() -> dict
```

**Output:** Template for all strategy implementations

---

#### **Task 2.3: Example Strategy Implementation**
**File:** `strategies/macd_cci_27min.py`

**Description:** Concrete implementation of MACD+CCI strategy as example.

**Dependencies:**
- `strategies/base.py`

**Key Functions:**
```python
class MACDCCIStrategy(BaseStrategy):
    def check_conditions(indicators: dict) -> Optional[str]:
        """Evaluate entry/exit conditions"""
        # Entry: 27min MACD > signal AND 6min CCI < threshold AND 1min close > open
        # Exit: 1min close < 20bar SMA OR 27min MACD < signal
```

**Output:** Usable strategy for live trading

---

#### **Task 2.4: Signal Generator**
**File:** `scanner/signal_generator.py`

**Description:** Evaluates all currently-loaded strategies, deduplicates signals, returns prioritized list.

**Dependencies:**
- `strategies/base.py`
- `logging_system.py`

**Key Functions:**
```python
class SignalGenerator:
    def __init__(strategies: list, executor)
    def on_bar_complete(timeframe: int, indicators: dict) -> list  # Returns [Signal, ...]
    def process_signals(signals: list) -> list  # Deduplication, filtering
```

**Deduplication Logic:**
- Don't emit multiple ENTRY signals while already LONG
- Don't emit multiple EXIT signals while FLAT
- Prevent same signal within N seconds (configurable)

**Output:** Clean, deduplicated signals ready for execution

---

### **Phase 3: System Integration** (2-3 hours)

#### **Task 3.1: Strategy Loader**
**File:** `scanner/strategy_loader.py`

**Description:** Watches JSON file, dynamically loads/reloads strategies without system restart.

**Dependencies:**
- `config/config_loader.py`
- `strategies/base.py`
- `scanner/bar_aggregator.py`
- `logging_system.py`

**Key Functions:**
```python
class StrategyLoader:
    def __init__(config_path: str, bar_aggregator: BarAggregator)
    def start_watching() -> None  # Runs in background thread
    def get_active_strategies() -> list
    def _check_and_reload() -> None  # Called every 5 seconds
    def _import_class(class_path: str) -> type
```

**Behavior:**
- Every 5 seconds: Check if JSON file changed
- If changed: Load new config, compare with current strategies
- Add new strategies: Instantiate, add to aggregator's timeframes
- Remove strategies: Delete from active list
- Update parameters: Reload existing strategies with new params
- No system restart needed

**Output:** Hot-reloadable strategy system

---

#### **Task 3.2: Live Trading System (Orchestrator)**
**File:** `scanner/live_trading_system.py`

**Description:** Main orchestrator that ties all components together.

**Dependencies:**
- All previous components
- `execution/executor.py`

**Key Functions:**
```python
class LiveTradingSystem:
    def __init__(config_path: str)
    def start() -> None  # Blocking, runs forever
    def on_bar(symbol: str, bar_1min: dict) -> None
    def shutdown() -> None
    def get_status() -> dict
```

**Flow:**
```
Databento Feed
    ↓ new 1-min bar
    ↓ on_bar(symbol, bar_1min)
    ↓
BarAggregator.process_bar()
    ↓ returns {3: {...}, 27: {...}}
    ↓
For each completed timeframe:
    ↓
    VBTIndicatorCalculator.update_bar()
        ↓ returns {'macd': X, 'cci': Y, ...}
        ↓
        SignalGenerator.on_bar_complete()
            ↓ returns ['BUY', 'SELL', None]
            ↓
            CrossTradeExecutor.submit_signal()
                ↓ HTTP POST → NT8
                ↓ log to executions.log
```

**Output:** Running live trading system

---

#### **Task 3.3: Entry Point Script**
**File:** `scanner/start_live_trading.py`

**Description:** Command-line entry point with argument parsing and safety checks.

**Key Functions:**
```python
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default='config/live_trading_config.json')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--loglevel', default='INFO')
    
    # Validation
    # Signal handlers (SIGTERM, SIGINT)
    # Initialize system
    # Start
```

**Output:** Safe entry point for production deployment

---

### **Phase 4: Testing & Validation** (2-3 hours)

#### **Task 4.1: Unit Tests**

**File:** `tests/unit/test_*.py`

**Test Coverage:**
- `test_bar_aggregator.py` - Resampling logic, boundary detection
- `test_vbt_indicator_calculator.py` - Indicator calculations, rolling windows
- `test_strategy_loader.py` - JSON loading, dynamic reloading
- `test_signal_generator.py` - Signal deduplication
- `test_config_loader.py` - Config validation

**Run:** `pytest tests/unit/ -v`

---

#### **Task 4.2: Integration Tests**

**File:** `tests/integration/test_*.py`

**Test Cases:**
- `test_databento_to_bars.py` - Feed → Aggregator
- `test_bars_to_signals.py` - Aggregator → Indicators → Signals
- `test_full_pipeline.py` - End-to-end with mock execution

**Run:** `pytest tests/integration/ -v`

---

### **Phase 5: Documentation** (1-2 hours)

#### **Task 5.1: Core Documentation**

**Files:**
- `docs/ARCHITECTURE.md` - System design, data flow
- `docs/API_REFERENCE.md` - All component APIs
- `docs/CONFIG_GUIDE.md` - How to create new strategies
- `docs/DEPLOYMENT.md` - Production deployment
- `docs/TROUBLESHOOTING.md` - Common issues

---

### **Phase 6: Utilities & Support** (1 hour)

#### **Task 6.1: Utilities**

**Files:**
- `utils/logging_system.py` - Centralized logging (DEBUG/INFO/WARNING/ERROR levels)
- `utils/config_validator.py` - JSON schema validation
- `utils/time_utils.py` - Market session awareness, timezone
- `utils/errors.py` - Custom exceptions
- `data/data_adapter.py` - Databento format → standard
- `data/validation.py` - OHLCV validation

---

## Dependencies

**Core Libraries:**
```
databento>=0.16.0          # Live data streaming
pandas>=2.0.0              # Data manipulation
numpy>=1.24.0              # Numerical computing
vectorbt-pro>=2.0.0        # Backtesting framework
requests>=2.31.0           # HTTP requests (CrossTrade)
python-dotenv>=1.0.0       # Environment variables
```

**Development Libraries:**
```
pytest>=7.0.0              # Testing
pytest-cov>=4.0.0          # Coverage
pytest-mock>=3.10.0        # Mocking
black>=23.0.0              # Code formatting
flake8>=6.0.0              # Linting
```

---

## Build Order & Dependencies

```
Phase 1 (Foundation)
├── utils/logging_system.py          (no dependencies)
├── utils/errors.py                  (no dependencies)
├── config/config_loader.py          (logging_system, errors)
├── scanner/databento_live_feed.py   (logging_system, errors)
├── scanner/bar_aggregator.py        (logging_system)
└── data/data_adapter.py             (logging_system)

Phase 2 (Logic)
├── strategies/base.py               (logging_system)
├── scanner/vbt_indicator_calculator.py (logging_system)
├── scanner/signal_generator.py      (base.py, logging_system)
└── strategies/macd_cci_27min.py     (base.py)

Phase 3 (Integration)
├── scanner/strategy_loader.py       (config_loader, base.py, bar_aggregator)
├── scanner/live_trading_system.py   (all Phase 1-2 components)
└── scanner/start_live_trading.py    (live_trading_system)

Phase 4 (Testing)
├── tests/unit/*
└── tests/integration/*

Phase 5 (Documentation)
└── docs/*
```

---

## Estimated Timeline

| Phase | Component | Estimate | Total |
|-------|-----------|----------|-------|
| 1 | Foundation (6 tasks) | 4-5h | 4-5h |
| 2 | Logic (4 tasks) | 3-4h | 7-9h |
| 3 | Integration (3 tasks) | 2-3h | 9-12h |
| 4 | Testing (2 tasks) | 2-3h | 11-15h |
| 5 | Documentation (1 task) | 1-2h | 12-17h |
| 6 | Utilities (1 task) | 1h | 13-18h |
| | **TOTAL** | | **13-18 hours** |

---

## Success Criteria

By end of Phase 3:
- ✅ Live system streams data without errors for 30+ minutes
- ✅ Strategies load dynamically without restart
- ✅ Indicators calculate correctly against backtested values
- ✅ Signals generate with proper deduplication
- ✅ Execution flow works (dry-run or paper trading)

By end of Phase 4:
- ✅ Unit test coverage >80%
- ✅ All integration tests pass
- ✅ End-to-end pipeline validated

By end of Phase 6:
- ✅ Full system ready for production deployment
- ✅ No manual restarts needed for strategy changes
- ✅ Comprehensive logging and monitoring
- ✅ Documented for maintenance

---

## Next Steps

1. **Review this plan** - Any changes needed?
2. **Confirm file structure** - Matches your expectations?
3. **Confirm build order** - Should we start with Phase 1?
4. **Confirm timeline** - 13-18 hours realistic?

Once approved, we can start building Phase 1 components.
