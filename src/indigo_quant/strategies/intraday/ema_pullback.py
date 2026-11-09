"""
Intraday Strategy Agent 3: EMA Pullback Continuation.
Buys pullbacks in an ongoing uptrend when price dips to/below EMA9
and immediately reclaims it with expanding MACD momentum and healthy RSI.
"""

from __future__ import annotations

import datetime
from typing import List

import numpy as np
import pandas as pd

from indigo_quant.strategies.base import ConditionResult
from indigo_quant.strategies.intraday.base import BaseIntradayStrategy, IntradayEvaluationResult


class IntradayEMAPullbackStrategy(BaseIntradayStrategy):
    """
    Intraday EMA Pullback Continuation Strategy (5-minute timeframe).
    Deterministic Rules:
    1. EMA9 > EMA20 (Trend Alignment)
    2. Close > Session VWAP
    3. Previous Candle Close <= Previous EMA9 (Pullback to EMA9)
    4. Current Candle Close > Current EMA9 (Reclaim)
    5. 50 <= RSI14 <= 65 (Pullback Zone)
    6. Current MACD Histogram > Previous MACD Histogram (Turning Up)
    7. Valid positive stop distance
    8. Timing: Before 15:00 IST
    """

    def __init__(self):
        super().__init__(
            strategy_id="intraday_ema_pullback",
            name="Intraday Agent 3: EMA Pullback Continuation",
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
        macd_hist = float(row.get("macd_hist", np.nan))
        prev_close = float(row.get("prev_close", np.nan))
        prev_ema9 = float(row.get("prev_ema9", np.nan))
        prev_macd_hist = float(row.get("prev_macd_hist", np.nan))
        prev_low = float(row.get("prev_low", np.nan))
        atr14 = float(row.get("atr14", close * 0.005))

        conditions: List[ConditionResult] = []

        # 1. EMA9 > EMA20
        cond_ema = not (np.isnan(ema9) or np.isnan(ema20)) and ema9 > ema20
        conditions.append(ConditionResult(
            name="ema9_gt_ema20",
            passed=cond_ema,
            description="EMA9 > EMA20",
            observed_value={"ema9": round(ema9, 2), "ema20": round(ema20, 2)},
            threshold_value="EMA9 > EMA20",
        ))

        # 2. Close > Session VWAP
        cond_vwap = not np.isnan(vwap) and close > vwap
        conditions.append(ConditionResult(
            name="close_gt_vwap",
            passed=cond_vwap,
            description="Close > Session VWAP",
            observed_value=round(close, 2),
            threshold_value=round(vwap, 2) if not np.isnan(vwap) else "NaN",
        ))

        # 3. Previous Candle Close <= Previous EMA9
        cond_prior_dip = not (np.isnan(prev_close) or np.isnan(prev_ema9)) and prev_close <= prev_ema9
        conditions.append(ConditionResult(
            name="prev_close_lte_prev_ema9",
            passed=cond_prior_dip,
            description="Previous candle closed at or below EMA9 (Pullback)",
            observed_value={"prev_close": round(prev_close, 2) if not np.isnan(prev_close) else "NaN", "prev_ema9": round(prev_ema9, 2) if not np.isnan(prev_ema9) else "NaN"},
            threshold_value="Prev Close <= Prev EMA9",
        ))

        # 4. Current Candle Close > Current EMA9
        cond_reclaim = not np.isnan(ema9) and close > ema9
        conditions.append(ConditionResult(
            name="close_gt_ema9",
            passed=cond_reclaim,
            description="Current candle closed above EMA9 (Reclaim)",
            observed_value=round(close, 2),
            threshold_value=round(ema9, 2) if not np.isnan(ema9) else "NaN",
        ))

        # 5. 50 <= RSI14 <= 65
        cond_rsi = not np.isnan(rsi14) and (50.0 <= rsi14 <= 65.0)
        conditions.append(ConditionResult(
            name="rsi_pullback_zone",
            passed=cond_rsi,
            description="50.0 <= RSI14 <= 65.0 (Pullback Zone)",
            observed_value=round(rsi14, 2) if not np.isnan(rsi14) else "NaN",
            threshold_value="[50.0, 65.0]",
        ))

        # 6. Current MACD Histogram > Previous MACD Histogram
        cond_hist = not (np.isnan(macd_hist) or np.isnan(prev_macd_hist)) and macd_hist > prev_macd_hist
        conditions.append(ConditionResult(
            name="macd_hist_rising",
            passed=cond_hist,
            description="Current MACD Histogram > Previous Histogram (Momentum inflection)",
            observed_value={"curr_hist": round(macd_hist, 3), "prev_hist": round(prev_macd_hist, 3)},
            threshold_value="Curr Hist > Prev Hist",
        ))

        # 7. Valid positive stop distance
        stop_dist = max(atr14 * 1.2, close * 0.002)
        cond_stop = stop_dist > 0 and close > stop_dist
        conditions.append(ConditionResult(
            name="positive_stop_distance",
            passed=cond_stop,
            description="Valid positive stop distance established",
            observed_value=round(stop_dist, 2),
            threshold_value="> 0",
        ))

        # 8. Timing constraint: before 15:00 IST
        time_cond = self.check_timing_constraints(candle_time)
        if time_cond:
            conditions.append(time_cond)

        rules_passed = [f"{c.name}: {c.description} (observed {c.observed_value})" for c in conditions if c.passed]
        rules_failed = [f"{c.name}: {c.description} (observed {c.observed_value})" for c in conditions if not c.passed]

        all_passed = all(c.passed for c in conditions)

        # Stop loss at prior candle low or 1.2*ATR
        if not np.isnan(prev_low) and prev_low < close:
            initial_stop = round(min(prev_low, close - stop_dist), 2)
        else:
            initial_stop = round(close - stop_dist, 2)

        target_price = round(close + ((close - initial_stop) * self.min_rr_ratio), 2)
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
