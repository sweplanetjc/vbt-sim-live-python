---
name: trading-strategy-validator
description: Validates trading strategies through rigorous walk-forward cross-validation on futures data (ES, NQ, GC, etc.). Use when the user mentions validating or rigorously testing a NEW strategy with specific indicators and timeframes. Automatically checks the strategy registry for duplicates, runs 6-phase validation workflow including walk-forward CV, and updates the registry with results (validated if ≥80% Sharpe retention, rejected if below threshold).
---

# Trading Strategy Validator (Futures-Algo)

**Purpose:** Systematically validate trading strategies using walk-forward cross-validation to prevent overfitting and ensure robust performance before live deployment. ALL strategies must go through this complete validation process before deployment.

---

## When to Activate This Skill

**Use this skill when:**
- Testing a strategy concept (new or parameter updates)
- Need rigorous validation (walk-forward CV)
- Want to prove strategy isn't overfit
- Adding to or updating strategy registry
- Preparing for live deployment

**Trigger Phrases:**
- "validate this strategy with walk-forward CV"
- "rigorously test RSI+MACD before deploying"
- "prove this strategy isn't overfit"
- "update parameters for RSI strategy"
- "add RSI+Bollinger Bands to strategy registry"

---

## Strategy Validation Workflow

```
┌──────────────────────────────────────────────────────────────┐
│ STRATEGY VALIDATION PATH (ALL STRATEGIES)                     │
├──────────────────────────────────────────────────────────────┤
│ 1. User has strategy idea or parameter update                │
│     ↓                                                         │
│ 2. trading-strategy-validator (THIS SKILL)                   │
│    - 6-phase validation workflow                             │
│    - Walk-forward CV                                          │
│    - 1-3 hours                                                │
│     ↓                                                         │
│ 3. Result: ✅ VALIDATED or ❌ REJECTED                        │
│     ↓                                                         │
│ 4. Update STRATEGY_REGISTRY.md                               │
│     ↓                                                         │
│ 5. Update live_scenario_config.json                          │
│     ↓                                                         │
│ 6. Scanner uses validated parameters                         │
└──────────────────────────────────────────────────────────────┘
```

---

## Validation Workflow (7 Phases)

### **Phase 0: Parse NLP Prompt & Confirm Understanding**

**MANDATORY FIRST STEP:** Parse the user's natural language request and confirm understanding BEFORE proceeding.

**Extract from user prompt:**
- Indicators (RSI, MACD, Bollinger Bands, etc.)
- Symbols/contracts (ES, NQ, GC, etc.)
- Timeframes (1m, 5m, 1h, 4h, etc.)
- Parameter ranges (if specified)
- Entry/exit conditions (if specified)

**Print confirmation:**
```
═══════════════════════════════════════════════════════════
📋 STRATEGY VALIDATION CONFIRMATION
═══════════════════════════════════════════════════════════

Based on your request, I will validate:

Strategy Type: [Name, e.g., "RSI Multi-Timeframe"]
Symbols: [ES, NQ, etc.]
Timeframes: 
  - Base: [1h]
  - Higher: [4h]

Indicators:
  - RSI (period: 10-20)
  - Entry threshold: 30
  - Exit threshold: 70

Entry Rule: RSI_1h < 30 AND RSI_4h < 50
Exit Rule: RSI_1h > 70 OR RSI_4h > 50

Parameter Ranges:
  - rsi_period: [10, 12, 14, 16, 18, 20]
  - threshold_low: [25, 30, 35]
  - threshold_high: [65, 70, 75]
  
Total Combinations: 108 (6 × 3 × 3)

Validation Method: Walk-forward cross-validation (4 folds)
Estimated Time: 1-3 hours
Data Required: ES 1-minute bars (last 2 years)

═══════════════════════════════════════════════════════════
⚠️  PROCEED WITH VALIDATION? (yes/no)
═══════════════════════════════════════════════════════════
```

**STOP HERE and wait for user confirmation.**

If user says:
- **"yes"** → Proceed to Phase 1
- **"no"** or modifies → Update parameters and re-confirm
- **unclear** → Ask clarifying questions

