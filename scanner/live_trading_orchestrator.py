"""Multi-Symbol Live Trading Orchestrator.

Coordinates the entire live trading system:
- Manages unlimited symbols and strategies
- Routes 1-min bars to correct BarAggregators
- Distributes aggregated bars to strategies
- Executes signals through OrderManager
- Handles graceful shutdown

Architecture:
    DatabentoLiveFeed (all symbols)
        → on_1min_bar()
        → BarAggregator instances (per-symbol)
        → _on_aggregated_bar()
        → Strategy instances (per strategy config per symbol)
        → _execute_signal()
        → OrderManager
"""

import json
import os
import signal
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set

from execution.crosstrade_client import CrossTradeClient
from execution.order_manager import OrderManager
from logging_system import get_logger
from scanner.bar_aggregator import BarAggregator
from scanner.databento_live_feed import DatabentoLiveFeed
from vbt_sim_live import TFs

logger = get_logger(__name__)


class LiveTradingOrchestrator:
    """Orchestrates multi-symbol live trading system.

    Responsibilities:
    1. Load configuration from JSON
    2. Initialize all components (feed, aggregators, strategies, execution)
    3. Route incoming 1-min bars to correct aggregators
    4. Route completed bars to strategies
    5. Execute signals via OrderManager
    6. Handle graceful shutdown (Ctrl+C)

    Usage:
        orchestrator = LiveTradingOrchestrator("config/live_trading_config.json")
        orchestrator.start()  # Blocking - runs until Ctrl+C
    """

    def __init__(self, config_path: str):
        """Initialize orchestrator.

        Args:
            config_path: Path to live trading config JSON file
        """
        self.config_path = Path(config_path)
        self.config = None
        self.is_running = False

        # Per-symbol data structures
        self.aggregators = {}  # {symbol: {timeframe: BarAggregator}}
        self.strategies = []  # [Strategy instances]

        # Shared components
        self.feed = None
        self.order_manager = None

        # Replay mode flag - True during historical replay, False for live trading
        self.replay_mode = True

        # Load and validate config
        self._load_config()

        # Initialize components
        self._create_aggregators()
        self._create_strategies()
        self._initialize_feed()
        self._initialize_execution()

        # Register signal handlers for graceful shutdown
        self._register_signal_handlers()

        logger.info(
            f"LiveTradingOrchestrator initialized: "
            f"{len(self.strategies)} strategies, "
            f"{len(self.aggregators)} symbols"
        )

    def set_live_mode(self):
        """Switch from replay mode to live trading mode.

        Called when replay is complete and we transition to real-time data.
        """
        self.replay_mode = False
        logger.info("🔴 REPLAY COMPLETE - SWITCHING TO LIVE TRADING MODE")
        logger.info("=" * 80)

    def _load_config(self) -> None:
        """Load and validate configuration file.

        Raises:
            FileNotFoundError: If config file doesn't exist
            ValueError: If config validation fails
        """
        if not self.config_path.exists():
            raise FileNotFoundError(f"Config file not found: {self.config_path}")

        logger.info(f"Loading config from {self.config_path}")

        with open(self.config_path) as f:
            self.config = json.load(f)

        # Replace environment variables
        self._replace_env_vars()

        # Validate required sections
        required_sections = ["databento", "strategies", "execution"]
        for section in required_sections:
            if section not in self.config:
                raise ValueError(f"Missing required config section: {section}")

        # Validate strategy symbols are in databento symbols
        self._validate_strategy_symbols()

        logger.info("Configuration loaded and validated successfully")

    def _replace_env_vars(self) -> None:
        """Replace ${VAR} placeholders with environment variables."""
        import re

        config_str = json.dumps(self.config)
        pattern = r"\$\{([^}]+)\}"
        matches = re.findall(pattern, config_str)

        for var in matches:
            value = os.getenv(var, "")
            if not value:
                logger.warning(f"Environment variable {var} not set")
            config_str = config_str.replace(f"${{{var}}}", value)

        self.config = json.loads(config_str)

    def _validate_strategy_symbols(self) -> None:
        """Validate that all strategy symbols are in databento config.

        Raises:
            ValueError: If strategy references unknown symbols
        """
        databento_symbols = set(self.config["databento"]["symbols"])

        for strat_name, strat_config in self.config["strategies"].items():
            if not strat_config.get("enabled", True):
                continue

            strat_symbols = set(strat_config["symbols"])
            missing = strat_symbols - databento_symbols

            if missing:
                raise ValueError(
                    f"Strategy '{strat_name}' references symbols not in databento: {missing}"
                )

    def _create_aggregators(self) -> None:
        """Create BarAggregator instances for each symbol+timeframe combination.

        Extracts all unique (symbol, timeframe) pairs from enabled strategies
        and creates nested dict structure: {symbol: {timeframe: BarAggregator}}
        """
        logger.info("Creating bar aggregators...")

        # Extract all unique (symbol, timeframe) pairs
        pairs = set()
        for strat_name, strat_config in self.config["strategies"].items():
            if not strat_config.get("enabled", True):
                continue

            for symbol in strat_config["symbols"]:
                for tf_str in strat_config["timeframes"]:
                    # Convert string to TFs enum
                    try:
                        tf = TFs[tf_str]
                        pairs.add((symbol, tf))
                    except KeyError:
                        logger.error(
                            f"Invalid timeframe '{tf_str}' in strategy {strat_name}"
                        )
                        raise

        # Create aggregators organized by symbol
        for symbol, tf in pairs:
            if symbol not in self.aggregators:
                self.aggregators[symbol] = {}

            # Create one BarAggregator per symbol per timeframe
            self.aggregators[symbol][tf] = BarAggregator(symbol=symbol, target_tf=tf)

            logger.info(f"  Created aggregator: {symbol} {tf.name}")

        logger.info(
            f"Created {sum(len(v) for v in self.aggregators.values())} aggregators "
            f"for {len(self.aggregators)} symbols"
        )

    def _create_strategies(self) -> None:
        """Instantiate strategy for each enabled strategy config.

        Creates one strategy instance per (strategy_config, symbol) pair.
        For example, if strategy config has symbols=["ES.c.0", "NQ.c.0"],
        creates two separate strategy instances.
        """
        logger.info("Creating strategy instances...")

        for strat_name, strat_config in self.config["strategies"].items():
            if not strat_config.get("enabled", True):
                logger.info(f"  Skipping disabled strategy: {strat_name}")
                continue

            # Import strategy class (currently only SimpleBullishCCIStrategy)
            from strategies.simple_bullish_cci import SimpleBullishCCIStrategy

            # Create one instance per symbol
            for symbol in strat_config["symbols"]:
                strategy = SimpleBullishCCIStrategy(symbol=symbol, config=strat_config)

                self.strategies.append(
                    {
                        "name": strat_name,
                        "symbol": symbol,
                        "timeframe": strategy.timeframe,
                        "instance": strategy,
                    }
                )

                logger.info(
                    f"  Created strategy: {strat_name} for {symbol} ({strategy.timeframe.name})"
                )

        logger.info(f"Created {len(self.strategies)} strategy instances")

    def _initialize_feed(self) -> None:
        """Initialize DatabentoLiveFeed with all configured symbols."""
        logger.info("Initializing Databento feed...")

        databento_config = self.config["databento"]

        self.feed = DatabentoLiveFeed(
            api_key=databento_config["api_key"],
            dataset=databento_config["dataset"],
            symbols=databento_config["symbols"],
            schema=databento_config.get("schema", "ohlcv-1s"),
            replay_hours=databento_config.get("replay_hours", 24),
            on_1min_bar=self.on_1min_bar,
            on_replay_complete=self.set_live_mode,
        )

        logger.info(
            f"Feed initialized with {len(self.config['databento']['symbols'])} symbols"
        )

    def _initialize_execution(self) -> None:
        """Initialize execution layer (OrderManager).

        Only initializes if not in dry_run mode.
        """
        exec_config = self.config["execution"]

        if exec_config.get("dry_run", True):
            logger.info("Running in DRY RUN mode - orders will be logged only")
            self.order_manager = None
        else:
            logger.info("Initializing live execution...")

            # Create CrossTradeClient
            client = CrossTradeClient(
                api_key=exec_config["crosstrade_api_key"],
                base_url=exec_config.get(
                    "crosstrade_url", "https://app.crosstrade.io/v1/api"
                ),
                account=exec_config.get("nt8_account"),
            )

            # Create OrderManager
            self.order_manager = OrderManager(
                client=client, account=exec_config.get("nt8_account")
            )

            logger.info("Live execution initialized")

    def _register_signal_handlers(self) -> None:
        """Register signal handlers for graceful shutdown."""

        def signal_handler(sig, frame):
            logger.info(f"Received signal {sig}, shutting down...")
            self.stop()
            sys.exit(0)

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    def on_1min_bar(self, bar: Dict) -> None:
        """Callback from DatabentoLiveFeed - route to correct aggregator.

        This is called for EVERY 1-minute bar from ALL symbols.
        Routes each bar to the appropriate symbol's aggregators.

        Args:
            bar: 1-minute bar dict with 'symbol' field
        """
        symbol = bar["symbol"]

        logger.info(
            f"📊 Received 1-min bar: {symbol} @ {bar['close']:.2f} (time: {bar['date']})"
        )

        # Skip if we don't have aggregators for this symbol
        if symbol not in self.aggregators:
            logger.debug(f"Received bar for untracked symbol: {symbol}")
            return

        # Route to all timeframes for this symbol
        for tf, aggregator in self.aggregators[symbol].items():
            completed_bar = aggregator.add_bar(bar)
            if completed_bar:
                logger.info(
                    f"✅ Completed {tf.name} bar for {symbol}: {completed_bar['close']:.2f}"
                )
                self._on_aggregated_bar(completed_bar, tf)

    def _on_aggregated_bar(self, bar: Dict, timeframe: TFs) -> None:
        """Route completed bar to strategies that trade this symbol+timeframe.

        Args:
            bar: Completed aggregated bar (includes 'symbol' field)
            timeframe: Timeframe of the bar
        """
        symbol = bar["symbol"]

        # Find strategies that match this symbol and timeframe
        for strat_dict in self.strategies:
            if strat_dict["symbol"] == symbol and strat_dict["timeframe"] == timeframe:
                strategy = strat_dict["instance"]
                logger.info(
                    f"🔍 Evaluating strategy {strat_dict['name']} on {symbol} {timeframe.name} bar"
                )
                signal = strategy.on_bar(bar)

                if signal:
                    logger.info(
                        f"🚨 Signal from {strat_dict['name']} ({symbol}): {signal}"
                    )
                    self._execute_signal(signal)
                else:
                    logger.info(f"   No signal generated")

    def _execute_signal(self, signal: Dict) -> None:
        """Send signal to execution layer.

        Args:
            signal: Signal dict with keys:
                - action: "entry" or "exit"
                - side: "long" (for entry)
                - symbol: Symbol identifier
                - quantity: Position size
                - reason: Human-readable reason
        """
        if self.order_manager is None:
            # Dry run mode - just log
            logger.info(f"[DRY RUN] Would execute signal: {signal}")
            return

        try:
            if signal["action"] == "entry":
                # Map symbol format if needed
                # Databento uses "ES.c.0", CrossTrade might need "ES 03-25"
                instrument = self._map_symbol_to_instrument(signal["symbol"])

                # Determine order action based on side
                from execution.models import OrderAction

                order_action = (
                    OrderAction.BUY if signal["side"] == "long" else OrderAction.SELL
                )

                order = self.order_manager.submit_market_order(
                    instrument=instrument,
                    action=order_action,
                    quantity=signal["quantity"],
                )

                logger.info(
                    f"Entry order submitted: {order.orderId} ({signal['symbol']})"
                )

            elif signal["action"] == "exit":
                instrument = self._map_symbol_to_instrument(signal["symbol"])

                # Flatten position
                order = self.order_manager.flatten_position(instrument=instrument)

                logger.info(
                    f"Exit order submitted: {order.orderId} ({signal['symbol']})"
                )

        except Exception as e:
            logger.error(f"Error executing signal: {e}", exc_info=True)

    def _map_symbol_to_instrument(self, symbol: str) -> str:
        """Map Databento symbol format to CrossTrade instrument format.

        Args:
            symbol: Databento symbol (e.g., "ES.c.0")

        Returns:
            CrossTrade instrument name (e.g., "ES 03-25")

        Note: For now, just returns the symbol as-is.
        In production, would need proper symbol mapping logic.
        """
        # TODO: Implement proper symbol mapping
        # For now, assume symbols are already in correct format
        return symbol

    def start(self) -> None:
        """Start live trading.

        This is a blocking call that:
        1. Starts the Databento feed (24hr replay + live streaming)
        2. Processes bars continuously
        3. Executes strategies
        4. Manages positions

        Runs until Ctrl+C or stop() is called.
        """
        logger.info("=" * 80)
        logger.info("STARTING LIVE TRADING SYSTEM")
        logger.info("=" * 80)
        logger.info(f"Strategies: {len(self.strategies)}")
        logger.info(f"Symbols: {sorted(self.aggregators.keys())}")
        logger.info(
            f"Mode: {'DRY RUN' if self.order_manager is None else 'LIVE EXECUTION'}"
        )
        logger.info("=" * 80)

        self.is_running = True

        # Start feed (blocking call)
        try:
            self.feed.start()
        except Exception as e:
            logger.error(f"Feed error: {e}", exc_info=True)
            self.stop()

    def stop(self) -> None:
        """Graceful shutdown.

        Stops the feed and cleans up resources.
        """
        logger.info("Stopping live trading system...")

        self.is_running = False

        if self.feed:
            self.feed.stop()

        # Print final statistics
        self._print_final_stats()

        logger.info("Live trading system stopped")

    def _print_final_stats(self) -> None:
        """Print final statistics (for debugging)."""
        logger.info("=" * 80)
        logger.info("FINAL STATISTICS")
        logger.info("=" * 80)

        # Strategy states
        for strat_dict in self.strategies:
            state = strat_dict["instance"].get_state()
            logger.info(
                f"{strat_dict['name']} ({state['symbol']}): "
                f"position={state['position']}, "
                f"bars={state['num_bars']}, "
                f"cci={state.get('latest_cci', 'N/A')}"
            )

        # Aggregator states
        for symbol, aggregators in self.aggregators.items():
            for tf, agg in aggregators.items():
                logger.info(
                    f"Aggregator {symbol} {tf.name}: {agg.get_bars_count()} bars in period"
                )

        logger.info("=" * 80)

    def get_status(self) -> Dict:
        """Get current system status (for monitoring/debugging).

        Returns:
            Dict with system state information
        """
        return {
            "is_running": self.is_running,
            "num_strategies": len(self.strategies),
            "num_symbols": len(self.aggregators),
            "strategy_states": [
                {
                    "name": s["name"],
                    "symbol": s["symbol"],
                    "state": s["instance"].get_state(),
                }
                for s in self.strategies
            ],
            "mode": "dry_run" if self.order_manager is None else "live",
        }


if __name__ == "__main__":
    """Run orchestrator from command line."""
    import sys

    config_path = (
        sys.argv[1] if len(sys.argv) > 1 else "config/live_trading_config.json"
    )

    orchestrator = LiveTradingOrchestrator(config_path)
    orchestrator.start()
