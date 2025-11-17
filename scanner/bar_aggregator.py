"""Generic per-symbol bar aggregator supporting ANY timeframe.

This module implements a time-based bar aggregation algorithm that works for
ANY minute-based timeframe (m1, m2, m3, m5, m6, m27, m30, etc.) without
hardcoded logic.

Key Design Principles:
1. Generic Timeframe Support: Uses time-based boundary detection
   - Calculates minutes_elapsed = (bar_time - period_start).total_seconds() / 60
   - Calculates period_minutes = target_tf.value // 60
   - New period starts when minutes_elapsed >= period_minutes

2. Per-Symbol Isolation: Each aggregator instance handles ONE symbol
   - Prevents cross-contamination between symbols
   - System creates one instance per symbol per timeframe

3. Symbol Field Preservation: Every completed bar includes 'symbol' field
   - Critical for routing bars to correct strategy instances

4. OHLCV Correctness:
   - Open = first bar's open
   - High = max(all highs)
   - Low = min(all lows)
   - Close = last bar's close
   - Volume = sum(all volumes)

Usage:
    # Create one aggregator per symbol per timeframe
    agg_es_m5 = BarAggregator(symbol="ES.c.0", target_tf=TFs.m5)
    agg_nq_m27 = BarAggregator(symbol="NQ.c.0", target_tf=TFs.m27)

    # Process incoming 1-minute bars
    for bar_1min in stream:
        if bar_1min['symbol'] == 'ES.c.0':
            completed_bar = agg_es_m5.add_bar(bar_1min)
            if completed_bar:
                print(f"ES 5-min bar complete: {completed_bar}")
        elif bar_1min['symbol'] == 'NQ.c.0':
            completed_bar = agg_nq_m27.add_bar(bar_1min)
            if completed_bar:
                print(f"NQ 27-min bar complete: {completed_bar}")
"""

from datetime import datetime
from typing import Dict, List, Optional

from vbt_sim_live import TFs


