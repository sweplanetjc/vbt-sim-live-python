"""
CrossTrade Market Data Manager

Provides cached access to market quotes with TTL-based invalidation.
Minimizes API calls while respecting rate limits.
"""

import time
from datetime import datetime, timedelta
from threading import Lock
from typing import Dict, Optional

from logging_system import get_logger

from .crosstrade_client import CrossTradeClient
from .exceptions import CrossTradeError
from .models import Quote

logger = get_logger(__name__)


class MarketDataManager:
    """Manages market data with caching to minimize API calls.

    Caches quotes with configurable TTL to balance freshness with
    rate limit compliance. Thread-safe for concurrent access.

    Args:
        client: CrossTradeClient instance
        cache_ttl_seconds: Time-to-live for cached quotes (default: 1 second)

    Usage:
        manager = MarketDataManager(client, cache_ttl_seconds=1)
        quote = manager.get_quote("ES 03-25")
        print(f"Last: {quote.last}, Bid: {quote.bid}, Ask: {quote.ask}")
    """

    def __init__(self, client: CrossTradeClient, cache_ttl_seconds: float = 1.0):
        """Initialize market data manager.

        Args:
            client: CrossTradeClient for API access
            cache_ttl_seconds: Cache time-to-live in seconds
        """
        self.client = client
        self.cache_ttl_seconds = cache_ttl_seconds

        # Cache: {instrument: (quote, timestamp)}
        self._cache: Dict[str, tuple[Quote, float]] = {}
        self._lock = Lock()

        logger.info(f"MarketDataManager initialized (cache TTL: {cache_ttl_seconds}s)")

    def get_quote(
        self, instrument: str, account: Optional[str] = None, use_cache: bool = True
    ) -> Quote:
        """Get real-time quote for instrument.

        Returns cached quote if available and not expired, otherwise
        fetches fresh quote from API.

        Args:
            instrument: Instrument name (e.g., "ES 03-25")
            account: Account name (uses client default if not provided)
            use_cache: Whether to use cached quotes (default: True)

        Returns:
            Quote object with last, bid, ask, volume

        Raises:
            CrossTradeError: If API request fails

        Example:
            >>> quote = manager.get_quote("ES 03-25")
            >>> spread = quote.ask - quote.bid
        """
        cache_key = f"{instrument}:{account or self.client.account}"

        # Check cache if enabled
        if use_cache:
            with self._lock:
                if cache_key in self._cache:
                    cached_quote, cached_time = self._cache[cache_key]
                    age = time.time() - cached_time

                    if age < self.cache_ttl_seconds:
                        logger.debug(f"Cache hit: {instrument} (age: {age:.3f}s)")
                        return cached_quote
                    else:
                        logger.debug(f"Cache expired: {instrument} (age: {age:.3f}s)")

        # Fetch fresh quote
        logger.debug(f"Fetching fresh quote: {instrument}")
        quote = self.client.get_quote(instrument, account)

        # Update cache
        with self._lock:
            self._cache[cache_key] = (quote, time.time())

        return quote

    def get_quotes_batch(
        self,
        instruments: list[str],
        account: Optional[str] = None,
        use_cache: bool = True,
    ) -> Dict[str, Quote]:
        """Get quotes for multiple instruments.

        Fetches quotes efficiently, using cache when possible and
        respecting rate limits via the underlying client.

        Args:
            instruments: List of instrument names
            account: Account name (uses client default if not provided)
            use_cache: Whether to use cached quotes (default: True)

        Returns:
            Dictionary mapping instrument to Quote object

        Example:
            >>> quotes = manager.get_quotes_batch(["ES 03-25", "NQ 03-25"])
            >>> for symbol, quote in quotes.items():
            ...     print(f"{symbol}: {quote.last}")
        """
        quotes = {}

        for instrument in instruments:
            try:
                quote = self.get_quote(instrument, account, use_cache)
                quotes[instrument] = quote
            except CrossTradeError as e:
                logger.error(f"Failed to fetch quote for {instrument}: {e}")
                # Continue with other instruments

        return quotes

    def clear_cache(self, instrument: Optional[str] = None):
        """Clear cached quotes.

        Args:
            instrument: Specific instrument to clear (clears all if None)

        Example:
            >>> manager.clear_cache()  # Clear all
            >>> manager.clear_cache("ES 03-25")  # Clear specific
        """
        with self._lock:
            if instrument is None:
                count = len(self._cache)
                self._cache.clear()
                logger.info(f"Cleared all cached quotes ({count} items)")
            else:
                # Clear all cache keys for this instrument
                keys_to_remove = [
                    k for k in self._cache.keys() if k.startswith(f"{instrument}:")
                ]
                for key in keys_to_remove:
                    del self._cache[key]
                logger.info(
                    f"Cleared cached quotes for {instrument} ({len(keys_to_remove)} items)"
                )

    def get_cache_stats(self) -> dict:
        """Get cache statistics.

        Returns:
            Dictionary with cache metrics:
                - total_items: Number of cached quotes
                - oldest_age: Age of oldest cached quote (seconds)
                - instruments: List of cached instruments
        """
        with self._lock:
            if not self._cache:
                return {"total_items": 0, "oldest_age": 0.0, "instruments": []}

            now = time.time()
            ages = [now - cached_time for _, cached_time in self._cache.values()]
            instruments = list(set(k.split(":")[0] for k in self._cache.keys()))

            return {
                "total_items": len(self._cache),
                "oldest_age": max(ages),
                "instruments": sorted(instruments),
            }