---

### **Phase 1: Registry Check & Duplicate Prevention**

**After user confirms**, check the registry before starting validation.

```bash
# Check if this combination has been tested
cat docs/STRATEGY_REGISTRY.md | grep -i "[TICKER].*[INDICATORS].*[TIMEFRAME]\|[INDICATORS].*[TICKER].*[TIMEFRAME]"

# Check all sections
grep -A 10 "## Validated Strategies" docs/STRATEGY_REGISTRY.md
grep -A 10 "## Strategies in Development" docs/STRATEGY_REGISTRY.md
grep -A 10 "## Strategies Under Consideration" docs/STRATEGY_REGISTRY.md
grep -A 10 "### Failed/Rejected Strategies" docs/STRATEGY_REGISTRY.md
```

**If found in registry:**
- Report existing results to user
- Ask if they want to re-test with different parameters
- **DO NOT** proceed without user confirmation

**If not found:**
- Proceed to Phase 2

---

### **Phase 2: Add to Registry ("Under Consideration")**

Create `docs/STRATEGY_REGISTRY.md` if it doesn't exist, then add entry:

```markdown
### [STRATEGY-ID] ([TICKER], [TIMEFRAME])

**Status:** 🔬 UNDER CONSIDERATION
**Added:** [YYYY-MM-DD]

#### Overview
- **Symbols:** [TICKER] (e.g., ES, NQ, GC)
- **Timeframe:** [X-minute] bars
- **Indicators:**
  - [Indicator 1](parameters) on [price column]
  - [Indicator 2](parameters) on [price column]
- **Entry Rule:** [Describe entry condition]
- **Exit Rule:** [Describe exit condition]

#### Testing Plan
- [ ] Define parameter ranges
- [ ] Run quick screening
- [ ] Walk-forward CV validation
- [ ] Code implementation (if validated)
- [ ] Live system integration (if validated)

#### Notes
[Any initial hypotheses or concerns]
```

**Inform User:**
> "I've added [STRATEGY-ID] to the registry under 'Strategies Under Consideration'. Now proceeding with validation workflow..."

---

### **Phase 3: Quick Screening Backtest**

**Purpose:** Rapidly eliminate weak parameter combinations BEFORE expensive walk-forward CV.

**⚠️ CRITICAL: Use Futures-Algo Data Loader**

```python
# Use the new data_loader.py (NOT old approaches)
from backtest.data_loader import load_futures_data
import vectorbtpro as vbt

# Load data
df = load_futures_data(
    symbol="ES",
    start_date="2020-01-01",
    end_date="2024-12-31",
    base_timeframe="1h",  # Or whatever your base TF is
    min_bars=1000
)

if df is None:
    print("Data not available. Run:")
    print("  python scripts/fetch_databento_data.py --symbol ES")
    exit(1)

# Convert to VectorBT
data = vbt.Data.from_data(df)
```

**MANDATORY: USE VECTORBT FOR BACKTESTING**

**Before writing code, verify:**
- [ ] Import: `import vectorbtpro as vbt`
- [ ] Use: `vbt.Portfolio.from_signals()` for backtesting
- [ ] NO Python for loops over bars (`for i in range(len(df)):`)
- [ ] Expected runtime: 2-5 min per 1,000 combos (NOT hours!)

**Red Flags (indicates wrong approach):**
- ❌ `for i in range(len(df)):`
- ❌ `df['entry'].iloc[i]`
- ❌ `position = 0` tracking in Python loop
- ❌ Screening takes > 30 minutes for < 5,000 combos

**Correct Pattern:**
```python
import vectorbtpro as vbt

# Generate signals (vectorized - OK!)
entries = (condition1) & (condition2) & ...
exits = (exit_cond1) | (exit_cond2) | ...

# Backtest (VectorBT - REQUIRED!)
portfolio = vbt.Portfolio.from_signals(
    close=df['close'],
    entries=entries,
    exits=exits,
    init_cash=100000,
    fees=0.00001,
    slippage=0.000005,
    size=CONTRACTS * POINT_VALUE[symbol],  # Contract-based sizing
    size_type='amount',
    freq='1h',  # Or your base timeframe
    accumulate=False
)

# Extract metrics (instant!)
stats = portfolio.stats()
sharpe = stats['Sharpe Ratio']
max_dd = stats['Max Drawdown [%]'] / 100
profit_factor = stats['Profit Factor']
```

