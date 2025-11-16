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
    live_ind = IndicatorCCI_(input_args=[high, low, close, 3], kwargs={})
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

    live_ind = IndicatorCCI_(input_args=[high, low, close, 3], kwargs={})
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
