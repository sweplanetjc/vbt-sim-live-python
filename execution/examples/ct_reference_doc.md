# CrossTrade Integration - Quick Visual Summary

## The Big Picture

```
┌─────────────────────────────────────────────────────────────────┐
│                    YOUR FUTURES-ALGO SYSTEM                      │
└─────────────────────────────────────────────────────────────────┘

PHASE 1: BACKTEST (Weekly - Offline)
────────────────────────────────────
Databento API
    ↓ (Historical bars)
VectorBT Pro Optimization
    ↓ (Tests 1000s of parameter combos)
Best Parameters
    ↓ (Save to JSON)
live_scenario_config.json

PHASE 2: LIVE SCANNING (Every 1-3 min)
───────────────────────────────────────
Databento API (or your data source)
    ↓ (Current 1m bars)
Load Config → Calculate Indicators
    ↓ (RSI, MACD with best params)
Check Entry/Exit Conditions
    ↓ (Pattern match?)
Generate Signal
    ↓ (Dict with signal_type, instrument, price)
signals.log

PHASE 3: EXECUTION (Instant) ← THIS IS CROSSTRADE!
───────────────────────────────────────────────────
Signal → SignalTranslator
    ↓ (Validate & convert)
OrderManager
    ↓ (Build order request)
CrossTradeClient
    ↓ (HTTP POST to NT8)
NinjaTrader 8 CrossTrade Plugin
    ↓ (Execute in market)
Order Confirmation
    ↓ (Fill status)
executions.log
```

## What Each Component Does

### From vector_bot (Execution Only):

**CrossTradeClient** (`crosstrade_client.py`)
- Low-level API wrapper
- Talks to NT8 via HTTP
- Endpoints: /accounts, /positions, /orders, /executions

**OrderManager** (`order_manager.py`)
- High-level order interface
- submit_market_order(), submit_limit_order(), flatten_position()
- Tracks order status

**SignalTranslator** (`signal_translator.py`)
- Converts scanner signals → NT8 orders
- Handles position sizing
- Validates before submission

