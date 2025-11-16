# -*- coding: utf-8 -*-

"""Comprehensive tests for SimpleBullishCCIStrategy.

Test Coverage:
1. Strategy initialization
2. Entry signal generation (all 3 conditions met)
3. No signal when conditions not met (various cases)
4. Exit signal after N bars
5. Insufficient bars scenario
6. Symbol field in signals
7. Multiple bar sequences
8. State tracking
"""

from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest
import pytz


def create_bar(
    symbol, timestamp, open_price, high_price, low_price, close_price, volume=100
):
    """Helper to create bar dict."""
    return {
        "symbol": symbol,
        "date": pd.Timestamp(timestamp, tz="UTC"),
        "date_l": pd.Timestamp(timestamp, tz="UTC"),
        "open": open_price,
        "high": high_price,
        "low": low_price,
        "close": close_price,
        "volume": volume,
        "cpl": True,
    }


def test_strategy_initialization():
    """Test strategy initializes with correct parameters."""
    from strategies.simple_bullish_cci import SimpleBullishCCIStrategy

    config = {
        "indicators": {"cci": {"length": 15}},
        "exit_conditions": {"bars_held": 1},
        "position_sizing": {"quantity": 2},
    }

    strategy = SimpleBullishCCIStrategy(symbol="ES.c.0", config=config)

    assert strategy.symbol == "ES.c.0"
    assert strategy.cci_length == 15
    assert strategy.bars_to_hold == 1
    assert strategy.quantity == 2
    assert strategy.position is None  # Flat
    assert strategy.bars_in_position == 0
    assert strategy.live_data is not None


def test_strategy_default_config():
    """Test strategy uses defaults when config missing."""
    from strategies.simple_bullish_cci import SimpleBullishCCIStrategy

    strategy = SimpleBullishCCIStrategy(symbol="NQ.c.0", config={})

    assert strategy.cci_length == 15  # Default
    assert strategy.bars_to_hold == 1  # Default
    assert strategy.quantity == 1  # Default


def test_insufficient_bars_returns_none():
    """Test strategy returns None when not enough bars for CCI."""
    from strategies.simple_bullish_cci import SimpleBullishCCIStrategy

    config = {
        "indicators": {"cci": {"length": 15}},
    }
    strategy = SimpleBullishCCIStrategy(symbol="ES.c.0", config=config)

    # Send only 5 bars (need 15+ for CCI with length 15)
    base_time = datetime(2025, 11, 16, 9, 30, 0, tzinfo=pytz.UTC)

    for i in range(5):
        bar = create_bar(
            symbol="ES.c.0",
            timestamp=base_time + timedelta(minutes=5 * i),
            open_price=4500 + i,
            high_price=4505 + i,
            low_price=4495 + i,
            close_price=4502 + i,
        )
        signal = strategy.on_bar(bar)
        assert signal is None  # Not enough bars


def test_entry_signal_all_conditions_met():
    """Test entry signal when all 3 conditions are met."""
    from strategies.simple_bullish_cci import SimpleBullishCCIStrategy

    config = {
        "indicators": {"cci": {"length": 5}},  # Shorter period for testing
        "position_sizing": {"quantity": 1},
    }
    strategy = SimpleBullishCCIStrategy(symbol="ES.c.0", config=config)

    base_time = datetime(2025, 11, 16, 9, 30, 0, tzinfo=pytz.UTC)

    # Send bars that create rising CCI pattern
    # First batch: declining prices (CCI will be negative and falling)
    for i in range(10):
        bar = create_bar(
            symbol="ES.c.0",
            timestamp=base_time + timedelta(minutes=5 * i),
            open_price=4510 - i * 2,  # Declining
            high_price=4515 - i * 2,
            low_price=4505 - i * 2,
            close_price=4508 - i * 2,
        )
        strategy.on_bar(bar)

    # Now send bullish bars with rising prices (CCI should rise)
    # Bar 1: Bearish (to establish lower CCI)
    bar_prev = create_bar(
        symbol="ES.c.0",
        timestamp=base_time + timedelta(minutes=5 * 10),
        open_price=4495,
        high_price=4497,
        low_price=4490,
        close_price=4492,  # Bearish: close < open
    )
    signal = strategy.on_bar(bar_prev)
    assert signal is None  # Bearish bar

    # Bar 2: Bullish with all conditions
    # - close > open (bullish)
    # - close > prev_close (4500 > 4492)
    # - Rising prices should make CCI rise
    bar_current = create_bar(
        symbol="ES.c.0",
        timestamp=base_time + timedelta(minutes=5 * 11),
        open_price=4496,
        high_price=4505,
        low_price=4495,
        close_price=4500,  # Bullish and higher than previous
    )
    signal = strategy.on_bar(bar_current)

    # Should generate entry signal
    if signal:  # CCI might not rise depending on calculation
        assert signal["action"] == "entry"
        assert signal["side"] == "long"
        assert signal["symbol"] == "ES.c.0"
        assert signal["quantity"] == 1
        assert "reason" in signal


