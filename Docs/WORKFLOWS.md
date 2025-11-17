# Workflows

## Workflow 1: Live Trading

**Entry Point:** `run_live_trading.py`

**Setup:**
1. Configure `.env`:
```bash
DATABENTO_API_KEY=your_key
CROSSTRADE_API_KEY=your_key
```

2. Configure `config/live_trading_config.json`:
- Symbols to trade
- Strategies to run
- NinjaTrader account
- dry_run mode (true for testing)

**Run:**
```bash
python run_live_trading.py config/live_trading_config.json --log-level INFO
```

**What Happens:**
1. Connects to Databento feed
2. Receives 24hr intraday replay (historical backfill)
3. Indicators warm up during replay
4. Strategies evaluate on every bar
5. Signals execute immediately (no replay suppression)
6. Continues with live data after replay

**Monitoring:**
```bash
# In separate terminal
python scripts/monitoring/monitor_live.py
```

**Logs:**
- Console output shows bar completions, strategy evaluations, orders
- Configure log level: DEBUG, INFO, WARNING, ERROR

---

## Workflow 2: Backtesting

**Entry Point:** `scripts/backtest/backtest_macd_bb_strategy.py` (example)

**Setup:**
1. Fetch historical data:
```bash
python scripts/data/fetch_databento_data.py \
    --symbols ES.c.0 NQ.c.0 \
    --start 2025-01-01 \
    --end 2025-11-17 \
    --schema ohlcv-1m
```

2. Configure backtest script:
- Date range
- Strategy parameters
- Symbols

**Run:**
```bash
cd scripts/backtest
python backtest_macd_bb_strategy.py
```

**Results:**
- Saved to `results/` directory
- Includes performance metrics, trades, drawdowns

---

## Workflow 3: Testing

**Unit Tests:**
```bash
pytest tests/unit/ -v
```

**Integration Tests:**
```bash
pytest tests/integration/ -v
```

**Specific Test:**
```bash
pytest tests/unit/test_bar_aggregator.py::test_completes_on_last_bar -v
```

**With Coverage:**
```bash
pytest --cov=scanner --cov=execution --cov=strategies --cov=indicators --cov-report=html
```

**Test Structure:**
- `tests/unit/` - Unit tests for individual components
- `tests/integration/` - Integration tests (data feeds, full workflows)

---

## Workflow 4: Adding a New Strategy

1. **Create strategy file:**
```bash
touch strategies/my_new_strategy.py
```

2. **Implement strategy:**
- Inherit from base strategy class
- Define indicators needed
- Implement `on_bar()` logic
- Return signal dict with action, side, quantity

3. **Add to config:**
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

4. **Test:**
```bash
# Unit test
pytest tests/unit/test_my_new_strategy.py -v

# Integration test with replay
python tests/integration/test_strategy_with_replay.py
```

5. **Run live (dry_run):**
```bash
python run_live_trading.py config/live_trading_config.json --log-level DEBUG
```

---

## Workflow 5: Debugging

**Debug Databento Feed:**
```bash
python scripts/debug/debug_databento.py
```

**Debug Parquet Files:**
```bash
python scripts/debug/debug_parquet_structure.py data/raw/ES_2025-11-17.parquet
```

**Check Symbol Mapping:**
```bash
python tests/integration/test_symbol_mapping.py
```

**Monitor Live System:**
```bash
tail -f /tmp/live_trading_*.log | grep -E "(Signal|ORDER|ERROR)"
```
