"""
Intraday Technical Indicator Engine for INDIGO QUANT.
Calculates session-anchored VWAP, Opening Range Breakout (ORB) levels,
time-of-day Relative Volume (RVOL), volatility compression metrics,
and multi-period moving averages without lookahead leakage.
"""

from __future__ import annotations

import datetime
from typing import Optional

import numpy as np
import pandas as pd

from indigo_quant.indicators.technical import (
    calculate_atr_wilder,
    calculate_bollinger_bands,
    calculate_ema,
    calculate_macd,
    calculate_rsi_wilder,
    calculate_sma,
)


def calculate_session_vwap(df: pd.DataFrame) -> pd.Series:
    """
    Calculate intraday Volume-Weighted Average Price (VWAP) anchored to each session open.
    VWAP strictly resets to the first bar at 09:15 IST each trading morning.
    Typical Price = (High + Low + Close) / 3.
    """
    if df.empty:
        return pd.Series(dtype=float)

    typical_price = (df["high"] + df["low"] + df["close"]) / 3.0
    turnover = typical_price * df["volume"]

    # Group strictly by calendar date of the bar
    dates = df.index.date if hasattr(df.index, "date") else pd.to_datetime(df.index).dt.date
    cum_turnover = turnover.groupby(dates).cumsum()
    cum_volume = df["volume"].groupby(dates).cumsum()

    # Avoid zero-division on opening auction zero-volume ticks
    vwap = cum_turnover / cum_volume.replace(0, np.nan)
    # If cum_volume is zero, fallback to typical price of that candle
    vwap = vwap.fillna(typical_price)
    vwap.name = "vwap"
    return vwap


def calculate_opening_range(
    df: pd.DataFrame,
    start_time: str = "09:15",
    end_time: str = "09:30",
) -> pd.DataFrame:
    """
    Calculates Opening Range High (ORB_High), Opening Range Low (ORB_Low),
    and whether the opening range is fully completed (ORB_Complete).
    The opening range comprises all completed candles between 09:15 and 09:30 IST.
    """
    res = pd.DataFrame(index=df.index)
    res["orb_high"] = np.nan
    res["orb_low"] = np.nan
    res["orb_complete"] = False

    if df.empty:
        return res

    dates = sorted(list(set(df.index.date if hasattr(df.index, "date") else pd.to_datetime(df.index).dt.date)))

    for dt in dates:
        session_mask = (df.index.date if hasattr(df.index, "date") else pd.to_datetime(df.index).dt.date) == dt
        session_df = df[session_mask]

        # Bars during opening window (09:15 to 09:30)
        orb_window = session_df.between_time(start_time, end_time)
        if not orb_window.empty:
            orb_h = float(orb_window["high"].max())
            orb_l = float(orb_window["low"].min())
            orb_cutoff_time = orb_window.index[-1]

            # Mark all bars on or after the cutoff time as complete with locked high/low
            after_cutoff_mask = session_df.index >= orb_cutoff_time
            res.loc[session_df[after_cutoff_mask].index, "orb_high"] = orb_h
            res.loc[session_df[after_cutoff_mask].index, "orb_low"] = orb_l
            res.loc[session_df[after_cutoff_mask].index, "orb_complete"] = True

    return res


def calculate_relative_volume(
    df: pd.DataFrame,
    min_baseline_sessions: int = 3,
) -> pd.Series:
    """
    Calculates intraday Relative Volume (RVOL) compared to identical time-of-day candles
    in preceding sessions.
    If fewer than `min_baseline_sessions` prior days exist for that specific minute, returns NaN.
    """
    rvol = pd.Series(index=df.index, dtype=float, name="rvol")
    if df.empty:
        return rvol

    # Extract time component
    times = df.index.time if hasattr(df.index, "time") else pd.to_datetime(df.index).dt.time
    dates = df.index.date if hasattr(df.index, "date") else pd.to_datetime(df.index).dt.date
    unique_dates = sorted(list(set(dates)))

    for i, cur_date in enumerate(unique_dates):
        if i < min_baseline_sessions:
            # Insufficient historical baseline days preceding cur_date
            continue

        prior_dates = unique_dates[max(0, i - 10) : i]
        prior_mask = np.isin(dates, prior_dates)
        prior_bars = df[prior_mask]

        cur_mask = dates == cur_date
        cur_bars = df[cur_mask]

        # Calculate mean volume per time-of-day in prior days
        prior_tod_mean = prior_bars.groupby(prior_bars.index.time)["volume"].mean()

        for idx, row in cur_bars.iterrows():
            t = idx.time() if hasattr(idx, "time") else pd.to_datetime(idx).time()
            if t in prior_tod_mean and prior_tod_mean[t] > 0:
                rvol.loc[idx] = float(row["volume"]) / float(prior_tod_mean[t])

    return rvol


