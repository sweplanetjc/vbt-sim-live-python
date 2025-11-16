"""Test bar aggregation from 1min to ANY timeframe.

Tests verify:
1. Generic timeframe support (m5, m27, etc.)
2. Per-symbol isolation
3. Symbol field preservation
4. OHLCV correctness
5. Period boundary detection
"""

from datetime import datetime, timedelta

import pytest
import pytz

from scanner.bar_aggregator import BarAggregator
from vbt_sim_live import TFs


def test_aggregator_initialization():
    """Should initialize with symbol and target timeframe."""
    agg = BarAggregator(symbol="ES.c.0", target_tf=TFs.m5)

    assert agg.symbol == "ES.c.0"
    assert agg.target_tf == TFs.m5
    assert agg.current_bar is None
    assert agg.period_start is None


def test_aggregates_1min_to_5min():
    """Should aggregate five 1-min bars into one 5-min bar.

    A 5-minute period starting at 09:30 includes bars at 09:30, 09:31, 09:32, 09:33, 09:34.
    The 6th bar (at 09:35) triggers completion of the previous period.
    """
    agg = BarAggregator(symbol="ES.c.0", target_tf=TFs.m5)

    # Create 6 consecutive 1-min bars
    base_time = datetime(2025, 11, 16, 9, 30, 0, tzinfo=pytz.UTC)

    bars_1min = []
    for i in range(6):
        bar = {
            "symbol": "ES.c.0",
            "date": base_time + timedelta(minutes=i),
            "date_l": base_time + timedelta(minutes=i),
            "open": 4500.0 + i,
            "high": 4505.0 + i,
            "low": 4495.0 + i,
            "close": 4502.0 + i,
            "volume": 100,
            "cpl": True,
        }
        bars_1min.append(bar)

    # Process bars - first 5 should not complete (bars 0-4)
    for i in range(5):
        result = agg.add_bar(bars_1min[i])
        assert result is None, f"Bar {i} should not complete period"

    # 6th bar (at 09:35) should complete the 09:30-09:34 period
    result = agg.add_bar(bars_1min[5])
    assert result is not None, "6th bar should complete 5-min period"

    # Verify OHLCV correctness - should only include bars 0-4
    assert result["symbol"] == "ES.c.0"
    assert result["open"] == 4500.0  # Bar 0's open
    assert result["close"] == 4506.0  # Bar 4's close (NOT bar 5!)
    assert result["high"] == max(b["high"] for b in bars_1min[:5])  # Only bars 0-4
    assert result["low"] == min(b["low"] for b in bars_1min[:5])
    assert result["volume"] == 500  # Sum of bars 0-4 only


def test_aggregates_to_27min():
    """Should work for 27-min timeframe (non-standard).

    27-minute period includes bars 0-26 (27 bars).
    The 28th bar triggers completion.
    """
    agg = BarAggregator(symbol="ES.c.0", target_tf=TFs.m27)

    # Create 28 bars
    base_time = datetime(2025, 11, 16, 9, 30, 0, tzinfo=pytz.UTC)

    bars = []
    for i in range(28):
        bars.append(
            {
                "symbol": "ES.c.0",
                "date": base_time + timedelta(minutes=i),
                "date_l": base_time + timedelta(minutes=i),
                "open": 4500.0 + (i * 0.1),
                "high": 4505.0,
                "low": 4495.0,
                "close": 4500.0,
                "volume": 100,
                "cpl": True,
            }
        )

    result = None
    for i, bar in enumerate(bars):
        r = agg.add_bar(bar)
        if i < 27:
            assert r is None, f"Bar {i} should not complete 27-min period"
        else:
            result = r

    assert result is not None, "28th bar should complete period"
    assert result["symbol"] == "ES.c.0"
    assert result["volume"] == 2700  # 27 * 100 (bars 0-26 only)
    assert result["open"] == 4500.0  # Bar 0's open
    assert result["close"] == 4500.0  # Bar 26's close


def test_symbol_field_preservation():
    """Every completed bar MUST include the 'symbol' field."""
    agg = BarAggregator(symbol="NQ.c.0", target_tf=TFs.m5)

    base_time = datetime(2025, 11, 16, 9, 30, 0, tzinfo=pytz.UTC)

    # Send 6 bars (6th triggers completion)
    result = None
    for i in range(6):
        bar = {
            "symbol": "NQ.c.0",
            "date": base_time + timedelta(minutes=i),
            "date_l": base_time + timedelta(minutes=i),
            "open": 15000.0,
            "high": 15005.0,
            "low": 14995.0,
            "close": 15000.0,
            "volume": 200,
            "cpl": True,
        }
        result = agg.add_bar(bar)

    assert result is not None
    assert "symbol" in result, "Completed bar must have 'symbol' field"
    assert result["symbol"] == "NQ.c.0"


