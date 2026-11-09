"""
Base interface and dataclasses for deterministic Intraday Strategy Agents.
Guarantees numeric reproducibility, strict no-lookahead condition evaluation,
independent capital tracking, and explicit condition logging.
"""

from __future__ import annotations

import datetime
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

import pandas as pd
from pydantic import BaseModel

from indigo_quant.strategies.base import ConditionResult


class IntradayEvaluationResult(BaseModel):
    strategy_id: str
    strategy_name: str
    strategy_version: str
    symbol: str
    timestamp: datetime.datetime
    decision: str  # "BUY", "NO_BUY", or "INSUFFICIENT_DATA"
    reference_close: float
    conditions: List[ConditionResult]
    rules_passed: List[str]
    rules_failed: List[str]
    rule_quality_score: float = 0.0
    initial_stop_price: float = 0.0
    target_price: float = 0.0
    stop_distance_pct: float = 0.0
    reward_to_risk_ratio: float = 0.0
    rejection_reason: Optional[str] = None
    candle_time: str = ""

    @property
    def quality_score(self) -> float:
        return self.rule_quality_score

    @property
    def initial_stop_estimate(self) -> float:
        return self.initial_stop_price

    @property
    def target_price_estimate(self) -> float:
        return self.target_price

    @property
    def date(self) -> datetime.date:
        return self.timestamp.date()


class BaseIntradayStrategy(ABC):
    """Abstract Base Class for all 5-minute Intraday Strategy Agents."""

    def __init__(
        self,
        strategy_id: str,
        name: str,
        version: str = "1.0.0",
        initial_capital: float = 100000.0,
        risk_per_trade_pct: float = 0.0025,  # 0.25% of equity
        min_rr_ratio: float = 1.5,
        no_new_entries_after: datetime.time = datetime.time(15, 0),
        force_exit_time: datetime.time = datetime.time(15, 25),
    ):
        self.strategy_id = strategy_id
        self.name = name
        self.version = version
        self.initial_capital = initial_capital
        self.risk_per_trade_pct = risk_per_trade_pct
        self.min_rr_ratio = min_rr_ratio
        self.no_new_entries_after = no_new_entries_after
        self.force_exit_time = force_exit_time

    @abstractmethod
    def evaluate(
        self,
        symbol: str,
        df: pd.DataFrame,
        idx: int = -1,
    ) -> IntradayEvaluationResult:
        """
        Evaluate candle at index `idx` using ONLY historical bars up to `idx`.
        Must never inspect `df.iloc[idx + 1:]`.
        """
        pass

    def check_timing_constraints(self, candle_time: datetime.time) -> Optional[ConditionResult]:
        """Verify the candle is before the 15:00 cutoff for new intraday entries."""
        is_before_cutoff = candle_time < self.no_new_entries_after
        return ConditionResult(
            name="entry_before_cutoff",
            passed=is_before_cutoff,
            description="No new intraday entries permitted after 15:00 IST",
            observed_value=candle_time.strftime("%H:%M"),
            threshold_value=self.no_new_entries_after.strftime("%H:%M"),
        )
