"""Test Databento live feed with replay."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, Mock, patch

import pytest
from scanner.databento_live_feed import DatabentoLiveFeed


def test_databento_feed_initialization():
    """Feed should initialize with multiple symbols."""
    config = {
        "api_key": "test-key",
        "dataset": "GLBX.MDP3",
        "symbols": ["ES.c.0", "NQ.c.0", "GC.c.0"],
        "schema": "ohlcv-1m",
        "replay_hours": 24,
    }

    feed = DatabentoLiveFeed(config, on_bar_callback=Mock())
    assert feed.symbols == ["ES.c.0", "NQ.c.0", "GC.c.0"]
    assert feed.schema == "ohlcv-1m"
    assert feed.replay_hours == 24


@patch("scanner.databento_live_feed.db.Live")
def test_replay_request_calculates_times(mock_live):
    """Should request 24 hours of replay data."""
    config = {
        "api_key": "test-key",
        "dataset": "GLBX.MDP3",
        "symbols": ["ES.c.0"],
        "schema": "ohlcv-1m",
        "replay_hours": 24,
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
        "replay_hours": 24,
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

    assert bar_dict["symbol"] == "NQ.c.0"
    assert "open" in bar_dict
    assert "close" in bar_dict
