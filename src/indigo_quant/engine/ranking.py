"""
Deterministic Rule Quality Ranking Engine.
Scores already-qualified candidate setups on a 0 to 100 scale using fixed weighted components.
This is a rule-ranking metric, NOT an estimated probability of success.
"""

from __future__ import annotations

from typing import Dict, Tuple

import numpy as np
import pandas as pd


class RuleRankingEngine:
    """
    Computes deterministic rule_quality_score (0-100) based on:
    - Trend quality: 25 pts
    - Momentum quality: 20 pts
    - Volume confirmation: 20 pts
    - Entry / Breakout quality: 20 pts
    - Volatility & Risk quality: 15 pts
    """

    @staticmethod
    def calculate_score(row: pd.Series) -> Tuple[float, Dict[str, float]]:
        """
        Compute weighted components and total rule quality score.
        All inputs clipped to strictly defined ranges.
        """
        close = float(row["close"])
        ema20 = float(row["ema20"])
        ema50 = float(row["ema50"])
        ema200 = float(row["ema200"])
        sma200 = float(row["sma200"])
        rsi14 = float(row["rsi14"])
        macd_hist = float(row["macd_hist"])
        adx14 = float(row["adx14"])
        rvol20 = float(row["rvol20"])
        atr14 = float(row["atr14"])
        high = float(row["high"])
        low = float(row["low"])
        ret_5d = float(row.get("return_5d_pct", 0.0))

        # 1. Trend Quality (25 pts max)
        # 1.1 EMA alignment (10 pts)
        pts_trend_align = 10.0 if (ema20 > ema50 > ema200) else (5.0 if ema20 > ema50 else 0.0)
        # 1.2 Proximity above SMA200 (10 pts max, 0% to 15% range)
        sma200_dist_pct = ((close - sma200) / sma200 * 100.0) if sma200 > 0 else 0.0
        pts_sma200 = float(np.clip((sma200_dist_pct / 15.0) * 10.0, 0.0, 10.0))
        # 1.3 ADX trend strength (5 pts max, 20 to 45 range)
        pts_adx = float(np.clip(((adx14 - 20.0) / 25.0) * 5.0, 0.0, 5.0))
        trend_score = pts_trend_align + pts_sma200 + pts_adx

        # 2. Momentum Quality (20 pts max)
        # 2.1 RSI optimality: ideal swing band is 55-65 (10 pts)
        if 55.0 <= rsi14 <= 65.0:
            pts_rsi = 10.0
        elif 50.0 <= rsi14 < 55.0 or 65.0 < rsi14 <= 70.0:
            pts_rsi = 7.5
        elif 45.0 <= rsi14 < 50.0 or 70.0 < rsi14 <= 75.0:
            pts_rsi = 5.0
        else:
            pts_rsi = 2.0
        # 2.2 MACD histogram positive & robust (5 pts max)
        pts_macd = 5.0 if macd_hist > 0 else 0.0
        # 2.3 5-day return momentum (5 pts max, 0% to 6%)
        pts_ret5d = float(np.clip((ret_5d / 6.0) * 5.0, 0.0, 5.0))
        momentum_score = pts_rsi + pts_macd + pts_ret5d

        # 3. Volume Confirmation (20 pts max)
        # RVOL20: 1.0x to 3.0x maps linearly from 5 to 20 pts
        pts_rvol = float(np.clip(5.0 + ((rvol20 - 1.0) / 2.0) * 15.0, 0.0, 20.0))
        volume_score = pts_rvol

        # 4. Entry / Breakout Quality (20 pts max)
        # 4.1 Proximity to EMA20 (not overextended): 0% to 4% distance is ideal (10 pts)
        ema20_dist_pct = abs((close - ema20) / ema20 * 100.0) if ema20 > 0 else 0.0
        if ema20_dist_pct <= 2.5:
            pts_ema_prox = 10.0
        elif ema20_dist_pct <= 5.0:
            pts_ema_prox = 7.0
        else:
            pts_ema_prox = 3.0
        # 4.2 Close position within day's high-low range (10 pts max)
        day_span = high - low
        range_loc = ((close - low) / day_span) if day_span > 0 else 0.5
        pts_range_loc = float(np.clip(range_loc * 10.0, 0.0, 10.0))
        entry_score = pts_ema_prox + pts_range_loc

        # 5. Volatility & Risk Quality (15 pts max)
        # 5.1 Controlled ATR %: 1.5% to 4.0% close is ideal (10 pts max)
        atr_pct = (atr14 / close * 100.0) if close > 0 else 5.0
        if 1.5 <= atr_pct <= 3.5:
            pts_atr = 10.0
        elif atr_pct < 1.5 or (3.5 < atr_pct <= 5.0):
            pts_atr = 6.0
        else:
            pts_atr = 2.0
        # 5.2 Volatility compression bonus (5 pts)
        bb_squeeze_pct = float(row.get("bb_squeeze_pct_120", 50.0))
        pts_squeeze = 5.0 if (not np.isnan(bb_squeeze_pct) and bb_squeeze_pct <= 25.0) else 2.5
        volatility_score = pts_atr + pts_squeeze

        total_score = float(np.clip(trend_score + momentum_score + volume_score + entry_score + volatility_score, 0.0, 100.0))

        components = {
            "trend_quality": round(trend_score, 1),
            "momentum_quality": round(momentum_score, 1),
            "volume_confirmation": round(volume_score, 1),
            "entry_quality": round(entry_score, 1),
            "volatility_risk_quality": round(volatility_score, 1),
            "total_score": round(total_score, 1),
        }

        return round(total_score, 1), components