class BarAggregator:
    """Aggregates 1-minute bars into ANY higher timeframe for a single symbol.

    This aggregator is designed to be instantiated per symbol. A multi-symbol
    system would create multiple instances (one per symbol per timeframe).

    Algorithm:
        The aggregator uses generic time-based boundary detection:

        1. When first bar arrives, record period_start time
        2. For each subsequent bar:
           - Calculate minutes_elapsed = (bar_time - period_start) / 60
           - Calculate period_minutes = target_tf.value // 60
           - If minutes_elapsed >= period_minutes:
               * Complete current period (return aggregated bar)
               * Start new period with current bar
           - Else:
               * Add bar to current period
               * Return None

        This works for ANY minute-based timeframe without hardcoding.

    Attributes:
        symbol: Symbol identifier (e.g., "ES.c.0")
        target_tf: Target timeframe (TFs enum: m2, m3, m5, m27, etc.)
        current_bar: Accumulated OHLCV for current period
        period_start: Timestamp when current period started
        bars_in_period: List of bars in current period (for debugging)
    """

    def __init__(self, symbol: str, target_tf: TFs):
        """Initialize aggregator for a single symbol.

        Args:
            symbol: Symbol identifier (e.g., "ES.c.0", "NQ.c.0")
            target_tf: Target timeframe from TFs enum

        Raises:
            ValueError: If target_tf is not intraday (must be < 1 day)
        """
        if not target_tf.is_intraday():
            raise ValueError(
                f"BarAggregator only supports intraday timeframes, got {target_tf.name}"
            )

        self.symbol = symbol
        self.target_tf = target_tf
        self.current_bar = None
        self.period_start = None
        self.bars_in_period = []

    def add_bar(self, bar: Dict) -> Optional[Dict]:
        """Add 1-minute bar, return completed aggregated bar if period boundary reached.

        This is the main method that implements the generic time-based algorithm.

        Args:
            bar: 1-minute bar dict with keys:
                - symbol: Symbol identifier
                - date: Bar timestamp (datetime or pd.Timestamp)
                - date_l: Bar last update timestamp
                - open, high, low, close: OHLC prices
                - volume: Volume
                - cpl: Complete flag

        Returns:
            Completed aggregated bar dict (with 'symbol' field) or None

        Raises:
            ValueError: If bar symbol doesn't match aggregator symbol
        """
        # Validate symbol matches
        if bar["symbol"] != self.symbol:
            raise ValueError(
                f"Bar symbol '{bar['symbol']}' doesn't match aggregator symbol '{self.symbol}'"
            )

        bar_time = bar["date"]

        # First bar - initialize period
        if self.period_start is None:
            self._start_new_period(bar)
            return None

        # Add bar to current period first
        self._add_to_current_period(bar)

        # Check if we should complete this period (i.e., next bar would start new period)
        # We complete when this bar is the LAST bar of the current period
        if self._is_period_complete(bar_time):
            # Complete and return the period
            completed_bar = self._complete_period()
            return completed_bar
        else:
            return None

    def _is_new_period(self, bar_time: datetime) -> bool:
        """Check if bar_time starts a new period using calendar boundary alignment.

        For live trading, bars must align to calendar boundaries:
        - m5: 00, 05, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55
        - m15: 00, 15, 30, 45
        - m30: 00, 30
        etc.

        Args:
            bar_time: Timestamp of incoming bar

        Returns:
            True if this bar starts a new period
        """
        # Calculate period length in minutes
        period_minutes = self.target_tf.value // 60

        # Floor both timestamps to their respective period boundaries
        period_start_floored = self._floor_to_period(self.period_start, period_minutes)
        bar_time_floored = self._floor_to_period(bar_time, period_minutes)

        # New period starts when the floored timestamps differ
        return bar_time_floored != period_start_floored

    def _is_period_complete(self, bar_time: datetime) -> bool:
        """Check if current period is complete after adding this bar.

        A period is complete when the next bar would cross the period boundary.
        For a 5-minute period starting at 01:40 (covers 01:40-01:45), the period
        completes when we receive the bar timestamped 01:44 (last bar before 01:45).

        We check: would the NEXT bar (1 minute after this one) cross into a new period?

        Args:
            bar_time: Timestamp of the bar just added

        Returns:
            True if this bar completes the period
        """
        from datetime import timedelta

        # Calculate what the next bar's timestamp would be (1 minute from now)
        next_bar_time = bar_time + timedelta(minutes=1)

        # If the next bar would start a new period, then this bar completes current period
        return self._is_new_period(next_bar_time)

    def _floor_to_period(self, timestamp: datetime, period_minutes: int) -> datetime:
        """Floor timestamp to the start of its period boundary.

        Args:
            timestamp: Timestamp to floor
            period_minutes: Period length in minutes

        Returns:
            Timestamp floored to period boundary
        """
        # Get minute of hour (0-59)
        minute = timestamp.minute
        # Calculate which period bucket this falls into
        period_bucket = (minute // period_minutes) * period_minutes
        # Return timestamp with minute floored to bucket start
        return timestamp.replace(minute=period_bucket, second=0, microsecond=0)

    def _start_new_period(self, bar: Dict) -> None:
        """Start new aggregation period with given bar.

        Args:
            bar: First bar of new period
        """
        self.period_start = bar["date"]
        self.current_bar = {
            "symbol": self.symbol,  # Preserve symbol field
            "date": bar["date"],
            "date_l": bar["date_l"],
            "open": bar["open"],
            "high": bar["high"],
            "low": bar["low"],
            "close": bar["close"],
            "volume": bar["volume"],
            "cpl": True,  # Aggregated bars are always complete
        }
        self.bars_in_period = [bar]

    def _add_to_current_period(self, bar: Dict) -> None:
        """Add bar to current period, updating OHLCV.

        Args:
            bar: Bar to add to current period
        """
        # If this is the first bar of a new period after completion, start new period
        if self.current_bar is None:
            self._start_new_period(bar)
            return

        # Check if this bar starts a new period
        if self._is_new_period(bar["date"]):
            # Start new period with this bar (previous period was already completed)
            self._start_new_period(bar)
            return

        # Update OHLCV according to aggregation rules
        # Open stays as first bar's open
        self.current_bar["high"] = max(self.current_bar["high"], bar["high"])
        self.current_bar["low"] = min(self.current_bar["low"], bar["low"])
        self.current_bar["close"] = bar["close"]  # Last bar's close
        self.current_bar["volume"] += bar["volume"]  # Sum volumes
        self.current_bar["date_l"] = bar["date_l"]  # Update last timestamp

        self.bars_in_period.append(bar)

    def _complete_period(self) -> Dict:
        """Complete current period and return aggregated bar.

        Returns:
            Completed aggregated bar with 'symbol' field preserved
        """
        if self.current_bar is None:
            raise RuntimeError("Cannot complete period - no current bar")

        # Return copy of current bar
        completed = self.current_bar.copy()

        # Reset for next period
        self.current_bar = None
        self.period_start = None
        self.bars_in_period = []

        return completed

    def get_current_bar(self) -> Optional[Dict]:
        """Get current incomplete bar (for debugging/monitoring).

        Returns:
            Current bar dict or None if no period active
        """
        return self.current_bar.copy() if self.current_bar else None

    def get_bars_count(self) -> int:
        """Get count of bars in current period (for debugging/monitoring).

        Returns:
            Number of 1-min bars accumulated in current period
        """
        return len(self.bars_in_period)

    def __repr__(self) -> str:
        """String representation for debugging."""
        return (
            f"BarAggregator(symbol='{self.symbol}', target_tf={self.target_tf.name}, "
            f"bars_in_period={len(self.bars_in_period)}, "
            f"period_start={self.period_start})"
        )