**CRITICAL: Multi-Timeframe (MTF) Alignment**

**For MTF strategies, MUST use VectorBT's Resampler with incomplete bars (from MASTER_REFERENCE.md):**

**CORRECT (no look-ahead bias):**
```python
import vectorbtpro as vbt

# Base timeframe data (e.g., 1h)
close_1h = df['close']

# Resample to higher timeframe using CURRENT close (incomplete bar)
close_4h = close_1h.vbt.resample_apply("4h", vbt.nb.last_reduce_nb)

# Calculate indicator on incomplete 4h bars
rsi_4h = vbt.RSI.run(close_4h, window=14).rsi

# Create resampler
resampler = vbt.Resampler(
    source_index=rsi_4h.index,      # 4h index
    target_index=close_1h.index,    # 1h index
    source_freq="4h",
    target_freq="1h"
)

# Realign 4h indicator to 1h timestamps (NO .fshift!)
rsi_4h_on_1h = rsi_4h.vbt.realign_opening(resampler)

# Use in strategy
entries = (rsi_1h < 30) & (rsi_4h_on_1h < 50)
```

**WRONG (causes repainting):**
```python
# ❌ DO NOT USE - creates look-ahead bias!
df_4h = df_1h.resample('4h').agg({'close': 'last', ...})
df['rsi_4h'] = df_4h['rsi'].reindex(df_1h.index, method='ffill')
# This backward-fills future values into the past!
```

**Why This Matters:**
- `.reindex(method='ffill')` uses future information
- Creates unrealistic signals
- Always use `vbt.Resampler` + `.vbt.realign_opening()` for MTF

**Critical: Use Contract-Based Position Sizing**

```python
# CORRECT position sizing for futures
INITIAL_CAPITAL = 100000.0  # $100k starting capital
CONTRACTS = 1               # Trade 1 contract at a time

# Point values for P&L calculation
POINT_VALUE = {
    'ES': 50,      # $50 per point
    'NQ': 20,      # $20 per point
    'GC': 100,     # $100 per ounce
    'YM': 5,       # $5 per point
    'RTY': 50,     # $50 per point
    'CL': 1000,    # $1000 per contract
    'ZB': 1000,    # $1000 per point
    'ZC': 50       # $50 per bushel
}

# P&L calculation (CORRECT)
pnl = (exit_price - entry_price) * POINT_VALUE[symbol] * CONTRACTS

# NOT percentage-based! Use actual point moves × contract multiplier
```

**Screening Period:**
- Test Period: 2020-01-01 to 2024-12-31 (full 5 years)
- Single backtest per parameter combination
- No train/test split (just looking for basic viability)

**Screening Criteria (ALL must pass):**

```python
screening_criteria = {
    'max_drawdown': 0.05,      # < 5% (ideal < 4%)
    'min_profit_factor': 1.5,  # Gross profit / Gross loss
    'min_sharpe': 1.5,         # Annualized Sharpe ratio
    'min_trades': 30,          # Minimum trades for statistical significance
}

# Filter survivors
survivors = results[
    (results['max_dd'] < screening_criteria['max_drawdown']) &
    (results['profit_factor'] > screening_criteria['min_profit_factor']) &
    (results['sharpe'] > screening_criteria['min_sharpe']) &
    (results['num_trades'] > screening_criteria['min_trades'])
]
```

