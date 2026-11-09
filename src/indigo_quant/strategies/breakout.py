"""
Agent B: Volume Breakout Strategy.
Identifies liquid Indian equities breaking above 20-session resistance with high volume participation.
"""

from __future__ import annotations

from typing import List

import pandas as pd

from indigo_quant.strategies.base import BaseStrategy, ConditionResult, StrategyEvaluationResult


class VolumeBreakoutStrategy(BaseStrategy):
    """
    Agent B — Volume Breakout
    All 9 mandatory rules must be satisfied for a BUY signal.
    """

    def __init__(self, version: str = "1.0.0", initial_capital: float = 100000.0):
        super().__init__(
            strategy_id="volume_breakout",
            name="Agent B: Volume Breakout",
            version=version,
            initial_capital=initial_capital,
        )

    def evaluate(self, symbol: str, df: pd.DataFrame, idx: int = -1) -> StrategyEvaluationResult:
        dt = df.index[idx]
        if hasattr(dt, "date"):
            eval_date = dt.date()
        else:
            eval_date = pd.to_datetime(dt).date()

        row = df.iloc[idx]

        close = float(row["close"])
        high = float(row["high"])
        low = float(row["low"])
        prev_20_high = float(row["previous_20_high"])
        rvol20 = float(row["rvol20"])
        ema20 = float(row["ema20"])
        ema50 = float(row["ema50"])
        ema200 = float(row["ema200"])
        rsi14 = float(row["rsi14"])
        adx14 = float(row["adx14"])
        atr14 = float(row["atr14"])

        conditions: List[ConditionResult] = []

        # 1. close >= previous_20_high * 1.005
        min_breakout = prev_20_high * 1.005
        cond1 = close >= min_breakout
        conditions.append(ConditionResult(
            name="min_breakout_confirmed",
            passed=bool(cond1),
            description="Close >= previous_20_high * 1.005",
            observed_value=round(close, 2),
            threshold_value=round(min_breakout, 2),
        ))

        # 2. close <= previous_20_high * 1.04
        max_breakout = prev_20_high * 1.04
        cond2 = close <= max_breakout
        conditions.append(ConditionResult(
            name="not_chasing_extended_breakout",
            passed=bool(cond2),
            description="Close <= previous_20_high * 1.04",
            observed_value=round(close, 2),
            threshold_value=round(max_breakout, 2),
        ))

        # 3. RVOL20 >= 1.50
        cond3 = rvol20 >= 1.50
        conditions.append(ConditionResult(
            name="high_volume_participation",
            passed=bool(cond3),
            description="RVOL20 >= 1.50",
            observed_value=round(rvol20, 2),
            threshold_value=1.50,
        ))

        # 4. EMA20 > EMA50
        cond4 = ema20 > ema50
        conditions.append(ConditionResult(
            name="intermediate_trend_up",
            passed=bool(cond4),
            description="EMA20 > EMA50",
            observed_value={"ema20": round(ema20, 2), "ema50": round(ema50, 2)},
            threshold_value="EMA20 > EMA50",
        ))

        # 5. close > EMA200
        cond5 = close > ema200
        conditions.append(ConditionResult(
            name="above_ema200",
            passed=bool(cond5),
            description="Close > EMA200",
            observed_value=round(close, 2),
            threshold_value=round(ema200, 2),
        ))

        # 6. 55 <= RSI14 <= 75
        cond6 = 55.0 <= rsi14 <= 75.0
        conditions.append(ConditionResult(
            name="breakout_momentum_rsi",
            passed=bool(cond6),
            description="55 <= RSI14 <= 75",
            observed_value=round(rsi14, 2),
            threshold_value="[55.0, 75.0]",
        ))

        # 7. ADX14 >= 20
        cond7 = adx14 >= 20.0
        conditions.append(ConditionResult(
            name="adx_trend_strength",
            passed=bool(cond7),
            description="ADX14 >= 20",
            observed_value=round(adx14, 2),
            threshold_value=20.0,
        ))

        # 8. ATR14 / close <= 0.05
        atr_ratio = atr14 / close if close > 0 else 1.0
        cond8 = atr_ratio <= 0.05
        conditions.append(ConditionResult(
            name="atr_volatility_ceiling",
            passed=bool(cond8),
            description="ATR14 / Close <= 0.05",
            observed_value=round(atr_ratio, 4),
            threshold_value=0.05,
        ))

        # 9. Daily close in upper 25% of day's range
        # If high equals low, treat as invalid and do not divide by zero
        day_range = high - low
        if day_range <= 0.0:
            cond9 = False
            range_loc = 0.0
        else:
            range_loc = (close - low) / day_range
            cond9 = range_loc >= 0.75

        conditions.append(ConditionResult(
            name="close_in_upper_quartile",
            passed=bool(cond9),
            description="Close in upper 25% of high-low range (>= 0.75)",
            observed_value=round(range_loc, 3),
            threshold_value=0.75,
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
