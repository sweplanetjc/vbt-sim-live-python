"""Comprehensive unit tests for LiveTradingOrchestrator.

Tests cover:
1. Config loading and validation
2. Aggregator creation (correct symbol+timeframe pairs)
3. Strategy instantiation
4. 1-min bar routing to aggregators
5. Aggregated bar routing to strategies
6. Signal routing to execution layer
7. Multi-symbol data isolation
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, Mock, call, patch

import pytest
import pytz

from scanner.live_trading_orchestrator import LiveTradingOrchestrator
from vbt_sim_live import TFs


@pytest.fixture
def test_config_path(tmp_path):
    """Create a temporary test config file."""
    config = {
        "databento": {
            "api_key": "test-key",
            "dataset": "GLBX.MDP3",
            "symbols": ["ES.c.0", "NQ.c.0", "GC.c.0"],
            "schema": "ohlcv-1m",
            "replay_hours": 24,
        },
        "strategies": {
            "test_strategy_ES": {
                "enabled": True,
                "description": "Test ES strategy",
                "symbols": ["ES.c.0"],
                "timeframes": ["m1", "m5"],
                "indicators": {"cci": {"length": 15}},
                "exit_conditions": {"bars_held": 1},
                "position_sizing": {"quantity": 1},
            },
            "test_strategy_NQ": {
                "enabled": True,
                "description": "Test NQ strategy",
                "symbols": ["NQ.c.0"],
                "timeframes": ["m1", "m5", "m15"],
                "indicators": {"cci": {"length": 20}},
                "exit_conditions": {"bars_held": 2},
                "position_sizing": {"quantity": 2},
            },
            "disabled_strategy": {
                "enabled": False,
                "symbols": ["GC.c.0"],
                "timeframes": ["m5"],
                "indicators": {"cci": {"length": 15}},
                "exit_conditions": {"bars_held": 1},
                "position_sizing": {"quantity": 1},
            },
        },
        "execution": {
            "crosstrade_api_key": "test-exec-key",
            "crosstrade_url": "https://test.crosstrade.io/v1/api",
            "nt8_account": "TEST123",
            "dry_run": True,
        },
        "logging": {"level": "INFO", "log_trades": True, "log_bars": False},
    }

    config_file = tmp_path / "test_config.json"
    with open(config_file, "w") as f:
        json.dump(config, f)

    return str(config_file)


# ===================================================================
# Test 1: Config Loading
# ===================================================================


@patch("scanner.live_trading_orchestrator.DatabentoLiveFeed")
def test_config_loading(mock_feed, test_config_path):
    """Test that config is loaded and validated correctly."""
    orchestrator = LiveTradingOrchestrator(test_config_path)

    # Config should be loaded
    assert orchestrator.config is not None
    assert "databento" in orchestrator.config
    assert "strategies" in orchestrator.config
    assert "execution" in orchestrator.config

    # Databento symbols should be loaded
    assert orchestrator.config["databento"]["symbols"] == [
        "ES.c.0",
        "NQ.c.0",
        "GC.c.0",
    ]


@patch("scanner.live_trading_orchestrator.DatabentoLiveFeed")
def test_config_missing_file(mock_feed):
    """Test that missing config file raises error."""
    with pytest.raises(FileNotFoundError):
        LiveTradingOrchestrator("nonexistent_config.json")


@patch("scanner.live_trading_orchestrator.DatabentoLiveFeed")
def test_config_validates_strategy_symbols(mock_feed, tmp_path):
    """Test that strategy symbols must be in databento symbols."""
    bad_config = {
        "databento": {
            "api_key": "test-key",
            "dataset": "GLBX.MDP3",
            "symbols": ["ES.c.0"],
            "schema": "ohlcv-1m",
            "replay_hours": 24,
        },
        "strategies": {
            "bad_strategy": {
                "enabled": True,
                "symbols": ["UNKNOWN.c.0"],  # Not in databento symbols
                "timeframes": ["m5"],
                "indicators": {"cci": {"length": 15}},
                "exit_conditions": {"bars_held": 1},
                "position_sizing": {"quantity": 1},
            }
        },
        "execution": {"dry_run": True},
    }

    config_file = tmp_path / "bad_config.json"
    with open(config_file, "w") as f:
        json.dump(bad_config, f)

    with pytest.raises(ValueError, match="references symbols not in databento"):
        LiveTradingOrchestrator(str(config_file))


# ===================================================================
# Test 2: Aggregator Creation
# ===================================================================


@patch("scanner.live_trading_orchestrator.DatabentoLiveFeed")
def test_aggregator_creation(mock_feed, test_config_path):
    """Test that aggregators are created for correct symbol+timeframe pairs."""
    orchestrator = LiveTradingOrchestrator(test_config_path)

    # Should have aggregators for ES and NQ (GC disabled)
    assert "ES.c.0" in orchestrator.aggregators
    assert "NQ.c.0" in orchestrator.aggregators
    assert "GC.c.0" not in orchestrator.aggregators

    # ES should have m1 and m5 aggregators
    assert TFs.m1 in orchestrator.aggregators["ES.c.0"]
    assert TFs.m5 in orchestrator.aggregators["ES.c.0"]
    assert TFs.m15 not in orchestrator.aggregators["ES.c.0"]

    # NQ should have m1, m5, and m15 aggregators
    assert TFs.m1 in orchestrator.aggregators["NQ.c.0"]
    assert TFs.m5 in orchestrator.aggregators["NQ.c.0"]
    assert TFs.m15 in orchestrator.aggregators["NQ.c.0"]


@patch("scanner.live_trading_orchestrator.DatabentoLiveFeed")
def test_aggregators_are_separate_instances(mock_feed, test_config_path):
    """Test that each symbol gets separate aggregator instances."""
    orchestrator = LiveTradingOrchestrator(test_config_path)

    # ES m5 and NQ m5 should be different instances
    es_m5 = orchestrator.aggregators["ES.c.0"][TFs.m5]
    nq_m5 = orchestrator.aggregators["NQ.c.0"][TFs.m5]

    assert es_m5 is not nq_m5
    assert es_m5.symbol == "ES.c.0"
    assert nq_m5.symbol == "NQ.c.0"


# ===================================================================
# Test 3: Strategy Instantiation
# ===================================================================


@patch("scanner.live_trading_orchestrator.DatabentoLiveFeed")
def test_strategy_instantiation(mock_feed, test_config_path):
    """Test that strategies are instantiated correctly."""
    orchestrator = LiveTradingOrchestrator(test_config_path)

    # Should have 2 strategy instances (ES and NQ, GC disabled)
    assert len(orchestrator.strategies) == 2

    # Check ES strategy
    es_strat = next(s for s in orchestrator.strategies if s["symbol"] == "ES.c.0")
    assert es_strat["name"] == "test_strategy_ES"
    assert es_strat["timeframe"] == TFs.m5
    assert es_strat["instance"] is not None

    # Check NQ strategy
    nq_strat = next(s for s in orchestrator.strategies if s["symbol"] == "NQ.c.0")
    assert nq_strat["name"] == "test_strategy_NQ"
    assert nq_strat["timeframe"] == TFs.m5


@patch("scanner.live_trading_orchestrator.DatabentoLiveFeed")
def test_disabled_strategies_not_created(mock_feed, test_config_path):
    """Test that disabled strategies are not instantiated."""
    orchestrator = LiveTradingOrchestrator(test_config_path)

    # Should not have strategy for GC (disabled)
    gc_strats = [s for s in orchestrator.strategies if s["symbol"] == "GC.c.0"]
    assert len(gc_strats) == 0


# ===================================================================
# Test 4: 1-Min Bar Routing to Aggregators
# ===================================================================


@patch("scanner.live_trading_orchestrator.DatabentoLiveFeed")
def test_1min_bar_routing(mock_feed, test_config_path):
    """Test that 1-min bars are routed to correct aggregators."""
    orchestrator = LiveTradingOrchestrator(test_config_path)

    # Mock aggregator methods
    for symbol, aggregators in orchestrator.aggregators.items():
        for tf, agg in aggregators.items():
            agg.add_bar = Mock(return_value=None)

    # Send ES bar
    es_bar = {
        "symbol": "ES.c.0",
        "date": datetime(2025, 11, 16, 9, 30, 0, tzinfo=pytz.UTC),
        "date_l": datetime(2025, 11, 16, 9, 30, 0, tzinfo=pytz.UTC),
        "open": 4500.0,
        "high": 4505.0,
        "low": 4495.0,
        "close": 4502.0,
        "volume": 100,
        "cpl": True,
    }

    orchestrator.on_1min_bar(es_bar)

    # ES aggregators should receive the bar
    orchestrator.aggregators["ES.c.0"][TFs.m1].add_bar.assert_called_once_with(es_bar)
    orchestrator.aggregators["ES.c.0"][TFs.m5].add_bar.assert_called_once_with(es_bar)

    # NQ aggregators should NOT receive the bar
    orchestrator.aggregators["NQ.c.0"][TFs.m1].add_bar.assert_not_called()
    orchestrator.aggregators["NQ.c.0"][TFs.m5].add_bar.assert_not_called()


@patch("scanner.live_trading_orchestrator.DatabentoLiveFeed")
def test_multi_symbol_bar_isolation(mock_feed, test_config_path):
    """Test that bars from different symbols don't cross-contaminate."""
    orchestrator = LiveTradingOrchestrator(test_config_path)

    # Mock aggregators
    for symbol, aggregators in orchestrator.aggregators.items():
        for tf, agg in aggregators.items():
            agg.add_bar = Mock(return_value=None)

    base_time = datetime(2025, 11, 16, 9, 30, 0, tzinfo=pytz.UTC)

    # Send 5 ES bars and 5 NQ bars
    for i in range(5):
        es_bar = {
            "symbol": "ES.c.0",
            "date": base_time + timedelta(minutes=i),
            "date_l": base_time + timedelta(minutes=i),
            "open": 4500.0 + i,
            "high": 4505.0,
            "low": 4495.0,
            "close": 4500.0,
            "volume": 100,
            "cpl": True,
        }
        orchestrator.on_1min_bar(es_bar)

        nq_bar = {
            "symbol": "NQ.c.0",
            "date": base_time + timedelta(minutes=i),
            "date_l": base_time + timedelta(minutes=i),
            "open": 15000.0 + i,
            "high": 15005.0,
            "low": 14995.0,
            "close": 15000.0,
            "volume": 200,
            "cpl": True,
        }
        orchestrator.on_1min_bar(nq_bar)

    # ES aggregators should have received exactly 5 ES bars
    assert orchestrator.aggregators["ES.c.0"][TFs.m1].add_bar.call_count == 5

    # NQ aggregators should have received exactly 5 NQ bars
    assert orchestrator.aggregators["NQ.c.0"][TFs.m1].add_bar.call_count == 5

    # Verify ES aggregator only received ES bars (not NQ bars)
    for call_obj in orchestrator.aggregators["ES.c.0"][TFs.m1].add_bar.call_args_list:
        bar = call_obj[0][0]  # First positional argument
        assert bar["symbol"] == "ES.c.0"
        assert bar["open"] >= 4500  # ES price range

    # Verify NQ aggregator only received NQ bars (not ES bars)
    for call_obj in orchestrator.aggregators["NQ.c.0"][TFs.m1].add_bar.call_args_list:
        bar = call_obj[0][0]
        assert bar["symbol"] == "NQ.c.0"
        assert bar["open"] >= 15000  # NQ price range


