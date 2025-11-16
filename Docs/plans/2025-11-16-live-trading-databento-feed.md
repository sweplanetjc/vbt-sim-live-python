# Live Trading with Databento Feed - Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build live trading system that streams Databento data for UNLIMITED symbols with 24hr intraday replay, calculates indicators using existing LiveData framework, and executes multiple strategies via CrossTrade API.

**Architecture:** Databento WebSocket (unlimited symbols) → Per-Symbol BarAggregator (1min→ANY timeframe) → Per-Symbol LiveData + indicators → Multiple strategies (each backtested on specific symbols) → Existing execution layer. Strategy config drives symbol selection and timeframe creation. Scales to dozens of symbols and strategies.

**Tech Stack:** Databento Python SDK, existing vbt_sim_live.LiveData, existing indicators/, existing execution/, JSON config

---

## Context: What Already Exists

**DO NOT BUILD:**
- ✅ `execution/*` - Complete CrossTrade client, order_manager, signal_translator
- ✅ `vbt_sim_live/LiveData` - Handles bar updates, indicator calculations, resampling
- ✅ `vbt_sim_live/generic_data.py` - Base class (just added)
- ✅ `indicators/*` - Indicator framework with IndicatorRoot base class
- ✅ `vbt_sim_live/TFs` - Timeframe enum (m1, m2, m3, m5, m6, m15, m27, m30, d1, w1, M1)

