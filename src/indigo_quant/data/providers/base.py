"""
Base interface and abstractions for market data providers.
"""

from __future__ import annotations

import datetime
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

import pandas as pd


class BaseDataProvider(ABC):
    """Abstract interface defining the contract for market data adapters."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Human-readable provider identifier."""
        pass

    @abstractmethod
    def fetch_ohlcv(
        self,
        symbol: str,
        exchange: str = "NSE",
        start_date: Optional[datetime.date] = None,
        end_date: Optional[datetime.date] = None,
    ) -> pd.DataFrame:
        """
        Fetch historical daily OHLCV bars.
        Returned DataFrame MUST:
        - Have index named 'date' of type pd.DatetimeIndex (or date objects), sorted ascending.
        - Contain float columns: 'open', 'high', 'low', 'close', 'volume'.
        - Optionally contain 'turnover', 'adj_close'.
        """
        pass

    @abstractmethod
    def fetch_corporate_actions(
        self,
        symbol: str,
        exchange: str = "NSE",
    ) -> List[Dict[str, Any]]:
        """
        Fetch corporate actions (dividends, splits, bonuses).
        Returns a list of dicts with keys:
        - 'symbol', 'exchange', 'ex_date', 'action_type', 'cash_amount', 'ratio_num', 'ratio_den'
        """
        pass

    @abstractmethod
    def is_healthy(self) -> bool:
        """Perform a quick liveness / readiness probe."""
        pass
