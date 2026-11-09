"""
Technical Indicator Engine for Indigo Quant.
Mathematically rigorous, vectorized indicator functions with strict lookahead prevention
and Wilder smoothing conventions.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd


def calculate_ema(series: pd.Series, period: int) -> pd.Series:
    """Calculate Exponential Moving Average (EMA)."""
    return series.ewm(span=period, adjust=False).mean()


def calculate_sma(series: pd.Series, period: int) -> pd.Series:
    """Calculate Simple Moving Average (SMA)."""
    return series.rolling(window=period, min_periods=period).mean()


def calculate_rsi_wilder(series: pd.Series, period: int = 14) -> pd.Series:
    """
    Calculate Relative Strength Index (RSI) using J. Welles Wilder's smoothing.
    Wilder smoothing corresponds to an exponential moving average with alpha = 1 / period.
    """
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)

    # Wilder smoothing (alpha = 1 / period)
    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()

    # Calculate RS and RSI
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))

    # When loss is 0, RSI is 100; when gain is 0, RSI is 0
    rsi = rsi.where(avg_loss != 0, 100.0)
    rsi = rsi.where(avg_gain != 0, 0.0)
    return rsi


def calculate_macd(
    series: pd.Series,
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """
    Calculate Moving Average Convergence Divergence (MACD).
    Returns (macd_line, macd_signal, macd_histogram).
    """
    fast_ema = calculate_ema(series, fast_period)
    slow_ema = calculate_ema(series, slow_period)
    macd_line = fast_ema - slow_ema
    macd_signal = calculate_ema(macd_line, signal_period)
    macd_histogram = macd_line - macd_signal
    return macd_line, macd_signal, macd_histogram


def calculate_atr_wilder(
    high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14
) -> pd.Series:
    """
    Calculate Average True Range (ATR) using J. Welles Wilder's smoothing.
    TR = max(high - low, abs(high - close_prev), abs(low - close_prev))
    """
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    atr = tr.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    return atr


def calculate_adx_wilder(
    high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """
    Calculate Average Directional Index (ADX), +DI, and -DI using Wilder smoothing.
    Returns (adx, plus_di, minus_di).
    """
    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    plus_dm_s = pd.Series(plus_dm, index=high.index)
    minus_dm_s = pd.Series(minus_dm, index=high.index)

    atr = calculate_atr_wilder(high, low, close, period=period)

    # Wilder smoothing of DM
    smooth_plus_dm = plus_dm_s.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    smooth_minus_dm = minus_dm_s.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()

    safe_atr = atr.replace(0, np.nan)
    plus_di = 100.0 * (smooth_plus_dm / safe_atr)
    minus_di = 100.0 * (smooth_minus_dm / safe_atr)

    di_sum = (plus_di + minus_di).replace(0, np.nan)
    dx = 100.0 * ((plus_di - minus_di).abs() / di_sum)

    adx = dx.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    return adx, plus_di, minus_di


def calculate_bollinger_bands(
    series: pd.Series, period: int = 20, num_std: float = 2.0
) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series, pd.Series]:
    """
    Calculate Bollinger Bands (20, 2).
    Returns (upper, middle, lower, band_width, percent_b).
    """
    middle = calculate_sma(series, period)
    rolling_std = series.rolling(window=period, min_periods=period).std(ddof=0)
    upper = middle + (num_std * rolling_std)
    lower = middle - (num_std * rolling_std)

    safe_middle = middle.replace(0, np.nan)
    band_width = (upper - lower) / safe_middle

    band_range = (upper - lower).replace(0, np.nan)
    percent_b = (series - lower) / band_range

    return upper, middle, lower, band_width, percent_b


def calculate_supertrend(
    high: pd.Series, low: pd.Series, close: pd.Series, period: int = 10, multiplier: float = 3.0
) -> tuple[pd.Series, pd.Series]:
    """
    Calculate Supertrend (10, 3).
    Returns (supertrend_line, supertrend_direction: +1 bullish, -1 bearish).
    """
    atr = calculate_atr_wilder(high, low, close, period=period)
    hl2 = (high + low) / 2.0

    basic_upper = hl2 + (multiplier * atr)
    basic_lower = hl2 - (multiplier * atr)

    upper_band = basic_upper.copy()
    lower_band = basic_lower.copy()

    direction = pd.Series(1, index=close.index, dtype=int)
    supertrend = pd.Series(np.nan, index=close.index, dtype=float)

    for i in range(1, len(close)):
        # Final Upper Band
        if basic_upper.iloc[i] < upper_band.iloc[i - 1] or close.iloc[i - 1] > upper_band.iloc[i - 1]:
            upper_band.iloc[i] = basic_upper.iloc[i]
        else:
            upper_band.iloc[i] = upper_band.iloc[i - 1]

        # Final Lower Band
        if basic_lower.iloc[i] > lower_band.iloc[i - 1] or close.iloc[i - 1] < lower_band.iloc[i - 1]:
            lower_band.iloc[i] = basic_lower.iloc[i]
        else:
            lower_band.iloc[i] = lower_band.iloc[i - 1]

        # Trend direction
        if close.iloc[i] > upper_band.iloc[i - 1]:
            direction.iloc[i] = 1
        elif close.iloc[i] < lower_band.iloc[i - 1]:
            direction.iloc[i] = -1
        else:
            direction.iloc[i] = direction.iloc[i - 1]

        supertrend.iloc[i] = lower_band.iloc[i] if direction.iloc[i] == 1 else upper_band.iloc[i]

    return supertrend, direction


def calculate_stochastic_rsi(
    series: pd.Series, rsi_period: int = 14, stoch_period: int = 14, k_period: int = 3, d_period: int = 3
) -> tuple[pd.Series, pd.Series]:
    """Calculate Stochastic RSI (%K, %D)."""
    rsi = calculate_rsi_wilder(series, rsi_period)
    min_rsi = rsi.rolling(stoch_period).min()
    max_rsi = rsi.rolling(stoch_period).max()
    denom = (max_rsi - min_rsi).replace(0, np.nan)
    stoch = (rsi - min_rsi) / denom
    fast_k = stoch.rolling(k_period).mean() * 100.0
    fast_d = fast_k.rolling(d_period).mean()
    return fast_k, fast_d


def calculate_obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    """Calculate On-Balance Volume (OBV)."""
    direction = np.sign(close.diff()).fillna(0.0)
    return (direction * volume).cumsum()


def calculate_rolling_vwap_20(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series) -> pd.Series:
    """
    Rolling 20-day volume-weighted average price approximation.
    Explicitly labeled rolling_vwap_20 to differentiate from genuine intraday VWAP.
    """
    typical_price = (high + low + close) / 3.0
    rolling_pv = (typical_price * volume).rolling(20, min_periods=20).sum()
    rolling_vol = volume.rolling(20, min_periods=20).sum().replace(0, np.nan)
    return rolling_pv / rolling_vol


def calculate_squeeze_percentile(bb_width: pd.Series, lookback: int = 120) -> pd.Series:
    """
    Calculate previous session's Bollinger Band width percentile within preceding 120 sessions.
    Strictly uses prior observations (.shift(1)) with zero future lookahead.
    """
    # Shift by 1 so current bar is never in the distribution
    shifted = bb_width.shift(1)

    def _pct_rank(window: np.ndarray) -> float:
        if len(window) < 10 or np.isnan(window[-1]):
            return np.nan
        val = window[-1]
        valid = window[~np.isnan(window)]
        if len(valid) == 0:
            return np.nan
        return float((valid < val).sum() / len(valid) * 100.0)

    return shifted.rolling(window=lookback, min_periods=30).apply(_pct_rank, raw=True)


def calculate_all_indicators(df: pd.DataFrame, benchmark_df: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """
    Compute full suite of technical indicators on an OHLCV DataFrame.
    Guarantees no lookahead leakage on all breakout and resistance levels.
    """
    res = df.copy()
    close = res["close"]
    high = res["high"]
    low = res["low"]
    open_s = res["open"]
    volume = res["volume"]

    # Trend Indicators
    res["ema9"] = calculate_ema(close, 9)
    res["ema20"] = calculate_ema(close, 20)
    res["ema50"] = calculate_ema(close, 50)
    res["ema200"] = calculate_ema(close, 200)

    res["sma20"] = calculate_sma(close, 20)
    res["sma50"] = calculate_sma(close, 50)
    res["sma200"] = calculate_sma(close, 200)

    # ADX and Directional Indicators
    res["adx14"], res["plus_di"], res["minus_di"] = calculate_adx_wilder(high, low, close, 14)

    # Supertrend (10, 3)
    res["supertrend"], res["supertrend_dir"] = calculate_supertrend(high, low, close, 10, 3.0)

    # Momentum Indicators
    res["rsi14"] = calculate_rsi_wilder(close, 14)
    res["macd_line"], res["macd_signal"], res["macd_hist"] = calculate_macd(close, 12, 26, 9)
    res["stoch_rsi_k"], res["stoch_rsi_d"] = calculate_stochastic_rsi(close, 14, 14, 3, 3)
    res["roc10"] = ((close - close.shift(10)) / close.shift(10)) * 100.0
    res["roc20"] = ((close - close.shift(20)) / close.shift(20)) * 100.0

    # Volatility Indicators
    (
        res["bb_upper"],
        res["bb_middle"],
        res["bb_lower"],
        res["bb_width"],
        res["bb_percent_b"],
    ) = calculate_bollinger_bands(close, 20, 2.0)
    res["atr14"] = calculate_atr_wilder(high, low, close, 14)
    res["atr_pct"] = (res["atr14"] / close) * 100.0

    # Volume Indicators
    res["volume_sma20"] = calculate_sma(volume, 20)
    res["rvol20"] = volume / res["volume_sma20"].replace(0, np.nan)
    res["obv"] = calculate_obv(close, volume)
    res["rolling_vwap_20"] = calculate_rolling_vwap_20(high, low, close, volume)

    # Market Structure & Resistance (STRICTLY SHIFTED to avoid lookahead)
    res["previous_20_high"] = high.shift(1).rolling(20, min_periods=20).max()
    res["previous_55_high"] = high.shift(1).rolling(55, min_periods=55).max()
    res["previous_20_low"] = low.shift(1).rolling(20, min_periods=20).min()
    res["high_52w"] = high.shift(1).rolling(252, min_periods=100).max()
    res["low_52w"] = low.shift(1).rolling(252, min_periods=100).min()

    # Relative Distances
    res["dist_ema20_pct"] = ((close - res["ema20"]) / res["ema20"]) * 100.0
    res["dist_ema50_pct"] = ((close - res["ema50"]) / res["ema50"]) * 100.0
    res["dist_ema200_pct"] = ((close - res["ema200"]) / res["ema200"]) * 100.0
    res["gap_pct"] = ((open_s - close.shift(1)) / close.shift(1)) * 100.0

    # Day Range Location: (close - low) / (high - low)
    day_span = (high - low).replace(0, np.nan)
    res["close_location_in_range"] = (close - low) / day_span

    # Squeeze lookback percentile
    res["bb_squeeze_pct_120"] = calculate_squeeze_percentile(res["bb_width"], lookback=120)

    # 5-session price return
    res["return_5d_pct"] = ((close - close.shift(5)) / close.shift(5)) * 100.0

    # Benchmark Relative Strength
    if benchmark_df is not None and not benchmark_df.empty:
        common_idx = res.index.intersection(benchmark_df.index)
        b_close = benchmark_df.loc[common_idx, "close"]
        s_close = res.loc[common_idx, "close"]
        b_ret20 = ((b_close - b_close.shift(20)) / b_close.shift(20)).reindex(res.index)
        s_ret20 = ((s_close - s_close.shift(20)) / s_close.shift(20)).reindex(res.index)
        res["rs_nifty_20"] = s_ret20 - b_ret20
    else:
        res["rs_nifty_20"] = np.nan

    return res
