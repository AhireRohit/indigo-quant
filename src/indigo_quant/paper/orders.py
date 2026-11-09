"""
Paper Order model definitions and idempotency generation.
"""

from __future__ import annotations

import datetime
import hashlib
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    REJECTED = "REJECTED"


def generate_order_id(account_id: str, symbol: str, side: str, signal_date: datetime.date) -> str:
    """
    Generate deterministic idempotency key for an order to prevent duplicate creation
    upon retry or restart.
    """
    raw = f"{account_id}:{symbol}:{side.upper()}:{signal_date.isoformat()}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"ord_{account_id}_{symbol}_{digest}"


class CreatePaperOrderRequest(BaseModel):
    account_id: str
    symbol: str
    strategy_id: str
    order_side: OrderSide
    order_type: OrderType = OrderType.MARKET
    quantity: int = Field(gt=0, description="Number of shares (positive integer)")
    signal_price: float = Field(gt=0.0)
    stop_price: Optional[float] = None
    target_price: Optional[float] = None
    signal_date: datetime.date
    validity_days: int = 2
