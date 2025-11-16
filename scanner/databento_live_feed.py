"""Databento live feed with intraday replay support.

Supports unlimited symbols - only limited by Databento plan/costs.
"""

from datetime import datetime, timedelta
from typing import Callable, Dict, List

import pandas as pd
import pytz

import databento as db
from logging_system import get_logger

logger = get_logger(__name__)


class DatabentoLiveFeed:
    """Streams live 1-minute OHLCV bars from Databento with 24hr replay.

    Supports ANY number of symbols (limited only by Databento API limits).
    Each bar includes symbol identifier for routing.

    Usage:
        config = {
            "api_key": "...",
            "dataset": "GLBX.MDP3",
            "symbols": ["ES.c.0", "NQ.c.0", "GC.c.0", ...],  # Unlimited
            "schema": "ohlcv-1m",
            "replay_hours": 24
        }

        def on_bar(bar_dict):
            symbol = bar_dict['symbol']
            print(f"{symbol}: {bar_dict['close']}")

        feed = DatabentoLiveFeed(config, on_bar_callback=on_bar)
        feed.start()  # Blocking - runs forever
    """

    def __init__(self, config: Dict, on_bar_callback: Callable):
        """Initialize feed.

        Args:
            config: Databento configuration dict
            on_bar_callback: Function called for each bar: callback(bar_dict)
                            bar_dict includes 'symbol' field for routing
        """
        self.api_key = config["api_key"]
        self.dataset = config["dataset"]
        self.symbols = config["symbols"]  # Can be unlimited list
        self.schema = config["schema"]
        self.replay_hours = config.get("replay_hours", 24)
        self.on_bar_callback = on_bar_callback

        self.client = None
        self.is_running = False

        logger.info(
            f"DatabentoLiveFeed initialized: {len(self.symbols)} symbols, replay={self.replay_hours}h"
        )
        logger.info(f"Symbols: {self.symbols}")

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
        return {
            "symbol": bar.instrument_id,  # CRITICAL: Symbol identifier for routing
            "date": pd.Timestamp(bar.ts_event, unit="ns", tz="UTC"),
            "date_l": pd.Timestamp(bar.ts_event, unit="ns", tz="UTC"),
            "open": bar.open / 1e9,  # Databento uses fixed-point
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

        # Calculate replay window
        start, end = self._calculate_replay_window()
        logger.info(f"Requesting replay: {start} to {end}")
        logger.info(f"Streaming {len(self.symbols)} symbols")

        # Subscribe with replay for ALL symbols
        self.client.subscribe(
            dataset=self.dataset,
            schema=self.schema,
            stype_in=db.SType.CONTINUOUS,
            symbols=self.symbols,  # All symbols streamed together
            start=start,
        )

        self.is_running = True
        bar_count = 0
        symbol_counts = {}

        logger.info("Streaming bars...")

        try:
            for bar in self.client:
                if not self.is_running:
                    break

                # Convert and emit
                bar_dict = self._convert_bar_to_dict(bar)
                self.on_bar_callback(bar_dict)

                # Track per-symbol counts
                symbol = bar_dict["symbol"]
                symbol_counts[symbol] = symbol_counts.get(symbol, 0) + 1

                bar_count += 1
                if bar_count % 1000 == 0:
                    logger.info(
                        f"Processed {bar_count} bars across {len(symbol_counts)} symbols"
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
            self.client.close()
