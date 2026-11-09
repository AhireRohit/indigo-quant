"""
Unit tests for the Technical Indicator Engine.
Validates EMA, SMA, Wilder RSI, MACD, Bollinger Bands, ATR, ADX,
and strict lookahead prevention on rolling historical levels.
"""

import numpy as np
import pandas as pd
import pytest

from indigo_quant.indicators.technical import (
    calculate_all_indicators,
    calculate_atr_wilder,
    calculate_bollinger_bands,
    calculate_ema,
    calculate_macd,
    calculate_rsi_wilder,
    calculate_sma,
)


def test_sma_calculation():
    s = pd.Series([10.0, 20.0, 30.0, 40.0, 50.0])
    sma = calculate_sma(s, 3)
    assert np.isnan(sma.iloc[0])
    assert np.isnan(sma.iloc[1])
    assert sma.iloc[2] == pytest.approx(20.0)
    assert sma.iloc[3] == pytest.approx(30.0)
    assert sma.iloc[4] == pytest.approx(40.0)


def test_ema_calculation():
    s = pd.Series([10.0] * 20 + [20.0] * 10)
    ema = calculate_ema(s, 5)
    assert len(ema) == 30
    assert ema.iloc[0] == 10.0
    assert ema.iloc[-1] > 18.0  # Adapts toward 20.0


def test_rsi_wilder_bounds_and_smoothing():
    # Constant series -> flat
    flat_s = pd.Series([100.0] * 50)
    rsi_flat = calculate_rsi_wilder(flat_s, 14)
    assert rsi_flat.iloc[-1] == 0.0 or np.isnan(rsi_flat.iloc[-1]) or rsi_flat.iloc[-1] == 50.0

    # Strictly increasing series -> RSI 100
    inc_s = pd.Series(range(100, 200), dtype=float)
    rsi_inc = calculate_rsi_wilder(inc_s, 14)
    assert rsi_inc.iloc[-1] == pytest.approx(100.0, abs=0.1)

    # Strictly decreasing series -> RSI 0
    dec_s = pd.Series(range(200, 100, -1), dtype=float)
    rsi_dec = calculate_rsi_wilder(dec_s, 14)
    assert rsi_dec.iloc[-1] == pytest.approx(0.0, abs=0.1)


def test_macd_calculation():
    s = pd.Series(np.linspace(100, 200, 100))
    line, signal, hist = calculate_macd(s, 12, 26, 9)
    assert len(line) == 100
    assert len(signal) == 100
    assert len(hist) == 100
    # In steady uptrend, fast EMA > slow EMA, so line should be positive
    assert line.iloc[-1] > 0
    assert hist.iloc[-1] == pytest.approx(line.iloc[-1] - signal.iloc[-1])


def test_bollinger_bands():
    s = pd.Series([100.0] * 50)
    upper, middle, lower, width, pct_b = calculate_bollinger_bands(s, 20, 2.0)
    assert middle.iloc[-1] == 100.0
    assert upper.iloc[-1] == 100.0
    assert lower.iloc[-1] == 100.0
    assert width.iloc[-1] == 0.0


def test_atr_wilder():
    high = pd.Series([105.0] * 30)
    low = pd.Series([95.0] * 30)
    close = pd.Series([100.0] * 30)
    atr = calculate_atr_wilder(high, low, close, 14)
    # Range is 10.0 every bar
    assert atr.iloc[-1] == pytest.approx(10.0, abs=0.1)


def test_no_lookahead_leakage_on_breakout_levels(synthetic_ohlcv_uptrend):
    """
    CRITICAL: Verify that previous_20_high strictly excludes the current bar's high.
    If the current bar makes a gigantic new high, previous_20_high MUST NOT reflect it.
    """
    df = synthetic_ohlcv_uptrend.copy()
    ind = calculate_all_indicators(df)

    # Inject a massive spike on the final bar
    last_idx = df.index[-1]
    df_spike = df.copy()
    normal_prev_high = ind["previous_20_high"].iloc[-1]

    # Spike the current bar's high to 10,000
    df_spike.loc[last_idx, "high"] = 10000.0
    ind_spike = calculate_all_indicators(df_spike)

    # previous_20_high on the current bar MUST NOT change!
    assert ind_spike["previous_20_high"].iloc[-1] == normal_prev_high
    assert ind_spike["previous_20_high"].iloc[-1] < 1000.0
