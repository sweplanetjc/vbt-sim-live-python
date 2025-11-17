# -*- coding: utf-8 -*-

"""CCI (Commodity Channel Index) Indicator."""

import numpy as np

import vectorbtpro as vbt

from .indicator_root import IndicatorRoot
from .indicator_utils import indicator_strategy_vbt_caller


class IndicatorCCI_(IndicatorRoot):
    """Live CCI indicator that updates incrementally."""

    def __init__(self, input_args, kwargs):
        super().__init__(input_args, kwargs)

    def prepare(self):
        """Calculate CCI for entire history."""
        # Use the smaller of input length or output array length to avoid index errors
        max_idx = min(len(self.high), len(self.__dict__[self.output_names[0]]))
        for j in range(max_idx):
            ret = cci_func_single(j, self)
            for i, n in enumerate(self.output_names):
                self.__dict__[n][j] = ret[i]

    def update(self):
        """Update CCI for last bar only."""
        ret = cci_func_single(-1, self)
        for i, n in enumerate(self.output_names):
            self.__dict__[n][-1] = ret[i]


def cci_func_single(i: int, obj: IndicatorCCI_):
    """Calculate CCI for a single bar.

    CCI = (Typical Price - SMA) / (0.015 * Mean Deviation)
    Typical Price = (High + Low + Close) / 3

    Args:
        i: Bar index to calculate CCI for. Can be negative for indexing from end.
        obj: IndicatorCCI_ instance containing price data and parameters.

    Returns:
        Tuple containing single CCI value, or (np.nan,) if insufficient data.
    """
    period = obj.length

    # Validate period
    if period <= 0:
        raise ValueError(f"Period must be positive, got {period}")

    # Handle negative indices
    if i < 0:
        i = len(obj.high) + i

    # Need at least 'period' bars
    if i < period - 1:
        return (np.nan,)

    # Calculate typical price
    start_idx = max(0, i - period + 1)
    end_idx = i + 1

    tp = (
        obj.high[start_idx:end_idx]
        + obj.low[start_idx:end_idx]
        + obj.close[start_idx:end_idx]
    ) / 3.0

    # SMA of typical price
    sma_tp = np.mean(tp)

    # Mean deviation
    mean_dev = np.mean(np.abs(tp - sma_tp))

    # Avoid division by zero
    if mean_dev == 0:
        return (0.0,)

    # CCI calculation
    current_tp = (obj.high[i] + obj.low[i] + obj.close[i]) / 3.0
    cci = (current_tp - sma_tp) / (0.015 * mean_dev)

    # Debug logging for troubleshooting
    if i == len(obj.high) - 1:  # Only log for last bar
        import logging

        logger = logging.getLogger(__name__)
        logger.info(
            f"CCI Debug: period={period}, current_tp={current_tp:.2f}, sma_tp={sma_tp:.2f}, mean_dev={mean_dev:.2f}, cci={cci:.2f}"
        )
        logger.info(f"CCI Debug: Last {min(5, len(tp))} TPs: {tp[-5:]}")

    return (cci,)


# VBT class definition
IndicatorCCI = vbt.IF(
    class_name="IndicatorCCI",
    short_name="cci",
    input_names=["high", "low", "close"],
    param_names=["length"],
    output_names=["cci"],
).with_apply_func(indicator_strategy_vbt_caller, takes_1d=True)

# Feature info
IndicatorCCI_feature_info = [
    {"name": "cci", "type": float, "type_np": np.float64, "default": np.nan}
]
