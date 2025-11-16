"""
CrossTrade API Client for Vector Bot

This module provides a Python client for interacting with the CrossTrade API
to execute trades, fetch market data, and manage positions in NinjaTrader 8.

Usage:
    from crosstrade import CrossTradeClient

    client = CrossTradeClient()
    accounts = client.get_accounts()
    quote = client.get_quote("ES 03-25")
"""

from .crosstrade_client import CrossTradeClient
from .exceptions import (
    AccountNotFoundError,
    AuthenticationError,
    CrossTradeError,
    OrderError,
    RateLimitError,
)
from .market_data import MarketDataManager
from .models import (
    Account,
    Execution,
    Order,
    OrderAction,
    OrderRequest,
    OrderState,
    OrderType,
    Position,
    Quote,
    TimeInForce,
)
from .order_manager import OrderManager
from .signal_translator import SignalTranslator, SignalType

__all__ = [
    "CrossTradeClient",
    "MarketDataManager",
    "OrderManager",
    "SignalTranslator",
    "SignalType",
    "Account",
    "Position",
    "Order",
    "Quote",
    "Execution",
    "OrderRequest",
    "OrderAction",
    "OrderType",
    "OrderState",
    "TimeInForce",
    "CrossTradeError",
    "AuthenticationError",
    "RateLimitError",
    "OrderError",
    "AccountNotFoundError",
]

__version__ = "1.0.0"