# ===================================================================
# Test 5: Aggregated Bar Routing to Strategies
# ===================================================================


@patch("scanner.live_trading_orchestrator.DatabentoLiveFeed")
def test_aggregated_bar_routing_to_strategies(mock_feed, test_config_path):
    """Test that completed bars are routed to correct strategies."""
    orchestrator = LiveTradingOrchestrator(test_config_path)

    # Mock strategy on_bar methods
    for strat in orchestrator.strategies:
        strat["instance"].on_bar = Mock(return_value=None)

    # Create completed 5-min bar for ES
    completed_bar = {
        "symbol": "ES.c.0",
        "date": datetime(2025, 11, 16, 9, 30, 0, tzinfo=pytz.UTC),
        "date_l": datetime(2025, 11, 16, 9, 35, 0, tzinfo=pytz.UTC),
        "open": 4500.0,
        "high": 4510.0,
        "low": 4495.0,
        "close": 4505.0,
        "volume": 500,
        "cpl": True,
    }

    orchestrator._on_aggregated_bar(completed_bar, TFs.m5)

    # ES strategy should receive the bar
    es_strat = next(s for s in orchestrator.strategies if s["symbol"] == "ES.c.0")
    es_strat["instance"].on_bar.assert_called_once_with(completed_bar)

    # NQ strategy should NOT receive the bar
    nq_strat = next(s for s in orchestrator.strategies if s["symbol"] == "NQ.c.0")
    nq_strat["instance"].on_bar.assert_not_called()


