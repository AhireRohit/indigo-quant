"""
Agent C: Bullish Pullback Recovery Strategy.
Identifies structurally bullish stocks recovering after a controlled pullback to EMA20.
"""

from __future__ import annotations

import datetime
from typing import List

import pandas as pd

from indigo_quant.strategies.base import BaseStrategy, ConditionResult, StrategyEvaluationResult


class BullishPullbackStrategy(BaseStrategy):
    """
    Agent C — Bullish Pullback Recovery
    All 9 mandatory rules must be satisfied for a BUY signal.
    Requires genuine cross using prior session values.
    """

    def __init__(self, version: str = "1.0.0", initial_capital: float = 100000.0):
        super().__init__(
            strategy_id="bullish_pullback",
            name="Agent C: Bullish Pullback Recovery",
            version=version,
            initial_capital=initial_capital,
        )

    def evaluate(self, symbol: str, df: pd.DataFrame, idx: int = -1) -> StrategyEvaluationResult:
        if df.empty or len(df) < 2:
            return StrategyEvaluationResult(
                symbol=symbol,
                strategy_id=self.strategy_id,
                strategy_version=self.version,
                signal_date=datetime.date.today(),
                decision="NO_TRADE",
                rule_quality_score=0.0,
                reference_close=0.0,
                target_price_estimate=0.0,
                initial_stop_estimate=0.0,
                conditions_passed=[],
                conditions_failed=[
                    ConditionResult(
                        name="sufficient_history",
                        passed=False,
                        description="At least 2 completed bars required for pullback evaluation",
                        observed_value={"bars_available": len(df)},
                        required_threshold={"min_bars": 2},
                    )
                ],
                metadata={"reason": "Insufficient history for pullback comparison"},
            )

        dt = df.index[idx]
        if hasattr(dt, "date"):
            eval_date = dt.date()
        else:
            eval_date = pd.to_datetime(dt).date()

        row = df.iloc[idx]
        prev_idx = idx - 1 if abs(idx) < len(df) else 0
        prev_row = df.iloc[prev_idx]

        close = float(row["close"])
        prev_close = float(prev_row["close"])
        ema20 = float(row.get("ema20", 0.0))
        prev_ema20 = float(prev_row.get("ema20", 0.0))
        ema50 = float(row.get("ema50", 0.0))
        ema200 = float(row.get("ema200", 0.0))
        rsi14 = float(row.get("rsi14", 50.0))
        prev_rsi14 = float(prev_row.get("rsi14", 50.0))
        macd_hist = float(row.get("macd_hist", 0.0))
        prev_macd_hist = float(prev_row.get("macd_hist", 0.0))
        rvol20 = float(row.get("rvol20", 1.0))

        conditions: List[ConditionResult] = []

        # 1. EMA50 > EMA200
        cond1 = ema50 > ema200
        conditions.append(ConditionResult(
            name="macro_bullish_structure",
            passed=bool(cond1),
            description="EMA50 > EMA200",
            observed_value={"ema50": round(ema50, 2), "ema200": round(ema200, 2)},
            threshold_value="EMA50 > EMA200",
        ))

        # 2. close > EMA50
        cond2 = close > ema50
        conditions.append(ConditionResult(
            name="above_ema50",
            passed=bool(cond2),
            description="Close > EMA50",
            observed_value=round(close, 2),
            threshold_value=round(ema50, 2),
        ))

        # 3. Previous close was at or below previous EMA20
        cond3 = prev_close <= prev_ema20
        conditions.append(ConditionResult(
            name="prior_pullback_below_ema20",
            passed=bool(cond3),
            description="Prior Close <= Prior EMA20",
            observed_value={"prev_close": round(prev_close, 2), "prev_ema20": round(prev_ema20, 2)},
            threshold_value="prev_close <= prev_ema20",
        ))

        # 4. Current close crosses above EMA20 (genuine cross)
        cond4 = close > ema20
        conditions.append(ConditionResult(
            name="genuine_ema20_cross",
            passed=bool(cond4 and cond3),
            description="Current Close > EMA20 (Genuine cross after pullback)",
            observed_value={"curr_close": round(close, 2), "curr_ema20": round(ema20, 2)},
            threshold_value="curr_close > curr_ema20 and prev_close <= prev_ema20",
        ))

        # 5. Previous RSI14 was between 38 and 50 inclusive
        cond5 = 38.0 <= prev_rsi14 <= 50.0
        conditions.append(ConditionResult(
            name="prior_rsi_in_pullback_zone",
            passed=bool(cond5),
            description="Prior RSI14 in [38.0, 50.0]",
            observed_value=round(prev_rsi14, 2),
            threshold_value="[38.0, 50.0]",
        ))

        # 6. Current RSI14 is between 50 and 65 inclusive
        cond6 = 50.0 <= rsi14 <= 65.0
        conditions.append(ConditionResult(
            name="curr_rsi_in_recovery_zone",
            passed=bool(cond6),
            description="Current RSI14 in [50.0, 65.0]",
            observed_value=round(rsi14, 2),
            threshold_value="[50.0, 65.0]",
        ))

        # 7. Current MACD histogram exceeds previous MACD histogram
        cond7 = macd_hist > prev_macd_hist
        conditions.append(ConditionResult(
            name="macd_histogram_turning_up",
            passed=bool(cond7),
            description="Current MACD histogram > Prior MACD histogram",
            observed_value={"curr_hist": round(macd_hist, 4), "prev_hist": round(prev_macd_hist, 4)},
            threshold_value="curr_hist > prev_hist",
        ))

        # 8. RVOL20 >= 0.90
        cond8 = rvol20 >= 0.90
        conditions.append(ConditionResult(
            name="adequate_volume_support",
            passed=bool(cond8),
            description="RVOL20 >= 0.90",
            observed_value=round(rvol20, 2),
            threshold_value=0.90,
        ))

        # 9. close <= EMA20 * 1.04
        max_ema20 = ema20 * 1.04
        cond9 = close <= max_ema20
        conditions.append(ConditionResult(
            name="entry_near_ema20_cross",
            passed=bool(cond9),
            description="Close <= EMA20 * 1.04",
            observed_value=round(close, 2),
            threshold_value=round(max_ema20, 2),
        ))

        rules_passed = [c.name for c in conditions if c.passed]
        rules_failed = [f"{c.name}: {c.description} (observed {c.observed_value})" for c in conditions if not c.passed]

        all_passed = len(rules_failed) == 0
        decision = "BUY" if all_passed else "NO_TRADE"
        rejection_reason = None if all_passed else f"Failed conditions: {'; '.join(rules_failed)}"

        return StrategyEvaluationResult(
            strategy_id=self.strategy_id,
            strategy_name=self.name,
            strategy_version=self.version,
            symbol=symbol,
            date=eval_date,
            decision=decision,
            reference_close=close,
            conditions=conditions,
            rules_passed=rules_passed,
            rules_failed=rules_failed,
            rejection_reason=rejection_reason,
        )
