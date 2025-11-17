# System Architecture

## Overview

vbt_sim_bot is a live trading system built on VectorBTPro that:
1. Ingests real-time market data from Databento
2. Aggregates 1-second bars → 1-minute bars → 5-minute+ bars
3. Evaluates trading strategies with technical indicators
4. Executes orders via CrossTrade API (NinjaTrader integration)

## Component Layers

### Layer 1: Data Ingestion
**scanner/databento_live_feed.py**
- Subscribes to Databento live feeds
- Handles 24-hour intraday replay (historical backfill)
- Emits 1-second OHLCV bars

### Layer 2: Bar Aggregation
**scanner/second_to_minute_aggregator.py**
- Aggregates 1-second bars → 1-minute bars
- Completes on last bar of each minute

**scanner/bar_aggregator.py**
- Aggregates 1-minute bars → higher timeframes (5m, 15m, etc.)
- Completes periods on last bar (not first bar of next period)

### Layer 3: Strategy Orchestration
**scanner/live_trading_orchestrator.py**
- Manages strategy instances per symbol/timeframe
- Routes completed bars to appropriate strategies
- Handles indicator warmup during replay
- Executes signals (no replay mode suppression)

### Layer 4: Strategy Evaluation
**strategies/simple_bullish_cci.py**
- Evaluates on each bar completion
- Uses LiveData for incremental updates
- Generates entry/exit signals

**indicators/indicator_cci.py**
- CCI calculation using Typical Price (HLC/3)
- Configurable period (15 for ES, 20 for NQ)

### Layer 5: Order Execution
**execution/order_manager.py**
- High-level order interface
- Manages order lifecycle

**execution/crosstrade_client.py**
- CrossTrade API client
- Symbol mapping (ES.c.0 → ESZ5)
- Rate limiting and error handling

## Data Flow

```
Databento Feed
    ↓ (1s OHLCV)
Second-to-Minute Aggregator
    ↓ (1m OHLCV)
Bar Aggregator
    ↓ (5m OHLCV)
Live Trading Orchestrator
    ↓ (per symbol/strategy)
Strategy Evaluation
    ↓ (signals)
Order Manager
    ↓ (orders)
CrossTrade Client
    ↓
NinjaTrader
```

## Key Design Decisions

**No Replay Mode Suppression:**
- Databento provides single stream: historical (0-24hr) + live
- Indicators warm up during historical
- Once warmed, execute all signals immediately
- No distinction between replay and live

**Bar Timing:**
- Periods complete on LAST bar of period
- 5-min bar for 06:40-06:45 completes when 06:44 bar arrives (at 06:45:01)
- Ensures strategies evaluate with complete period data

**Symbol Mapping:**
- Databento: continuous contracts (ES.c.0)
- CrossTrade: specific months (ESZ5 = ES December 2025)
- Mapping in orchestrator before order submission

## Configuration

**config/live_trading_config.json:**
- Databento: symbols, schema (ohlcv-1s), replay hours
- Strategies: which symbols, timeframes, parameters
- Execution: CrossTrade credentials, account, dry_run mode
