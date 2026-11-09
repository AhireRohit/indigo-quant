"""
Unit tests for Market Regime and Risk Engine.
Validates capital constraints, stop limits, and benchmark trend filters.
"""

import numpy as np
import pandas as pd
import pytest

from indigo_quant.engine.market_regime import MarketRegimeEngine, MarketRegimeStatus
from indigo_quant.engine.risk import RiskEngine


def test_market_regime_bullish():
    # 250 bars with close > EMA200 and EMA50 > EMA200
    closes = np.linspace(10000, 25000, 250)
    df = pd.DataFrame({"close": closes}, index=pd.date_range("2023-01-01", periods=250, freq="D"))

    engine = MarketRegimeEngine(min_required_sessions=200)
    status, details = engine.evaluate(df)
    assert status == MarketRegimeStatus.BULLISH
    assert details["allow_new_entries"] is True


def test_market_regime_defensive_when_close_below_ema200():
    # Uptrend then crash
    closes = list(np.linspace(10000, 25000, 220)) + list(np.linspace(25000, 12000, 30))
    df = pd.DataFrame({"close": closes}, index=pd.date_range("2023-01-01", periods=250, freq="D"))

    engine = MarketRegimeEngine(min_required_sessions=200)
    status, details = engine.evaluate(df)
    assert status == MarketRegimeStatus.DEFENSIVE
    assert details["allow_new_entries"] is False


def test_market_regime_unknown_on_missing_or_short_history():
    engine = MarketRegimeEngine(min_required_sessions=200)
    # Empty
    s1, _ = engine.evaluate(pd.DataFrame())
    assert s1 == MarketRegimeStatus.UNKNOWN

    # Short history
    df_short = pd.DataFrame({"close": [100.0] * 50}, index=pd.date_range("2024-01-01", periods=50, freq="D"))
    s2, _ = engine.evaluate(df_short)
    assert s2 == MarketRegimeStatus.UNKNOWN


def test_risk_engine_sizing_and_constraints():
    risk = RiskEngine(
        max_risk_per_trade_pct=0.005,      # 0.5% of 100k = ₹500
        max_position_allocation_pct=0.20,  # 20% of 100k = ₹20,000
        max_open_positions=5,
        max_portfolio_exposure_pct=0.75,
    )

    # Candidate: price = ₹100, ATR = ₹2.0
    # Stop distance: max(0.02, 1.5 * 2.0 / 100) = max(0.02, 0.03) = 0.03 (3.0% stop)
    # Stop price = ₹97.0
    # Per share risk = ₹3.0
    # Risk qty = floor(500 / 3) = 166 shares
    # Alloc qty = floor(20000 / 100) = 200 shares
    # Sizing = min(166, 200, cash_qty) = 166
    assessment = risk.evaluate_candidate(
        entry_price=100.0,
        atr14=2.0,
        portfolio_equity=100000.0,
        available_cash=50000.0,
        current_open_positions_count=0,
        current_invested_capital=0.0,
    )

    assert assessment.is_approved is True
    assert assessment.stop_distance_pct == 0.03
    assert assessment.target_price == 110.0  # +10%
    assert assessment.reward_to_risk_ratio == pytest.approx(10.0 / 3.0, abs=0.05)
    assert assessment.recommended_quantity == 166


def test_risk_engine_rejects_volatile_stocks():
    risk = RiskEngine(max_stop_distance_pct=0.05)

    # ATR = ₹6.0 on ₹100 stock -> 1.5 * 6 / 100 = 0.09 (9% stop > 5% max)
    assessment = risk.evaluate_candidate(
        entry_price=100.0,
        atr14=6.0,
        portfolio_equity=100000.0,
        available_cash=50000.0,
        current_open_positions_count=0,
        current_invested_capital=0.0,
    )

    assert assessment.is_approved is False
    assert "exceeds maximum allowable risk ceiling" in assessment.rejection_reason


def test_risk_engine_rejects_when_max_positions_reached():
    risk = RiskEngine(max_open_positions=5)
    assessment = risk.evaluate_candidate(
        entry_price=100.0,
        atr14=2.0,
        portfolio_equity=100000.0,
        available_cash=50000.0,
        current_open_positions_count=5,  # 5 already open
        current_invested_capital=80000.0,
    )

    assert assessment.is_approved is False
    assert "Maximum simultaneous limit" in assessment.rejection_reason
