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
        for j in range(len(self.high)):
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
    """
    period = obj.length

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

    return (cci,)


# VBT class definition
IndicatorCCI = vbt.IF(
    class_name="IndicatorCCI",
    short_name="cci",
    input_names=["high", "low", "close", "length"],
    param_names=[],
    output_names=["cci"],
).with_apply_func(indicator_strategy_vbt_caller, takes_1d=True)

# Feature info
IndicatorCCI_feature_info = [
    {"name": "cci", "type": float, "type_np": np.float64, "default": np.nan}
]
