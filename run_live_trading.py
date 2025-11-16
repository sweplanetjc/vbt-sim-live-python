#!/usr/bin/env python3
"""
Entry point for live trading system.

Usage:
    python run_live_trading.py config/live_trading_config.json
    python run_live_trading.py config/live_trading_config.json --log-level DEBUG
    python run_live_trading.py config/live_trading_config.json --log-file logs/trading.log
    python run_live_trading.py --help
"""

import argparse
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from logging_system import get_logger, setup_logging
from scanner.live_trading_orchestrator import LiveTradingOrchestrator


def main():
    """Main entry point for live trading."""
    parser = argparse.ArgumentParser(
        description="Start multi-symbol live trading system with Databento feed",
        epilog="Example: python run_live_trading.py config/live_trading_config.json",
    )
    parser.add_argument(
        "config_path", type=str, help="Path to live trading configuration JSON file"
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)",
    )
    parser.add_argument(
        "--log-file",
        type=str,
        default=None,
        help="Path to log file (default: console only)",
    )

    args = parser.parse_args()

    # Setup logging
    setup_logging(level=args.log_level, log_file=args.log_file)
    logger = get_logger(__name__)

    # Validate config file exists
    config_path = Path(args.config_path)
    if not config_path.exists():
        logger.error(f"Config file not found: {config_path}")
        sys.exit(1)

    # Start live trading
    logger.info(f"Starting live trading with config: {config_path}")
    logger.info(f"Log level: {args.log_level}")

    try:
        orchestrator = LiveTradingOrchestrator(str(config_path))
        orchestrator.start()  # Blocking - runs until Ctrl+C
    except KeyboardInterrupt:
        logger.info("Received Ctrl+C, shutting down...")
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        sys.exit(1)

    logger.info("Live trading stopped")


if __name__ == "__main__":
    main()
