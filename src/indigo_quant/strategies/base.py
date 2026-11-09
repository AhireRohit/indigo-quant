"""
Base class for all quantitative swing-trading strategy agents.
Ensures deterministic numeric evaluation, explicit condition logging,
and zero subjective or non-reproducible rules.
"""

from __future__ import annotations

import datetime
from abc import ABC, abstractmethod
from typing import Any, List, Optional

import pandas as pd
from pydantic import BaseModel


class ConditionResult(BaseModel):
    name: str
    passed: bool
    description: str
    observed_value: Any
    threshold_value: Any


class StrategyEvaluationResult(BaseModel):
    strategy_id: str
    strategy_name: str
    strategy_version: str
    symbol: str
    date: datetime.date
    decision: str  # "BUY" or "NO_TRADE"
    reference_close: float
    conditions: List[ConditionResult]
    rules_passed: List[str]
    rules_failed: List[str]
    rule_quality_score: float = 0.0
    initial_stop_estimate: float = 0.0
    target_price_estimate: float = 0.0
    stop_distance_pct: float = 0.0
    reward_to_risk_ratio: float = 0.0
    rejection_reason: Optional[str] = None


class BaseStrategy(ABC):
    """Abstract Strategy Agent."""

    def __init__(self, strategy_id: str, name: str, version: str = "1.0.0", initial_capital: float = 100000.0):
        self.strategy_id = strategy_id
        self.name = name
        self.version = version
        self.initial_capital = initial_capital

    @abstractmethod
    def evaluate(self, symbol: str, df: pd.DataFrame, idx: int = -1) -> StrategyEvaluationResult:
        """
        Evaluate exact strategy conditions on pre-calculated indicators DataFrame.
        idx=-1 corresponds to the latest available bar.
        """
        pass
