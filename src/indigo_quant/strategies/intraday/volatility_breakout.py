"""
Intraday Strategy Agent 4: Volatility Breakout.
Identifies explosive range expansions following volatility compression (ATR10/ATR50 <= 0.80),
confirmed by breaking 10-candle highs, session VWAP support, and heavy RVOL.
"""

from __future__ import annotations

import datetime
from typing import List

import numpy as np
import pandas as pd

from indigo_quant.strategies.base import ConditionResult
from indigo_quant.strategies.intraday.base import BaseIntradayStrategy, IntradayEvaluationResult


class IntradayVolatilityBreakoutStrategy(BaseIntradayStrategy):
    """
    Intraday Volatility Breakout Strategy (5-minute timeframe).
    Deterministic Rules:
    1. Volatility compression: ATR10 / ATR50 <= 0.80 (at least 20% contraction)
    2. Candle Close > Previous 10-Candle High (excluding current candle)
    3. Close > Session VWAP
    4. EMA9 > EMA20
    5. Relative Volume (RVOL) >= 1.50
    6. ATR and risk limits pass
    7. Timing: Before 15:00 IST
    """

    def __init__(self, compression_threshold: float = 0.80):
        super().__init__(
            strategy_id="intraday_volatility_breakout",
            name="Intraday Agent 4: Volatility Breakout",
            version="1.0.0",
        )
        self.compression_threshold = compression_threshold

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
        rvol = float(row.get("rvol", np.nan))
        prev_10_high = float(row.get("prev_10_high", np.nan))
        vol_ratio = float(row.get("vol_compression_ratio", np.nan))
        is_compressed = bool(row.get("is_vol_compressed", False))
        atr14 = float(row.get("atr14", close * 0.005))

        conditions: List[ConditionResult] = []

        # 1. Volatility Compression Preceding Breakout (ATR10 / ATR50 <= threshold)
        cond_comp = is_compressed and not np.isnan(vol_ratio)
        comp_desc = f"Volatility compression: ATR10/ATR50 <= {self.compression_threshold:.2f}"
        if np.isnan(vol_ratio):
            comp_desc += " [Insufficient historical warm-up bars for long ATR]"
        conditions.append(ConditionResult(
            name="volatility_compression",
            passed=cond_comp,
            description=comp_desc,
            observed_value=round(vol_ratio, 2) if not np.isnan(vol_ratio) else "Unavailable",
            threshold_value=f"<= {self.compression_threshold:.2f}",
        ))

        # 2. Close > Previous 10-Candle High
        cond_break = not np.isnan(prev_10_high) and close > prev_10_high
        conditions.append(ConditionResult(
            name="close_gt_prev_10_high",
            passed=cond_break,
            description="Close > Previous 10-Candle High (excluding current bar)",
            observed_value=round(close, 2),
            threshold_value=round(prev_10_high, 2) if not np.isnan(prev_10_high) else "NaN",
        ))

        # 3. Close > Session VWAP
        cond_vwap = not np.isnan(vwap) and close > vwap
        conditions.append(ConditionResult(
            name="close_gt_vwap",
            passed=cond_vwap,
            description="Close > Session VWAP",
            observed_value=round(close, 2),
            threshold_value=round(vwap, 2) if not np.isnan(vwap) else "NaN",
        ))

        # 4. EMA9 > EMA20
        cond_ema = not (np.isnan(ema9) or np.isnan(ema20)) and ema9 > ema20
        conditions.append(ConditionResult(
            name="ema9_gt_ema20",
            passed=cond_ema,
            description="EMA9 > EMA20",
            observed_value={"ema9": round(ema9, 2), "ema20": round(ema20, 2)},
            threshold_value="EMA9 > EMA20",
        ))

        # 5. Relative Volume (RVOL) >= 1.50
        cond_rvol = not np.isnan(rvol) and rvol >= 1.50
        rvol_desc = "Relative Volume (RVOL) >= 1.50 vs time-of-day baseline"
        if np.isnan(rvol):
            rvol_desc += " [Insufficient historical time-of-day baseline]"
        conditions.append(ConditionResult(
            name="rvol_surge",
            passed=cond_rvol,
            description=rvol_desc,
            observed_value=round(rvol, 2) if not np.isnan(rvol) else "Unavailable",
            threshold_value=">= 1.50",
        ))

        # 6. ATR risk limits
        stop_dist = max(atr14 * 1.5, close * 0.002)
        cond_risk = stop_dist > 0 and close > stop_dist
        conditions.append(ConditionResult(
            name="positive_risk_limits",
            passed=cond_risk,
            description="ATR Risk limits pass (valid stop distance)",
            observed_value=round(stop_dist, 2),
            threshold_value="> 0",
        ))

        # 7. Timing constraint: before 15:00 IST
        time_cond = self.check_timing_constraints(candle_time)
        if time_cond:
            conditions.append(time_cond)

        rules_passed = [f"{c.name}: {c.description} (observed {c.observed_value})" for c in conditions if c.passed]
        rules_failed = [f"{c.name}: {c.description} (observed {c.observed_value})" for c in conditions if not c.passed]

        all_passed = all(c.passed for c in conditions)

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
