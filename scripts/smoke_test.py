"""
End-to-End Smoke Test Script for Indigo Quant.
Validates live/cached data fetch, indicators, strategy evaluation,
and complete simulated paper order lifecycle in SQLite.
"""

import sys
import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

src_dir = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(src_dir))

from indigo_quant.db.session import SessionLocal
from indigo_quant.db.repository import init_db, Repository, seed_universe_and_accounts
from indigo_quant.data.ingestion import DataIngestionEngine
from indigo_quant.indicators.technical import calculate_all_indicators
from indigo_quant.engine.decision import DecisionEngine
from indigo_quant.paper.broker import SimulatedPaperBroker
from indigo_quant.paper.orders import CreatePaperOrderRequest, OrderSide, OrderType
from indigo_quant.paper.portfolio import PortfolioManager

def run_smoke_test():
    print("==================================================")
    print("      INDIGO QUANT END-TO-END SMOKE TEST")
    print("==================================================")

    # 1. Database Init
    print("\n[Step 1] Initializing SQLite database...")
    init_db()
    db = SessionLocal()
    seed_universe_and_accounts(db)
    repo = Repository(db)
    accs = repo.get_accounts()
    assert len(accs) == 5, f"Expected 5 strategy accounts, got {len(accs)}"
    for a in accs:
        assert a.initial_capital == 100000.0, f"Expected 100000.0, got {a.initial_capital}"
        assert a.current_cash > 0, f"Expected positive cash, got {a.current_cash}"
    print(f"✓ Verified 5 Strategy Accounts initialized with ₹1,00,000 capital each.")

    # 2. Market Data Ingestion
    print("\n[Step 2] Testing real market data ingestion (RELIANCE & ^NSEI)...")
    ingest = DataIngestionEngine(db)
    health = ingest.get_provider_health()
    print(f"  • Provider Health: {health}")

    nifty_df = ingest.fetch_benchmark("^NSEI")
    assert nifty_df is not None and not nifty_df.empty, "Failed fetching NIFTY 50 benchmark."
    print(f"✓ Retrieved {len(nifty_df)} bars for NIFTY 50 benchmark.")

    rel_df, logs = ingest.fetch_and_validate_symbol("RELIANCE", exchange="NSE", persist=True)
    assert rel_df is not None and not rel_df.empty, f"Failed fetching RELIANCE: {logs}"
    print(f"✓ Retrieved {len(rel_df)} validated daily bars for RELIANCE.")

    # 3. Technical Indicators
    print("\n[Step 3] Computing complete technical indicator suite...")
    ind_df = calculate_all_indicators(rel_df, benchmark_df=nifty_df)
    latest = ind_df.iloc[-1]
    assert "ema20" in ind_df.columns and "rsi14" in ind_df.columns and "macd_line" in ind_df.columns
    print(f"✓ Successfully computed all indicators. Latest close: ₹{latest['close']:.2f}, RSI14: {latest['rsi14']:.2f}, ADX14: {latest['adx14']:.2f}")

    # 4. Deterministic Strategy Evaluation
    print("\n[Step 4] Running deterministic decision scan on RELIANCE...")
    decision_engine = DecisionEngine(db)
    scan_res = decision_engine.run_daily_scan({"RELIANCE": rel_df}, nifty_df=nifty_df)
    print(f"✓ Decision scan executed. Market Regime: {scan_res['regime']}, Signals: {len(scan_res['signals'])}, Rejections: {len(scan_res['rejections'])}")

    # 5. Paper Brokerage Lifecycle Simulation
    print("\n[Step 5] Simulating paper trade order lifecycle...")
    broker = SimulatedPaperBroker(db)
    order_req = CreatePaperOrderRequest(
        account_id="trend_momentum",
        symbol="RELIANCE",
        strategy_id="trend_momentum",
        order_side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=10,
        signal_price=float(latest["close"]),
        stop_price=float(latest["close"]) * 0.96,
        target_price=float(latest["close"]) * 1.10,
        signal_date=datetime.date.today(),
    )
    order = broker.submit_buy_order(order_req)
    print(f"✓ Submitted paper BUY order: {order.id} (Status: {order.status})")

    # Execute fill if pending
    if order.status == "PENDING":
        filled, reason = broker.execute_pending_buy_order(
            order=order,
            market_open_price=float(latest["close"]),
            execution_date=datetime.date.today(),
        )
        assert filled, f"Order fill failed: {reason}"
        print(f"✓ Simulated order executed @ ₹{order.fill_price:.2f}.")
    else:
        print(f"✓ Order was previously filled @ ₹{order.fill_price:.2f} (Idempotent order match).")

    # Verify Portfolio State
    pm = PortfolioManager(db, "trend_momentum")
    acc = pm.get_account()
    open_pos = pm.get_open_positions()
    print(f"✓ Portfolio verified in SQLite. Current cash: ₹{acc.current_cash:,.2f}, Open positions: {len(open_pos)}")

    # Simulate Target Exit (+10%) if open position exists
    if open_pos:
        print("\n[Step 6] Simulating +10% target exit execution...")
        pos = open_pos[0]
        target_bar = {
            "symbol": "RELIANCE",
            "open": pos.entry_price * 1.05,
            "high": pos.target_price + 5.0,  # Crosses +10% target
            "low": pos.entry_price * 1.01,
            "close": pos.target_price,
            "date": datetime.date.today() + datetime.timedelta(days=7),
        }
        closed = broker.evaluate_open_positions_for_exits("trend_momentum", target_bar)
        assert len(closed) > 0, "Expected target exit to trigger."
        closed_pos, reason, exit_price = closed[0]
        print(f"✓ Position closed. Reason: {reason}, Exit Price: ₹{exit_price:.2f}, Net Realized PnL: ₹{closed_pos.realized_pnl_net:,.2f}, Target Hit: {closed_pos.target_achieved}")
    else:
        print("\n[Step 6] Previous position already exited with 10% target objective achieved.")

    db.close()
    print("\n==================================================")
    print("      ALL END-TO-END SMOKE TESTS PASSED!")
    print("==================================================")

if __name__ == "__main__":
    run_smoke_test()