@patch("scanner.live_trading_orchestrator.DatabentoLiveFeed")
def test_strategy_receives_correct_timeframe(mock_feed, test_config_path):
    """Test that strategies only receive bars for their configured timeframe."""
    orchestrator = LiveTradingOrchestrator(test_config_path)

    # Mock NQ strategy (trades m5 timeframe)
    nq_strat = next(s for s in orchestrator.strategies if s["symbol"] == "NQ.c.0")
    nq_strat["instance"].on_bar = Mock(return_value=None)

    # Send m5 bar - should be received
    m5_bar = {
        "symbol": "NQ.c.0",
        "date": datetime(2025, 11, 16, 9, 30, 0, tzinfo=pytz.UTC),
        "open": 15000.0,
        "high": 15005.0,
        "low": 14995.0,
        "close": 15000.0,
        "volume": 500,
        "cpl": True,
    }
    orchestrator._on_aggregated_bar(m5_bar, TFs.m5)
    nq_strat["instance"].on_bar.assert_called_once()

    # Reset mock
    nq_strat["instance"].on_bar.reset_mock()

    # Send m15 bar - should NOT be received (strategy uses m5)
    m15_bar = {
        "symbol": "NQ.c.0",
        "date": datetime(2025, 11, 16, 9, 30, 0, tzinfo=pytz.UTC),
        "open": 15000.0,
        "high": 15010.0,
        "low": 14990.0,
        "close": 15005.0,
        "volume": 1500,
        "cpl": True,
    }
    orchestrator._on_aggregated_bar(m15_bar, TFs.m15)
    nq_strat["instance"].on_bar.assert_not_called()


