"""
Intraday Strategy Agent 1: VWAP Momentum.
Buys momentum surges confirmed by session VWAP, fast EMA alignment,
RSI expansion, positive MACD, and above-average same-time-of-day relative volume.
"""

from __future__ import annotations

import datetime
from typing import List

import numpy as np
import pandas as pd

from indigo_quant.strategies.base import ConditionResult
from indigo_quant.strategies.intraday.base import BaseIntradayStrategy, IntradayEvaluationResult


class IntradayVWAPMomentumStrategy(BaseIntradayStrategy):
    """
    Intraday VWAP Momentum Strategy (5-minute timeframe).
    Deterministic Rules:
    1. Close > session VWAP
    2. EMA9 > EMA20
    3. 52 <= RSI14 <= 70
    4. MACD line > MACD signal
    5. Relative Volume (RVOL) >= 1.20
    6. Close > previous candle High
    7. Current candle Volume > 0
    8. Timing: Before 15:00 IST
    """

    def __init__(self):
        super().__init__(
            strategy_id="intraday_vwap_momentum",
            name="Intraday Agent 1: VWAP Momentum",
            version="1.0.0",
        )

    def evaluate(self, symbol: str, df: pd.DataFrame, idx: int = -1) -> IntradayEvaluationResult:
        if df.empty or abs(idx) > len(df):
            return IntradayEvaluationResult(
                strategy_id=self.strategy_id,
                strategy_name=self.name,
                strategy_version=self.version,
                symbol=symbol,
                timestamp=datetime.datetime.now(),
                decision="INSUFFICIENT_DATA",
                reference_close=0.0,
                conditions=[],
                rules_passed=[],
                rules_failed=["Empty or invalid intraday DataFrame."],
                rejection_reason="No candle data available.",
            )

        row = df.iloc[idx]
        ts = df.index[idx]
        candle_dt = ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else pd.to_datetime(ts).to_pydatetime()
        candle_time = candle_dt.time()
        close = float(row["close"])
        vwap = float(row.get("vwap", np.nan))
        ema9 = float(row.get("ema9", np.nan))
        ema20 = float(row.get("ema20", np.nan))
        rsi14 = float(row.get("rsi14", np.nan))
        macd_line = float(row.get("macd_line", np.nan))
        macd_signal = float(row.get("macd_signal", np.nan))
        rvol = float(row.get("rvol", np.nan))
        prev_high = float(row.get("prev_high", np.nan))
        volume = float(row.get("volume", 0.0))
        atr14 = float(row.get("atr14", close * 0.005))

        conditions: List[ConditionResult] = []

        # 1. Close > Session VWAP
        cond_vwap = not np.isnan(vwap) and close > vwap
        conditions.append(ConditionResult(
            name="close_gt_vwap",
            passed=cond_vwap,
            description="Close > Session VWAP",
            observed_value=round(close, 2),
            threshold_value=round(vwap, 2) if not np.isnan(vwap) else "NaN",
        ))

        # 2. EMA9 > EMA20
        cond_ema = not (np.isnan(ema9) or np.isnan(ema20)) and ema9 > ema20
        conditions.append(ConditionResult(
            name="ema9_gt_ema20",
            passed=cond_ema,
            description="EMA9 > EMA20",
            observed_value={"ema9": round(ema9, 2), "ema20": round(ema20, 2)},
            threshold_value="EMA9 > EMA20",
        ))

        # 3. 52 <= RSI14 <= 70
        cond_rsi = not np.isnan(rsi14) and (52.0 <= rsi14 <= 70.0)
        conditions.append(ConditionResult(
            name="rsi_momentum_zone",
            passed=cond_rsi,
            description="52.0 <= RSI14 <= 70.0 (Momentum Zone)",
            observed_value=round(rsi14, 2) if not np.isnan(rsi14) else "NaN",
            threshold_value="[52.0, 70.0]",
        ))

        # 4. MACD Line > MACD Signal
        cond_macd = not (np.isnan(macd_line) or np.isnan(macd_signal)) and macd_line > macd_signal
        conditions.append(ConditionResult(
            name="macd_bullish",
            passed=cond_macd,
            description="MACD Line > Signal Line",
            observed_value={"macd": round(macd_line, 3), "signal": round(macd_signal, 3)},
            threshold_value="MACD > Signal",
        ))

        # 5. RVOL >= 1.20
        cond_rvol = not np.isnan(rvol) and rvol >= 1.20
        rvol_desc = "Relative Volume (RVOL) >= 1.20 vs intraday time-of-day baseline"
        if np.isnan(rvol):
            rvol_desc += " [Insufficient historical time-of-day baseline]"
        conditions.append(ConditionResult(
            name="rvol_above_baseline",
            passed=cond_rvol,
            description=rvol_desc,
            observed_value=round(rvol, 2) if not np.isnan(rvol) else "Unavailable",
            threshold_value=">= 1.20",
        ))

        # 6. Close > Previous Candle High
        cond_break = not np.isnan(prev_high) and close > prev_high
        conditions.append(ConditionResult(
            name="close_gt_prev_high",
            passed=cond_break,
            description="Close > Previous Candle High",
            observed_value=round(close, 2),
            threshold_value=round(prev_high, 2) if not np.isnan(prev_high) else "NaN",
        ))

        # 7. Volume > 0
        cond_vol = volume > 0
        conditions.append(ConditionResult(
            name="positive_volume",
            passed=cond_vol,
            description="Candle Volume > 0",
            observed_value=volume,
            threshold_value="> 0",
        ))

        # 8. Timing constraint: before 15:00 IST
        time_cond = self.check_timing_constraints(candle_time)
        if time_cond:
            conditions.append(time_cond)

        rules_passed = [f"{c.name}: {c.description} (observed {c.observed_value})" for c in conditions if c.passed]
        rules_failed = [f"{c.name}: {c.description} (observed {c.observed_value})" for c in conditions if not c.passed]

        all_passed = all(c.passed for c in conditions)

        # Stop & Target Calculation
        # Stop loss: 1.5 * ATR below entry (or previous candle low if tighter and safe)
        stop_dist = max(atr14 * 1.5, close * 0.002)
        initial_stop = round(close - stop_dist, 2)
        target_price = round(close + (stop_dist * self.min_rr_ratio), 2)
        stop_dist_pct = round(((close - initial_stop) / close) * 100.0, 2)
        rr_ratio = round((target_price - close) / (close - initial_stop), 2)

        quality_score = round((len(rules_passed) / len(conditions)) * 100.0, 1) if conditions else 0.0

        decision = "BUY" if all_passed else "NO_BUY"
        rejection_reason = None if all_passed else f"Failed {len(rules_failed)} rule(s): {', '.join([c.name for c in conditions if not c.passed])}"

        return IntradayEvaluationResult(
            strategy_id=self.strategy_id,
            strategy_name=self.name,
            strategy_version=self.version,
            symbol=symbol,
            timestamp=candle_dt,
            decision=decision,
            reference_close=close,
            conditions=conditions,
            rules_passed=rules_passed,
            rules_failed=rules_failed,
            rule_quality_score=quality_score,
            initial_stop_price=initial_stop,
            target_price=target_price,
            stop_distance_pct=stop_dist_pct,
            reward_to_risk_ratio=rr_ratio,
            rejection_reason=rejection_reason,
            candle_time=candle_time.strftime("%H:%M"),
        )
