"""
CrossTrade API Exceptions

Custom exception hierarchy for CrossTrade API errors.
"""

from typing import Optional


class CrossTradeError(Exception):
    """Base exception for all CrossTrade API errors."""
    pass


class AuthenticationError(CrossTradeError):
    """Raised when API authentication fails (401)."""
    pass


class RateLimitError(CrossTradeError):
    """Raised when rate limit is exceeded (429)."""
    def __init__(self, retry_after: Optional[int] = None):
        self.retry_after = retry_after
        message = f"Rate limit exceeded. Retry after {retry_after} seconds." if retry_after else "Rate limit exceeded."
        super().__init__(message)


class OrderError(CrossTradeError):
    """Raised when order submission or modification fails."""
    pass


class AccountNotFoundError(CrossTradeError):
    """Raised when specified account is not found."""
    pass


class InstrumentNotFoundError(CrossTradeError):
    """Raised when specified instrument is not found or invalid."""
    pass


class InsufficientMarginError(CrossTradeError):
    """Raised when account has insufficient margin for order."""
    pass