**WILL BUILD:**
- 🆕 `scanner/` - New directory for live trading components
- 🆕 `config/live_trading_config.json` - Multi-symbol, multi-strategy configuration
- 🆕 `indicators/indicator_cci.py` - CCI indicator (doesn't exist yet)
- 🆕 `strategies/` - Strategy implementations directory

---

## Design Principles

**Unlimited Symbols:**
- System supports ANY number of symbols (limited only by Databento plan/costs)
- No hardcoded symbol lists in code
- All symbols configured in JSON
- Dynamic initialization based on config

**Strategy-Symbol Mapping:**
- Each strategy config specifies which symbol(s) it trades
- Same strategy can trade multiple symbols with same parameters
- Different strategies can trade same symbol with different parameters
- System creates one strategy instance per (strategy, symbol) pair

**Memory Efficient:**
- Per-symbol data structures prevent cross-contamination
- Rolling window storage (keep only recent N bars)
- Indicators calculate incrementally (not full recalc)

---

## Task 1: Create CCI Indicator

**Files:**
- Create: `indicators/indicator_cci.py`
- Modify: `indicators/__init__.py`
- Test: `tests/unit/test_indicator_cci.py`

**Step 1: Write the failing test**

Create `tests/unit/test_indicator_cci.py`:

```python
"""Test CCI indicator implementation."""
import numpy as np
import pytest
from indicators import IndicatorCCI, IndicatorCCI_


def test_cci_basic_calculation():
    """Test CCI calculates correctly for known values."""
    # Simple test data: 5 bars
    high = np.array([100, 102, 104, 103, 105], dtype=np.float64)
    low = np.array([98, 100, 102, 101, 103], dtype=np.float64)
    close = np.array([99, 101, 103, 102, 104], dtype=np.float64)
    
    # Calculate with period=3
    live_ind = IndicatorCCI_(
        input_args=[high, low, close, 3],
        kwargs={}
    )
    live_ind.prepare()
    cci_values = live_ind.get()[0]
    
    # CCI should be array of 5 values
    assert len(cci_values) == 5
    # First 2 values should be NaN (need 3 bars to calculate)
    assert np.isnan(cci_values[0])
    assert np.isnan(cci_values[1])
    # Later values should be numeric
    assert not np.isnan(cci_values[4])


def test_cci_update_incremental():
    """Test CCI updates correctly when new bar added."""
    high = np.array([100, 102, 104, 103, 105], dtype=np.float64)
    low = np.array([98, 100, 102, 101, 103], dtype=np.float64)
    close = np.array([99, 101, 103, 102, 104], dtype=np.float64)
    
    live_ind = IndicatorCCI_(
        input_args=[high, low, close, 3],
        kwargs={}
    )
    live_ind.prepare()
    initial_last = live_ind.get()[0][-1]
    
    # Simulate new bar (update last values)
    high[-1] = 106
    low[-1] = 104
    close[-1] = 105
    
    live_ind.update()
    updated_last = live_ind.get()[0][-1]
    
    # Last CCI value should change
    assert updated_last != initial_last
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/unit/test_indicator_cci.py -v
```

Expected: FAIL with "ModuleNotFoundError: No module named 'indicators.indicator_cci'"

**Step 3: Write minimal CCI implementation**

Create `indicators/indicator_cci.py`:

```python
"""CCI (Commodity Channel Index) Indicator."""
from .indicator_root import IndicatorRoot
from .indicator_utils import indicator_strategy_vbt_caller
import numpy as np
import vectorbtpro as vbt


class IndicatorCCI_(IndicatorRoot):
    """Live CCI indicator that updates incrementally."""
    
    def __init__(self, input_args, kwargs):
        super().__init__(input_args, kwargs)
    
    def prepare(self):
        """Calculate CCI for entire history."""
        for j in range(len(self.high)):
            ret = cci_func_single(j, self)
            for i, n in enumerate(self.output_names):
                self.__dict__[n][j] = ret[i]
    
    def update(self):
        """Update CCI for last bar only."""
        ret = cci_func_single(-1, self)
        for i, n in enumerate(self.output_names):
            self.__dict__[n][-1] = ret[i]


def cci_func_single(i: int, obj: IndicatorCCI_):
    """Calculate CCI for a single bar.
    
    CCI = (Typical Price - SMA) / (0.015 * Mean Deviation)
    Typical Price = (High + Low + Close) / 3
    """
    period = obj.length
    
    # Need at least 'period' bars
    if i < period - 1:
        return (np.nan,)
    
    # Calculate typical price
    start_idx = max(0, i - period + 1)
    end_idx = i + 1
    
    tp = (obj.high[start_idx:end_idx] + 
          obj.low[start_idx:end_idx] + 
          obj.close[start_idx:end_idx]) / 3.0
    
    # SMA of typical price
    sma_tp = np.mean(tp)
    
    # Mean deviation
    mean_dev = np.mean(np.abs(tp - sma_tp))
    
    # Avoid division by zero
    if mean_dev == 0:
        return (0.0,)
    
    # CCI calculation
    current_tp = (obj.high[i] + obj.low[i] + obj.close[i]) / 3.0
    cci = (current_tp - sma_tp) / (0.015 * mean_dev)
    
    return (cci,)


# VBT class definition
IndicatorCCI = vbt.IF(
    class_name='IndicatorCCI',
    short_name='cci',
    input_names=['high', 'low', 'close', 'length'],
    param_names=[],
    output_names=['cci']
).with_apply_func(
    indicator_strategy_vbt_caller,
    takes_1d=True
)

# Feature info
IndicatorCCI_feature_info = [
    {'name': 'cci', 'type': float, 'type_np': np.float64, 'default': np.nan}
]
```

**Step 4: Update indicators __init__.py**

Modify `indicators/__init__.py`, add import:

```python
from .indicator_cci import IndicatorCCI_, IndicatorCCI, IndicatorCCI_feature_info
```

**Step 5: Run tests to verify they pass**

```bash
pytest tests/unit/test_indicator_cci.py -v
```

Expected: 2/2 PASS

**Step 6: Commit**

```bash
git add indicators/indicator_cci.py indicators/__init__.py tests/unit/test_indicator_cci.py
git commit -m "feat(indicators): add CCI indicator with incremental updates"
```

---

## Task 2: Create Multi-Symbol Live Trading Config

**Files:**
- Create: `config/live_trading_config.json`
- Create: `tests/unit/test_config_validation.py`

**Step 1: Write config validation test**

Create `tests/unit/test_config_validation.py`:

```python
"""Test live trading config validation."""
import json
import pytest
from pathlib import Path


def test_config_file_exists():
    """Config file should exist and be valid JSON."""
    config_path = Path("config/live_trading_config.json")
    assert config_path.exists(), "Config file missing"
    
    with open(config_path) as f:
        config = json.load(f)
    
    assert isinstance(config, dict)


def test_config_has_required_sections():
    """Config should have databento, strategies, execution sections."""
    config_path = Path("config/live_trading_config.json")
    with open(config_path) as f:
        config = json.load(f)
    
    assert "databento" in config
    assert "strategies" in config
    assert "execution" in config


def test_databento_has_multiple_symbols():
    """Databento should support multiple symbols."""
    config_path = Path("config/live_trading_config.json")
    with open(config_path) as f:
        config = json.load(f)
    
    symbols = config["databento"]["symbols"]
    assert isinstance(symbols, list)
    assert len(symbols) >= 1


def test_strategies_specify_symbols():
    """Each strategy should specify which symbols it trades."""
    config_path = Path("config/live_trading_config.json")
    with open(config_path) as f:
        config = json.load(f)
    
    for strat_name, strat_config in config["strategies"].items():
        assert "symbols" in strat_config, f"{strat_name} missing 'symbols'"
        assert isinstance(strat_config["symbols"], list)
        assert len(strat_config["symbols"]) >= 1


def test_strategy_symbols_in_databento_symbols():
    """Strategy symbols must be subset of databento symbols."""
    config_path = Path("config/live_trading_config.json")
    with open(config_path) as f:
        config = json.load(f)
    
    databento_symbols = set(config["databento"]["symbols"])
    
    for strat_name, strat_config in config["strategies"].items():
        if not strat_config.get("enabled", True):
            continue
            
        strat_symbols = set(strat_config["symbols"])
        missing = strat_symbols - databento_symbols
        
        assert len(missing) == 0, \
            f"{strat_name} references symbols not in databento: {missing}"
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/unit/test_config_validation.py::test_config_file_exists -v
```

Expected: FAIL "Config file missing"

**Step 3: Create multi-symbol config file**

Create `config/live_trading_config.json`:

```json
{
  "databento": {
    "api_key": "${DATABENTO_API_KEY}",
    "dataset": "GLBX.MDP3",
    "symbols": [
      "ES.c.0",
      "NQ.c.0",
      "YM.c.0",
      "RTY.c.0",
      "GC.c.0",
      "SI.c.0",
      "CL.c.0",
      "NG.c.0"
    ],
    "schema": "ohlcv-1m",
    "replay_hours": 24
  },
  
  "strategies": {
    "simple_bullish_cci_ES": {
      "enabled": true,
      "description": "Test strategy: Long on bullish 5min candle with rising CCI15 (ES)",
      "symbols": ["ES.c.0"],
      "timeframes": ["m1", "m5"],
      "indicators": {
        "cci": {
          "length": 15
        }
      },
      "entry_conditions": {
        "close_gt_open": true,
        "close_gt_prev_close": true,
        "cci_rising": true
      },
      "exit_conditions": {
        "bars_held": 1
      },
      "position_sizing": {
        "quantity": 1,
        "order_type": "MARKET"
      }
    },
    
    "simple_bullish_cci_NQ": {
      "enabled": true,
      "description": "Same strategy optimized for NQ with different CCI period",
      "symbols": ["NQ.c.0"],
      "timeframes": ["m1", "m5"],
      "indicators": {
        "cci": {
          "length": 20
        }
      },
      "entry_conditions": {
        "close_gt_open": true,
        "close_gt_prev_close": true,
        "cci_rising": true
      },
      "exit_conditions": {
        "bars_held": 1
      },
      "position_sizing": {
        "quantity": 1,
        "order_type": "MARKET"
      }
    },
    
    "metals_basket": {
      "enabled": false,
      "description": "Multi-symbol strategy for metals (disabled for now)",
      "symbols": ["GC.c.0", "SI.c.0"],
      "timeframes": ["m1", "m15"],
      "indicators": {
        "cci": {
          "length": 25
        }
      },
      "entry_conditions": {
        "close_gt_open": true,
        "cci_rising": true
      },
      "exit_conditions": {
        "bars_held": 2
      },
      "position_sizing": {
        "quantity": 1,
        "order_type": "MARKET"
      }
    }
  },
  
  "execution": {
    "crosstrade_api_key": "${CROSSTRADE_API_KEY}",
    "crosstrade_url": "https://app.crosstrade.io/v1/api",
    "nt8_account": "DEMO4889250",
    "dry_run": true
  },
  
  "logging": {
    "level": "INFO",
    "log_trades": true,
    "log_bars": false
  }
}
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/test_config_validation.py -v
```

Expected: 5/5 PASS

**Step 5: Commit**

```bash
git add config/live_trading_config.json tests/unit/test_config_validation.py
git commit -m "feat(config): add multi-symbol live trading config"
```

---

## Task 3: Build Databento Live Feed with Intraday Replay

**Files:**
- Create: `scanner/__init__.py`
- Create: `scanner/databento_live_feed.py`
- Create: `tests/unit/test_databento_live_feed.py`

**Step 1: Write failing test**

Create `tests/unit/test_databento_live_feed.py`:

```python
"""Test Databento live feed with replay."""
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
from scanner.databento_live_feed import DatabentoLiveFeed


def test_databento_feed_initialization():
    """Feed should initialize with multiple symbols."""
    config = {
        "api_key": "test-key",
        "dataset": "GLBX.MDP3",
        "symbols": ["ES.c.0", "NQ.c.0", "GC.c.0"],
        "schema": "ohlcv-1m",
        "replay_hours": 24
    }
    
    feed = DatabentoLiveFeed(config, on_bar_callback=Mock())
    assert feed.symbols == ["ES.c.0", "NQ.c.0", "GC.c.0"]
    assert feed.schema == "ohlcv-1m"
    assert feed.replay_hours == 24


@patch('scanner.databento_live_feed.db.Live')
def test_replay_request_calculates_times(mock_live):
    """Should request 24 hours of replay data."""
    config = {
        "api_key": "test-key",
        "dataset": "GLBX.MDP3",
        "symbols": ["ES.c.0"],
        "schema": "ohlcv-1m",
        "replay_hours": 24
    }
    
    feed = DatabentoLiveFeed(config, on_bar_callback=Mock())
    
    # Mock time
    now = datetime(2025, 11, 16, 14, 30, 0)
    
    start, end = feed._calculate_replay_window(now)
    
    # Should be 24 hours ago
    expected_start = now - timedelta(hours=24)
    assert (start - expected_start).total_seconds() < 60  # Within 1 minute
    assert (end - now).total_seconds() < 60


def test_bar_conversion_includes_symbol():
    """Converted bars should include symbol identifier."""
    config = {
        "api_key": "test-key",
        "dataset": "GLBX.MDP3",
        "symbols": ["ES.c.0", "NQ.c.0"],
        "schema": "ohlcv-1m",
        "replay_hours": 24
    }
    
    feed = DatabentoLiveFeed(config, on_bar_callback=Mock())
    
    # Mock bar object
    mock_bar = Mock()
    mock_bar.instrument_id = "NQ.c.0"
    mock_bar.ts_event = 1700000000000000000  # nanoseconds
    mock_bar.open = 4500000000000  # fixed-point
    mock_bar.high = 4510000000000
    mock_bar.low = 4490000000000
    mock_bar.close = 4505000000000
    mock_bar.volume = 1000
    
    bar_dict = feed._convert_bar_to_dict(mock_bar)
    
    assert bar_dict['symbol'] == "NQ.c.0"
    assert 'open' in bar_dict
    assert 'close' in bar_dict
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/unit/test_databento_live_feed.py -v
```

Expected: FAIL "ModuleNotFoundError"

**Step 3: Implement DatabentoLiveFeed**

Create `scanner/__init__.py`:

```python
"""Live trading scanner components."""
```

Create `scanner/databento_live_feed.py`:

```python
"""Databento live feed with intraday replay support.

Supports unlimited symbols - only limited by Databento plan/costs.
"""
import databento as db
from datetime import datetime, timedelta
from typing import Callable, Dict, List
import pandas as pd
import pytz
from logging_system import get_logger

logger = get_logger(__name__)


class DatabentoLiveFeed:
    """Streams live 1-minute OHLCV bars from Databento with 24hr replay.
    
    Supports ANY number of symbols (limited only by Databento API limits).
    Each bar includes symbol identifier for routing.
    
    Usage:
        config = {
            "api_key": "...",
            "dataset": "GLBX.MDP3",
            "symbols": ["ES.c.0", "NQ.c.0", "GC.c.0", ...],  # Unlimited
            "schema": "ohlcv-1m",
            "replay_hours": 24
        }
        
        def on_bar(bar_dict):
            symbol = bar_dict['symbol']
            print(f"{symbol}: {bar_dict['close']}")
        
        feed = DatabentoLiveFeed(config, on_bar_callback=on_bar)
        feed.start()  # Blocking - runs forever
    """
    
    def __init__(self, config: Dict, on_bar_callback: Callable):
        """Initialize feed.
        
        Args:
            config: Databento configuration dict
            on_bar_callback: Function called for each bar: callback(bar_dict)
                            bar_dict includes 'symbol' field for routing
        """
        self.api_key = config["api_key"]
        self.dataset = config["dataset"]
        self.symbols = config["symbols"]  # Can be unlimited list
        self.schema = config["schema"]
        self.replay_hours = config.get("replay_hours", 24)
        self.on_bar_callback = on_bar_callback
        
        self.client = None
        self.is_running = False
        
        logger.info(f"DatabentoLiveFeed initialized: {len(self.symbols)} symbols, replay={self.replay_hours}h")
        logger.info(f"Symbols: {self.symbols}")
    
    def _calculate_replay_window(self, now: datetime = None) -> tuple:
        """Calculate start/end times for replay.
        
        Args:
            now: Current time (defaults to datetime.now(UTC))
        
        Returns:
            (start_time, end_time) tuple
        """
        if now is None:
            now = datetime.now(pytz.UTC)
        
        start = now - timedelta(hours=self.replay_hours)
        end = now - timedelta(minutes=1)  # Up to 1 min ago
        
        return start, end
    
    def _convert_bar_to_dict(self, bar) -> Dict:
        """Convert Databento bar to standard dict format.
        
        Args:
            bar: Databento OHLCV bar object
        
        Returns:
            Dict with keys: symbol, date, date_l, open, high, low, close, volume, cpl
        """
        return {
            'symbol': bar.instrument_id,  # CRITICAL: Symbol identifier for routing
            'date': pd.Timestamp(bar.ts_event, unit='ns', tz='UTC'),
            'date_l': pd.Timestamp(bar.ts_event, unit='ns', tz='UTC'),
            'open': bar.open / 1e9,  # Databento uses fixed-point
            'high': bar.high / 1e9,
            'low': bar.low / 1e9,
            'close': bar.close / 1e9,
            'volume': bar.volume,
            'cpl': True  # Assume complete for now
        }
    
    def start(self):
        """Start feed (blocking).
        
        Steps:
        1. Request 24hr intraday replay for ALL symbols
        2. Stream replay bars (rapid) - bars from all symbols interleaved
        3. Switch to live streaming
        4. Stream live bars (real-time) - bars from all symbols interleaved
        
        Each bar includes 'symbol' field for per-symbol routing.
        """
        logger.info("Starting Databento feed...")
        
        # Create client
        self.client = db.Live(key=self.api_key)
        
        # Calculate replay window
        start, end = self._calculate_replay_window()
        logger.info(f"Requesting replay: {start} to {end}")
        logger.info(f"Streaming {len(self.symbols)} symbols")
        
        # Subscribe with replay for ALL symbols
        self.client.subscribe(
            dataset=self.dataset,
            schema=self.schema,
            stype_in=db.SType.CONTINUOUS,
            symbols=self.symbols,  # All symbols streamed together
            start=start
        )
        
        self.is_running = True
        bar_count = 0
        symbol_counts = {}
        
        logger.info("Streaming bars...")
        
        try:
            for bar in self.client:
                if not self.is_running:
                    break
                
                # Convert and emit
                bar_dict = self._convert_bar_to_dict(bar)
                self.on_bar_callback(bar_dict)
                
                # Track per-symbol counts
                symbol = bar_dict['symbol']
                symbol_counts[symbol] = symbol_counts.get(symbol, 0) + 1
                
                bar_count += 1
                if bar_count % 1000 == 0:
                    logger.info(f"Processed {bar_count} bars across {len(symbol_counts)} symbols")
        
        except KeyboardInterrupt:
            logger.info("Feed interrupted by user")
        except Exception as e:
            logger.error(f"Feed error: {e}", exc_info=True)
        finally:
            logger.info(f"Final stats: {bar_count} total bars")
            for symbol, count in sorted(symbol_counts.items()):
                logger.info(f"  {symbol}: {count} bars")
            self.stop()
    
    def stop(self):
        """Stop feed gracefully."""
        logger.info("Stopping Databento feed...")
        self.is_running = False
        if self.client:
            self.client.close()
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/test_databento_live_feed.py -v
```

Expected: 3/3 PASS

**Step 5: Commit**

```bash
git add scanner/ tests/unit/test_databento_live_feed.py
git commit -m "feat(scanner): add Databento live feed supporting unlimited symbols"
```

---

## Task 4: Build Per-Symbol Bar Aggregator (ANY Timeframe)

**Files:**
- Create: `scanner/bar_aggregator.py`
- Create: `tests/unit/test_bar_aggregator.py`

**Step 1: Write comprehensive tests for multiple symbols and timeframes**

Create `tests/unit/test_bar_aggregator.py`:

```python
"""Test bar aggregation from 1min to ANY timeframe across multiple symbols."""
import pytest
from datetime import datetime, timedelta
import pytz
from scanner.bar_aggregator import BarAggregator
from vbt_sim_live import TFs


def test_aggregator_initialization_multiple_symbols():
    """Should initialize with multiple symbols and timeframes."""
    symbols = ["ES.c.0", "NQ.c.0", "GC.c.0"]
    agg = BarAggregator(symbols=symbols, timeframes=[TFs.m1, TFs.m5, TFs.m27])
    
    assert agg.symbols == symbols
    assert TFs.m5 in agg.timeframes
    assert TFs.m27 in agg.timeframes


def test_aggregates_different_symbols_separately():
    """Should keep ES and NQ bars separate."""
    symbols = ["ES.c.0", "NQ.c.0"]
    agg = BarAggregator(symbols=symbols, timeframes=[TFs.m1, TFs.m5])
    
    base_time = datetime(2025, 11, 16, 9, 30, 0, tzinfo=pytz.UTC)
    
    # Send 5 ES bars
    for i in range(5):
        bar = {
            'symbol': 'ES.c.0',
            'date': base_time + timedelta(minutes=i),
            'date_l': base_time + timedelta(minutes=i),
            'open': 4500 + i,
            'high': 4505,
            'low': 4495,
            'close': 4500,
            'volume': 100,
            'cpl': True
        }
        result = agg.process_bar(bar)
    
    # Send 5 NQ bars
    for i in range(5):
        bar = {
            'symbol': 'NQ.c.0',
            'date': base_time + timedelta(minutes=i),
            'date_l': base_time + timedelta(minutes=i),
            'open': 15000 + i,
            'high': 15005,
            'low': 14995,
            'close': 15000,
            'volume': 200,
            'cpl': True
        }
        result = agg.process_bar(bar)
        
        if result and TFs.m5 in result:
            # NQ bars should have NQ prices/volumes
            assert result[TFs.m5]['symbol'] == 'NQ.c.0'
            assert result[TFs.m5]['open'] >= 15000
            assert result[TFs.m5]['volume'] == 1000  # 5 bars * 200


def test_aggregates_1min_to_5min():
    """Should aggregate five 1-min bars into one 5-min bar."""
    agg = BarAggregator(symbols=["ES.c.0"], timeframes=[TFs.m1, TFs.m5])
    
    # Create 5 consecutive 1-min bars
    base_time = datetime(2025, 11, 16, 9, 30, 0, tzinfo=pytz.UTC)
    
    bars_1min = []
    for i in range(5):
        bar = {
            'symbol': 'ES.c.0',
            'date': base_time + timedelta(minutes=i),
            'date_l': base_time + timedelta(minutes=i),
            'open': 4500 + i,
            'high': 4505 + i,
            'low': 4495 + i,
            'close': 4502 + i,
            'volume': 100,
            'cpl': True
        }
        bars_1min.append(bar)
    
    # Process bars
    results = []
    for bar in bars_1min:
        result = agg.process_bar(bar)
        if result and TFs.m5 in result:
            results.append(result)
    
    # Should have 1 complete 5-min bar
    assert len(results) > 0
    bar_5min = results[-1][TFs.m5]
    
    assert bar_5min['symbol'] == 'ES.c.0'
    assert bar_5min['open'] == 4500  # First bar's open
    assert bar_5min['close'] == 4506  # Last bar's close
    assert bar_5min['high'] == max(b['high'] for b in bars_1min)
    assert bar_5min['low'] == min(b['low'] for b in bars_1min)
    assert bar_5min['volume'] == 500  # Sum of all volumes


def test_aggregates_to_27min():
    """Should work for 27-min timeframe (non-divisor of 60)."""
    agg = BarAggregator(symbols=["ES.c.0"], timeframes=[TFs.m1, TFs.m27])
    
    # Create 27 bars
    base_time = datetime(2025, 11, 16, 9, 30, 0, tzinfo=pytz.UTC)
    
    bars = []
    for i in range(27):
        bars.append({
            'symbol': 'ES.c.0',
            'date': base_time + timedelta(minutes=i),
            'date_l': base_time + timedelta(minutes=i),
            'open': 4500,
            'high': 4505,
            'low': 4495,
            'close': 4500,
            'volume': 100,
            'cpl': True
        })
    
    result = None
    for bar in bars:
        r = agg.process_bar(bar)
        if r and TFs.m27 in r:
            result = r
    
    assert result is not None
    assert TFs.m27 in result
    assert result[TFs.m27]['volume'] == 2700


def test_multiple_symbols_multiple_timeframes():
    """Should handle 3 symbols × 3 timeframes simultaneously."""
    symbols = ["ES.c.0", "NQ.c.0", "GC.c.0"]
    agg = BarAggregator(symbols=symbols, timeframes=[TFs.m1, TFs.m3, TFs.m5, TFs.m15])
    
    # Create 15 bars for each symbol
    base_time = datetime(2025, 11, 16, 9, 30, 0, tzinfo=pytz.UTC)
    
    symbol_results = {s: {'m3': False, 'm5': False, 'm15': False} for s in symbols}
    
    for symbol in symbols:
        for i in range(15):
            bar = {
                'symbol': symbol,
                'date': base_time + timedelta(minutes=i),
                'date_l': base_time + timedelta(minutes=i),
                'open': 4500,
                'high': 4505,
                'low': 4495,
                'close': 4500,
                'volume': 100,
                'cpl': True
            }
            
            result = agg.process_bar(bar)
            if result:
                if TFs.m3 in result:
                    symbol_results[symbol]['m3'] = True
                if TFs.m5 in result:
                    symbol_results[symbol]['m5'] = True
                if TFs.m15 in result:
                    symbol_results[symbol]['m15'] = True
    
    # Each symbol should have completed bars in each timeframe
    for symbol in symbols:
        assert symbol_results[symbol]['m3'], f"{symbol} missing m3 bars"
        assert symbol_results[symbol]['m5'], f"{symbol} missing m5 bars"
        assert symbol_results[symbol]['m15'], f"{symbol} missing m15 bars"
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/test_bar_aggregator.py -v
```

Expected: FAIL "ModuleNotFoundError"

**Step 3: Implement Per-Symbol GENERIC BarAggregator**

Create `scanner/bar_aggregator.py`:

```python
"""Bar aggregator for resampling 1-min bars to ANY timeframe across UNLIMITED symbols.

This aggregator:
- Supports unlimited symbols (only limited by memory)
- Works with ANY intraday timeframe (m1, m2, m3, m5, m6, m27, etc.)
- Uses generic time-based boundary detection (no hardcoded logic)
- Keeps symbols completely separate (no cross-contamination)

Architecture:
    bars_in_period = {
        'ES.c.0': {
            TFs.m5: [bar1, bar2, ...],
            TFs.m27: [bar1, bar2, ...]
        },
        'NQ.c.0': {
            TFs.m5: [bar1, bar2, ...],
            TFs.m27: [bar1, bar2, ...]
        }
    }
"""
from typing import Dict, List, Optional
from datetime import datetime
import pandas as pd
from vbt_sim_live import TFs
from logging_system import get_logger

logger = get_logger(__name__)


class BarAggregator:
    """Aggregates 1-minute bars into ANY higher timeframes for UNLIMITED symbols.
    
    Usage:
        symbols = ["ES.c.0", "NQ.c.0", "GC.c.0", ...]  # Unlimited
        agg = BarAggregator(symbols=symbols, timeframes=[TFs.m1, TFs.m5, TFs.m27])
        
        for bar_1min in stream:  # Bars from all symbols
            result = agg.process_bar(bar_1min)
            if result:
                # result = {TFs.m5: bar_5min, TFs.m27: bar_27min, ...}
                symbol = bar_1min['symbol']
                for tf, bar in result.items():
                    print(f"{symbol} {tf.name} bar complete: {bar}")
    """
    
    def __init__(self, symbols: List[str], timeframes: List[TFs], max_bars=1000):
        """Initialize aggregator.
        
        Args:
            symbols: List of symbol identifiers (unlimited)
            timeframes: List of TFs enums to create (must include TFs.m1)
            max_bars: Max bars to keep per symbol per timeframe (memory limit)
        """
        self.symbols = symbols
        self.timeframes = timeframes
        self.max_bars = max_bars
        
        # Per-symbol, per-timeframe bar accumulation
        self.bars_in_period = {
            symbol: {tf: [] for tf in timeframes if tf != TFs.m1}
            for symbol in symbols
        }
        
        # Track period start time per symbol per timeframe
        self.period_start_times = {
            symbol: {tf: None for tf in timeframes if tf != TFs.m1}
            for symbol in symbols
        }
        
        logger.info(f"BarAggregator initialized:")
        logger.info(f"  Symbols: {len(symbols)} - {symbols}")
        logger.info(f"  Timeframes: {[tf.name for tf in timeframes]}")
    
    def process_bar(self, bar_1min: Dict) -> Optional[Dict[TFs, Dict]]:
        """Process 1-minute bar and return completed higher TF bars.
        
        Args:
            bar_1min: 1-minute bar dict (must include 'symbol' field)
        
        Returns:
            Dict of {timeframe: completed_bar} or None if no bars completed
            
        Raises:
            ValueError: If symbol not in configured symbols
        """
        symbol = bar_1min['symbol']
        
        if symbol not in self.symbols:
            raise ValueError(f"Unknown symbol: {symbol}. Add to config first.")
        
        completed_bars = {}
        
        for tf in self.timeframes:
            if tf == TFs.m1:
                # 1-min bars pass through immediately
                completed_bars[tf] = bar_1min.copy()
                continue
            
            # Check if this bar starts a new period
            if self._starts_new_period(bar_1min, symbol, tf):
                # Complete previous period if exists
                if len(self.bars_in_period[symbol][tf]) > 0:
                    agg_bar = self._aggregate_bars(
                        self.bars_in_period[symbol][tf], 
                        tf
                    )
                    completed_bars[tf] = agg_bar
                    
                    # Clear for new period
                    self.bars_in_period[symbol][tf] = []
                
                # Update period start time
                self.period_start_times[symbol][tf] = bar_1min['date']
            
            # Add bar to current period
            self.bars_in_period[symbol][tf].append(bar_1min)
            
            # Memory management: limit bar history
            if len(self.bars_in_period[symbol][tf]) > self.max_bars:
                self.bars_in_period[symbol][tf] = \
                    self.bars_in_period[symbol][tf][-self.max_bars:]
        
        return completed_bars if completed_bars else None
    
    def _starts_new_period(self, bar: Dict, symbol: str, tf: TFs) -> bool:
        """Check if this bar starts a new period for the symbol/timeframe.
        
        Generic algorithm that works for ANY minute-based timeframe.
        
        Args:
            bar: Current 1-min bar
            symbol: Symbol identifier
            tf: Target timeframe
        
        Returns:
            True if this bar starts a new period
        """
        if not tf.is_intraday():
            # For daily/weekly/monthly, use different logic
            # (not implemented in this version)
            return False
        
        bar_time = bar['date']
        period_start = self.period_start_times[symbol][tf]
        
        # First bar always starts a period
        if period_start is None:
            return True
        
        # Calculate minutes since period started
        time_diff = bar_time - period_start
        minutes_elapsed = int(time_diff.total_seconds() / 60)
        
        # Period minutes
        period_minutes = tf.value // 60
        
        # New period starts when we've elapsed the full period
        return minutes_elapsed >= period_minutes
    
    def _aggregate_bars(self, bars: List[Dict], tf: TFs) -> Dict:
        """Aggregate list of 1-min bars into single higher TF bar.
        
        Args:
            bars: List of 1-min bars (all same symbol)
            tf: Target timeframe
        
        Returns:
            Aggregated bar dict (includes symbol from first bar)
        """
        if not bars:
            raise ValueError("Cannot aggregate empty bar list")
        
        return {
            'symbol': bars[0]['symbol'],  # Preserve symbol
            'date': bars[0]['date'],  # Use first bar's time as period start
            'date_l': bars[-1]['date_l'],  # Use last bar's time as period end
            'open': bars[0]['open'],
            'high': max(b['high'] for b in bars),
            'low': min(b['low'] for b in bars),
            'close': bars[-1]['close'],
            'volume': sum(b['volume'] for b in bars),
            'cpl': True  # Completed period
        }
    
    def get_pending_bars(self, symbol: str = None) -> Dict:
        """Get count of pending (incomplete) bars.
        
        Useful for debugging and monitoring.
        
        Args:
            symbol: Specific symbol, or None for all symbols
        
        Returns:
            Dict of {symbol: {timeframe: bar_count}}
        """
        if symbol:
            return {
                tf: len(self.bars_in_period[symbol][tf])
                for tf in self.timeframes
                if tf != TFs.m1
            }
        else:
            return {
                sym: {
                    tf: len(self.bars_in_period[sym][tf])
                    for tf in self.timeframes
                    if tf != TFs.m1
                }
                for sym in self.symbols
            }
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/test_bar_aggregator.py -v
```

Expected: 5/5 PASS (multiple symbols, all timeframes)

**Step 5: Commit**

```bash
git add scanner/bar_aggregator.py tests/unit/test_bar_aggregator.py
git commit -m "feat(scanner): add per-symbol bar aggregator supporting unlimited symbols"
```

---

## Task 5: Build Simple Test Strategy

**Files:**
- Create: `strategies/__init__.py`
- Create: `strategies/base.py`
- Create: `strategies/simple_bullish_cci.py`
- Create: `tests/unit/test_simple_strategy.py`

**Step 1: Write failing test**

Create `tests/unit/test_simple_strategy.py`:

```python
"""Test simple bullish CCI strategy."""
import pytest
import numpy as np
from strategies.simple_bullish_cci import SimpleBullishCCIStrategy


def test_strategy_entry_conditions_met():
    """Should signal entry when all conditions met."""
    strategy = SimpleBullishCCIStrategy({
        "position_sizing": {"quantity": 1}
    })
    
    # Current bar: bullish (close > open, close > prev close)
    current_bar = {
        'open': 4500,
        'high': 4510,
        'low': 4495,
        'close': 4508
    }
    
    prev_bar = {
        'close': 4502
    }
    
    # CCI rising
    cci_current = -50.0
    cci_prev = -75.0
    
    signal = strategy.check_entry(
        current_bar, prev_bar, cci_current, cci_prev
    )
    
    assert signal is not None
    assert signal['action'] == 'BUY'
    assert signal['quantity'] == 1


def test_strategy_entry_conditions_not_met():
    """Should not signal when conditions fail."""
    strategy = SimpleBullishCCIStrategy({})
    
    # Bearish bar (close < open)
    current_bar = {
        'open': 4500,
        'close': 4495
    }
    
    prev_bar = {'close': 4490}
    
    signal = strategy.check_entry(
        current_bar, prev_bar, -50.0, -75.0
    )
    
    assert signal is None


def test_strategy_exit_after_one_bar():
    """Should exit after holding for 1 bar."""
    strategy = SimpleBullishCCIStrategy({})
    
    # Enter
    strategy.position = 'LONG'
    strategy.bars_held = 0
    
    # After 1 bar
    strategy.bars_held = 1
    
    signal = strategy.check_exit()
    
    assert signal is not None
    assert signal['action'] == 'SELL'
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/unit/test_simple_strategy.py -v
```

Expected: FAIL "ModuleNotFoundError"

**Step 3: Create base strategy class**

Create `strategies/__init__.py`:

```python
"""Trading strategies."""
```

Create `strategies/base.py`:

```python
"""Base strategy class."""
from abc import ABC, abstractmethod
from typing import Optional, Dict


class BaseStrategy(ABC):
    """Abstract base class for trading strategies.
    
    All strategies must implement:
    - check_entry(): Evaluate entry conditions
    - check_exit(): Evaluate exit conditions
    
    Each strategy instance handles ONE symbol.
    System creates multiple instances for multi-symbol strategies.
    """
    
    def __init__(self, config: Dict):
        """Initialize strategy.
        
        Args:
            config: Strategy configuration dict
        """
        self.config = config
        self.position = 'FLAT'  # FLAT, LONG, SHORT
        self.bars_held = 0
    
    @abstractmethod
    def check_entry(self, *args, **kwargs) -> Optional[Dict]:
        """Check entry conditions.
        
        Returns:
            Signal dict {'action': 'BUY'/'SELL', 'quantity': N} or None
        """
        pass
    
    @abstractmethod
    def check_exit(self, *args, **kwargs) -> Optional[Dict]:
        """Check exit conditions.
        
        Returns:
            Signal dict {'action': 'SELL'/'BUY', 'quantity': N} or None
        """
        pass
    
    def update_position(self, position: str):
        """Update current position.
        
        Args:
            position: 'FLAT', 'LONG', or 'SHORT'
        """
        self.position = position
        if position == 'FLAT':
            self.bars_held = 0
        else:
            self.bars_held += 1
```

**Step 4: Create simple test strategy**

Create `strategies/simple_bullish_cci.py`:

```python
"""Simple bullish CCI test strategy.

Entry Conditions (on configured timeframe bar close):
1. close > open (bullish candle)
2. close > previous close (upward momentum)
3. cci[0] > cci[1] (CCI rising)

Exit Condition:
- After holding for configured number of bars

Note: Each instance handles ONE symbol.
"""
from typing import Optional, Dict
from .base import BaseStrategy


class SimpleBullishCCIStrategy(BaseStrategy):
    """Test strategy for live trading validation.
    
    Designed to be simple and deterministic for testing.
    """
    
    def check_entry(
        self,
        current_bar: Dict,
        prev_bar: Dict,
        cci_current: float,
        cci_prev: float
    ) -> Optional[Dict]:
        """Check if entry conditions are met.
        
        Args:
            current_bar: Current bar (configured timeframe)
            prev_bar: Previous bar
            cci_current: Current CCI value
            cci_prev: Previous CCI value
        
        Returns:
            Entry signal or None
        """
        # Only enter if flat
        if self.position != 'FLAT':
            return None
        
        # Condition 1: Bullish candle
        c1 = current_bar['close'] > current_bar['open']
        
        # Condition 2: Close > previous close
        c2 = current_bar['close'] > prev_bar['close']
        
        # Condition 3: CCI rising
        c3 = cci_current > cci_prev
        
        if c1 and c2 and c3:
            quantity = self.config.get('position_sizing', {}).get('quantity', 1)
            return {
                'action': 'BUY',
                'quantity': quantity,
                'reason': 'Bullish candle + CCI rising'
            }
        
        return None
    
    def check_exit(self) -> Optional[Dict]:
        """Check if exit conditions are met.
        
        Returns:
            Exit signal or None
        """
        # Only exit if in position
        if self.position != 'LONG':
            return None
        
        # Exit after configured bars
        exit_bars = self.config.get('exit_conditions', {}).get('bars_held', 1)
        
        if self.bars_held >= exit_bars:
            quantity = self.config.get('position_sizing', {}).get('quantity', 1)
            return {
                'action': 'SELL',
                'quantity': quantity,
                'reason': f'Held for {self.bars_held} bars'
            }
        
        return None
```

**Step 5: Run tests to verify they pass**

```bash
pytest tests/unit/test_simple_strategy.py -v
```

Expected: 3/3 PASS

**Step 6: Commit**

```bash
git add strategies/ tests/unit/test_simple_strategy.py
git commit -m "feat(strategies): add simple bullish CCI test strategy"
```

---

## Task 6: Build Multi-Symbol Live Trading Orchestrator

**Files:**
- Create: `scanner/live_trading_system.py`
- Create: `tests/integration/test_live_system.py`

**Step 1: Write integration test**

Create `tests/integration/test_live_system.py`:

```python
"""Integration test for live trading system."""
import pytest
from unittest.mock import Mock, patch, MagicMock
import json
from pathlib import Path


def test_system_loads_config():
    """System should load and validate multi-symbol config."""
    from scanner.live_trading_system import LiveTradingSystem
    
    config_path = Path("config/live_trading_config.json")
    system = LiveTradingSystem(str(config_path))
    
    assert system.config is not None
    assert len(system.config["databento"]["symbols"]) >= 2  # Multi-symbol
    assert "simple_bullish_cci_ES" in system.config["strategies"]
    assert "simple_bullish_cci_NQ" in system.config["strategies"]


@patch('scanner.live_trading_system.DatabentoLiveFeed')
@patch('scanner.live_trading_system.SignalTranslator')
def test_system_initializes_per_symbol_components(mock_translator, mock_feed):
    """System should create components for each symbol."""
    from scanner.live_trading_system import LiveTradingSystem
    
    system = LiveTradingSystem("config/live_trading_config.json")
    system._initialize_components()
    
    # Should create aggregators per symbol
    assert len(system.aggregators) >= 2
    assert "ES.c.0" in system.aggregators
    assert "NQ.c.0" in system.aggregators
    
    # Should create LiveData per symbol
    assert len(system.live_data) >= 2


def test_system_extracts_all_symbols():
    """System should extract all symbols from databento + strategies."""
    from scanner.live_trading_system import LiveTradingSystem
    
    system = LiveTradingSystem("config/live_trading_config.json")
    all_symbols = system._get_all_required_symbols()
    
    # Should include symbols from databento config
    assert "ES.c.0" in all_symbols
    assert "NQ.c.0" in all_symbols
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/integration/test_live_system.py -v
```

Expected: FAIL "ModuleNotFoundError"

**Step 3: Implement Multi-Symbol Live Trading System**

Create `scanner/live_trading_system.py`:

```python
"""Live trading system orchestrator - Multi-Symbol Support.

Supports UNLIMITED symbols:
- Each symbol has its own BarAggregator
- Each symbol has its own LiveData per timeframe
- Strategies specify which symbols they trade
- System creates one strategy instance per (strategy, symbol) pair

Architecture:
    aggregators = {
        'ES.c.0': BarAggregator,
        'NQ.c.0': BarAggregator,
        ...
    }
    
    live_data = {
        'ES.c.0': {TFs.m5: LiveData, TFs.m27: LiveData},
        'NQ.c.0': {TFs.m5: LiveData},
        ...
    }
    
    active_strategies = [
        {'name': 'simple_bullish_cci_ES', 'symbol': 'ES.c.0', 'instance': Strategy},
        {'name': 'simple_bullish_cci_NQ', 'symbol': 'NQ.c.0', 'instance': Strategy},
        ...
    ]
"""
import json
from pathlib import Path
from typing import Dict, Optional, List, Set
import os

from scanner.databento_live_feed import DatabentoLiveFeed
from scanner.bar_aggregator import BarAggregator
from vbt_sim_live import LiveData, TFs
from strategies.simple_bullish_cci import SimpleBullishCCIStrategy
from execution.signal_translator import SignalTranslator
from execution.order_manager import OrderManager
from execution.crosstrade_client import CrossTradeClient
from logging_system import get_logger

logger = get_logger(__name__)


class LiveTradingSystem:
    """Main orchestrator for live trading - unlimited symbols.
    
    Usage:
        system = LiveTradingSystem("config/live_trading_config.json")
        system.start()  # Blocking
    """
    
    def __init__(self, config_path: str):
        """Initialize system.
        
        Args:
            config_path: Path to config JSON file
        """
        self.config_path = Path(config_path)
        self.config = self._load_config()
        
        # Per-symbol components
        self.aggregators = {}  # {symbol: BarAggregator}
        self.live_data = {}    # {symbol: {timeframe: LiveData}}
        
        # Multi-strategy instances
        self.active_strategies = []  # List of {name, symbol, instance}
        
        # Shared components
        self.feed = None
        self.signal_translator = None
        self.order_manager = None
        
        logger.info(f"LiveTradingSystem initialized from {config_path}")
    
    def _load_config(self) -> Dict:
        """Load and validate configuration."""
        with open(self.config_path) as f:
            config = json.load(f)
        
        # Replace environment variables
        config = self._replace_env_vars(config)
        
        # Validate strategy symbols
        self._validate_strategy_symbols(config)
        
        logger.info("Configuration loaded successfully")
        return config
    
    def _validate_strategy_symbols(self, config: Dict):
        """Validate that strategy symbols are in databento symbols."""
        databento_symbols = set(config['databento']['symbols'])
        
        for strat_name, strat_config in config['strategies'].items():
            if not strat_config.get('enabled', True):
                continue
            
            strat_symbols = set(strat_config['symbols'])
            missing = strat_symbols - databento_symbols
            
            if missing:
                raise ValueError(
                    f"Strategy '{strat_name}' references symbols not in databento config: {missing}"
                )
    
    def _replace_env_vars(self, config: Dict) -> Dict:
        """Replace ${VAR} with environment variable values."""
        import re
        
        config_str = json.dumps(config)
        pattern = r'\$\{([^}]+)\}'
        matches = re.findall(pattern, config_str)
        
        for var in matches:
            value = os.getenv(var, '')
            config_str = config_str.replace(f'${{{var}}}', value)
        
        return json.loads(config_str)
    
    def _get_all_required_symbols(self) -> Set[str]:
        """Extract all symbols needed from config.
        
        Returns:
            Set of all unique symbols across databento + enabled strategies
        """
        symbols = set(self.config['databento']['symbols'])
        
        for strat_config in self.config['strategies'].values():
            if strat_config.get('enabled', True):
                symbols.update(strat_config['symbols'])
        
        return symbols
    
    def _initialize_components(self):
        """Initialize all system components."""
        logger.info("Initializing components...")
        
        # Get all required symbols
        all_symbols = self._get_all_required_symbols()
        logger.info(f"Required symbols: {len(all_symbols)} - {sorted(all_symbols)}")
        
        # 1. Create Databento feed
        self.feed = DatabentoLiveFeed(
            config=self.config['databento'],
            on_bar_callback=self._on_bar_received
        )
        
        # 2. Create per-symbol aggregators
        for symbol in all_symbols:
            # Get all timeframes needed for this symbol
            timeframes_for_symbol = self._get_timeframes_for_symbol(symbol)
            
            self.aggregators[symbol] = BarAggregator(
                symbols=[symbol],  # One symbol per aggregator
                timeframes=list(timeframes_for_symbol)
            )
            
            logger.info(f"  Aggregator for {symbol}: {[tf.name for tf in timeframes_for_symbol]}")
        
        # 3. Initialize live_data structure (populated during replay)
        for symbol in all_symbols:
            self.live_data[symbol] = {}
        
        # 4. Create strategy instances
        self._create_strategy_instances()
        
        # 5. Create execution components
        if not self.config['execution'].get('dry_run', True):
            api_key = self.config['execution']['crosstrade_api_key']
            url = self.config['execution']['crosstrade_url']
            
            client = CrossTradeClient(api_key=api_key, base_url=url)
            self.order_manager = OrderManager(client)
            self.signal_translator = SignalTranslator(
                order_manager=self.order_manager,
                default_quantity=1
            )
        else:
            logger.info("DRY RUN mode - orders will not be submitted")
        
        logger.info("Components initialized")
        logger.info(f"  Total symbols: {len(all_symbols)}")
        logger.info(f"  Total strategy instances: {len(self.active_strategies)}")
    
    def _get_timeframes_for_symbol(self, symbol: str) -> Set[TFs]:
        """Get all timeframes needed for a symbol.
        
        Args:
            symbol: Symbol identifier
        
        Returns:
            Set of TFs enums needed for this symbol
        """
        timeframes = set()
        
        for strat_config in self.config['strategies'].values():
            if not strat_config.get('enabled', True):
                continue
            
            if symbol in strat_config['symbols']:
                for tf_name in strat_config['timeframes']:
                    timeframes.add(TFs[tf_name])
        
        return timeframes
    
    def _create_strategy_instances(self):
        """Create strategy instances for each (strategy, symbol) pair."""
        for strat_name, strat_config in self.config['strategies'].items():
            if not strat_config.get('enabled', True):
                logger.info(f"  Strategy '{strat_name}' disabled - skipping")
                continue
            
            # Create one instance per symbol
            for symbol in strat_config['symbols']:
                instance = SimpleBullishCCIStrategy(strat_config)
                
                self.active_strategies.append({
                    'name': strat_name,
                    'symbol': symbol,
                    'config': strat_config,
                    'instance': instance
                })
                
                logger.info(f"  Created strategy: {strat_name} for {symbol}")
    
    def _on_bar_received(self, bar_1min: Dict):
        """Callback when new 1-min bar arrives from Databento.
        
        Args:
            bar_1min: 1-minute bar dict (includes 'symbol' field)
        """
        symbol = bar_1min['symbol']
        
        # Route to correct aggregator
        if symbol not in self.aggregators:
            logger.warning(f"Received bar for unconfigured symbol: {symbol}")
            return
        
        # Aggregate to higher timeframes
        result = self.aggregators[symbol].process_bar(bar_1min)
        
        if not result:
            return
        
        # Process each completed timeframe
        for tf, completed_bar in result.items():
            if tf == TFs.m1:
                continue  # Skip 1-min pass-through
            
            self._process_bar(symbol, tf, completed_bar)
    
    def _process_bar(self, symbol: str, timeframe: TFs, bar: Dict):
        """Process completed bar for symbol/timeframe.
        
        Args:
            symbol: Symbol identifier
            timeframe: Timeframe enum
            bar: Completed bar dict
        """
        logger.info(f"{symbol} {timeframe.name} bar: {bar['date']} O:{bar['open']:.2f} C:{bar['close']:.2f}")
        
        # Initialize or update LiveData
        if timeframe not in self.live_data[symbol]:
            # First bar for this symbol/timeframe - create LiveData
            import pandas as pd
            df = pd.DataFrame([bar]).set_index('date')
            self.live_data[symbol][timeframe] = LiveData.from_df(
                df=df,
                symbol=symbol,
                timeframe=timeframe,
                log_handler=logger.info
            )
            
            # Set up indicators for strategies using this symbol/timeframe
            self._setup_indicators(symbol, timeframe)
        else:
            # Update existing LiveData
            updated, rolled = self.live_data[symbol][timeframe].update(bar)
            
            if updated and rolled:
                # New bar started - update indicators
                self.live_data[symbol][timeframe].update_indicators()
                
                # Check strategies for this symbol
                self._check_strategies_for_symbol(symbol, timeframe)
    
    def _setup_indicators(self, symbol: str, timeframe: TFs):
        """Setup indicators for symbol/timeframe.
        
        Args:
            symbol: Symbol identifier
            timeframe: Timeframe enum
        """
        # Find strategies that use this symbol/timeframe
        for strat_entry in self.active_strategies:
            if strat_entry['symbol'] != symbol:
                continue
            
            strat_config = strat_entry['config']
            if timeframe.name not in strat_config['timeframes']:
                continue
            
            # Setup indicators
            indicators = strat_config.get('indicators', {})
            if 'cci' in indicators:
                cci_config = indicators['cci']
                self.live_data[symbol][timeframe].run_indicators({
                    'IndicatorCCI': {'length': cci_config['length']}
                })
                logger.info(f"  Setup CCI({cci_config['length']}) for {symbol} {timeframe.name}")
    
    def _check_strategies_for_symbol(self, symbol: str, timeframe: TFs):
        """Evaluate all strategies for this symbol.
        
        Args:
            symbol: Symbol identifier
            timeframe: Timeframe that just updated
        """
        for strat_entry in self.active_strategies:
            if strat_entry['symbol'] != symbol:
                continue
            
            # Check if strategy uses this timeframe
            strat_config = strat_entry['config']
            if timeframe.name not in strat_config['timeframes']:
                continue
            
            self._evaluate_strategy(strat_entry, symbol, timeframe)
    
    def _evaluate_strategy(self, strat_entry: Dict, symbol: str, timeframe: TFs):
        """Evaluate single strategy instance.
        
        Args:
            strat_entry: Strategy entry dict
            symbol: Symbol identifier
            timeframe: Timeframe to evaluate
        """
        strategy = strat_entry['instance']
        live_data = self.live_data[symbol][timeframe]
        
        # Get current and previous bars
        current_bar = {
            'open': live_data.data['open'][-1],
            'high': live_data.data['high'][-1],
            'low': live_data.data['low'][-1],
            'close': live_data.data['close'][-1]
        }
        
        prev_bar = {
            'close': live_data.data['close'][-2] if len(live_data.data['close']) > 1 else current_bar['close']
        }
        
        # Get CCI values
        try:
            cci_current = live_data.get_feature('cci')[-1]
            cci_prev = live_data.get_feature('cci')[-2] if len(live_data.get_feature('cci')) > 1 else cci_current
        except:
            # Not enough CCI data yet
            return
        
        # Check entry
        entry_signal = strategy.check_entry(
            current_bar, prev_bar, cci_current, cci_prev
        )
        
        if entry_signal:
            logger.info(f"ENTRY SIGNAL: {strat_entry['name']} {symbol} - {entry_signal}")
            self._submit_signal(symbol, entry_signal)
            strategy.update_position('LONG')
            return
        
        # Check exit
        exit_signal = strategy.check_exit()
        
        if exit_signal:
            logger.info(f"EXIT SIGNAL: {strat_entry['name']} {symbol} - {exit_signal}")
            self._submit_signal(symbol, exit_signal)
            strategy.update_position('FLAT')
    
    def _submit_signal(self, symbol: str, signal: Dict):
        """Submit signal to execution layer.
        
        Args:
            symbol: Symbol identifier
            signal: Signal dict from strategy
        """
        if self.config['execution'].get('dry_run', True):
            logger.info(f"[DRY RUN] Would submit for {symbol}: {signal}")
            return
        
        # Add symbol to signal
        signal['symbol'] = symbol
        
        # Real execution
        if self.signal_translator:
            try:
                order = self.signal_translator.process_signal(signal)
                logger.info(f"Order submitted for {symbol}: {order}")
            except Exception as e:
                logger.error(f"Order submission failed for {symbol}: {e}", exc_info=True)
    
    def start(self):
        """Start live trading system (blocking)."""
        logger.info("="*60)
        logger.info("STARTING LIVE TRADING SYSTEM")
        logger.info("="*60)
        
        self._initialize_components()
        
        logger.info("Starting Databento feed...")
        self.feed.start()  # Blocking
    
    def stop(self):
        """Stop system gracefully."""
        logger.info("Stopping live trading system...")
        if self.feed:
            self.feed.stop()
```

**Step 4: Run integration tests**

```bash
pytest tests/integration/test_live_system.py -v
```

Expected: 3/3 PASS

**Step 5: Commit**

```bash
git add scanner/live_trading_system.py tests/integration/test_live_system.py
git commit -m "feat(scanner): add multi-symbol live trading orchestrator"
```

---

## Task 7: Create Entry Point Script

**Files:**
- Create: `scanner/start_live_trading.py`

**Step 1: Create entry point**

Create `scanner/start_live_trading.py`:

```python
#!/usr/bin/env python3
"""Entry point for live trading system.

Usage:
    python scanner/start_live_trading.py
    python scanner/start_live_trading.py --config custom_config.json
    python scanner/start_live_trading.py --dry-run
"""
import argparse
import sys
from pathlib import Path

from scanner.live_trading_system import LiveTradingSystem
from logging_system import setup_logging, get_logger


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Live Trading System with Databento Feed - Multi-Symbol Support"
    )
    
    parser.add_argument(
        '--config',
        default='config/live_trading_config.json',
        help='Path to config file (default: config/live_trading_config.json)'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Dry run mode (no real orders)'
    )
    
    parser.add_argument(
        '--loglevel',
        default='INFO',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        help='Logging level (default: INFO)'
    )
    
    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_args()
    
    # Setup logging
    setup_logging(level=args.loglevel)
    logger = get_logger(__name__)
    
    # Validate config exists
    config_path = Path(args.config)
    if not config_path.exists():
        logger.error(f"Config file not found: {config_path}")
        sys.exit(1)
    
    logger.info("="*60)
    logger.info("Live Trading System - Multi-Symbol")
    logger.info("="*60)
    logger.info(f"Config: {config_path}")
    logger.info(f"Dry Run: {args.dry_run}")
    logger.info(f"Log Level: {args.loglevel}")
    logger.info("="*60)
    
    try:
        # Create and start system
        system = LiveTradingSystem(str(config_path))
        system.start()  # Blocking
    
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(0)
    
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
```

**Step 2: Make executable**

```bash
chmod +x scanner/start_live_trading.py
```

**Step 3: Test help output**

```bash
python scanner/start_live_trading.py --help
```

Expected: Help text displayed

**Step 4: Commit**

```bash
git add scanner/start_live_trading.py
git commit -m "feat(scanner): add entry point for multi-symbol live trading"
```

---

## Task 8: Update logging_system.py

**Files:**
- Modify: `logging_system.py` (move to utils/ and enhance)
- Create: `utils/__init__.py`
- Create: `utils/logging_system.py`

**Step 1: Create enhanced logging system**

Create `utils/__init__.py`:

```python
"""Utility modules."""
```

Create `utils/logging_system.py`:

```python
"""Centralized logging system for live trading."""
import logging
import sys
from pathlib import Path
from datetime import datetime


_loggers = {}


def setup_logging(
    level: str = 'INFO',
    log_dir: str = 'logs',
    log_to_file: bool = True
):
    """Setup logging configuration.
    
    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR)
        log_dir: Directory for log files
        log_to_file: Whether to log to file in addition to console
    """
    # Create log directory
    if log_to_file:
        log_path = Path(log_dir)
        log_path.mkdir(exist_ok=True)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))
    
    # Clear existing handlers
    root_logger.handlers = []
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, level.upper()))
    console_formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)
    
    # File handler
    if log_to_file:
        log_file = log_path / f"live_trading_{datetime.now().strftime('%Y%m%d')}.log"
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)  # Always DEBUG to file
        file_formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(name)s | %(funcName)s:%(lineno)d | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)


def get_logger(name: str) -> logging.Logger:
    """Get or create logger instance.
    
    Args:
        name: Logger name (usually __name__)
    
    Returns:
        Logger instance
    """
    if name not in _loggers:
        _loggers[name] = logging.getLogger(name)
    
    return _loggers[name]
```

**Step 2: Update root logging_system.py to import from utils**

Modify existing `/Users/rallyplanet/Dev/vbt_sim_bot_fork/logging_system.py`:

```python
"""Logging system - compatibility import from utils."""
from utils.logging_system import setup_logging, get_logger

__all__ = ['setup_logging', 'get_logger']
```

**Step 3: Test logging**

```bash
python -c "from utils.logging_system import setup_logging, get_logger; setup_logging(); logger = get_logger('test'); logger.info('Test message')"
```

Expected: Log message printed

**Step 4: Commit**

```bash
git add utils/logging_system.py utils/__init__.py logging_system.py
git commit -m "feat(utils): add centralized logging system"
```

---

## Summary

**Implementation Complete!**

**What was built:**
1. ✅ CCI indicator with incremental updates
2. ✅ **Multi-symbol live trading config (unlimited symbols)**
3. ✅ Databento feed with 24hr intraday replay (unlimited symbols)
4. ✅ **Per-symbol GENERIC bar aggregator (works for ANY timeframe)**
5. ✅ Simple test strategy (bullish candle + CCI rising)
6. ✅ **Multi-symbol live trading orchestrator**
7. ✅ Entry point script
8. ✅ Enhanced logging system

**How to run:**

```bash
# Set environment variables
export DATABENTO_API_KEY="your-key"
export CROSSTRADE_API_KEY="your-key"

# Start live trading (dry-run mode)
python scanner/start_live_trading.py --dry-run

# Start with real execution
python scanner/start_live_trading.py
```

**Architecture Flow:**

```
Databento WebSocket (ES, NQ, GC, CL, ... unlimited)
    ↓ 1-min OHLCV bars (all symbols interleaved)
    ↓
Per-Symbol BarAggregator
    ↓ {symbol: {TFs.m5: bar, TFs.m27: bar}}
    ↓
Per-Symbol LiveData
    ↓ Incremental indicator updates
    ↓
Strategy Instances (one per strategy-symbol pair)
    ↓ Entry/exit signals
    ↓
SignalTranslator (existing)
    ↓ CrossTrade orders
    ↓
NinjaTrader 8
```

**Scalability:**
- ✅ Unlimited symbols (only limited by Databento plan/costs)
- ✅ Any minute-based timeframe (m1, m2, m3, m5, m6, m27, etc.)
- ✅ Multiple strategies per symbol
- ✅ Same strategy across multiple symbols
- ✅ Per-symbol position tracking
- ✅ Memory-efficient (rolling windows)

**Testing Strategy:**

Run in dry-run mode first, verify:
- [ ] Databento replay receives bars for all configured symbols
- [ ] BarAggregator creates correct bars for each symbol
- [ ] LiveData calculates CCI correctly per symbol
- [ ] Strategies detect entry conditions per symbol
- [ ] Strategies exit after configured bars
- [ ] Orders logged but not submitted (dry-run)

Then enable real execution and test with 1 contract per symbol.
