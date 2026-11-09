"""
Integration tests for Indigo Quant end-to-end pipeline.
"""

import datetime

from indigo_quant.db.repository import Repository
from indigo_quant.engine.decision import DecisionEngine
from indigo_quant.engine.execution import ExecutionEngine


def test_full_decision_and_execution_pipeline(db_session, synthetic_ohlcv_uptrend):
    repo = Repository(db_session)
    decision = DecisionEngine(db_session)
    execution = ExecutionEngine(db_session)

    # Synthetic NIFTY 50 in bull trend
    nifty_df = synthetic_ohlcv_uptrend.copy()
    stock_df = synthetic_ohlcv_uptrend.copy()
    stock_df.attrs["provider"] = "test_fixture"

    # 1. Run Decision Scan
    scan_result = decision.run_daily_scan(
        symbols_data={"SYNTHETIC_STOCK": stock_df},
        nifty_df=nifty_df,
    )

    assert "regime" in scan_result
    assert "signals" in scan_result

    # 2. Convert to Orders
    orders = execution.queue_orders_from_signals(scan_result["signals"])

    # 3. Process fills
    quotes = {"SYNTHETIC_STOCK": float(stock_df["close"].iloc[-1])}
    execution.process_pending_fills(quotes, datetime.date.today())

    # 4. Confirm database state
    stored_orders = repo.get_orders()
    assert len(stored_orders) == len(orders)
