"""
Agent A: Trend Momentum Strategy.
Identifies liquid Indian equities demonstrating sustained bullish strength with trend and momentum alignment.
"""

from __future__ import annotations

from typing import List

import pandas as pd

from indigo_quant.strategies.base import BaseStrategy, ConditionResult, StrategyEvaluationResult


class TrendMomentumStrategy(BaseStrategy):
    """
    Agent A — Trend Momentum
    All 10 mandatory rules must be satisfied for a BUY signal.
    """

    def __init__(self, version: str = "1.0.0", initial_capital: float = 100000.0):
        super().__init__(
            strategy_id="trend_momentum",
            name="Agent A: Trend Momentum",
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
        df.iloc[idx - 1] if abs(idx) < len(df) else row

        close = float(row["close"])
        ema20 = float(row["ema20"])
        ema50 = float(row["ema50"])
        ema200 = float(row["ema200"])
        sma200 = float(row["sma200"])
        rsi14 = float(row["rsi14"])
        macd_line = float(row["macd_line"])
        macd_sig = float(row["macd_signal"])
        macd_hist = float(row["macd_hist"])
        adx14 = float(row["adx14"])
        rvol20 = float(row["rvol20"])
        ret_5d = float(row.get("return_5d_pct", 0.0))

        conditions: List[ConditionResult] = []

        # 1. EMA20 > EMA50 > EMA200
        cond1 = ema20 > ema50 > ema200
        conditions.append(ConditionResult(
            name="trend_alignment",
            passed=bool(cond1),
            description="EMA20 > EMA50 > EMA200",
            observed_value={"ema20": round(ema20, 2), "ema50": round(ema50, 2), "ema200": round(ema200, 2)},
            threshold_value="EMA20 > EMA50 > EMA200",
        ))

        # 2. close > SMA200
        cond2 = close > sma200
        conditions.append(ConditionResult(
            name="above_sma200",
            passed=bool(cond2),
            description="Close > SMA200",
            observed_value=round(close, 2),
            threshold_value=round(sma200, 2),
        ))

        # 3. close >= EMA20
        cond3 = close >= ema20
        conditions.append(ConditionResult(
            name="above_or_at_ema20",
            passed=bool(cond3),
            description="Close >= EMA20",
            observed_value=round(close, 2),
            threshold_value=round(ema20, 2),
        ))

        # 4. 52 <= RSI14 <= 68
        cond4 = 52.0 <= rsi14 <= 68.0
        conditions.append(ConditionResult(
            name="rsi_in_range",
            passed=bool(cond4),
            description="52 <= RSI14 <= 68",
            observed_value=round(rsi14, 2),
            threshold_value="[52.0, 68.0]",
        ))

        # 5. MACD_line > MACD_signal
        cond5 = macd_line > macd_sig
        conditions.append(ConditionResult(
            name="macd_bullish",
            passed=bool(cond5),
            description="MACD line > MACD signal",
            observed_value=round(macd_line, 3),
            threshold_value=round(macd_sig, 3),
        ))

        # 6. MACD_histogram > 0
        cond6 = macd_hist > 0.0
        conditions.append(ConditionResult(
            name="macd_hist_positive",
            passed=bool(cond6),
            description="MACD histogram > 0",
            observed_value=round(macd_hist, 3),
            threshold_value=0.0,
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

        # 8. RVOL20 >= 1.10
        cond8 = rvol20 >= 1.10
        conditions.append(ConditionResult(
            name="rvol_confirmation",
            passed=bool(cond8),
            description="RVOL20 >= 1.10",
            observed_value=round(rvol20, 2),
            threshold_value=1.10,
        ))

        # 9. close <= EMA20 * 1.05
        max_ema20_ext = ema20 * 1.05
        cond9 = close <= max_ema20_ext
        conditions.append(ConditionResult(
            name="not_extended_from_ema20",
            passed=bool(cond9),
            description="Close <= EMA20 * 1.05",
            observed_value=round(close, 2),
            threshold_value=round(max_ema20_ext, 2),
        ))

        # 10. Five-session price return is positive
        cond10 = ret_5d > 0.0
        conditions.append(ConditionResult(
            name="positive_5d_return",
            passed=bool(cond10),
            description="5-session return > 0%",
            observed_value=round(ret_5d, 2),
            threshold_value=0.0,
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