**Screening Output:**
```
Quick Screening Results:

Total combinations tested: 840
Survivors (passed all criteria): 67 (8.0%)

Criteria:
  ✓ Max Drawdown < 5%
  ✓ Profit Factor > 1.5
  ✓ Sharpe Ratio > 1.5
  ✓ Minimum Trades > 30

Top 5 Survivors:
1. Params: [X,Y,Z] - Sharpe: 3.45, DD: 2.1%, PF: 2.8, Trades: 142
2. Params: [X,Y,Z] - Sharpe: 3.21, DD: 2.5%, PF: 2.6, Trades: 138
...

Proceeding to Phase 4 (Walk-Forward CV) with 67 survivors...
```

**Save screening results:**
```python
survivors.to_csv(f"backtest_results/{strategy_id}_screening_survivors.csv")
```

---

### **Phase 4: Walk-Forward Cross-Validation**

**Purpose:** Test survivors on unseen data to detect overfitting.

**Setup:**
- 4 Folds (train/test splits)
- Each fold: 75% train, 25% test
- Walk-forward (time-based splits)

**Example Folds (5-year period):**
```
Fold 1: Train 2020-2021.75 | Test 2021.75-2022.25
Fold 2: Train 2021-2022.75  | Test 2022.75-2023.25
Fold 3: Train 2022-2023.75  | Test 2023.75-2024.25
Fold 4: Train 2023-2024.75  | Test 2024.75-2025 (if data available)
```

**Process:**
1. For each survivor parameter combo:
2. For each fold:
   - Optimize on train period (no new optimization, just use fixed params)
   - Test on unseen test period
   - Record: train Sharpe, test Sharpe, Sharpe retention
3. Calculate average metrics across folds
4. Check validation criteria

**Code Pattern:**
```python
from backtest.data_loader import load_futures_data
import vectorbtpro as vbt

# Define folds
folds = [
    {"train_start": "2020-01-01", "train_end": "2021-09-30", 
     "test_start": "2021-10-01", "test_end": "2022-03-31"},
    {"train_start": "2021-01-01", "train_end": "2022-09-30",
     "test_start": "2022-10-01", "test_end": "2023-03-31"},
    # ... more folds
]

results = []

for fold_idx, fold in enumerate(folds):
    print(f"\nFold {fold_idx + 1}/4:")
    
    # Load train data
    df_train = load_futures_data(
        "ES", fold["train_start"], fold["train_end"], "1h"
    )
    
    # Load test data
    df_test = load_futures_data(
        "ES", fold["test_start"], fold["test_end"], "1h"
    )
    
    # For each survivor combo
    for params in survivors:
        # Backtest on train
        train_sharpe = backtest_with_params(df_train, params)
        
        # Backtest on test (unseen data)
        test_sharpe = backtest_with_params(df_test, params)
        
        # Calculate retention
        retention = (test_sharpe / train_sharpe) * 100
        
        results.append({
            'fold': fold_idx + 1,
            'params': params,
            'train_sharpe': train_sharpe,
            'test_sharpe': test_sharpe,
            'retention': retention
        })

# Aggregate across folds
cv_results = pd.DataFrame(results)
avg_results = cv_results.groupby('params').agg({
    'train_sharpe': 'mean',
    'test_sharpe': 'mean',
    'retention': 'mean'
})
```

**Save CV results:**
```python
cv_results.to_csv(f"backtest_results/{strategy_id}_walk_forward_cv_results.csv")
```

---

### **Phase 5: Validation Criteria Check**

**MUST PASS ALL CRITERIA:**

```python
validation_criteria = {
    'min_avg_sharpe_retention': 80.0,    # ≥80% average across folds
    'min_fold_sharpe_retention': 70.0,   # Every single fold ≥70%
    'min_avg_test_sharpe': 1.2,          # Average test Sharpe ≥1.2
    'max_sharpe_std': 0.5,               # Low variability across folds
}

# Check criteria
passed = (
    (avg_results['retention'].mean() >= 80.0) and
    (avg_results['retention'].min() >= 70.0) and
    (avg_results['test_sharpe'].mean() >= 1.2) and
    (avg_results['test_sharpe'].std() <= 0.5)
)
```

**Validation Decision:**
- **PASS:** All criteria met → Proceed to Phase 6 (Update Registry as VALIDATED)
- **FAIL:** Any criterion failed → Update Registry as REJECTED

---