def test_period_boundary_detection_m3():
    """Test boundary detection for m3 timeframe.

    Bars 0-2 complete when bar 3 arrives.
    Bars 3-5 complete when bar 6 arrives.
    """
    agg = BarAggregator(symbol="ES.c.0", target_tf=TFs.m3)

    base_time = datetime(2025, 11, 16, 9, 30, 0, tzinfo=pytz.UTC)

    # Send 7 bars (should complete 2 periods)
    completed_bars = []
    for i in range(7):
        bar = {
            "symbol": "ES.c.0",
            "date": base_time + timedelta(minutes=i),
            "date_l": base_time + timedelta(minutes=i),
            "open": 4500.0 + i,
            "high": 4505.0,
            "low": 4495.0,
            "close": 4500.0 + i,
            "volume": 100,
            "cpl": True,
        }
        result = agg.add_bar(bar)
        if result:
            completed_bars.append(result)

    assert len(completed_bars) == 2, "Should complete 2 m3 periods from 7 m1 bars"

    # First period: bars 0,1,2 (completed when bar 3 arrives)
    assert completed_bars[0]["open"] == 4500.0
    assert completed_bars[0]["close"] == 4502.0
    assert completed_bars[0]["volume"] == 300

    # Second period: bars 3,4,5 (completed when bar 6 arrives)
    assert completed_bars[1]["open"] == 4503.0
    assert completed_bars[1]["close"] == 4505.0
    assert completed_bars[1]["volume"] == 300


def test_ohlcv_correctness():
    """Test that OHLCV aggregation is correct."""
    agg = BarAggregator(symbol="GC.c.0", target_tf=TFs.m5)

    base_time = datetime(2025, 11, 16, 9, 30, 0, tzinfo=pytz.UTC)

    # Create bars with specific OHLC values to test aggregation
    bars = [
        {"open": 2000.0, "high": 2010.0, "low": 1995.0, "close": 2005.0, "volume": 50},
        {"open": 2005.0, "high": 2020.0, "low": 2000.0, "close": 2015.0, "volume": 75},
        {"open": 2015.0, "high": 2025.0, "low": 2010.0, "close": 2020.0, "volume": 100},
        {"open": 2020.0, "high": 2030.0, "low": 2015.0, "close": 2018.0, "volume": 60},
        {"open": 2018.0, "high": 2022.0, "low": 1990.0, "close": 1995.0, "volume": 115},
        {
            "open": 1995.0,
            "high": 2000.0,
            "low": 1985.0,
            "close": 1998.0,
            "volume": 50,
        },  # 6th bar triggers
    ]

    result = None
    for i, bar_data in enumerate(bars):
        bar = {
            "symbol": "GC.c.0",
            "date": base_time + timedelta(minutes=i),
            "date_l": base_time + timedelta(minutes=i),
            "open": bar_data["open"],
            "high": bar_data["high"],
            "low": bar_data["low"],
            "close": bar_data["close"],
            "volume": bar_data["volume"],
            "cpl": True,
        }
        result = agg.add_bar(bar)

    assert result is not None

    # Open = first bar's open (bar 0)
    assert result["open"] == 2000.0

    # High = max of all highs (bars 0-4 only, NOT bar 5)
    assert result["high"] == 2030.0

    # Low = min of all lows (bars 0-4 only, NOT bar 5)
    assert result["low"] == 1990.0

    # Close = last bar's close (bar 4, NOT bar 5)
    assert result["close"] == 1995.0

    # Volume = sum of volumes (bars 0-4 only, NOT bar 5)
    assert result["volume"] == 400


def test_multiple_periods():
    """Test that multiple periods can be aggregated consecutively.

    16 bars: bars 0-4 (period 1), bars 5-9 (period 2), bars 10-14 (period 3), bar 15 (starts period 4).
    Completions at bars 5, 10, 15.
    """
    agg = BarAggregator(symbol="ES.c.0", target_tf=TFs.m5)

    base_time = datetime(2025, 11, 16, 9, 30, 0, tzinfo=pytz.UTC)

    # Send 16 bars (should complete 3 periods)
    completed_bars = []
    for i in range(16):
        bar = {
            "symbol": "ES.c.0",
            "date": base_time + timedelta(minutes=i),
            "date_l": base_time + timedelta(minutes=i),
            "open": 4500.0 + i,
            "high": 4505.0 + i,
            "low": 4495.0 + i,
            "close": 4500.0 + i,
            "volume": 100,
            "cpl": True,
        }
        result = agg.add_bar(bar)
        if result:
            completed_bars.append(result)

    assert len(completed_bars) == 3, "Should complete 3 periods from 16 bars"

    # Verify each period
    for idx, completed in enumerate(completed_bars):
        expected_open = 4500.0 + (idx * 5)
        expected_close = 4500.0 + (idx * 5) + 4
        assert completed["open"] == expected_open
        assert completed["close"] == expected_close
        assert completed["volume"] == 500


