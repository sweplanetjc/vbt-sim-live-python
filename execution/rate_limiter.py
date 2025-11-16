"""
Rate Limiter for CrossTrade API

CrossTrade API has a limit of 60 requests per minute.
This module implements a token bucket rate limiter.
"""

import time
import threading
from typing import Optional


class RateLimiter:
    """Token bucket rate limiter.

    Args:
        max_requests: Maximum requests per period (default: 60)
        period_seconds: Time period in seconds (default: 60)
        burst_size: Maximum burst size (default: same as max_requests)
    """

    def __init__(
        self,
        max_requests: int = 60,
        period_seconds: float = 60.0,
        burst_size: Optional[int] = None
    ):
        self.max_requests = max_requests
        self.period_seconds = period_seconds
        self.burst_size = burst_size or max_requests

        # Token bucket
        self.tokens = float(self.burst_size)
        self.last_update = time.time()
        self.lock = threading.Lock()

        # Refill rate: tokens per second
        self.refill_rate = self.max_requests / self.period_seconds

    def acquire(self, tokens: int = 1) -> bool:
        """Acquire tokens. Returns True if successful, False if would exceed limit.

        Args:
            tokens: Number of tokens to acquire

        Returns:
            True if tokens acquired, False if insufficient tokens
        """
        with self.lock:
            self._refill()

            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            return False

    def wait_for_token(self, tokens: int = 1, timeout: Optional[float] = None) -> bool:
        """Wait for tokens to become available.

        Args:
            tokens: Number of tokens needed
            timeout: Maximum time to wait (seconds). None = wait forever.

        Returns:
            True if tokens acquired, False if timeout
        """
        start_time = time.time()

        while True:
            if self.acquire(tokens):
                return True

            # Check timeout
            if timeout is not None and (time.time() - start_time) >= timeout:
                return False

            # Sleep for a short time before retrying
            time.sleep(0.1)

    def _refill(self):
        """Refill tokens based on elapsed time."""
        now = time.time()
        elapsed = now - self.last_update

        # Add tokens based on elapsed time
        new_tokens = elapsed * self.refill_rate
        self.tokens = min(self.burst_size, self.tokens + new_tokens)

        self.last_update = now

    def get_tokens(self) -> float:
        """Get current number of available tokens."""
        with self.lock:
            self._refill()
            return self.tokens
