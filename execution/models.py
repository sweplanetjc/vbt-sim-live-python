"""
CrossTrade API Data Models

Pydantic models for type-safe API request/response handling.
"""

from typing import Optional, List
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field


class OrderAction(str, Enum):
    """Order action (buy/sell)."""
    BUY = "BUY"
    SELL = "SELL"
    BUY_TO_COVER = "BUY_TO_COVER"
    SELL_SHORT = "SELL_SHORT"


class OrderType(str, Enum):
    """Order type."""
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_MARKET = "STOP_MARKET"
    STOP_LIMIT = "STOP_LIMIT"


class TimeInForce(str, Enum):
    """Time in force."""
    DAY = "DAY"
    GTC = "GTC"
    IOC = "IOC"
    FOK = "FOK"


class OrderState(str, Enum):
    """Order state."""
    WORKING = "WORKING"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    PENDING_SUBMIT = "PENDING_SUBMIT"


class Account(BaseModel):
    """NinjaTrader account information."""
    name: str
    connection: Optional[str] = None
    cashValue: float = Field(0.0, alias="cashValue")
    realizedPnL: Optional[float] = Field(None, alias="realizedPnL")
    unrealizedPnL: Optional[float] = Field(None, alias="unrealizedPnL")

    class Config:
        populate_by_name = True


class Position(BaseModel):
    """Position information."""
    instrument: str
    quantity: int
    averagePrice: float = Field(alias="averagePrice")
    unrealizedPnL: Optional[float] = Field(None, alias="unrealizedPnL")

    class Config:
        populate_by_name = True


class Order(BaseModel):
    """Order information."""
    orderId: str = Field(alias="orderId")
    instrument: str
    action: OrderAction
    quantity: int
    orderType: OrderType = Field(alias="orderType")
    limitPrice: Optional[float] = Field(None, alias="limitPrice")
    stopPrice: Optional[float] = Field(None, alias="stopPrice")
    filledQuantity: int = Field(0, alias="filledQuantity")
    averageFillPrice: Optional[float] = Field(None, alias="averageFillPrice")
    state: OrderState
    timestamp: datetime

    class Config:
        populate_by_name = True


class Quote(BaseModel):
    """Market quote data."""
    instrument: str
    last: Optional[float] = None
    bid: Optional[float] = None
    ask: Optional[float] = None
    volume: Optional[int] = None
    timestamp: datetime

    class Config:
        populate_by_name = True


class Execution(BaseModel):
    """Trade execution information."""
    executionId: str = Field(alias="executionId")
    orderId: str = Field(alias="orderId")
    instrument: str
    action: OrderAction
    quantity: int
    price: float
    timestamp: datetime

    class Config:
        populate_by_name = True


class OrderRequest(BaseModel):
    """Order submission request."""
    instrument: str
    action: OrderAction
    quantity: int
    orderType: OrderType = Field(alias="orderType")
    timeInForce: TimeInForce = Field(TimeInForce.DAY, alias="timeInForce")
    limitPrice: Optional[float] = Field(None, alias="limitPrice")
    stopPrice: Optional[float] = Field(None, alias="stopPrice")

    class Config:
        populate_by_name = True

    def to_dict(self):
        """Convert to API request dictionary."""
        data = {
            "instrument": self.instrument,
            "action": self.action.value,
            "quantity": self.quantity,
            "orderType": self.orderType.value,
            "timeInForce": self.timeInForce.value,
        }
        if self.limitPrice is not None:
            data["limitPrice"] = self.limitPrice
        if self.stopPrice is not None:
            data["stopPrice"] = self.stopPrice
        return data