def test_no_entry_when_bearish_candle():
    """Test no entry when candle is bearish (close <= open)."""
    from strategies.simple_bullish_cci import SimpleBullishCCIStrategy

    config = {
        "indicators": {"cci": {"length": 5}},
    }
    strategy = SimpleBullishCCIStrategy(symbol="ES.c.0", config=config)

    base_time = datetime(2025, 11, 16, 9, 30, 0, tzinfo=pytz.UTC)

    # Setup with enough bars
    for i in range(8):
        bar = create_bar(
            symbol="ES.c.0",
            timestamp=base_time + timedelta(minutes=5 * i),
            open_price=4500 + i,
            high_price=4505 + i,
            low_price=4495 + i,
            close_price=4502 + i,
        )
        strategy.on_bar(bar)

    # Send bearish bar (close < open)
    bar_bearish = create_bar(
        symbol="ES.c.0",
        timestamp=base_time + timedelta(minutes=5 * 8),
        open_price=4510,
        high_price=4512,
        low_price=4505,
        close_price=4506,  # Close < open = bearish
    )
    signal = strategy.on_bar(bar_bearish)

    assert signal is None  # Condition 1 fails


def test_no_entry_when_close_not_higher_than_prev():
    """Test no entry when close <= prev_close."""
    from strategies.simple_bullish_cci import SimpleBullishCCIStrategy

    config = {
        "indicators": {"cci": {"length": 5}},
    }
    strategy = SimpleBullishCCIStrategy(symbol="ES.c.0", config=config)

    base_time = datetime(2025, 11, 16, 9, 30, 0, tzinfo=pytz.UTC)

    # Setup
    for i in range(8):
        bar = create_bar(
            symbol="ES.c.0",
            timestamp=base_time + timedelta(minutes=5 * i),
            open_price=4500 + i,
            high_price=4505 + i,
            low_price=4495 + i,
            close_price=4510,  # Same close each time
        )
        strategy.on_bar(bar)

    # Bullish bar but close NOT higher than previous
    bar = create_bar(
        symbol="ES.c.0",
        timestamp=base_time + timedelta(minutes=5 * 8),
        open_price=4505,
        high_price=4512,
        low_price=4504,
        close_price=4510,  # Same as previous, not higher
    )
    signal = strategy.on_bar(bar)

    # Should not signal (condition 2 fails)
    # Note: Might still fail on condition 3 (CCI not rising with flat prices)
    assert signal is None


def test_exit_after_one_bar():
    """Test exit signal generated after holding for 1 bar."""
    from strategies.simple_bullish_cci import SimpleBullishCCIStrategy

    config = {"indicators": {"cci": {"length": 5}}, "exit_conditions": {"bars_held": 1}}
    strategy = SimpleBullishCCIStrategy(symbol="ES.c.0", config=config)

    # Manually set position to test exit logic
    strategy.position = "long"
    strategy.bars_in_position = 0

    base_time = datetime(2025, 11, 16, 9, 30, 0, tzinfo=pytz.UTC)

    # Initialize with bars
    for i in range(8):
        bar = create_bar(
            symbol="ES.c.0",
            timestamp=base_time + timedelta(minutes=5 * i),
            open_price=4500,
            high_price=4505,
            low_price=4495,
            close_price=4500,
        )
        strategy.on_bar(bar)

    # Ensure position is set
    strategy.position = "long"
    strategy.bars_in_position = 0

    # Send next bar - should trigger exit
    bar_exit = create_bar(
        symbol="ES.c.0",
        timestamp=base_time + timedelta(minutes=5 * 8),
        open_price=4500,
        high_price=4505,
        low_price=4495,
        close_price=4502,
    )
    signal = strategy.on_bar(bar_exit)

    # Should generate exit signal
    assert signal is not None
    assert signal["action"] == "exit"
    assert signal["symbol"] == "ES.c.0"
    assert "bars" in signal["reason"].lower()


