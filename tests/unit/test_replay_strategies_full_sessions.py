"""
Full-Session Multi-Asset Replay & Strategy Verification Test Suite.
Tests RELIANCE, TCS, INFY, SBIN candle-by-candle through entire trading sessions.
Verifies:
- All 4 intraday strategy agents (VWAP Momentum, ORB, EMA Pullback, Volatility Breakout).
- Zero missing attributes (quality_score, rule_quality_score, reference_close, etc.).
- Proper BUY / NO_BUY / INSUFFICIENT_DATA decisions with numerical explanations.
- Strict causal step-by-step execution, fee deductions, and 15:25 square-offs.
"""

from __future__ import annotations

import datetime
from pathlib import Path
import pytest
import numpy as np
import pandas as pd

from indigo_quant.replay.engine import ReplayEngine
from indigo_quant.strategies.intraday import (
    IntradayVWAPMomentumStrategy,
    IntradayOpeningRangeBreakoutStrategy,
    IntradayEMAPullbackStrategy,
    IntradayVolatilityBreakoutStrategy,
)


@pytest.mark.parametrize("symbol", ["RELIANCE", "TCS", "INFY", "SBIN"])
def test_full_session_replay_all_strategies(symbol: str):
    """
    Step through an entire 5-minute trading session for the symbol.
    Evaluate all 4 intraday strategies at every single candle.
    """
    engine = ReplayEngine(
        symbol=symbol,
        session_date=datetime.date(2026, 11, 9),
        interval="5m",
        mode="INTRADAY",
        selected_strategies=[
            "intraday_vwap_momentum",
            "intraday_opening_range_breakout",
            "intraday_ema_pullback",
            "intraday_volatility_breakout",
        ],
        initial_capital=100000.0,
    )
    loaded = engine.load_data()
    assert loaded is True, f"Failed to load replay session for {symbol}"
    assert engine.total_steps > 0, f"No steps loaded for {symbol}"

    # Step through every single candle
    for step in range(1, engine.total_steps + 1):
        engine.step_to(step)
        assert engine.current_step == step

        latest_candle = engine.get_latest_candle()
        assert latest_candle is not None
        assert not np.isnan(latest_candle["close"])
        assert latest_candle["close"] > 0

        # Verify decisions for all 4 strategies
        for sid in engine.enabled_strategies:
            dec = engine.latest_decisions.get(sid)
            assert dec is not None, f"Strategy {sid} did not produce a decision at step {step}"
            
            # Check decision value
            assert dec.decision in ["BUY", "NO_BUY", "INSUFFICIENT_DATA"]
            
            # Attribute check: quality_score & rule_quality_score
            assert hasattr(dec, "quality_score"), f"{sid} missing quality_score property"
            assert hasattr(dec, "rule_quality_score"), f"{sid} missing rule_quality_score attribute"
            assert isinstance(dec.quality_score, (int, float))
            assert 0.0 <= dec.quality_score <= 100.0
            
            # Attribute check: reference_close, stops, targets
            assert hasattr(dec, "reference_close")
            assert dec.reference_close == float(latest_candle["close"])
            assert hasattr(dec, "initial_stop_price")
            assert hasattr(dec, "target_price")
            assert hasattr(dec, "conditions")
            assert isinstance(dec.conditions, list)
            
            # Attribute check: rejection explanation
            if dec.decision != "BUY":
                assert dec.rejection_reason is not None and len(dec.rejection_reason) > 0
            else:
                assert dec.target_price > dec.reference_close
                assert dec.initial_stop_price < dec.reference_close

            # Condition items check
            for cond in dec.conditions:
                assert hasattr(cond, "name")
                assert hasattr(cond, "passed")
                assert isinstance(cond.passed, bool)
                assert hasattr(cond, "actual_value")
                assert hasattr(cond, "observed_value")

    # Session Completion Checks
    # At the end of session, all intraday positions must be closed
    for sid, acc in engine.broker.accounts.items():
        assert len(acc.open_positions) == 0, f"Account {sid} has unclosed positions after 15:25 square-off"
        assert acc.total_equity == round(acc.cash, 2)
        assert acc.cash > 0

        # If trades occurred, verify fee modeling
        for t in acc.closed_trades:
            assert t.shares > 0
            assert t.entry_price > 0
            assert t.exit_price > 0
            assert t.total_charges > 0  # Indian fees must have been deducted
            assert t.exit_reason in ["TARGET_HIT", "STOP_LOSS", "END_OF_SESSION_EXIT", "TIME_EXPIRATION"]
            assert hasattr(t, "mae_pct")
            assert hasattr(t, "mfe_pct")
            assert hasattr(t, "net_return_pct")
