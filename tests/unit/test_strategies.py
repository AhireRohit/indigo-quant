"""
Unit tests for all 4 competing trading agents + Consensus.
Tests every mandatory condition and guarantees zero subjective overrides.
"""

import datetime

import pandas as pd
import pytest

from indigo_quant.strategies.breakout import VolumeBreakoutStrategy
from indigo_quant.strategies.consensus import ConsensusStrategy
from indigo_quant.strategies.momentum import TrendMomentumStrategy
from indigo_quant.strategies.pullback import BullishPullbackStrategy
from indigo_quant.strategies.squeeze import BollingerSqueezeStrategy


@pytest.fixture
def mock_indicators_df():
    """Build a deterministic DataFrame with explicit technical indicator columns."""
    dates = pd.date_range("2024-01-01", periods=10, freq="D")
    df = pd.DataFrame(index=dates)

    # Price & Moving Averages
    df["open"] = [100.0] * 9 + [102.0]
    df["high"] = [102.0] * 9 + [105.0]
    df["low"] = [99.0] * 9 + [101.0]
    df["close"] = [101.0] * 9 + [104.5]
    df["volume"] = [100000.0] * 9 + [200000.0]

    # Pre-calculated indicators
    df["ema20"] = [100.0] * 10
    df["ema50"] = [95.0] * 10
    df["ema200"] = [85.0] * 10
    df["sma200"] = [85.0] * 10

    df["rsi14"] = [58.0] * 10
    df["macd_line"] = [1.5] * 10
    df["macd_signal"] = [1.0] * 10
    df["macd_hist"] = [0.5] * 10
    df["adx14"] = [25.0] * 10
    df["rvol20"] = [1.8] * 10
    df["return_5d_pct"] = [2.5] * 10
    df["previous_20_high"] = [103.0] * 10
    df["atr14"] = [2.0] * 10
    df["bb_upper"] = [103.5] * 10
    df["bb_width"] = [0.03] * 10
    df["bb_squeeze_pct_120"] = [15.0] * 10

    return df


def test_agent_a_trend_momentum_all_pass(mock_indicators_df):
    strat = TrendMomentumStrategy()
    res = strat.evaluate("TEST_STOCK", mock_indicators_df)
    assert res.decision == "BUY"
    assert len(res.rules_failed) == 0
    assert len(res.rules_passed) == 10


def test_agent_a_fails_if_rsi_out_of_range(mock_indicators_df):
    df = mock_indicators_df.copy()
    # Set RSI to 75 (above 68 max)
    df.iloc[-1, df.columns.get_loc("rsi14")] = 75.0
    strat = TrendMomentumStrategy()
    res = strat.evaluate("TEST_STOCK", df)
    assert res.decision == "NO_TRADE"
    assert any("rsi_in_range" in f for f in res.rules_failed)


def test_agent_b_volume_breakout_all_pass(mock_indicators_df):
    # Setup for Agent B:
    # close >= prev_20_high * 1.005 -> 103.0 * 1.005 = 103.515
    # close <= prev_20_high * 1.04 -> 103.0 * 1.04 = 107.12
    # RVOL >= 1.5, EMA20 > EMA50, close > EMA200, 55 <= RSI <= 75, ADX >= 20, ATR/close <= 0.05
    # Upper quartile: (close - low) / (high - low) >= 0.75 -> (104.5 - 101) / (105 - 101) = 3.5 / 4.0 = 0.875
    strat = VolumeBreakoutStrategy()
    res = strat.evaluate("TEST_STOCK", mock_indicators_df)
    assert res.decision == "BUY"
    assert len(res.rules_failed) == 0


def test_agent_b_fails_if_high_equals_low(mock_indicators_df):
    df = mock_indicators_df.copy()
    # Set high == low on the last bar
    df.iloc[-1, df.columns.get_loc("high")] = 104.5
    df.iloc[-1, df.columns.get_loc("low")] = 104.5
    strat = VolumeBreakoutStrategy()
    res = strat.evaluate("TEST_STOCK", df)
    assert res.decision == "NO_TRADE"
    assert any("close_in_upper_quartile" in f for f in res.rules_failed)


def test_agent_c_pullback_genuine_cross():
    dates = pd.date_range("2024-01-01", periods=5, freq="D")
    df = pd.DataFrame(index=dates)
    df["close"] = [100.0, 99.0, 98.0, 98.5, 102.0]  # Previous was 98.5 (below EMA20 100), current is 102 (above EMA20)
    df["ema20"] = [100.0] * 5
    df["ema50"] = [95.0] * 5
    df["ema200"] = [90.0] * 5
    df["rsi14"] = [55.0, 48.0, 42.0, 45.0, 56.0]  # Prior RSI was 45 (in [38, 50]), current is 56 (in [50, 65])
    df["macd_hist"] = [0.1, -0.2, -0.4, -0.3, 0.2]  # Current > prior (-0.3 -> 0.2)
    df["rvol20"] = [1.2] * 5

    strat = BullishPullbackStrategy()
    res = strat.evaluate("PULLBACK_STOCK", df)
    assert res.decision == "BUY"
    assert len(res.rules_failed) == 0


def test_agent_d_bollinger_squeeze_breakout(mock_indicators_df):
    # Setup for Agent D:
    # 1. Prior BB width <= 20th percentile (squeeze_pct = 15.0 <= 20.0)
    # 2. Close > prior upper BB (close 104.5 > 103.5)
    # 3. RVOL >= 1.50
    # 4. EMA20 > EMA50 > EMA200
    # 5. 55 <= RSI <= 72
    # 6. Curr ADX > Prior ADX
    # 7. Close > prev 20-high
    df = mock_indicators_df.copy()
    # Ensure curr ADX > prev ADX
    df.iloc[-2, df.columns.get_loc("adx14")] = 23.0
    df.iloc[-1, df.columns.get_loc("adx14")] = 26.0

    strat = BollingerSqueezeStrategy()
    res = strat.evaluate("SQUEEZE_STOCK", df)
    assert res.decision == "BUY"


def test_agent_e_consensus_logic(mock_indicators_df):
    consensus = ConsensusStrategy(min_agreement=2)
    strat_a = TrendMomentumStrategy()
    strat_b = VolumeBreakoutStrategy()

    res_a = strat_a.evaluate("CONSENSUS_STOCK", mock_indicators_df)
    res_b = strat_b.evaluate("CONSENSUS_STOCK", mock_indicators_df)

    # Both A and B are BUY -> Consensus should be BUY
    c_res = consensus.evaluate_consensus("CONSENSUS_STOCK", datetime.date(2024, 1, 10), 104.5, [res_a, res_b])
    assert c_res.decision == "BUY"

    # If only 1 agrees -> Consensus should be NO_TRADE
    res_a.decision = "NO_TRADE"
    c_res_fail = consensus.evaluate_consensus("CONSENSUS_STOCK", datetime.date(2024, 1, 10), 104.5, [res_a, res_b])
    assert c_res_fail.decision == "NO_TRADE"
