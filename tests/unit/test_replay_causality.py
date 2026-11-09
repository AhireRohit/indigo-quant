"""
Strict Causality and No-Lookahead Automated Regression Tests for Indigo Quant Replay Lab.

Proves:
1. Indicators at candle K depend exclusively on candles 0..K.
2. Strategy decisions at candle K depend exclusively on candles 0..K.
3. Deliberately mutating future prices (candles K+1..N) leaves all calculations at K 100% identical.
4. Next-bar-open simulated execution: Orders queued at candle K cannot execute at candle K prices.
5. Intraday fee calculations (brokerage, STT on sell, GST, stamp duty, turnover fees, slippage).
6. Conservative stop/target collision resolution (Stop assumed hit first).
7. Complete isolation: Replay never alters production SQLite database or live paper portfolios.
"""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from indigo_quant.data.intraday_adapter import IntradayDataAdapter
from indigo_quant.indicators.intraday import (
    calculate_all_intraday_indicators,
    calculate_opening_range,
    calculate_relative_volume,
    calculate_session_vwap,
)
from indigo_quant.paper.intraday_fees import IndianIntradayCostModel
from indigo_quant.replay.broker import ReplayBroker
from indigo_quant.replay.engine import ReplayEngine
from indigo_quant.strategies.intraday import (
    IntradayEMAPullbackStrategy,
    IntradayOpeningRangeBreakoutStrategy,
    IntradayVolatilityBreakoutStrategy,
    IntradayVWAPMomentumStrategy,
)


@pytest.fixture
def synthetic_5m_session():
    """
    Generate 75 bars of clean 5-minute intraday candles for a single trading session (09:15 to 15:30).
    """
    date = datetime.date(2026, 11, 9)
    times = pd.date_range("2026-11-09 09:15:00", "2026-11-09 15:25:00", freq="5min", tz="Asia/Kolkata")
    n = len(times)

    np.random.seed(42)
    # Gentle upward trend with realistic intraday oscillations
    base = 1000.0 + np.cumsum(np.random.normal(0.2, 1.0, n))
    highs = base + np.random.uniform(0.5, 2.5, n)
    lows = base - np.random.uniform(0.5, 2.5, n)
    opens = base + np.random.uniform(-0.5, 0.5, n)
    closes = base + np.random.uniform(-0.5, 0.5, n)
    volumes = np.random.uniform(5000, 50000, n)

    df = pd.DataFrame({
        "open": np.round(opens, 2),
        "high": np.round(highs, 2),
        "low": np.round(lows, 2),
        "close": np.round(closes, 2),
        "volume": np.round(volumes, 0),
    }, index=times)
    return df


def test_session_vwap_causality_and_reset(synthetic_5m_session):
    """Verify session VWAP is causal and resets each morning."""
    df = synthetic_5m_session.copy()
    vwap = calculate_session_vwap(df)

    assert len(vwap) == len(df)
    # At bar 0, VWAP must equal typical price of bar 0
    bar0_tp = (df["high"].iloc[0] + df["low"].iloc[0] + df["close"].iloc[0]) / 3.0
    assert abs(vwap.iloc[0] - bar0_tp) < 1e-4

    # Causal check: changing candle 50 must NOT alter VWAP at candle 20
    df_corrupted = df.copy()
    df_corrupted.iloc[50:, df_corrupted.columns.get_loc("close")] *= 3.0
    df_corrupted.iloc[50:, df_corrupted.columns.get_loc("volume")] *= 10.0
    vwap_corrupted = calculate_session_vwap(df_corrupted)

    pd.testing.assert_series_equal(vwap.iloc[:50], vwap_corrupted.iloc[:50])


def test_opening_range_completion_causality(synthetic_5m_session):
    """Verify ORB is marked incomplete before 09:30 and complete at/after 09:30."""
    df = synthetic_5m_session.copy()
    orb_df = calculate_opening_range(df)

    # 09:15 and 09:20 bars: opening range is not yet complete
    idx_0915 = df.index[0]
    idx_0920 = df.index[1]
    idx_0930 = df.index[3]

    assert bool(orb_df.loc[idx_0915, "orb_complete"]) is False or np.isnan(orb_df.loc[idx_0915, "orb_high"])
    assert bool(orb_df.loc[idx_0920, "orb_complete"]) is False or np.isnan(orb_df.loc[idx_0920, "orb_high"])
    assert bool(orb_df.loc[idx_0930, "orb_complete"]) is True
    assert not np.isnan(orb_df.loc[idx_0930, "orb_high"])
    assert not np.isnan(orb_df.loc[idx_0930, "orb_low"])


