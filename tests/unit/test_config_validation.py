"""Test live trading config validation."""

import json
from pathlib import Path

import pytest


def test_config_file_exists():
    """Config file should exist and be valid JSON."""
    config_path = Path("config/live_trading_config.json")
    assert config_path.exists(), "Config file missing"

    with open(config_path) as f:
        config = json.load(f)

    assert isinstance(config, dict)


def test_config_has_required_sections():
    """Config should have databento, strategies, execution sections."""
    config_path = Path("config/live_trading_config.json")
    with open(config_path) as f:
        config = json.load(f)

    assert "databento" in config
    assert "strategies" in config
    assert "execution" in config


def test_databento_has_multiple_symbols():
    """Databento should support multiple symbols."""
    config_path = Path("config/live_trading_config.json")
    with open(config_path) as f:
        config = json.load(f)

    symbols = config["databento"]["symbols"]
    assert isinstance(symbols, list)
    assert len(symbols) >= 1


def test_strategies_specify_symbols():
    """Each strategy should specify which symbols it trades."""
    config_path = Path("config/live_trading_config.json")
    with open(config_path) as f:
        config = json.load(f)

    for strat_name, strat_config in config["strategies"].items():
        assert "symbols" in strat_config, f"{strat_name} missing 'symbols'"
        assert isinstance(strat_config["symbols"], list)
        assert len(strat_config["symbols"]) >= 1


def test_strategy_symbols_in_databento_symbols():
    """Strategy symbols must be subset of databento symbols."""
    config_path = Path("config/live_trading_config.json")
    with open(config_path) as f:
        config = json.load(f)

    databento_symbols = set(config["databento"]["symbols"])

    for strat_name, strat_config in config["strategies"].items():
        if not strat_config.get("enabled", True):
            continue

        strat_symbols = set(strat_config["symbols"])
        missing = strat_symbols - databento_symbols

        assert len(missing) == 0, (
            f"{strat_name} references symbols not in databento: {missing}"
        )
