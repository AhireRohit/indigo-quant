"""
Agent D: Bollinger Squeeze Breakout Strategy.
Identifies volatility compression followed by upward expansion breaking prior resistance.
Strictly calculates squeeze percentile using prior known observations with zero lookahead.
"""

from __future__ import annotations

import datetime
from typing import List

import numpy as np
import pandas as pd

from indigo_quant.strategies.base import BaseStrategy, ConditionResult, StrategyEvaluationResult


class BollingerSqueezeStrategy(BaseStrategy):
    """
    Agent D — Bollinger Squeeze Breakout
    All 7 mandatory rules must be satisfied for a BUY signal.
    """

    def __init__(self, version: str = "1.0.0", initial_capital: float = 100000.0):
        super().__init__(
            strategy_id="bollinger_squeeze",
            name="Agent D: Bollinger Squeeze Breakout",
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
                        description="At least 2 completed bars required for squeeze evaluation",
                        observed_value={"bars_available": len(df)},
                        required_threshold={"min_bars": 2},
                    )
                ],
                metadata={"reason": "Insufficient history for squeeze evaluation"},
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
        prev_bb_upper = float(prev_row.get("bb_upper", 0.0))
        prev_bb_width = float(prev_row.get("bb_width", 0.0))
        rvol20 = float(row.get("rvol20", 1.0))
        ema20 = float(row.get("ema20", 0.0))
        ema50 = float(row.get("ema50", 0.0))
        ema200 = float(row.get("ema200", 0.0))
        rsi14 = float(row.get("rsi14", 50.0))
        adx14 = float(row.get("adx14", 0.0))
        prev_adx14 = float(prev_row.get("adx14", 0.0))
        prev_20_high = float(row["previous_20_high"])

        # Calculate squeeze percentile using strictly prior bars
        # Squeeze percentile column 'bb_squeeze_pct_120' was computed over .shift(1).rolling(120)
        squeeze_pct = float(row.get("bb_squeeze_pct_120", np.nan))
        if np.isnan(squeeze_pct) and len(df) >= 30:
            # Fallback manual calculation of prior 120 width percentile
            prior_widths = df["bb_width"].iloc[max(0, idx - 121) : idx]
            if len(prior_widths) > 0:
                squeeze_pct = float((prior_widths < prev_bb_width).sum() / len(prior_widths) * 100.0)

        conditions: List[ConditionResult] = []

        # 1. Previous-session BB width <= 20th percentile of preceding 120-session historical distribution
        cond1 = not np.isnan(squeeze_pct) and squeeze_pct <= 20.0
        conditions.append(ConditionResult(
            name="volatility_squeeze_percentile",
            passed=bool(cond1),
            description="Prior BB width <= 20th percentile of prior 120 sessions",
            observed_value=round(squeeze_pct, 2) if not np.isnan(squeeze_pct) else "NaN",
            threshold_value=20.0,
        ))

        # 2. Current close breaks above previous session's upper Bollinger Band
        cond2 = close > prev_bb_upper
        conditions.append(ConditionResult(
            name="breakout_above_prior_upper_bb",
            passed=bool(cond2),
            description="Close > Prior Upper BB",
            observed_value=round(close, 2),
            threshold_value=round(prev_bb_upper, 2),
        ))

        # 3. RVOL20 >= 1.50
        cond3 = rvol20 >= 1.50
        conditions.append(ConditionResult(
            name="volume_expansion_rvol",
            passed=bool(cond3),
            description="RVOL20 >= 1.50",
            observed_value=round(rvol20, 2),
            threshold_value=1.50,
        ))

        # 4. EMA20 > EMA50 > EMA200
        cond4 = ema20 > ema50 > ema200
        conditions.append(ConditionResult(
            name="trend_alignment",
            passed=bool(cond4),
            description="EMA20 > EMA50 > EMA200",
            observed_value={"ema20": round(ema20, 2), "ema50": round(ema50, 2), "ema200": round(ema200, 2)},
            threshold_value="EMA20 > EMA50 > EMA200",
        ))

        # 5. 55 <= RSI14 <= 72
        cond5 = 55.0 <= rsi14 <= 72.0
        conditions.append(ConditionResult(
            name="rsi_expansion_zone",
            passed=bool(cond5),
            description="55 <= RSI14 <= 72",
            observed_value=round(rsi14, 2),
            threshold_value="[55.0, 72.0]",
        ))

        # 6. Current ADX14 is greater than previous ADX14
        cond6 = adx14 > prev_adx14
        conditions.append(ConditionResult(
            name="adx_rising",
            passed=bool(cond6),
            description="Current ADX14 > Prior ADX14",
            observed_value={"curr_adx": round(adx14, 2), "prev_adx": round(prev_adx14, 2)},
            threshold_value="curr_adx > prev_adx",
        ))

        # 7. Current close is above the previous 20-session highest high
        cond7 = close > prev_20_high
        conditions.append(ConditionResult(
            name="breakout_above_20_high",
            passed=bool(cond7),
            description="Close > Previous 20-session Highest High",
            observed_value=round(close, 2),
            threshold_value=round(prev_20_high, 2),
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