**MarketDataManager** (`market_data.py`)
- Gets current quotes from NT8
- Optional (you'll use Databento for data)

### Your New Files (Not in vector_bot):

**live_scanner.py**
- Monitors market every 1-3 min
- Calculates indicators (RSI, MACD, etc.)
- Generates signals when conditions match

**backtest_runner.py**
- Weekly VectorBT optimization
- Finds best parameters
- Saves to live_scenario_config.json

**simple_executor.py** (example provided)
- Wrapper around crosstrade components
- Used by live_scanner.py
- Handles signal → order execution

## The Integration Point

```python
# In your live_scanner.py:

from execution.simple_executor import SimpleExecutor

executor = SimpleExecutor()  # Initialize crosstrade

while True:
    # Scan market
    signals = scan_for_patterns()
    
    # Execute signals
    for signal in signals:
        executor.execute_signal(signal)  # ← This is crosstrade!
    
    time.sleep(180)  # Wait 3 min
```

## File Structure

```
futures-algo/
├── backtest/
│   ├── scenarios.py
│   ├── backtest_runner.py        # VectorBT optimization
│   └── data_loader.py             # Databento fetcher
│
├── scanner/
│   ├── live_scanner.py            # Real-time pattern matcher
│   └── signal_generator.py        # Creates signal dicts
│
├── execution/                      # ← CROSSTRADE MODULE GOES HERE
│   ├── __init__.py
│   ├── crosstrade_client.py       # From vector_bot
│   ├── order_manager.py           # From vector_bot
│   ├── signal_translator.py       # From vector_bot
│   ├── market_data.py             # From vector_bot
│   ├── models.py                  # From vector_bot
│   └── simple_executor.py         # Your wrapper (example provided)
│
├── config/
│   ├── live_scenario_config.json  # Best params from backtest
│   └── execution_config.json      # NT8 settings
│
└── logs/
    ├── signals.log                # All generated signals
    ├── executions.log             # Order confirmations
    └── scanner.log                # Scanner activity
```

## What CrossTrade Does NOT Do

❌ Does NOT provide market data → Use Databento
❌ Does NOT run backtests → Use VectorBT Pro
❌ Does NOT generate signals → Use live_scanner.py
❌ Does NOT optimize parameters → Use backtest_runner.py

## What CrossTrade DOES Do

✅ Submits orders to NinjaTrader 8
✅ Tracks order status (WORKING, FILLED, REJECTED)
✅ Manages positions (check, flatten, exit)
✅ Handles order types (market, limit, stop)

## Signal Flow Example

```
Scanner detects RSI < 30 on ES
    ↓
signal = {
    "signal_type": "LONG_ENTRY",
    "instrument": "ES 03-25",
    "price": 5850.0,
    "timestamp": "2025-11-13T09:30:00"
}
    ↓
executor.execute_signal(signal)
    ↓
SignalTranslator validates signal
    ↓
OrderManager creates order request
    ↓
CrossTradeClient sends HTTP POST:
    POST http://localhost:8080/orders
    {
        "account": "Sim101",
        "instrument": "ES 03-25",
        "action": "BUY",
        "quantity": 1,
        "orderType": "MARKET"
    }
    ↓
NT8 CrossTrade Plugin receives
    ↓
NT8 submits order to market
    ↓
Order fills
    ↓
CrossTrade returns:
    {
        "orderId": "abc123",
        "state": "FILLED",
        "fillPrice": 5850.25,
        "fillTime": "2025-11-13T09:30:02"
    }
    ↓
Executor logs to executions.log
```

## Quick Start Steps

### 1. Setup NT8 (One-time)
```bash
# Install CrossTrade plugin in NinjaTrader 8
# Enable in Tools → Options → CrossTrade
# Set port to 8080 (default)
# Test: curl http://localhost:8080/accounts
```

### 2. Copy crosstrade module
```bash
cd futures-algo
mkdir execution
# Copy files from vector_bot/crosstrade/ to futures-algo/execution/
```

### 3. Create config
```bash
# Create config/execution_config.json:
{
  "crosstrade_url": "http://localhost:8080",
  "nt8_account": "Sim101",
  "default_quantity": 1,
  "use_market_orders": true
}
```

### 4. Test connection
```python
from execution.crosstrade_client import CrossTradeClient

client = CrossTradeClient()
print(client.get_accounts())  # Should print: ['Sim101']
```

### 5. Integrate with scanner
```python
# In live_scanner.py:
from execution.simple_executor import SimpleExecutor

executor = SimpleExecutor()

# When signal detected:
signal = {
    "signal_type": "LONG_ENTRY",
    "instrument": "ES 03-25",
    "price": current_price,
    "timestamp": datetime.now().isoformat()
}

executor.execute_signal(signal)
```

## Testing Strategy

### Phase 1: Unit Tests (No orders)
- Test signal validation
- Test order building
- Mock NT8 responses

### Phase 2: Integration Tests (Sim account)
- Submit real orders to Sim101
- Verify fills
- Test position tracking

### Phase 3: Paper Trading (2-4 weeks)
- Run scanner + executor live on Sim
- Log all activity
- Compare to backtest expectations

### Phase 4: Production (Gradual)
- Switch to Live account
- Start with 1 contract
- Monitor for 1 week
- Scale up slowly

## Common Issues

### NT8 not responding?
```bash
# Check if running:
curl http://localhost:8080/accounts

# If error, start NT8 and enable CrossTrade plugin
```

### Order rejected?
```python
# Check margin before order:
positions = client.get_positions()
# Verify you have margin for new position
```

### Duplicate signals?
```python
# Check for existing position first:
existing = translator.check_existing_position(instrument)
if existing:
    return  # Skip signal
```

## Key Files to Reference

1. **CROSSTRADE_INTEGRATION_PLAN.md** - Full detailed guide (9 parts)
2. **crosstrade_example.py** - 6 working examples
3. **MASTER_REFERENCE.md** - VectorBT optimization guide
4. **VBT_SIM_LIVE_ARCHITECTURE_GUIDE.md** - Real-time trading guide

## Next Steps

1. [ ] Copy crosstrade module from vector_bot
2. [ ] Install NT8 with CrossTrade plugin
3. [ ] Create execution_config.json
4. [ ] Test connection (run crosstrade_example.py Example 1)
5. [ ] Integrate with live_scanner.py
6. [ ] Paper trade for 2-4 weeks
7. [ ] Go live with 1 contract

**Questions? Check CROSSTRADE_INTEGRATION_PLAN.md for detailed answers!**