# ===================================================================
# Test 6: Signal Routing to Execution Layer
# ===================================================================


@patch("scanner.live_trading_orchestrator.DatabentoLiveFeed")
def test_signal_execution_dry_run(mock_feed, test_config_path):
    """Test that signals are logged in dry run mode."""
    orchestrator = LiveTradingOrchestrator(test_config_path)

    # Should be in dry run mode
    assert orchestrator.order_manager is None

    # Send entry signal
    entry_signal = {
        "action": "entry",
        "side": "long",
        "symbol": "ES.c.0",
        "quantity": 1,
        "reason": "Test entry",
    }

    # Should not raise error (just logs)
    orchestrator._execute_signal(entry_signal)

    # Send exit signal
    exit_signal = {
        "action": "exit",
        "symbol": "ES.c.0",
        "quantity": 1,
        "reason": "Test exit",
    }

    orchestrator._execute_signal(exit_signal)


@patch("scanner.live_trading_orchestrator.DatabentoLiveFeed")
@patch("scanner.live_trading_orchestrator.OrderManager")
@patch("scanner.live_trading_orchestrator.CrossTradeClient")
def test_signal_execution_live_mode(
    mock_client_class, mock_manager_class, mock_feed, tmp_path
):
    """Test that signals are executed in live mode."""
    # Create config with dry_run=False
    live_config = {
        "databento": {
            "api_key": "test-key",
            "dataset": "GLBX.MDP3",
            "symbols": ["ES.c.0"],
            "schema": "ohlcv-1m",
            "replay_hours": 24,
        },
        "strategies": {
            "test_strategy": {
                "enabled": True,
                "symbols": ["ES.c.0"],
                "timeframes": ["m5"],
                "indicators": {"cci": {"length": 15}},
                "exit_conditions": {"bars_held": 1},
                "position_sizing": {"quantity": 1},
            }
        },
        "execution": {
            "crosstrade_api_key": "live-key",
            "crosstrade_url": "https://live.crosstrade.io/v1/api",
            "nt8_account": "LIVE123",
            "dry_run": False,  # Live mode
        },
    }

    config_file = tmp_path / "live_config.json"
    with open(config_file, "w") as f:
        json.dump(live_config, f)

    # Mock OrderManager
    mock_manager = Mock()
    mock_order = Mock()
    mock_order.orderId = "ORDER123"
    mock_manager.submit_market_order.return_value = mock_order
    mock_manager.flatten_position.return_value = mock_order
    mock_manager_class.return_value = mock_manager

    # Mock CrossTradeClient
    mock_client = Mock()
    mock_client_class.return_value = mock_client

    orchestrator = LiveTradingOrchestrator(str(config_file))

    # Should have order manager
    assert orchestrator.order_manager is not None

    # Send entry signal
    from execution.models import OrderAction

    entry_signal = {
        "action": "entry",
        "side": "long",
        "symbol": "ES.c.0",
        "quantity": 1,
        "reason": "Test entry",
    }

    orchestrator._execute_signal(entry_signal)

    # Should have called submit_market_order
    mock_manager.submit_market_order.assert_called_once()
    call_args = mock_manager.submit_market_order.call_args[1]
    assert call_args["quantity"] == 1