def test_timeframe_m2():
    """Test m2 (2-minute) timeframe.

    Bars 0-1 complete when bar 2 arrives.
    Bars 2-3 complete when bar 4 arrives.
    """
    agg = BarAggregator(symbol="ES.c.0", target_tf=TFs.m2)

    base_time = datetime(2025, 11, 16, 9, 30, 0, tzinfo=pytz.UTC)

    # Send 5 bars (should complete 2 periods)
    completed_bars = []
    for i in range(5):
        bar = {
            "symbol": "ES.c.0",
            "date": base_time + timedelta(minutes=i),
            "date_l": base_time + timedelta(minutes=i),
            "open": 4500.0,
            "high": 4505.0,
            "low": 4495.0,
            "close": 4500.0,
            "volume": 100,
            "cpl": True,
        }
        result = agg.add_bar(bar)
        if result:
            completed_bars.append(result)

    assert len(completed_bars) == 2
    assert completed_bars[0]["volume"] == 200
    assert completed_bars[1]["volume"] == 200


def test_timeframe_m15():
    """Test m15 (15-minute) timeframe.

    Bars 0-14 (15 bars) complete when bar 15 arrives.
    """
    agg = BarAggregator(symbol="ES.c.0", target_tf=TFs.m15)

    base_time = datetime(2025, 11, 16, 9, 30, 0, tzinfo=pytz.UTC)

    # Send first 15 bars (should not complete)
    for i in range(15):
        bar = {
            "symbol": "ES.c.0",
            "date": base_time + timedelta(minutes=i),
            "date_l": base_time + timedelta(minutes=i),
            "open": 4500.0,
            "high": 4505.0,
            "low": 4495.0,
            "close": 4500.0,
            "volume": 100,
            "cpl": True,
        }
        result = agg.add_bar(bar)
        assert result is None

    # 16th bar triggers completion
    bar = {
        "symbol": "ES.c.0",
        "date": base_time + timedelta(minutes=15),
        "date_l": base_time + timedelta(minutes=15),
        "open": 4500.0,
        "high": 4505.0,
        "low": 4495.0,
        "close": 4500.0,
        "volume": 100,
        "cpl": True,
    }
    result = agg.add_bar(bar)
    assert result is not None
    assert result["volume"] == 1500  # Bars 0-14 only (15 bars)


def test_completed_bar_excludes_triggering_bar():
    """Completed bar should NOT include the bar that triggered completion."""
    agg = BarAggregator(symbol="ES.c.0", target_tf=TFs.m5)

    base_time = datetime(2025, 11, 16, 9, 30, 0, tzinfo=pytz.UTC)

    # Send 6 bars with distinct values
    for i in range(6):
        bar = {
            "symbol": "ES.c.0",
            "date": base_time + timedelta(minutes=i),
            "date_l": base_time + timedelta(minutes=i),
            "open": 4500.0 + i,
            "high": 4505.0 + i,
            "low": 4495.0 + i,
            "close": 4502.0 + i,
            "volume": 100,
            "cpl": True,
        }
        result = agg.add_bar(bar)
        if result:
            # Completed bar should have close from bar 4, NOT bar 5
            assert result["close"] == 4506.0  # Bar 4 (index 4)
            assert result["close"] != 4507.0  # Bar 5 should not be included!
            # Volume should be 500 (bars 0-4), not 600
            assert result["volume"] == 500
            # High should be from bar 4 (4509.0), not bar 5 (4510.0)
            assert result["high"] == 4509.0


def test_date_l_is_last_bar_of_period():
    """Completed bar's date_l should be from last bar of completed period."""
    agg = BarAggregator(symbol="ES.c.0", target_tf=TFs.m5)

    base_time = datetime(2025, 11, 16, 9, 30, 0, tzinfo=pytz.UTC)

    # Send 6 bars with distinct date_l values (30 seconds into each minute)
    for i in range(6):
        bar = {
            "symbol": "ES.c.0",
            "date": base_time + timedelta(minutes=i),
            "date_l": base_time + timedelta(minutes=i, seconds=30),  # 30 secs into minute
            "open": 4500.0,
            "high": 4505.0,
            "low": 4495.0,
            "close": 4500.0,
            "volume": 100,
            "cpl": True,
        }
        result = agg.add_bar(bar)
        if result:
            # date should be from first bar (09:30:00)
            assert result["date"] == base_time
            # date_l should be from last bar of period (09:34:30, NOT 09:35:30)
            expected_date_l = base_time + timedelta(minutes=4, seconds=30)
            assert result["date_l"] == expected_date_l


def test_symbol_mismatch_error():
    """Should raise ValueError when bar symbol doesn't match aggregator symbol."""
    agg = BarAggregator(symbol="ES.c.0", target_tf=TFs.m5)

    base_time = datetime(2025, 11, 16, 9, 30, 0, tzinfo=pytz.UTC)

    # Try to add bar with wrong symbol
    bar = {
        "symbol": "NQ.c.0",  # Wrong symbol!
        "date": base_time,
        "date_l": base_time,
        "open": 4500.0,
        "high": 4505.0,
        "low": 4495.0,
        "close": 4500.0,
        "volume": 100,
        "cpl": True,
    }

    with pytest.raises(ValueError, match="Symbol mismatch"):
        agg.add_bar(bar)

