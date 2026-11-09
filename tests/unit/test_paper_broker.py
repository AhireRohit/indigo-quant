"""
Unit tests for the Simulated Paper Broker, Fee Model, and Exit Simulator.
"""

import datetime

from indigo_quant.paper.broker import SimulatedPaperBroker
from indigo_quant.paper.fees import IndianDeliveryCostModel
from indigo_quant.paper.orders import CreatePaperOrderRequest, OrderSide, OrderType
from indigo_quant.paper.portfolio import PortfolioManager


def test_indian_delivery_cost_model_buy():
    model = IndianDeliveryCostModel()
    charges = model.calculate_charges("BUY", price=1000.0, quantity=100)

    # Gross turnover = 100,000
    assert charges.gross_turnover == 100000.0
    # STT = 0.1% = 100
    assert charges.stt == 100.0
    # Stamp duty = 0.015% = 15
    assert charges.stamp_duty == 15.0
    # Slippage = 0.1% = 100
    assert charges.slippage == 100.0
    # DP charges = 0 on BUY
    assert charges.dp_charge == 0.0
    # Total charges positive
    assert charges.total_charges > 115.0
    # Effective cash outlay = gross + slippage + charges
    assert charges.effective_cash_impact > 100200.0


def test_indian_delivery_cost_model_sell():
    model = IndianDeliveryCostModel()
    charges = model.calculate_charges("SELL", price=1000.0, quantity=100)

    # DP charge = ₹15.93 flat on delivery sell
    assert charges.dp_charge == 15.93
    # Net proceeds < gross
    assert charges.effective_cash_impact < 100000.0


def test_paper_broker_order_lifecycle_and_gap_handling(db_session):
    broker = SimulatedPaperBroker(db_session)
    pm = PortfolioManager(db_session, "trend_momentum")
    init_cash = pm.get_account().current_cash

    req = CreatePaperOrderRequest(
        account_id="trend_momentum",
        symbol="TCS",
        strategy_id="trend_momentum",
        order_side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=5,
        signal_price=3500.0,
        stop_price=3360.0,
        target_price=3850.0,
        signal_date=datetime.date(2024, 1, 1),
    )

    # 1. Submit Order
    order = broker.submit_buy_order(req)
    assert order.status == "PENDING"

    # 2. Duplicate submission idempotency
    dup_order = broker.submit_buy_order(req)
    assert dup_order.id == order.id

    # 3. Simulate Fill
    filled, reason = broker.execute_pending_buy_order(
        order=order,
        market_open_price=3510.0,
        execution_date=datetime.date(2024, 1, 2),
    )
    assert filled is True
    assert order.status == "FILLED"

    # Verify cash debit
    acc = pm.get_account()
    assert acc.current_cash < init_cash

    # 4. Test Overnight Gap-Down below stop exit
    # Stop is ~₹3373. Market opens at ₹3300 (gap below stop)
    gap_bar = {
        "symbol": "TCS",
        "open": 3300.0,  # Below stop!
        "high": 3350.0,
        "low": 3280.0,
        "close": 3320.0,
        "date": datetime.date(2024, 1, 3),
    }
    closed = broker.evaluate_open_positions_for_exits("trend_momentum", gap_bar)
    assert len(closed) == 1
    pos, exit_reason, exit_price = closed[0]
    assert exit_reason == "STOP_LOSS_GAP"
    # Fills at open price (minus slippage), NOT at the stop price!
    assert exit_price < 3310.0


def test_paper_broker_intrabar_conflict_assumes_stop_hit_first(db_session):
    broker = SimulatedPaperBroker(db_session)
    PortfolioManager(db_session, "volume_breakout")

    req = CreatePaperOrderRequest(
        account_id="volume_breakout",
        symbol="INFY",
        strategy_id="volume_breakout",
        order_side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=10,
        signal_price=1500.0,
        stop_price=1450.0,
        target_price=1650.0,
        signal_date=datetime.date(2024, 1, 1),
    )

    order = broker.submit_buy_order(req)
    broker.execute_pending_buy_order(order, 1500.0, datetime.date(2024, 1, 2))

    # Wild candle: Low <= stop (1450) AND High >= target (1650)
    conflict_bar = {
        "symbol": "INFY",
        "open": 1500.0,
        "high": 1700.0,  # Touched target!
        "low": 1400.0,   # Touched stop!
        "close": 1550.0,
        "date": datetime.date(2024, 1, 3),
    }
    closed = broker.evaluate_open_positions_for_exits("volume_breakout", conflict_bar)
    assert len(closed) == 1
    _, exit_reason, _ = closed[0]
    # Conservative priority: Assume stop was hit first
    assert exit_reason == "STOP_LOSS_INTRABAR_CONFLICT"