# ===================================================================
# Test 7: Multi-Symbol Data Isolation
# ===================================================================


@patch("scanner.live_trading_orchestrator.DatabentoLiveFeed")
def test_multi_symbol_complete_isolation(mock_feed, test_config_path):
    """Test complete end-to-end isolation between symbols."""
    orchestrator = LiveTradingOrchestrator(test_config_path)

    # Mock all strategy on_bar methods
    for strat in orchestrator.strategies:
        strat["instance"].on_bar = Mock(return_value=None)

    base_time = datetime(2025, 11, 16, 9, 30, 0, tzinfo=pytz.UTC)

    # Send 5 ES bars (should complete one 5-min bar)
    for i in range(5):
        es_bar = {
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
        orchestrator.on_1min_bar(es_bar)

    # Send 5 NQ bars (should complete one 5-min bar)
    for i in range(5):
        nq_bar = {
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
        orchestrator.on_1min_bar(nq_bar)

    # ES strategy should have been called (once for completed 5-min bar)
    es_strat = next(s for s in orchestrator.strategies if s["symbol"] == "ES.c.0")
    assert es_strat["instance"].on_bar.call_count >= 1

    # Verify ES strategy only received ES bars
    for call_obj in es_strat["instance"].on_bar.call_args_list:
        bar = call_obj[0][0]
        assert bar["symbol"] == "ES.c.0"

    # NQ strategy should have been called
    nq_strat = next(s for s in orchestrator.strategies if s["symbol"] == "NQ.c.0")
    assert nq_strat["instance"].on_bar.call_count >= 1

    # Verify NQ strategy only received NQ bars
    for call_obj in nq_strat["instance"].on_bar.call_args_list:
        bar = call_obj[0][0]
        assert bar["symbol"] == "NQ.c.0"


# ===================================================================
# Additional Tests
# ===================================================================


@patch("scanner.live_trading_orchestrator.DatabentoLiveFeed")
def test_get_status(mock_feed, test_config_path):
    """Test get_status returns correct system state."""
    orchestrator = LiveTradingOrchestrator(test_config_path)

    status = orchestrator.get_status()

    assert "is_running" in status
    assert status["num_strategies"] == 2
    assert status["num_symbols"] == 2  # ES and NQ
    assert status["mode"] == "dry_run"
    assert len(status["strategy_states"]) == 2


@patch("scanner.live_trading_orchestrator.DatabentoLiveFeed")
def test_unknown_symbol_ignored(mock_feed, test_config_path):
    """Test that bars from unknown symbols are ignored gracefully."""
    orchestrator = LiveTradingOrchestrator(test_config_path)

    # Send bar for symbol not in config
    unknown_bar = {
        "symbol": "UNKNOWN.c.0",
        "date": datetime(2025, 11, 16, 9, 30, 0, tzinfo=pytz.UTC),
        "date_l": datetime(2025, 11, 16, 9, 30, 0, tzinfo=pytz.UTC),
        "open": 1000.0,
        "high": 1005.0,
        "low": 995.0,
        "close": 1000.0,
        "volume": 100,
        "cpl": True,
    }

    # Should not raise error
    orchestrator.on_1min_bar(unknown_bar)


@patch("scanner.live_trading_orchestrator.DatabentoLiveFeed")
def test_environment_variable_replacement(mock_feed, tmp_path):
    """Test that environment variables are replaced in config."""
    import os

    # Set test environment variable
    os.environ["TEST_API_KEY"] = "my-secret-key"

    config = {
        "databento": {
            "api_key": "${TEST_API_KEY}",
            "dataset": "GLBX.MDP3",
            "symbols": ["ES.c.0"],
            "schema": "ohlcv-1m",
            "replay_hours": 24,
        },
        "strategies": {
            "test_strategy": {
                "enabled": True,
                "symbols": ["ES.c.0"],
                "timeframes": ["m5"],
                "indicators": {"cci": {"length": 15}},
                "exit_conditions": {"bars_held": 1},
                "position_sizing": {"quantity": 1},
            }
        },
        "execution": {"dry_run": True},
    }

    config_file = tmp_path / "env_config.json"
    with open(config_file, "w") as f:
        json.dump(config, f)

    orchestrator = LiveTradingOrchestrator(str(config_file))

    # API key should be replaced
    assert orchestrator.config["databento"]["api_key"] == "my-secret-key"

    # Clean up
    del os.environ["TEST_API_KEY"]
