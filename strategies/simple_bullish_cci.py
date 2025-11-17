# -*- coding: utf-8 -*-

"""Simple Bullish CCI Test Strategy.

Strategy Rules (5-minute timeframe):
- Entry Conditions (all must be true):
  1. close > open (bullish candle)
  2. close > prev_close (upward momentum)
  3. cci15 > cci15_previous (CCI rising)

- Exit Condition:
  - Close position immediately after next 5-minute bar completes (hold for 1 bar)

This is a simple test strategy designed to validate the live trading pipeline.
Each strategy instance handles ONE symbol only.

Usage:
    config = {
        "indicators": {"cci": {"length": 15}},
        "exit_conditions": {"bars_held": 1},
        "position_sizing": {"quantity": 1}
    }

    strategy = SimpleBullishCCIStrategy(symbol="ES.c.0", config=config)

    # On each new 5-min bar:
    signal = strategy.on_bar(bar_dict)
    if signal:
        print(f"Signal: {signal['action']} {signal['symbol']}")
"""

from typing import Dict, Optional

from indicators.indicator_cci import IndicatorCCI_
from logging_system import get_logger
from vbt_sim_live import LiveData, TFs

logger = get_logger(__name__)


class SimpleBullishCCIStrategy:
    """Simple test strategy for validating live trading execution.

    This strategy:
    - Integrates with LiveData for incremental bar/indicator updates
    - Tracks position state (flat/long)
    - Emits entry/exit signals with symbol identifier
    - Each instance handles ONE symbol only (multi-symbol creates multiple instances)

    Attributes:
        symbol: Symbol identifier (e.g., "ES.c.0")
        timeframe: Trading timeframe (default: 5-minute)
        cci_length: CCI period (default: 15)
        position: Current position state ("flat" or "long")
        bars_in_position: Count of bars held in current position
        live_data: LiveData instance for this symbol/timeframe
    """

    def __init__(self, symbol: str, config: Dict):
        """Initialize strategy for a single symbol.

        Args:
            symbol: Symbol identifier (e.g., "ES.c.0")
            config: Strategy configuration dict with keys:
                - indicators.cci.length: CCI period (default: 15)
                - exit_conditions.bars_held: Bars to hold position (default: 1)
                - position_sizing.quantity: Position size (default: 1)
        """
        self.symbol = symbol
        self.config = config

        # Extract configuration
        self.timeframe = TFs.m5  # Fixed at 5-minute for this strategy
        self.cci_length = config.get("indicators", {}).get("cci", {}).get("length", 15)
        self.bars_to_hold = config.get("exit_conditions", {}).get("bars_held", 1)
        self.quantity = config.get("position_sizing", {}).get("quantity", 1)

        # Position state
        self.position = None  # None = flat, "long" = in position
        self.bars_in_position = 0

        # LiveData instance for this symbol+timeframe
        # Initialize with empty data dict and 100-bar rolling window
        initial_data = self._create_empty_data_dict(window_size=100)
        self.live_data = LiveData(
            data=initial_data,
            symbol=symbol,
            timeframe=self.timeframe,
            tz="America/New_York",
            log_handler=None,
        )

        # Set up CCI indicator
        self.live_data.indicator_info = {"IndicatorCCI_": {"length": self.cci_length}}

        # Prepare indicators (will be empty initially, updated as bars arrive)
        self.cci_indicator = None
        self._indicators_initialized = False

        logger.info(
            f"SimpleBullishCCIStrategy initialized: symbol={symbol}, "
            f"cci_length={self.cci_length}, bars_to_hold={self.bars_to_hold}"
        )

    def _create_empty_data_dict(self, window_size: int = 100) -> Dict:
        """Create empty data dictionary for LiveData initialization.

        Args:
            window_size: Number of bars to keep in rolling window

        Returns:
            Dict with numpy arrays for OHLCV data
        """
        import numpy as np

        return {
            "date": np.full(window_size, np.datetime64("NaT"), dtype="datetime64[ns]"),
            "date_l": np.full(
                window_size, np.datetime64("NaT"), dtype="datetime64[ns]"
            ),
            "open": np.full(window_size, np.nan, dtype=np.float64),
            "high": np.full(window_size, np.nan, dtype=np.float64),
            "low": np.full(window_size, np.nan, dtype=np.float64),
            "close": np.full(window_size, np.nan, dtype=np.float64),
            "volume": np.full(window_size, np.nan, dtype=np.float64),
            "cpl": np.full(window_size, False, dtype=np.bool_),
        }

    def _initialize_indicators(self):
        """Initialize CCI indicator once we have enough bars."""
        # Create CCI indicator
        import numpy as np

        # Get price arrays
        high_full = self.live_data.get_feature("high")
        low_full = self.live_data.get_feature("low")
        close_full = self.live_data.get_feature("close")

        # Filter out NaN values - only use valid bars for indicator calculation
        valid_mask = ~np.isnan(close_full)
        high = high_full[valid_mask]
        low = low_full[valid_mask]
        close = close_full[valid_mask]

        self.cci_indicator = IndicatorCCI_(
            input_args=[high, low, close, self.cci_length],
            kwargs={"timeframe": self.timeframe, "tz": "America/New_York"},
        )

        # Prepare (calculate for all historical bars)
        self.cci_indicator.prepare()

        # Add CCI feature to live_data
        cci_values = self.cci_indicator.get()[0]

        # Ensure CCI array matches the size of other arrays in live_data
        # The CCI was calculated only on valid bars, so we need to pad it
        # to match the full array size and place values at the correct positions
        existing_size = len(close_full)

        # Create a new array with the right size, filled with NaN
        cci_padded = np.full(existing_size, np.nan, dtype=np.float64)

        # Place CCI values at the end of the valid bar positions
        # CCI needs cci_length bars to calculate, so first (cci_length-1) values will be NaN
        num_cci_values = len(cci_values)
        valid_indices = np.where(valid_mask)[0]

        if num_cci_values > 0 and len(valid_indices) >= num_cci_values:
            # Place CCI values at the last N valid positions where N = len(cci_values)
            cci_padded[valid_indices[-num_cci_values:]] = cci_values

        self.live_data.add_feature("cci", cci_padded)

        self._indicators_initialized = True
        logger.info(f"CCI indicator initialized for {self.symbol}")

    def on_bar(self, bar: Dict) -> Optional[Dict]:
        """Process new 5-minute bar and generate signals.

        This method:
        1. Updates LiveData with new bar
        2. Updates CCI indicator incrementally
        3. Checks entry conditions (if flat)
        4. Checks exit conditions (if in position)
        5. Returns signal dict if action needed

        Args:
            bar: Bar dict with keys: symbol, date, date_l, open, high, low, close, volume, cpl

        Returns:
            Signal dict with keys:
                - action: "entry" or "exit"
                - side: "long" (for entry only)
                - symbol: Symbol identifier
                - quantity: Position size
                - reason: Human-readable reason for signal
            Or None if no action needed
        """
        # Verify symbol matches
        if bar.get("symbol") != self.symbol:
            logger.warning(
                f"Bar symbol mismatch: expected {self.symbol}, got {bar.get('symbol')}"
            )
            return None

        # Update LiveData with new bar
        updated, rolled = self.live_data.update(bar)

        if not updated:
            return None

        # Initialize indicators if we have enough bars
        if not self._indicators_initialized:
            # Need at least cci_length + 1 bars for CCI calculation
            num_valid_bars = self._count_valid_bars()
            if num_valid_bars >= self.cci_length + 1:
                self._initialize_indicators()
            else:
                # Not enough bars yet
                return None

        # Update CCI indicator incrementally
        if self._indicators_initialized:
            import numpy as np

            # Get latest data from LiveData
            close_full = self.live_data.get_feature("close")
            high_full = self.live_data.get_feature("high")
            low_full = self.live_data.get_feature("low")

            # Filter out NaN values to get valid bars
            valid_mask = ~np.isnan(close_full)
            high_valid = high_full[valid_mask]
            low_valid = low_full[valid_mask]
            close_valid = close_full[valid_mask]

            # Update indicator's input arrays with latest data
            self.cci_indicator.high = high_valid
            self.cci_indicator.low = low_valid
            self.cci_indicator.close = close_valid

            # Update length to match array size for create_features()
            # but preserve the CCI period parameter separately
            cci_period = (
                self.cci_indicator.length
            )  # Save the CCI period (15 for ES, 20 for NQ)
            self.cci_indicator.length = len(
                close_valid
            )  # Set to array size for output array creation

            # Recreate output arrays with new length
            self.cci_indicator.create_features()

            # Restore the CCI period parameter
            self.cci_indicator.length = cci_period

            # Recalculate CCI for all bars
            self.cci_indicator.prepare()

            # Get CCI values
            cci_values = self.cci_indicator.get()[0]

            # Map CCI values back to padded array positions
            existing_size = len(close_full)
            cci_padded = np.full(existing_size, np.nan, dtype=np.float64)

            # Place CCI values at valid bar positions
            num_cci_values = len(cci_values)
            valid_indices = np.where(valid_mask)[0]

            if num_cci_values > 0 and len(valid_indices) >= num_cci_values:
                cci_padded[valid_indices[-num_cci_values:]] = cci_values

            self.live_data.data["cci"] = cci_padded

        # Check if we have at least 2 valid bars for comparison
        num_valid_bars = self._count_valid_bars()
        if num_valid_bars < 2:
            return None

        # Get current and previous bar data
        df = self.live_data.to_df(set_index=False)

        # Filter out invalid bars (NaN close prices)
        import pandas as pd

        df_valid = df[df["close"].notna()].copy()

        if len(df_valid) < 2:
            return None

        current = df_valid.iloc[-1]
        previous = df_valid.iloc[-2]

        # Log CCI values for monitoring (always show on evaluation)
        import numpy as np

        current_cci = current.get("cci", np.nan)
        previous_cci = previous.get("cci", np.nan)

        # Debug: Show CCI array to diagnose why prev is NaN
        cci_array = self.live_data.get_feature("cci")
        valid_cci = cci_array[~np.isnan(cci_array)]
        logger.debug(f"  {self.symbol} CCI array (valid values): {valid_cci[-5:]}")

        logger.info(
            f"  {self.symbol} CCI evaluation: prev={previous_cci:.2f}, current={current_cci:.2f}, "
            f"O={current['open']:.2f}, H={current['high']:.2f}, L={current['low']:.2f}, C={current['close']:.2f}"
        )

        # Entry logic
        if self.position is None:
            if self._check_entry_conditions(current, previous):
                self.position = "long"
                self.bars_in_position = 0

                logger.info(f"ENTRY SIGNAL: {self.symbol} - Long position opened")
                logger.info(
                    f"  Current bar: O={current['open']:.2f}, C={current['close']:.2f}, "
                    f"CCI={current.get('cci', 'N/A')}"
                )

                return {
                    "action": "entry",
                    "side": "long",
                    "symbol": self.symbol,
                    "quantity": self.quantity,
                    "reason": f"Bullish candle + CCI rising (CCI: {previous.get('cci', 'N/A'):.1f} -> {current.get('cci', 'N/A'):.1f})",
                }

        # Exit logic (if in position)
        elif self.position == "long":
            self.bars_in_position += 1

            if self.bars_in_position >= self.bars_to_hold:
                self.position = None
                self.bars_in_position = 0

                logger.info(
                    f"EXIT SIGNAL: {self.symbol} - Long position closed after {self.bars_to_hold} bar(s)"
                )

                return {
                    "action": "exit",
                    "symbol": self.symbol,
                    "quantity": self.quantity,
                    "reason": f"Held for {self.bars_to_hold} bar(s)",
                }

        return None

    def _count_valid_bars(self) -> int:
        """Count number of valid (non-NaN) bars in LiveData.

        Returns:
            Count of bars with valid close prices
        """
        import numpy as np

        close_prices = self.live_data.get_feature("close")
        return int(np.sum(~np.isnan(close_prices)))

    def _check_entry_conditions(self, current, previous) -> bool:
        """Check if all entry conditions are met.

        Entry Conditions:
        1. close > open (bullish candle)
        2. close > prev_close (upward momentum)
        3. cci > cci_previous (CCI rising)

        Args:
            current: Current bar (pandas Series)
            previous: Previous bar (pandas Series)

        Returns:
            True if all conditions met, False otherwise
        """
        import numpy as np

        # Condition 1: Bullish candle (close > open)
        c1 = current["close"] > current["open"]

        # Condition 2: Close > previous close
        c2 = current["close"] > previous["close"]

        # Condition 3: CCI rising
        # Check if CCI values exist and are not NaN
        current_cci = current.get("cci", np.nan)
        previous_cci = previous.get("cci", np.nan)

        if np.isnan(current_cci) or np.isnan(previous_cci):
            return False

        c3 = current_cci > previous_cci

        if c1 and c2 and c3:
            logger.debug(f"All entry conditions met for {self.symbol}:")
            logger.debug(
                f"  C1 (bullish): {current['close']:.2f} > {current['open']:.2f}"
            )
            logger.debug(
                f"  C2 (momentum): {current['close']:.2f} > {previous['close']:.2f}"
            )
            logger.debug(f"  C3 (CCI rising): {current_cci:.1f} > {previous_cci:.1f}")
            return True

        return False

    def get_state(self) -> Dict:
        """Get current strategy state (for monitoring/debugging).

        Returns:
            Dict with position, bars_in_position, num_bars, latest_cci
        """
        import numpy as np

        num_valid_bars = self._count_valid_bars()

        latest_cci = np.nan
        if self._indicators_initialized and num_valid_bars > 0:
            cci_values = self.cci_indicator.get()[0]
            # Find last non-NaN CCI value
            valid_cci = cci_values[~np.isnan(cci_values)]
            if len(valid_cci) > 0:
                latest_cci = valid_cci[-1]

        return {
            "symbol": self.symbol,
            "position": self.position or "flat",
            "bars_in_position": self.bars_in_position,
            "num_bars": num_valid_bars,
            "indicators_ready": self._indicators_initialized,
            "latest_cci": latest_cci,
        }
