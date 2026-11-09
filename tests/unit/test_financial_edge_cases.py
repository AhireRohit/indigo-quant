"""
Financial Correctness and Difficult Edge-Case Tests for Indigo Quant.
Tests overnight gaps, corporate actions, illiquidity, holidays, and portfolio isolation.
"""

import datetime

import pandas as pd

from indigo_quant.data.calendar import (
    get_next_trading_day,
    is_trading_day,
)
from indigo_quant.data.validation import check_liquidity, validate_ohlcv_dataframe
from indigo_quant.paper.broker import SimulatedPaperBroker
from indigo_quant.paper.orders import CreatePaperOrderRequest, OrderSide, OrderType
from indigo_quant.paper.portfolio import PortfolioManager


def test_calendar_weekends_and_holidays():
    # Saturday & Sunday are closed
    sat = datetime.date(2024, 1, 6)
    sun = datetime.date(2024, 1, 7)
    mon = datetime.date(2024, 1, 8)
    assert not is_trading_day(sat)
    assert not is_trading_day(sun)
    assert is_trading_day(mon)

    # Republic Day is a registered holiday
    republic_day = datetime.date(2024, 1, 26)
    assert not is_trading_day(republic_day)

    # Next trading day after Friday before a holiday
    # 2024-01-25 (Thursday) -> next day is 26th (Holiday), then 27 (Sat), 28 (Sun) -> Next is 29th (Monday)
    thu = datetime.date(2024, 1, 25)
    next_day = get_next_trading_day(thu)
    assert next_day == datetime.date(2024, 1, 29)


def test_illiquid_security_rejection():
    # Less than ₹5 crore average turnover
    dates = pd.date_range("2024-01-01", periods=25, freq="D")
    df = pd.DataFrame(index=dates)
    df["close"] = [100.0] * 25
    # Volume 1000 shares * 100 = ₹1,00,000 << ₹5,00,00,000
    df["volume"] = [1000.0] * 25
    df["turnover"] = df["close"] * df["volume"]

    is_liquid, reason = check_liquidity(df, min_price=75.0, min_avg_turnover=50000000.0)
    assert is_liquid is False
    assert "below ₹50,000,000" in reason


def test_insufficient_history_rejection():
    dates = pd.date_range("2024-01-01", periods=50, freq="D")
    df = pd.DataFrame({
        "open": [100.0] * 50,
        "high": [102.0] * 50,
        "low": [99.0] * 50,
        "close": [101.0] * 50,
        "volume": [100000.0] * 50,
    }, index=dates)

    is_valid, errors = validate_ohlcv_dataframe(df, "SHORT_HISTORY_STOCK", min_required_bars=260, check_freshness=False)
    assert is_valid is False
    assert any("Insufficient historical bars" in e for e in errors)


def test_isolated_portfolios_multiple_agents_buying_same_ticker(db_session):
    """
    Ensure separate portfolios can each independently hold the same ticker
    without collision or balance crosstalk.
    """
    broker = SimulatedPaperBroker(db_session)

    # Strategy A buys RELIANCE
    req_a = CreatePaperOrderRequest(
        account_id="trend_momentum",
        symbol="RELIANCE",
        strategy_id="trend_momentum",
        order_side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=5,
        signal_price=2500.0,
        stop_price=2400.0,
        target_price=2750.0,
        signal_date=datetime.date(2024, 1, 1),
    )
    ord_a = broker.submit_buy_order(req_a)
    broker.execute_pending_buy_order(ord_a, 2500.0, datetime.date(2024, 1, 2))

    # Strategy B also independently buys RELIANCE
    req_b = CreatePaperOrderRequest(
        account_id="volume_breakout",
        symbol="RELIANCE",
        strategy_id="volume_breakout",
        order_side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=5,
        signal_price=2500.0,
        stop_price=2400.0,
        target_price=2750.0,
        signal_date=datetime.date(2024, 1, 1),
    )
    ord_b = broker.submit_buy_order(req_b)
    broker.execute_pending_buy_order(ord_b, 2500.0, datetime.date(2024, 1, 2))

    pm_a = PortfolioManager(db_session, "trend_momentum")
    pm_b = PortfolioManager(db_session, "volume_breakout")

    pos_a = pm_a.get_open_positions()
    pos_b = pm_b.get_open_positions()

    assert len(pos_a) == 1
    assert len(pos_b) == 1
    assert pos_a[0].account_id == "trend_momentum"
    assert pos_b[0].account_id == "volume_breakout"
    assert pos_a[0].id != pos_b[0].id


def test_gap_above_target_exit(db_session):
    broker = SimulatedPaperBroker(db_session)
    PortfolioManager(db_session, "trend_momentum")

    req = CreatePaperOrderRequest(
        account_id="trend_momentum",
        symbol="TITAN",
        strategy_id="trend_momentum",
        order_side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=5,
        signal_price=3000.0,
        stop_price=2880.0,
        target_price=3300.0,
        signal_date=datetime.date(2024, 1, 1),
    )
    ord_titan = broker.submit_buy_order(req)
    broker.execute_pending_buy_order(ord_titan, 3000.0, datetime.date(2024, 1, 2))

    # Bar gaps up massively above target (+15%)
    gap_up_bar = {
        "symbol": "TITAN",
        "open": 3450.0,  # Gapped way above 3300 target!
        "high": 3500.0,
        "low": 3420.0,
        "close": 3480.0,
        "date": datetime.date(2024, 1, 5),
    }

    closed = broker.evaluate_open_positions_for_exits("trend_momentum", gap_up_bar)
    assert len(closed) == 1
    pos, reason, exit_price = closed[0]
    assert reason.startswith("TARGET_HIT")
    assert pos.target_achieved is True
    assert pos.realized_pnl_net > 0.0