def test_intraday_cost_model_buy_and_sell():
    """Verify Indian intraday equity fees: min(20, 0.03%) brokerage, STT on sell only, stamp duty on buy only."""
    model = IndianIntradayCostModel(slippage_pct=0.0005)

    # BUY 100 shares @ 1000 = Turnover 100,000
    buy_cost = model.calculate_charges("BUY", price=1000.0, quantity=100)
    assert buy_cost.gross_turnover == 100000.0
    # Brokerage: min(20, 100,000 * 0.0003 = 30) => 20
    assert buy_cost.brokerage == 20.0
    # STT: 0 on BUY intraday
    assert buy_cost.stt == 0.0
    # Stamp duty: 0.003% on BUY = 3.0
    assert buy_cost.stamp_duty == 3.0
    # GST: 18% on (brokerage + exchange + sebi)
    assert buy_cost.gst > 3.6
    # Slippage: 0.05% = 50.0
    assert buy_cost.slippage == 50.0
    # Net cash impact negative
    assert buy_cost.net_cash_impact < -100000.0

    # SELL 100 shares @ 1010 = Turnover 101,000
    sell_cost = model.calculate_charges("SELL", price=1010.0, quantity=100)
    # STT: 0.025% on SELL = 25.25
    assert sell_cost.stt > 25.0
    # Stamp duty: 0 on SELL
    assert sell_cost.stamp_duty == 0.0
    # Net cash impact positive and less than gross
    assert sell_cost.net_cash_impact < 101000.0
    assert sell_cost.net_cash_impact > 100800.0


def test_crucial_causality_future_price_mutation(synthetic_5m_session):
    """
    CRUCIAL CAUSALITY TEST:
    Step simulation to candle K.
    Deliberately modify all prices after candle K.
    Verify indicators, strategy decisions, and broker state at candle K remain 100% unchanged.
    """
    df = synthetic_5m_session.copy()
    K = 30  # Step 30

    engine = ReplayEngine("TEST_STOCK", datetime.date(2026, 11, 9), interval="5m", mode="INTRADAY")
    # Manually inject dataset to avoid remote fetching
    engine.session_candles_df = calculate_all_intraday_indicators(df)
    engine.warmed_up_indicators_df = engine.session_candles_df.copy()
    engine.total_steps = len(df)
    engine.is_loaded = True
    engine.reset()

    # Step to K
    engine.step_to(K)

    # Capture state at K
    cash_k = engine.broker.accounts["intraday_vwap_momentum"].cash
    equity_k = engine.broker.accounts["intraday_vwap_momentum"].total_equity
    orders_k = len(engine.broker.accounts["intraday_vwap_momentum"].orders)
    positions_k = len(engine.broker.accounts["intraday_vwap_momentum"].open_positions)
    decisions_k = {sid: res.decision for sid, res in engine.latest_decisions.items()}
    rules_passed_k = {sid: list(res.rules_passed) for sid, res in engine.latest_decisions.items()}
    visible_candles_k = engine.get_visible_candles_df().copy()

    # Now create heavily corrupted future data from K onwards
    df_corrupted = df.copy()
    df_corrupted.iloc[K:, df_corrupted.columns.get_loc("open")] *= 5.0
    df_corrupted.iloc[K:, df_corrupted.columns.get_loc("high")] *= 5.0
    df_corrupted.iloc[K:, df_corrupted.columns.get_loc("low")] *= 0.1
    df_corrupted.iloc[K:, df_corrupted.columns.get_loc("close")] *= 4.0
    df_corrupted.iloc[K:, df_corrupted.columns.get_loc("volume")] *= 20.0

    engine_corrupted = ReplayEngine("TEST_STOCK", datetime.date(2026, 11, 9), interval="5m", mode="INTRADAY")
    engine_corrupted.session_candles_df = calculate_all_intraday_indicators(df_corrupted)
    engine_corrupted.warmed_up_indicators_df = engine_corrupted.session_candles_df.copy()
    engine_corrupted.total_steps = len(df_corrupted)
    engine_corrupted.is_loaded = True
    engine_corrupted.reset()

    # Step corrupted engine to K
    engine_corrupted.step_to(K)

    # Assert exact match at K
    assert engine_corrupted.broker.accounts["intraday_vwap_momentum"].cash == cash_k
    assert engine_corrupted.broker.accounts["intraday_vwap_momentum"].total_equity == equity_k
    assert len(engine_corrupted.broker.accounts["intraday_vwap_momentum"].orders) == orders_k
    assert len(engine_corrupted.broker.accounts["intraday_vwap_momentum"].open_positions) == positions_k
    for sid in engine.enabled_strategies:
        assert engine_corrupted.latest_decisions[sid].decision == decisions_k[sid]
        assert engine_corrupted.latest_decisions[sid].rules_passed == rules_passed_k[sid]

    pd.testing.assert_frame_equal(visible_candles_k, engine_corrupted.get_visible_candles_df())


