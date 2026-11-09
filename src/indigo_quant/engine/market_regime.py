"""
Market Regime Filter for Indian Equities.
Evaluates NIFTY 50 benchmark structure to permit or block new swing entries.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Optional, Tuple

import pandas as pd

from indigo_quant.indicators.technical import calculate_ema


class MarketRegimeStatus(str, Enum):
    BULLISH = "BULLISH"
    DEFENSIVE = "DEFENSIVE"
    UNKNOWN = "UNKNOWN"


class MarketRegimeEngine:
    """
    Evaluates benchmark health using deterministic rules on NIFTY 50 daily data.
    Default Rule:
    1. NIFTY 50 close > EMA200
    2. NIFTY 50 EMA50 > EMA200
    Both must pass to permit new BUY signals.
    """

    def __init__(self, min_required_sessions: int = 200):
        self.min_required_sessions = min_required_sessions

    def evaluate(self, nifty_df: Optional[pd.DataFrame]) -> Tuple[MarketRegimeStatus, Dict[str, Any]]:
        """
        Evaluate regime status.
        Returns (MarketRegimeStatus, details_dict).
        """
        if nifty_df is None or nifty_df.empty:
            return MarketRegimeStatus.UNKNOWN, {
                "reason": "NIFTY 50 benchmark data is missing or empty. Fail-closed defensively.",
                "allow_new_entries": False,
            }

        if len(nifty_df) < self.min_required_sessions:
            return MarketRegimeStatus.UNKNOWN, {
                "reason": f"Insufficient NIFTY 50 history ({len(nifty_df)} < {self.min_required_sessions}). Fail-closed.",
                "allow_new_entries": False,
            }

        close = nifty_df["close"]
        ema50 = calculate_ema(close, 50)
        ema200 = calculate_ema(close, 200)

        latest_close = float(close.iloc[-1])
        latest_ema50 = float(ema50.iloc[-1])
        latest_ema200 = float(ema200.iloc[-1])
        latest_date = nifty_df.index[-1]
        if hasattr(latest_date, "date"):
            latest_date = latest_date.date()

        cond1_close_gt_ema200 = latest_close > latest_ema200
        cond2_ema50_gt_ema200 = latest_ema50 > latest_ema200

        details = {
            "benchmark": "^NSEI",
            "date": str(latest_date),
            "close": round(latest_close, 2),
            "ema50": round(latest_ema50, 2),
            "ema200": round(latest_ema200, 2),
            "cond_close_gt_ema200": bool(cond1_close_gt_ema200),
            "cond_ema50_gt_ema200": bool(cond2_ema50_gt_ema200),
        }

        if cond1_close_gt_ema200 and cond2_ema50_gt_ema200:
            details["reason"] = (
                f"NIFTY 50 (₹{latest_close:.1f}) is above EMA200 (₹{latest_ema200:.1f}) "
                f"and EMA50 (₹{latest_ema50:.1f}) > EMA200. Bullish regime confirmed."
            )
            details["allow_new_entries"] = True
            return MarketRegimeStatus.BULLISH, details
        else:
            failed = []
            if not cond1_close_gt_ema200:
                failed.append(f"Close (₹{latest_close:.1f}) <= EMA200 (₹{latest_ema200:.1f})")
            if not cond2_ema50_gt_ema200:
                failed.append(f"EMA50 (₹{latest_ema50:.1f}) <= EMA200 (₹{latest_ema200:.1f})")

            details["reason"] = f"Defensive regime. Failed conditions: {', '.join(failed)}. New BUY orders blocked."
            details["allow_new_entries"] = False
            return MarketRegimeStatus.DEFENSIVE, details
