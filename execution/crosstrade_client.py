"""
CrossTrade API Client

Main client for interacting with CrossTrade API.
"""

import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv
from retry import retry

from logging_system import get_logger

from .exceptions import (
    AccountNotFoundError,
    AuthenticationError,
    CrossTradeError,
    InstrumentNotFoundError,
    InsufficientMarginError,
    OrderError,
    RateLimitError,
)
from .models import (
    Account,
    Execution,
    Order,
    OrderRequest,
    OrderState,
    Position,
    Quote,
)
from .rate_limiter import RateLimiter

logger = get_logger(__name__)


class CrossTradeClient:
    """Client for CrossTrade API.

    Handles authentication, rate limiting, retries, and error handling.

    Usage:
        client = CrossTradeClient()
        accounts = client.get_accounts()
        quote = client.get_quote("ES 03-25")
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        account: Optional[str] = None,
        rate_limiter: Optional[RateLimiter] = None,
    ):
        """Initialize CrossTrade client.

        Args:
            api_key: API key (reads from CROSSTRADE_API_KEY env var if not provided)
            base_url: Base URL (reads from CROSSTRADE_BASE_URL env var if not provided)
            account: Default account name (reads from CROSSTRADE_ACCOUNT env var if not provided)
            rate_limiter: Custom rate limiter (creates default 60 req/min if not provided)
        """
        # Load environment variables
        load_dotenv()

        # Configuration
        self.api_key = api_key or os.getenv("CROSSTRADE_API_KEY")
        self.base_url = base_url or os.getenv(
            "CROSSTRADE_BASE_URL", "https://app.crosstrade.io/v1/api"
        )
        self.account = account or os.getenv("CROSSTRADE_ACCOUNT")

        if not self.api_key:
            raise ValueError(
                "API key not provided. Set CROSSTRADE_API_KEY environment variable or pass api_key parameter."
            )

        # Rate limiter (60 requests per minute)
        self.rate_limiter = rate_limiter or RateLimiter(
            max_requests=60, period_seconds=60
        )

        # HTTP session
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            }
        )

        logger.info("CrossTrade client initialized")
        logger.info(f"Base URL: {self.base_url}")
        logger.info(f"Default account: {self.account}")

    def _request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        """Make HTTP request with rate limiting and error handling.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            endpoint: API endpoint (without base URL)
            **kwargs: Additional arguments for requests

        Returns:
            Response object

        Raises:
            AuthenticationError: 401 status
            RateLimitError: 429 status
            CrossTradeError: Other errors
        """
        # Wait for rate limit token
        if not self.rate_limiter.wait_for_token(timeout=10):
            raise RateLimitError()

        # Build URL
        url = f"{self.base_url}{endpoint}"

        # Make request
        try:
            response = self.session.request(
                method=method, url=url, timeout=kwargs.pop("timeout", 10), **kwargs
            )

            # Handle errors
            if response.status_code == 401:
                raise AuthenticationError("Invalid API key")
            elif response.status_code == 429:
                retry_after_header = response.headers.get("Retry-After")
                retry_after = None
                if retry_after_header:
                    try:
                        # Try to parse as integer seconds
                        retry_after = int(retry_after_header)
                    except ValueError:
                        # Header may be non-integer (e.g., "1s") or malformed
                        try:
                            # Try float and cast to int
                            retry_after = int(float(retry_after_header))
                        except ValueError:
                            # Fall back to None
                            retry_after = None
                raise RateLimitError(retry_after=retry_after)
            elif response.status_code == 404:
                raise AccountNotFoundError(f"Resource not found: {endpoint}")
            elif response.status_code >= 400:
                raise CrossTradeError(
                    f"API error {response.status_code}: {response.text}"
                )

            return response

        except requests.exceptions.Timeout as e:
            raise CrossTradeError("Request timeout") from e
        except requests.exceptions.ConnectionError as e:
            raise CrossTradeError("Connection error") from e

    # ===================================================================
    # Account Methods
    # ===================================================================

    @retry(exceptions=RateLimitError, tries=3, delay=2)
    def get_accounts(self) -> List[Account]:
        """Get all accounts.

        Returns:
            List of Account objects
        """
        logger.info("Fetching accounts")
        response = self._request("GET", "/accounts")

        # Parse response - handle both dict and list formats
        data = response.json()
        if isinstance(data, dict) and "accounts" in data:
            accounts_data = data["accounts"]
        elif isinstance(data, list):
            accounts_data = data
        else:
            accounts_data = [data]

        accounts = [
            Account(**acc) if isinstance(acc, dict) else Account(name=str(acc))
            for acc in accounts_data
        ]
        logger.info(f"Found {len(accounts)} account(s)")
        return accounts

    @retry(exceptions=RateLimitError, tries=3, delay=2)
    def get_account(self, account: Optional[str] = None) -> Account:
        """Get specific account details.

        Args:
            account: Account name (uses default if not provided)

        Returns:
            Account object
        """
        account = account or self.account
        if not account:
            raise ValueError("Account name required")

        logger.info(f"Fetching account: {account}")
        response = self._request("GET", f"/accounts/{account}")
        return Account(**response.json())

    # ===================================================================
    # Position Methods
    # ===================================================================

    @retry(exceptions=RateLimitError, tries=3, delay=2)
    def get_positions(self, account: Optional[str] = None) -> List[Position]:
        """Get all positions for account.

        Args:
            account: Account name (uses default if not provided)

        Returns:
            List of Position objects
        """
        account = account or self.account
        if not account:
            raise ValueError("Account name required")

        logger.info(f"Fetching positions for {account}")
        response = self._request("GET", f"/accounts/{account}/positions")

        data = response.json()
        # API returns {"positions": [...], "success": true}
        if isinstance(data, dict) and "positions" in data:
            positions = [Position(**pos) for pos in data["positions"]]
        elif isinstance(data, list):
            positions = [Position(**pos) for pos in data]
        else:
            positions = []

        logger.info(f"Found {len(positions)} position(s)")
        return positions

    @retry(exceptions=RateLimitError, tries=3, delay=2)
    def close_position(self, instrument: str, account: Optional[str] = None) -> Order:
        """Close specific position.

        Args:
            instrument: Instrument name (e.g., "ES 03-25")
            account: Account name (uses default if not provided)

        Returns:
            Order object for closing order
        """
        account = account or self.account
        if not account:
            raise ValueError("Account name required")

        logger.info(f"Closing position: {instrument} in {account}")
        response = self._request(
            "POST", f"/accounts/{account}/positions/{instrument}/close"
        )
        return Order(**response.json())

    @retry(exceptions=RateLimitError, tries=3, delay=2)
    def flatten_account(self, account: Optional[str] = None) -> Dict[str, Any]:
        """Close all positions in account.

        Args:
            account: Account name (uses default if not provided)

        Returns:
            Dictionary with orderIds, closedPositions, and success flag
        """
        account = account or self.account
        if not account:
            raise ValueError("Account name required")

        logger.info(f"Flattening account: {account}")

        # API endpoint: /v1/api/positions/flatten
        # Can optionally pass account filter in body
        body = {"account": account} if account else {}
        response = self._request("POST", "/positions/flatten", json=body)

        data = response.json()

        order_ids = data.get("orderIds", [])
        closed_positions = data.get("closedPositions", [])
        success = data.get("success", False)

        logger.info(
            f"Flatten result: {len(order_ids)} order(s), {len(closed_positions)} position(s) closed, success={success}"
        )
        return data

    # ===================================================================
    # Order Methods
    # ===================================================================

    @retry(exceptions=RateLimitError, tries=3, delay=2)
    def get_orders(
        self, account: Optional[str] = None, active_only: bool = True
    ) -> List[Order]:
        """Get orders for account.

        Args:
            account: Account name (uses default if not provided)
            active_only: Only return working orders (default: True)

        Returns:
            List of Order objects
        """
        account = account or self.account
        if not account:
            raise ValueError("Account name required")

        logger.info(f"Fetching orders for {account} (active_only={active_only})")
        endpoint = f"/accounts/{account}/orders"
        if active_only:
            endpoint += "?status=WORKING"

        response = self._request("GET", endpoint)

        data = response.json()
        if isinstance(data, list):
            orders = [Order(**order) for order in data]
        else:
            orders = []

        logger.info(f"Found {len(orders)} order(s)")
        return orders

    @retry(exceptions=RateLimitError, tries=3, delay=2)
    def submit_order(
        self, order_request: OrderRequest, account: Optional[str] = None
    ) -> Order:
        """Submit new order.

        Args:
            order_request: OrderRequest object with order details
            account: Account name (uses default if not provided)

        Returns:
            Order object for submitted order

        Raises:
            OrderError: If order submission fails
            InsufficientMarginError: If insufficient margin
        """
        account = account or self.account
        if not account:
            raise ValueError("Account name required")

        logger.info(
            f"Submitting order: {order_request.action} {order_request.quantity} {order_request.instrument}"
        )

        try:
            response = self._request(
                "POST",
                f"/accounts/{account}/orders/place",
                json=order_request.to_dict(),
            )
            response_data = response.json()

            # API returns {orderId, success}, but we need full Order object
            # Get the order details from get_orders endpoint
            if response_data.get("success"):
                order_id = response_data["orderId"]
                logger.info(f"Order submitted successfully: {order_id}")

                # Fetch full order details
                orders = self.get_orders(account)
                for order in orders:
                    if order.orderId == order_id:
                        return order

                # If order not found immediately, create minimal Order object
                # (it may still be pending)
                order = Order(
                    orderId=order_id,
                    instrument=order_request.instrument,
                    action=order_request.action,
                    quantity=order_request.quantity,
                    orderType=order_request.orderType,
                    limitPrice=order_request.limitPrice,
                    stopPrice=order_request.stopPrice,
                    filledQuantity=0,
                    state=OrderState.PENDING_SUBMIT,
                    timestamp=datetime.utcnow(),
                )
                return order
            else:
                raise OrderError(f"Order submission failed: {response_data}")

        except CrossTradeError as e:
            if "margin" in str(e).lower():
                raise InsufficientMarginError(str(e))
            raise OrderError(str(e))

    @retry(exceptions=RateLimitError, tries=3, delay=2)
    def cancel_order(self, order_id: str, account: Optional[str] = None) -> Order:
        """Cancel existing order.

        Args:
            order_id: Order ID to cancel
            account: Account name (uses default if not provided)

        Returns:
            Updated Order object
        """
        account = account or self.account
        if not account:
            raise ValueError("Account name required")

        logger.info(f"Cancelling order: {order_id}")
        response = self._request("DELETE", f"/accounts/{account}/orders/{order_id}")
        order = Order(**response.json())
        logger.info(f"Order cancelled: {order_id}")
        return order

    # ===================================================================
    # Market Data Methods
    # ===================================================================

    @retry(exceptions=RateLimitError, tries=3, delay=2)
    def get_quote(self, instrument: str, account: Optional[str] = None) -> Quote:
        """Get real-time quote for instrument.

        Args:
            instrument: Instrument name (e.g., "ES 03-25")
            account: Account name (uses default if not provided)

        Returns:
            Quote object with last, bid, ask, volume
        """
        account = account or self.account
        if not account:
            raise ValueError("Account name required")

        logger.debug(f"Fetching quote: {instrument}")
        response = self._request(
            "GET", f"/accounts/{account}/quote", params={"instrument": instrument}
        )
        quote_data = response.json()

        # Add timestamp if not present in API response
        if "timestamp" not in quote_data:
            quote_data["timestamp"] = datetime.utcnow()

        # Add instrument if not present in API response
        if "instrument" not in quote_data:
            quote_data["instrument"] = instrument

        quote = Quote(**quote_data)
        return quote

    # ===================================================================
    # Execution Methods
    # ===================================================================

    @retry(exceptions=RateLimitError, tries=3, delay=2)
    def get_executions(
        self,
        account: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> List[Execution]:
        """Get trade executions for account.

        Args:
            account: Account name (uses default if not provided)
            start_date: Start date filter
            end_date: End date filter

        Returns:
            List of Execution objects
        """
        account = account or self.account
        if not account:
            raise ValueError("Account name required")

        logger.info(f"Fetching executions for {account}")

        params = {}
        if start_date:
            params["start_date"] = start_date.isoformat()
        if end_date:
            params["end_date"] = end_date.isoformat()

        response = self._request(
            "GET", f"/accounts/{account}/executions", params=params if params else None
        )

        data = response.json()
        if isinstance(data, list):
            executions = [Execution(**exec) for exec in data]
        else:
            executions = []

        logger.info(f"Found {len(executions)} execution(s)")
        return executions