### **Phase 6: Update Registry**

**Scenario A: VALIDATED (Passed All Criteria)**

**Actions:**
1. Remove from "Strategies Under Consideration"
2. Add to "Validated Strategies" section
3. Document complete results

**Template:**
```markdown
### [STRATEGY-ID] ([TICKER], [TIMEFRAME])

**Status:** ✅ **VALIDATED**
**Validated:** [YYYY-MM-DD]

#### Overview
- **Symbols:** [TICKER]
- **Timeframe:** [X-minute] bars
- **Indicators:**
  - [Indicator 1](parameters)
  - [Indicator 2](parameters)
- **Entry Rule:** [Description]
- **Exit Rule:** [Description]

#### Walk-Forward CV Results

**Tested:** [YYYY-MM-DD]
**Folds:** 4 (2020-2024)
**Results Location:** `backtest_results/[strategy_id]_walk_forward_cv_results.csv`

| Metric | Fold 1 | Fold 2 | Fold 3 | Fold 4 | Average |
|--------|--------|--------|--------|--------|---------|
| **Train Sharpe** | X.XX | X.XX | X.XX | X.XX | **X.XX** |
| **Test Sharpe** | X.XX | X.XX | X.XX | X.XX | **X.XX** |
| **Retention (%)** | XX.X% | XX.X% | XX.X% | XX.X% | **XX.X%** ✅ |

**Overall Assessment:**
- ✅ Average Sharpe retention: XX.X% (threshold: 80%)
- ✅ All folds ≥70% retention (no single fold failure)
- ✅ Average test Sharpe: X.XX (threshold: 1.2)
- ✅ Low variability across folds (std: 0.XX)

#### Best Parameters

```json
{
  "rsi_window": 14,
  "rsi_threshold_low": 30,
  "rsi_threshold_high": 70,
  "macd_fast": 12,
  "macd_slow": 26,
  "macd_signal": 9
}
```

#### Deployment Status

**Current Status:** ✅ **READY FOR WEEKLY OPTIMIZATION**

**Next Steps:**
- [ ] Generate `live_scenario_config.json` with best params
- [ ] Integrate with live scanner
- [ ] Paper trade for 2-4 weeks before going live
- [ ] Paper trading validation (2-4 weeks)
- [ ] Production deployment

**Notes:**
- Strategy validated with walk-forward CV - robust and not overfit
- Re-validate with walk-forward CV when updating parameters
- Ready for live deployment after paper trading
```

---

**Scenario B: REJECTED (Failed Criteria)**

**Actions:**
1. Remove from "Strategies Under Consideration"
2. Add to "Archive → Failed/Rejected Strategies" section
3. Document why it failed

**Template:**
```markdown
### [STRATEGY-ID] ([TICKER], [TIMEFRAME])

**Status:** ❌ REJECTED
**Test Date:** [YYYY-MM-DD]

**Reason:** [Primary failure - e.g., "Poor Sharpe retention (XX%)", "Overfitting detected"]

**Results Summary:**
- Average Train Sharpe: X.XX
- Average Test Sharpe: X.XX
- Sharpe Retention: XX% ❌ (threshold: 80%)

**Why It Failed:**
- [Specific reason 1]
- [Specific reason 2]
- [Specific reason 3]

**Lessons Learned:**
- [Insight 1]
- [Insight 2]

**Recommendations:**
- [What to try next]
- [What to avoid]
```

---

**Inform User:**

**If VALIDATED:**
> "🎉 Strategy validated! [STRATEGY-ID] passed all criteria with XX% average Sharpe retention.
>
> ✅ Added to 'Validated Strategies' in registry.
>
> **Next Steps:**
> 1. Generate live config: `live_scenario_config.json`
> 2. Paper trade for 2-4 weeks
> 3. Re-validate when updating parameters
> 4. Deploy to production
>
> See full results in `docs/STRATEGY_REGISTRY.md`"

