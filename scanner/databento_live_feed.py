"""Databento live feed with intraday replay support.

Supports unlimited symbols - only limited by Databento plan/costs.
"""

from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional

import pandas as pd
import pytz

import databento as db
from logging_system import get_logger
from scanner.second_to_minute_aggregator import SecondToMinuteAggregator

logger = get_logger(__name__)


class DatabentoLiveFeed:
    """Streams live 1-minute OHLCV bars from Databento with 24hr replay.

    Internally receives 1-second bars from Databento (required for RAW_SYMBOL live data)
    and aggregates them into 1-minute bars before calling on_bar_callback.

    Supports ANY number of symbols (limited only by Databento API limits).
    Each bar includes symbol identifier for routing.

    Usage:
        def on_bar(bar_dict):
            # Receives 1-minute bars
            symbol = bar_dict['symbol']
            print(f"{symbol}: {bar_dict['close']}")

        def on_replay_complete():
            print("Replay finished, switching to live mode")

        feed = DatabentoLiveFeed(
            api_key="...",
            dataset="GLBX.MDP3",
            symbols=["ESZ5", "NQZ5", "GCX5", ...],  # RAW_SYMBOL format
            schema="ohlcv-1s",  # 1-second bars (aggregated to 1-min internally)
            replay_hours=24,
            on_1min_bar=on_bar,
            on_replay_complete=on_replay_complete,
        )
        feed.start()  # Blocking - runs forever
    """

    def __init__(
        self,
        api_key: str,
        dataset: str,
        symbols: List[str],
        schema: str = "ohlcv-1s",
        replay_hours: int = 24,
        on_1min_bar: Optional[Callable] = None,
        on_replay_complete: Optional[Callable] = None,
    ):
        """Initialize Databento live feed.

        Args:
            api_key: Databento API key
            dataset: Dataset name (e.g., "GLBX.MDP3")
            symbols: List of symbols to stream
            schema: Data schema (default: ohlcv-1s)
            replay_hours: Hours of historical replay (default: 24)
            on_1min_bar: Callback for completed 1-minute bars
            on_replay_complete: Callback when replay finishes
        """
        self.api_key = api_key
        self.dataset = dataset
        self.symbols = symbols  # Can be unlimited list
        self.schema = schema
        self.replay_hours = replay_hours
        self.on_bar_callback = on_1min_bar
        self.on_replay_complete = on_replay_complete

        self.client = None
        self.is_running = False

        # Symbol mapping: instrument_id → symbol name
        # Will be populated when we receive data
        self.symbol_map = {}

        # Create 1s→1m aggregators for each symbol
        # These aggregate 1-second bars from Databento into 1-minute bars
        # before passing to on_bar_callback
        self.aggregators = {}
        for symbol in self.symbols:
            self.aggregators[symbol] = SecondToMinuteAggregator(
                symbol=symbol,
                on_1min_bar=self.on_bar_callback,  # Aggregator calls this with 1-min bars
            )

        logger.info(
            f"DatabentoLiveFeed initialized: {len(self.symbols)} symbols, replay={self.replay_hours}h"
        )
        logger.info(f"Symbols: {self.symbols}")
        logger.info(f"Created {len(self.aggregators)} 1s→1m aggregators")

    def _calculate_replay_window(self, now: datetime = None) -> tuple:
        """Calculate start/end times for replay.

        Args:
            now: Current time (defaults to datetime.now(UTC))

        Returns:
            (start_time, end_time) tuple
        """
        if now is None:
            now = datetime.now(pytz.UTC)

        start = now - timedelta(hours=self.replay_hours)
        end = now - timedelta(minutes=1)  # Up to 1 min ago

        return start, end

    def _convert_bar_to_dict(self, bar) -> Dict:
        """Convert Databento bar to standard dict format.

        Args:
            bar: Databento OHLCV bar object

        Returns:
            Dict with keys: symbol, date, date_l, open, high, low, close, volume, cpl
        """
        # Get symbol from mapping dict (instrument_id → symbol)
        symbol = self.symbol_map.get(bar.instrument_id, str(bar.instrument_id))

        return {
            "symbol": symbol,  # Symbol identifier for routing
            "date": pd.Timestamp(bar.ts_event, unit="ns", tz="UTC"),
            "date_l": pd.Timestamp(bar.ts_event, unit="ns", tz="UTC"),
            "open": bar.open / 1e9,  # Databento uses fixed-point (multiply by 1e9)
            "high": bar.high / 1e9,
            "low": bar.low / 1e9,
            "close": bar.close / 1e9,
            "volume": bar.volume,
            "cpl": True,  # Assume complete for now
        }

    def start(self):
        """Start feed (blocking).

        Steps:
        1. Request 24hr intraday replay for ALL symbols
        2. Stream replay bars (rapid) - bars from all symbols interleaved
        3. Switch to live streaming
        4. Stream live bars (real-time) - bars from all symbols interleaved

        Each bar includes 'symbol' field for per-symbol routing.
        """
        logger.info("Starting Databento feed...")

        # Create client
        self.client = db.Live(key=self.api_key)

        # Subscribe to live stream with intraday replay
        logger.info(f"Subscribing with replay for {len(self.symbols)} symbols")
        logger.info(f"Symbols: {self.symbols}")

        # Subscribe for ALL symbols with intraday replay
        # Use start=0 for maximum available replay (up to 24 hours)
        logger.info(f"Requesting {self.replay_hours}hr intraday replay")
        self.client.subscribe(
            dataset=self.dataset,
            schema=self.schema,
            stype_in="continuous",  # Use continuous symbology (like old implementation)
            symbols=self.symbols,  # All symbols streamed together
            start=0,  # Request full 24hr replay to warm up indicators
        )

        self.is_running = True
        bar_count = 0
        symbol_counts = {}

        logger.info("Streaming bars...")

        try:
            for record in self.client:
                if not self.is_running:
                    break

                # Log record type for debugging
                record_type = type(record).__name__

                # Check for SymbolMappingMsg - build instrument_id → symbol mapping
                if record_type == "SymbolMappingMsg":
                    # Map instrument_id to symbol (use stype_in_symbol which is the continuous format)
                    self.symbol_map[record.instrument_id] = record.stype_in_symbol
                    logger.info(
                        f"Symbol mapping: {record.instrument_id} → {record.stype_in_symbol}"
                    )
                    continue

                # Check for replay completion message
                if record_type == "SystemMsg":
                    msg_text = getattr(record, "msg", "")
                    if "Finished" in msg_text and "replay" in msg_text:
                        logger.info(f"System message (SystemMsg): {msg_text}")
                        if self.on_replay_complete:
                            self.on_replay_complete()
                        continue

                # Skip non-bar records (SystemMsg, ErrorMsg, etc.)
                if not hasattr(record, "open"):
                    # Log system messages at INFO level so we can see them
                    if hasattr(record, "msg"):
                        logger.info(f"System message ({record_type}): {record.msg}")
                    else:
                        logger.info(f"Non-bar record type: {record_type}")
                    continue

                # Convert 1-second bar to dict
                bar_dict = self._convert_bar_to_dict(record)
                symbol = bar_dict["symbol"]

                # Log first few bars to confirm we're receiving data
                if bar_count < 10:
                    logger.info(
                        f"✅ Received 1s bar: {symbol} @ {bar_dict['close']:.2f} (time: {bar_dict['date']})"
                    )

                # Route to appropriate 1s→1m aggregator
                # The aggregator will call on_bar_callback when 1-min bar completes
                if symbol in self.aggregators:
                    self.aggregators[symbol].add_bar(bar_dict)
                else:
                    logger.warning(f"Received bar for unknown symbol: {symbol}")

                # Track per-symbol counts (1-second bars)
                symbol_counts[symbol] = symbol_counts.get(symbol, 0) + 1

                bar_count += 1
                if bar_count % 1000 == 0:
                    logger.info(
                        f"Processed {bar_count} 1s bars across {len(symbol_counts)} symbols"
                    )

        except KeyboardInterrupt:
            logger.info("Feed interrupted by user")
        except Exception as e:
            logger.error(f"Feed error: {e}", exc_info=True)
        finally:
            logger.info(f"Final stats: {bar_count} total bars")
            for symbol, count in sorted(symbol_counts.items()):
                logger.info(f"  {symbol}: {count} bars")
            self.stop()

    def stop(self):
        """Stop feed gracefully."""
        logger.info("Stopping Databento feed...")
        self.is_running = False
        if self.client:
            try:
                self.client.terminate()
            except Exception as e:
                logger.warning(f"Error terminating client: {e}")
