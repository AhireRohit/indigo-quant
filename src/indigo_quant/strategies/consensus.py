"""
Agent E: Multi-Agent Consensus Strategy.
Maintains a separate ₹1,00,000 portfolio.
Requires agreement from at least 2 independent strategies on the same symbol and session.
"""

from __future__ import annotations

import datetime
from typing import List

import pandas as pd

from indigo_quant.strategies.base import BaseStrategy, ConditionResult, StrategyEvaluationResult


class ConsensusStrategy(BaseStrategy):
    """
    Agent E — Consensus
    Requires at least 2 independent strategies to issue BUY signals.
    """

    def __init__(self, version: str = "1.0.0", initial_capital: float = 100000.0, min_agreement: int = 2):
        super().__init__(
            strategy_id="consensus",
            name="Agent E: Multi-Agent Consensus",
            version=version,
            initial_capital=initial_capital,
        )
        self.min_agreement = min_agreement

    def evaluate(self, symbol: str, df: pd.DataFrame, idx: int = -1) -> StrategyEvaluationResult:
        """
        Consensus is evaluated across individual strategy results via evaluate_consensus.
        This base method handles standalone invocation if needed.
        """
        dt = df.index[idx]
        eval_date = dt.date() if hasattr(dt, "date") else pd.to_datetime(dt).date()
        close = float(df.iloc[idx]["close"])

        return StrategyEvaluationResult(
            strategy_id=self.strategy_id,
            strategy_name=self.name,
            strategy_version=self.version,
            symbol=symbol,
            date=eval_date,
            decision="NO_TRADE",
            reference_close=close,
            conditions=[],
            rules_passed=[],
            rules_failed=["Direct single-strategy evaluation not applicable for consensus."],
            rejection_reason="Consensus requires evaluation across independent strategies.",
        )

    def evaluate_consensus(
        self,
        symbol: str,
        eval_date: datetime.date,
        close_price: float,
        strategy_results: List[StrategyEvaluationResult],
    ) -> StrategyEvaluationResult:
        """
        Evaluate consensus from the results of individual strategies on the same date.
        """
        qualifying_strategies = [
            res.strategy_id for res in strategy_results
            if res.decision == "BUY" and res.strategy_id != "consensus"
        ]

        count = len(qualifying_strategies)
        cond = count >= self.min_agreement

        condition = ConditionResult(
            name="multi_agent_agreement",
            passed=bool(cond),
            description=f"At least {self.min_agreement} independent strategies issue BUY",
            observed_value={"qualifying_count": count, "strategies": qualifying_strategies},
            threshold_value=self.min_agreement,
        )

        decision = "BUY" if cond else "NO_TRADE"
        rules_passed = ["multi_agent_agreement"] if cond else []
        rules_failed = [] if cond else [f"Only {count} independent strategies agreed (need {self.min_agreement})"]
        rejection_reason = None if cond else f"Insufficient strategy agreement: {count}/{self.min_agreement}"

        return StrategyEvaluationResult(
            strategy_id=self.strategy_id,
            strategy_name=self.name,
            strategy_version=self.version,
            symbol=symbol,
            date=eval_date,
            decision=decision,
            reference_close=close_price,
            conditions=[condition],
            rules_passed=rules_passed,
            rules_failed=rules_failed,
            rejection_reason=rejection_reason,
        )