**If REJECTED:**
> "⚠️ Strategy rejected. [STRATEGY-ID] failed criteria: [REASON]
>
> Sharpe retention: XX% (threshold: 80%)
>
> ❌ Moved to 'Failed/Rejected' section in registry.
>
> **Lessons Learned:**
> - [Key insight 1]
> - [Key insight 2]
>
> **Recommendations:**
> - [What to try next]
>
> See full analysis in `docs/STRATEGY_REGISTRY.md`"

---

## File Structure Integration

```
futures-algo/
├── .claude/
│   └── skills/
│       └── trading-strategy-validator.md    ← This skill (complete validation)
│
├── backtest/
│   ├── data_loader.py                       ← Shared data loading (CRITICAL)
│   ├── backtest_runner.py                   ← Fast optimization (other skill)
│   ├── strategy_validator.py                ← Walk-forward CV (this skill)
│   └── templates/
│       ├── rsi_mtf_template.py
│       └── rsi_macd_mtf_template.py
│
├── backtest_results/
│   ├── [strategy_id]_screening_survivors.csv
│   ├── [strategy_id]_walk_forward_cv_results.csv
│   └── [strategy_id]_walk_forward_cv_charts.png
│
├── config/
│   ├── live_scenario_config.json            ← From trading-strategy-validator
│   └── validation_criteria.json             ← Validation thresholds
│
└── docs/
    ├── STRATEGY_REGISTRY.md                 ← This skill updates
    └── DATABENTO_INTEGRATION_GUIDE.md
```

---

## Error Handling

### Common Issues

**Issue: Data file not found**
```bash
# Solution
python scripts/fetch_databento_data.py --symbol ES

# Or fetch all
python scripts/fetch_databento_data.py --all

# Check cost first
python scripts/fetch_databento_data.py --check-cost
```

**Issue: Insufficient data for fold splitting**
```
Solution: Need at least 3-4 years of data for 4-fold walk-forward CV
Action: Expand date range or reduce number of folds
```

**Issue: No signals generated (0 trades)**
```
Solution: Check entry/exit conditions are not too restrictive
Action: Review indicator values, loosen parameters
```

**Issue: Walk-forward CV takes too long (>3 hours)**
```
Solution: Reduce survivors from screening, test fewer parameter combos
Action: Tighten screening criteria to get fewer survivors
```

**Issue: All folds fail validation**
```
Solution: Strategy may be overfit to screening period
Action: Try different parameter ranges or different indicators
```

---

## Integration with Other Skills

**This skill works with:**
- `data_loader.py` - Shared data loading module
- `live_scenario_config.json` - Output for live scanner

**Workflow:**
```
1. User has strategy idea or parameter update
    ↓
2. THIS SKILL: Rigorous validation (1-3 hours)
    ↓ (if validated ≥80% Sharpe retention)
3. Update STRATEGY_REGISTRY.md
    ↓
4. Generate live_scenario_config.json
    ↓
5. Scanner uses validated parameters
    ↓
6. When parameters need updating: Re-validate via THIS SKILL
```

---

## Final Checklist

Before marking validation complete, ensure:

- [ ] Registry checked for duplicates (Phase 1)
- [ ] Added to "Under Consideration" (Phase 2)
- [ ] Quick screening completed (Phase 3)
- [ ] Walk-forward CV completed with 4 folds (Phase 4)
- [ ] Validation criteria checked (Phase 5)
- [ ] Registry updated (VALIDATED or REJECTED) (Phase 6)
- [ ] User informed of results with next steps
- [ ] Results saved to `backtest_results/` directory

---

## Validation Standards

| Aspect | Details |
|--------|---------|
| **Purpose** | Rigorous validation of ALL strategies before deployment |
| **Time** | 1-3 hours |
| **Method** | Walk-forward CV (4 folds) |
| **Output** | STRATEGY_REGISTRY.md entry + live_scenario_config.json |
| **Use Case** | New strategies AND parameter updates |
| **Frequency** | Every time parameters change |
| **Threshold** | 80%+ Sharpe retention required for validation |

---

**Last Updated:** November 13, 2025  
**Version:** 2.0.0 (Futures-Algo Architecture)  
**Skill Type:** Autonomous execution with human approval checkpoints