def calculate_volatility_compression(
    df: pd.DataFrame,
    short_window: int = 10,
    long_window: int = 50,
    threshold: float = 0.80,
) -> Tuple[pd.Series, pd.Series]:
    """
    Calculates volatility compression ratio (Short-term ATR / Long-term ATR)
    and compression flag (True when ratio <= threshold).
    Documented default threshold: 0.80 (20% volatility contraction).
    """
    atr_short = calculate_atr_wilder(df["high"], df["low"], df["close"], short_window)
    atr_long = calculate_atr_wilder(df["high"], df["low"], df["close"], long_window)
    ratio = atr_short / atr_long.replace(0, np.nan)
    ratio = ratio.fillna(1.0)
    is_compressed = ratio <= threshold
    return ratio, is_compressed


def calculate_all_intraday_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Comprehensive, causal intraday indicator calculation for Indigo Quant.
    Strictly NO LOOKAHEAD: each candle $i$ depends exclusively on candles $0 \\dots i$.
    """
    if df.empty:
        return df.copy()

    res = df.copy()

    # 1. Moving Averages
    close = res["close"]
    res["ema9"] = calculate_ema(close, 9)
    res["ema20"] = calculate_ema(close, 20)
    res["ema50"] = calculate_ema(close, 50)
    res["ema200"] = calculate_ema(close, 200)

    # 2. RSI (14)
    res["rsi14"] = calculate_rsi_wilder(close, 14)

    # 3. MACD (12, 26, 9)
    m_line, m_sig, m_hist = calculate_macd(close, fast_period=12, slow_period=26, signal_period=9)
    res["macd_line"] = m_line
    res["macd_signal"] = m_sig
    res["macd_hist"] = m_hist

    # 4. Session VWAP
    res["vwap"] = calculate_session_vwap(res)

    # 5. Bollinger Bands (20, 2)
    bb_u, bb_m, bb_l, bb_w, bb_pb = calculate_bollinger_bands(close, period=20, num_std=2.0)
    res["bb_upper"] = bb_u
    res["bb_middle"] = bb_m
    res["bb_lower"] = bb_l
    res["bb_width"] = bb_w

    # 6. ATR (14)
    res["atr14"] = calculate_atr_wilder(res["high"], res["low"], res["close"], 14)

    # 7. Opening Range (ORB 09:15-09:30)
    orb_df = calculate_opening_range(res)
    res["orb_high"] = orb_df["orb_high"]
    res["orb_low"] = orb_df["orb_low"]
    res["orb_complete"] = orb_df["orb_complete"]

    # 8. Relative Volume (RVOL)
    res["rvol"] = calculate_relative_volume(res)

    # 9. Volatility Compression
    comp_ratio, is_comp = calculate_volatility_compression(res, short_window=10, long_window=50, threshold=0.80)
    res["vol_compression_ratio"] = comp_ratio
    res["is_vol_compressed"] = is_comp

    # 10. Prior Candle References (Causal 1-bar shift)
    res["prev_high"] = res["high"].shift(1)
    res["prev_low"] = res["low"].shift(1)
    res["prev_close"] = res["close"].shift(1)
    res["prev_ema9"] = res["ema9"].shift(1)
    res["prev_macd_hist"] = res["macd_hist"].shift(1)

    # 11. Prior 10-candle High excluding current candle
    res["prev_10_high"] = res["high"].shift(1).rolling(10).max()

    return res