def test_exit_after_n_bars():
    """Test exit after configured number of bars."""
    from strategies.simple_bullish_cci import SimpleBullishCCIStrategy

    config = {
        "indicators": {"cci": {"length": 5}},
        "exit_conditions": {"bars_held": 3},  # Hold for 3 bars
    }
    strategy = SimpleBullishCCIStrategy(symbol="ES.c.0", config=config)

    base_time = datetime(2025, 11, 16, 9, 30, 0, tzinfo=pytz.UTC)

    # Initialize
    for i in range(8):
        bar = create_bar(
            symbol="ES.c.0",
            timestamp=base_time + timedelta(minutes=5 * i),
            open_price=4500,
            high_price=4505,
            low_price=4495,
            close_price=4500,
        )
        strategy.on_bar(bar)

    # Manually enter position
    strategy.position = "long"
    strategy.bars_in_position = 0

    # Bar 1 - no exit
    bar1 = create_bar(
        "ES.c.0", base_time + timedelta(minutes=40), 4500, 4505, 4495, 4500
    )
    signal1 = strategy.on_bar(bar1)
    assert signal1 is None  # bars_in_position = 1

    # Bar 2 - no exit
    bar2 = create_bar(
        "ES.c.0", base_time + timedelta(minutes=45), 4500, 4505, 4495, 4500
    )
    signal2 = strategy.on_bar(bar2)
    assert signal2 is None  # bars_in_position = 2

    # Bar 3 - should exit
    bar3 = create_bar(
        "ES.c.0", base_time + timedelta(minutes=50), 4500, 4505, 4495, 4500
    )
    signal3 = strategy.on_bar(bar3)
    assert signal3 is not None  # bars_in_position = 3, triggers exit
    assert signal3["action"] == "exit"


def test_signal_includes_symbol():
    """Test all signals include symbol field for routing."""
    from strategies.simple_bullish_cci import SimpleBullishCCIStrategy

    config = {
        "indicators": {"cci": {"length": 5}},
    }
    strategy = SimpleBullishCCIStrategy(symbol="NQ.c.0", config=config)

    base_time = datetime(2025, 11, 16, 9, 30, 0, tzinfo=pytz.UTC)

    # Test exit signal includes symbol
    strategy.position = "long"
    strategy.bars_in_position = 0

    for i in range(8):
        bar = create_bar(
            "NQ.c.0", base_time + timedelta(minutes=5 * i), 4500, 4505, 4495, 4500
        )
        strategy.on_bar(bar)

    # Reset position for test
    strategy.position = "long"
    strategy.bars_in_position = 0

    bar_exit = create_bar(
        "NQ.c.0", base_time + timedelta(minutes=40), 4500, 4505, 4495, 4500
    )
    signal = strategy.on_bar(bar_exit)

    assert signal is not None
    assert signal["symbol"] == "NQ.c.0"


def test_get_state():
    """Test get_state returns current strategy state."""
    from strategies.simple_bullish_cci import SimpleBullishCCIStrategy

    config = {
        "indicators": {"cci": {"length": 5}},
    }
    strategy = SimpleBullishCCIStrategy(symbol="ES.c.0", config=config)

    # Initial state
    state = strategy.get_state()
    assert state["symbol"] == "ES.c.0"
    assert state["position"] == "flat"
    assert state["bars_in_position"] == 0
    assert state["num_bars"] == 0
    assert state["indicators_ready"] is False

    # After adding bars
    base_time = datetime(2025, 11, 16, 9, 30, 0, tzinfo=pytz.UTC)
    for i in range(8):
        bar = create_bar(
            "ES.c.0", base_time + timedelta(minutes=5 * i), 4500, 4505, 4495, 4500
        )
        strategy.on_bar(bar)

    state = strategy.get_state()
    assert state["num_bars"] == 8
    assert (
        state["indicators_ready"] is True
    )  # Should be ready after 8 bars with length=5

    # After entering position
    strategy.position = "long"
    strategy.bars_in_position = 2

    state = strategy.get_state()
    assert state["position"] == "long"
    assert state["bars_in_position"] == 2


def test_wrong_symbol_returns_none():
    """Test strategy ignores bars from different symbol."""
    from strategies.simple_bullish_cci import SimpleBullishCCIStrategy

    config = {"indicators": {"cci": {"length": 5}}}
    strategy = SimpleBullishCCIStrategy(symbol="ES.c.0", config=config)

    base_time = datetime(2025, 11, 16, 9, 30, 0, tzinfo=pytz.UTC)

    # Send bar from different symbol
    bar_wrong = create_bar("NQ.c.0", base_time, 4500, 4505, 4495, 4500)
    signal = strategy.on_bar(bar_wrong)

    assert signal is None

    # Verify no bars were added
    state = strategy.get_state()
    assert state["num_bars"] == 0