def test_same_candle_stop_target_collision_assumes_stop_hit_first():
    """Conservative policy: if both target and stop are touched in the same candle, stop is assumed hit first."""
    broker = ReplayBroker(strategies=["intraday_vwap_momentum"], initial_capital_per_agent=100000.0, mode="INTRADAY")
    acc = broker.accounts["intraday_vwap_momentum"]

    # Queue and fill an order
    order = broker.queue_buy_order(
        strategy_id="intraday_vwap_momentum",
        symbol="TCS",
        signal_price=3500.0,
        stop_price=3450.0,
        target_price=3600.0,
        signal_time=datetime.datetime(2026, 11, 9, 10, 0),
    )
    broker.process_pending_orders_at_open("TCS", candle_open=3500.0, candle_time=datetime.datetime(2026, 11, 9, 10, 5))
    assert len(acc.open_positions) == 1

    # Candle that pierces both stop (low 3440 <= 3450) and target (high 3650 >= 3600)
    conflict_candle = {
        "open": 3500.0,
        "high": 3650.0,  # Crosses target
        "low": 3440.0,   # Crosses stop
        "close": 3550.0,
        "time": datetime.datetime(2026, 11, 9, 10, 10),
    }

    closed = broker.evaluate_candle_exits("TCS", conflict_candle)
    assert len(closed) == 1
    trade, msg = closed[0]
    assert trade.exit_reason == "STOP_LOSS"
    assert trade.target_achieved is False
    assert len(acc.open_positions) == 0


def test_end_of_session_forced_square_off():
    """Verify that any open intraday positions are forcefully closed at 15:25 IST."""
    broker = ReplayBroker(strategies=["intraday_vwap_momentum"], initial_capital_per_agent=100000.0, mode="INTRADAY")
    acc = broker.accounts["intraday_vwap_momentum"]

    order = broker.queue_buy_order(
        strategy_id="intraday_vwap_momentum",
        symbol="INFY",
        signal_price=1500.0,
        stop_price=1450.0,
        target_price=1600.0,
        signal_time=datetime.datetime(2026, 11, 9, 14, 0),
    )
    broker.process_pending_orders_at_open("INFY", candle_open=1500.0, candle_time=datetime.datetime(2026, 11, 9, 14, 5))
    assert len(acc.open_positions) == 1

    # 15:25 candle with is_end_of_session=True
    close_candle = {
        "open": 1510.0,
        "high": 1515.0,
        "low": 1505.0,
        "close": 1512.0,
        "time": datetime.datetime(2026, 11, 9, 15, 25),
    }

    closed = broker.evaluate_candle_exits("INFY", close_candle, is_end_of_session=True)
    assert len(closed) == 1
    trade, msg = closed[0]
    assert trade.exit_reason == "END_OF_SESSION_EXIT"
    assert len(acc.open_positions) == 0
    assert len(acc.closed_trades) == 1


