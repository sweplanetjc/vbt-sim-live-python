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
    """Should aggregate five 1-min bars into one 5-min bar."""
    agg = BarAggregator(symbol="ES.c.0", target_tf=TFs.m5)

    # Create 5 consecutive 1-min bars
    base_time = datetime(2025, 11, 16, 9, 30, 0, tzinfo=pytz.UTC)

    bars_1min = []
    for i in range(5):
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

    # Process bars - first 4 should not complete
    for i in range(4):
        result = agg.add_bar(bars_1min[i])
        assert result is None, f"Bar {i} should not complete period"

    # 5th bar should complete the period
    result = agg.add_bar(bars_1min[4])
    assert result is not None, "5th bar should complete 5-min period"

    # Verify OHLCV correctness
    assert result["symbol"] == "ES.c.0"
    assert result["open"] == 4500.0  # First bar's open
    assert result["close"] == 4506.0  # Last bar's close
    assert result["high"] == max(b["high"] for b in bars_1min)
    assert result["low"] == min(b["low"] for b in bars_1min)
    assert result["volume"] == 500  # Sum of all volumes


def test_aggregates_to_27min():
    """Should work for 27-min timeframe (non-standard)."""
    agg = BarAggregator(symbol="ES.c.0", target_tf=TFs.m27)

    # Create 27 bars
    base_time = datetime(2025, 11, 16, 9, 30, 0, tzinfo=pytz.UTC)

    bars = []
    for i in range(27):
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
        if i < 26:
            assert r is None, f"Bar {i} should not complete 27-min period"
        else:
            result = r

    assert result is not None, "27th bar should complete period"
    assert result["symbol"] == "ES.c.0"
    assert result["volume"] == 2700  # 27 * 100
    assert result["open"] == 4500.0
    assert result["close"] == 4500.0


def test_symbol_field_preservation():
    """Every completed bar MUST include the 'symbol' field."""
    agg = BarAggregator(symbol="NQ.c.0", target_tf=TFs.m5)

    base_time = datetime(2025, 11, 16, 9, 30, 0, tzinfo=pytz.UTC)

    # Send 5 bars
    for i in range(5):
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
    """Test boundary detection for m3 timeframe."""
    agg = BarAggregator(symbol="ES.c.0", target_tf=TFs.m3)

    base_time = datetime(2025, 11, 16, 9, 30, 0, tzinfo=pytz.UTC)

    # Send 6 bars (should complete 2 periods)
    completed_bars = []
    for i in range(6):
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

    assert len(completed_bars) == 2, "Should complete 2 m3 periods from 6 m1 bars"

    # First period: bars 0,1,2
    assert completed_bars[0]["open"] == 4500.0
    assert completed_bars[0]["close"] == 4502.0
    assert completed_bars[0]["volume"] == 300

    # Second period: bars 3,4,5
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

    # Open = first bar's open
    assert result["open"] == 2000.0

    # High = max of all highs
    assert result["high"] == 2030.0

    # Low = min of all lows
    assert result["low"] == 1990.0

    # Close = last bar's close
    assert result["close"] == 1995.0

    # Volume = sum of all volumes
    assert result["volume"] == 400


def test_multiple_periods():
    """Test that multiple periods can be aggregated consecutively."""
    agg = BarAggregator(symbol="ES.c.0", target_tf=TFs.m5)

    base_time = datetime(2025, 11, 16, 9, 30, 0, tzinfo=pytz.UTC)

    # Send 15 bars (should complete 3 periods)
    completed_bars = []
    for i in range(15):
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

    assert len(completed_bars) == 3, "Should complete 3 periods from 15 bars"

    # Verify each period
    for idx, completed in enumerate(completed_bars):
        expected_open = 4500.0 + (idx * 5)
        expected_close = 4500.0 + (idx * 5) + 4
        assert completed["open"] == expected_open
        assert completed["close"] == expected_close
        assert completed["volume"] == 500


def test_timeframe_m2():
    """Test m2 (2-minute) timeframe."""
    agg = BarAggregator(symbol="ES.c.0", target_tf=TFs.m2)

    base_time = datetime(2025, 11, 16, 9, 30, 0, tzinfo=pytz.UTC)

    # Send 4 bars (should complete 2 periods)
    completed_bars = []
    for i in range(4):
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
    """Test m15 (15-minute) timeframe."""
    agg = BarAggregator(symbol="ES.c.0", target_tf=TFs.m15)

    base_time = datetime(2025, 11, 16, 9, 30, 0, tzinfo=pytz.UTC)

    # Send 15 bars
    for i in range(14):
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

    # 15th bar completes
    bar = {
        "symbol": "ES.c.0",
        "date": base_time + timedelta(minutes=14),
        "date_l": base_time + timedelta(minutes=14),
        "open": 4500.0,
        "high": 4505.0,
        "low": 4495.0,
        "close": 4500.0,
        "volume": 100,
        "cpl": True,
    }
    result = agg.add_bar(bar)
    assert result is not None
    assert result["volume"] == 1500
    assert result is not None
    assert result["volume"] == 1500