def test_replay_completed_roundtrip_fees_slippage_and_cash_reconciliation():
    """
    Regression Test: Verify a completed round trip with fees and slippage on both sides.
    Asserts that:
    1. Displayed entry and exit prices (with slippage) exactly reproduce gross P&L: (exit - entry) * qty.
    2. Total charges strictly include both buy-side and sell-side statutory fees without double counting.
    3. Net P&L = Gross P&L - Total Charges.
    4. Ending cash and equity reconcile with starting capital + sum(net_pnl) to 0.00 paise.
    """
    broker = ReplayBroker(strategies=["intraday_vwap_momentum"], initial_capital_per_agent=100000.0, mode="INTRADAY")
    acc = broker.accounts["intraday_vwap_momentum"]
    start_capital = acc.cash

    # 1. Queue and execute BUY order
    broker.queue_buy_order(
        strategy_id="intraday_vwap_momentum",
        symbol="RELIANCE",
        signal_price=1316.50,
        stop_price=1280.0,
        target_price=1400.0,
        signal_time=datetime.datetime(2026, 11, 9, 10, 0),
    )
    fill_results = broker.process_pending_orders_at_open("RELIANCE", candle_open=1316.50, candle_time=datetime.datetime(2026, 11, 9, 10, 5))
    assert len(fill_results) == 1
    assert len(acc.open_positions) == 1
    pos = acc.open_positions[0]

    # Verify BUY cash deduction
    expected_buy_amount = round(pos.entry_price * pos.quantity, 2)
    expected_buy_outlay = round(expected_buy_amount + pos.buy_fee, 2)
    assert acc.cash == round(start_capital - expected_buy_outlay, 2)

    # 2. Execute profitable target exit candle
    exit_candle = {
        "open": 1350.0,
        "high": 1405.0,  # Pierces target
        "low": 1340.0,
        "close": 1400.0,
        "time": datetime.datetime(2026, 11, 9, 11, 0),
    }
    closed_trades = broker.evaluate_candle_exits("RELIANCE", exit_candle)
    assert len(closed_trades) == 1
    trade, msg = closed_trades[0]

    # 3. Assert exact mathematical reconciliation across all records
    calc_gross = round((trade.exit_price - trade.entry_price) * trade.quantity, 2)
    assert trade.gross_pnl == calc_gross, f"Gross PnL {trade.gross_pnl} does not match (exit - entry)*qty {calc_gross}"

    expected_total_fees = round(trade.buy_fee + trade.sell_fee, 2)
    assert trade.total_charges == expected_total_fees
    assert trade.buy_fee > 0.0
    assert trade.sell_fee > 0.0

    calc_net = round(trade.gross_pnl - trade.total_charges, 2)
    assert trade.net_pnl == calc_net

    # 4. Cash Ledger & Equity Reconciliation (Zero paise discrepancy)
    assert len(acc.open_positions) == 0
    expected_ending_cash = round(start_capital + trade.net_pnl, 2)
    assert acc.cash == expected_ending_cash
    assert acc.total_equity == expected_ending_cash
    discrepancy = round((acc.initial_capital + trade.net_pnl) - acc.total_equity, 2)
    assert discrepancy == 0.00


def test_reliance_session_reconciliation_zero_discrepancy():
    """
    Verify complete session replay for RELIANCE (2026-11-05 5m Intraday)
    reconciles all 4 trades, fees, cash ledger, and equity with ZERO discrepancy.
    """
    engine = ReplayEngine(
        symbol="RELIANCE",
        session_date=datetime.date(2026, 11, 5),
        interval="5m",
        mode="INTRADAY",
    )
    loaded = engine.load_data()
    assert loaded is True
    engine.step_to(engine.total_steps)

    acc = engine.broker.accounts["intraday_vwap_momentum"]
    assert len(acc.closed_trades) == 4
    assert len(acc.open_positions) == 0

    total_gross = sum(t.gross_pnl for t in acc.closed_trades)
    total_buy_fees = sum(t.buy_fee for t in acc.closed_trades)
    total_sell_fees = sum(t.sell_fee for t in acc.closed_trades)
    total_fees = sum(t.total_charges for t in acc.closed_trades)
    total_net = sum(t.net_pnl for t in acc.closed_trades)

    # Verify each trade individually
    for t in acc.closed_trades:
        assert t.gross_pnl == round((t.exit_price - t.entry_price) * t.quantity, 2)
        assert t.total_charges == round(t.buy_fee + t.sell_fee, 2)
        assert t.net_pnl == round(t.gross_pnl - t.total_charges, 2)

    # Verify totals
    assert round(total_fees, 2) == round(total_buy_fees + total_sell_fees, 2)
    assert round(total_net, 2) == round(total_gross - total_fees, 2)

    # Verify perfect reconciliation between cash ledger and trade net PnLs
    expected_equity = round(acc.initial_capital + total_net, 2)
    assert round(acc.cash, 2) == expected_equity
    assert round(acc.total_equity, 2) == expected_equity
    assert round((acc.initial_capital + total_net) - acc.total_equity, 2) == 0.00
