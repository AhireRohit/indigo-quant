"""
Autonomous Scheduler and Background Job Engine.
Uses APScheduler with Asia/Kolkata timezone.
Coordinates EOD data ingestion, market regime checks, signal generation,
intraday order execution, position exit monitoring, and daily reporting.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.orm import Session

from indigo_quant.data.calendar import (
    IST,
    get_latest_completed_trading_day,
    is_trading_day,
    now_ist,
)
from indigo_quant.data.ingestion import DataIngestionEngine
from indigo_quant.db.models import PaperOrder
from indigo_quant.db.repository import Repository
from indigo_quant.db.session import SessionLocal
from indigo_quant.engine.decision import DecisionEngine
from indigo_quant.engine.execution import ExecutionEngine
from indigo_quant.export.public_data import export_public_snapshots
from indigo_quant.export.static_report import generate_static_html
from indigo_quant.notifications.telegram import TelegramNotifier

logger = logging.getLogger(__name__)


class IndigoScheduler:
    """Manages scheduled background automation for Indigo Quant."""

    def __init__(self):
        self.scheduler = BackgroundScheduler(timezone=IST)
        self.notifier = TelegramNotifier()
        self.is_running = False

    def start(self) -> None:
        """Register cron jobs and start scheduler."""
        if self.is_running:
            return

        # 1. Evening Scan (19:15 IST Monday to Friday)
        self.scheduler.add_job(
            self.run_evening_scan_job,
            CronTrigger(hour=19, minute=15, day_of_week="mon-fri", timezone=IST),
            id="evening_eod_scan",
            name="Evening EOD Market Scan and Signal Generation",
            replace_existing=True,
        )

        # 2. Evening Retry Check (22:00 IST Monday to Friday)
        self.scheduler.add_job(
            self.run_evening_retry_job,
            CronTrigger(hour=22, minute=0, day_of_week="mon-fri", timezone=IST),
            id="evening_retry_scan",
            name="Evening EOD Verification and Retry Check",
            replace_existing=True,
        )

        # 3. Morning Market Opening Fill Processing (09:20 IST Monday to Friday)
        self.scheduler.add_job(
            self.run_morning_open_job,
            CronTrigger(hour=9, minute=20, day_of_week="mon-fri", timezone=IST),
            id="morning_order_fills",
            name="Morning Paper Order Fill Execution",
            replace_existing=True,
        )

        # 4. Market Closing Exit Monitoring (15:20 IST Monday to Friday)
        self.scheduler.add_job(
            self.run_afternoon_exit_job,
            CronTrigger(hour=15, minute=20, day_of_week="mon-fri", timezone=IST),
            id="afternoon_position_exits",
            name="Closing Exit Evaluation (Targets, Stops, Time)",
            replace_existing=True,
        )

        self.scheduler.start()
        self.is_running = True
        logger.info("IndigoScheduler started with timezone Asia/Kolkata.")

    def stop(self) -> None:
        """Gracefully shut down scheduler."""
        if self.is_running:
            self.scheduler.shutdown(wait=False)
            self.is_running = False
            logger.info("IndigoScheduler stopped.")

    def run_evening_scan_job(self, force: bool = False) -> Dict[str, Any]:
        """
        Evening routine: fetch verified EOD candles, run decision engine,
        queue paper orders, send Telegram alerts, and update daily log.
        """
        start_t = time.time()
        today = now_ist().date()
        logger.info("Triggered Evening Scan for %s (force=%s)", today, force)

        if not force and not is_trading_day(today):
            logger.info("Today (%s) is a market holiday or weekend. Skipping regular scan.", today)
            return {"status": "SKIPPED", "reason": "Market closed"}

        db: Session = SessionLocal()
        try:
            repo = Repository(db)
            ingest = DataIngestionEngine(db)
            decision = DecisionEngine(db)
            execution = ExecutionEngine(db)

            # 1. Fetch benchmark
            nifty_df = ingest.fetch_benchmark("^NSEI")

            # 2. Ingest active universe data
            instruments = repo.get_active_instruments()
            universe_data = {}
            for inst in instruments:
                df, _ = ingest.fetch_and_validate_symbol(inst.symbol, exchange=inst.exchange)
                if df is not None and not df.empty:
                    universe_data[inst.symbol] = df

            # 3. Run Decision Engine
            scan_result = decision.run_daily_scan(universe_data, nifty_df=nifty_df, target_date=today)
            signals = scan_result.get("signals", [])

            # 4. Queue eligible paper orders
            queued = execution.queue_orders_from_signals(signals)

            # 5. Dispatch Telegram BUY alerts
            for sig in signals:
                if sig.get("decision") == "BUY":
                    self.notifier.send_buy_alert(sig)

            duration = time.time() - start_t
            msg = f"Evening scan complete: {len(universe_data)} symbols scanned, {len(signals)} BUY signals, {len(queued)} orders queued."
            repo.log_job_run("evening_eod_scan", "SUCCESS", duration, msg, details=scan_result)
            logger.info(msg)

            # 6. Send daily summary recap to Telegram
            accounts = repo.get_accounts()
            tot_equity = sum(a.current_equity for a in accounts)
            open_pos_cnt = len(repo.get_open_positions())
            rankings = [{"name": a.name, "equity": a.current_equity} for a in accounts]
            summary_dict = {
                "date": str(today),
                "regime": scan_result.get("regime", "UNKNOWN"),
                "nifty_close": nifty_df["close"].iloc[-1] if nifty_df is not None and not nifty_df.empty else 0.0,
                "scanned_count": len(universe_data),
                "signals_count": len(signals),
                "open_positions_count": open_pos_cnt,
                "total_equity": tot_equity,
                "initial_capital": 500000.0,
                "strategy_rankings": rankings,
            }
            self.notifier.send_daily_summary(summary_dict)

            # 7. Refresh public data snapshots for Streamlit Cloud and static reports
            try:
                export_public_snapshots()
                generate_static_html()
            except Exception as exp_err:
                logger.warning("Could not refresh public data snapshots: %s", exp_err)

            return {"status": "SUCCESS", "message": msg, "result": scan_result}

        except Exception as e:
            duration = time.time() - start_t
            logger.error("Evening scan failed: %s", e, exc_info=True)
            db.rollback()
            repo = Repository(db)
            repo.log_job_run("evening_eod_scan", "FAILED", duration, str(e))
            self.notifier.send_error_alert("Evening EOD Scan Job", str(e))
            return {"status": "FAILED", "error": str(e)}
        finally:
            db.close()

    def run_evening_retry_job(self) -> Dict[str, Any]:
        """Verify data freshness at 22:00 IST. If evening scan had missing data, retry."""
        today = now_ist().date()
        if not is_trading_day(today):
            return {"status": "SKIPPED", "reason": "Non-trading day"}

        db: Session = SessionLocal()
        try:
            repo = Repository(db)
            expected_date = get_latest_completed_trading_day()
            # Check latest bar in database for benchmark
            nifty_latest = repo.get_latest_bar_date("^NSEI")
            if nifty_latest and nifty_latest >= expected_date:
                logger.info("Data for %s is already up to date. No retry needed.", expected_date)
                return {"status": "UP_TO_DATE"}

            logger.warning("Data for %s was missing at 22:00 IST. Re-running evening scan...", expected_date)
            return self.run_evening_scan_job(force=True)
        finally:
            db.close()

    def run_morning_open_job(self) -> Dict[str, Any]:
        """At 09:20 IST, simulate paper order fills for pending orders."""
        today = now_ist().date()
        if not is_trading_day(today):
            return {"status": "SKIPPED", "reason": "Market closed"}

        db: Session = SessionLocal()
        try:
            execution = ExecutionEngine(db)
            ingest = DataIngestionEngine(db)

            # Fetch fresh quotes for pending symbols
            pending_orders = execution.db.query(PaperOrder).filter(PaperOrder.status == "PENDING").all()
            quotes = {}
            for ord in pending_orders:
                price, _, _ = ingest.yahoo.fetch_latest_quote(ord.symbol)
                if price:
                    quotes[ord.symbol] = price

            filled = execution.process_pending_fills(quotes, execution_date=today)
            for f_ord in filled:
                self.notifier.send_order_filled_alert({
                    "id": f_ord.id,
                    "symbol": f_ord.symbol,
                    "order_side": f_ord.order_side,
                    "quantity": f_ord.quantity,
                    "fill_price": f_ord.fill_price,
                    "fill_date": str(today),
                    "strategy_id": f_ord.strategy_id,
                })

            msg = f"Morning session: {len(filled)} pending orders filled."
            logger.info(msg)

            try:
                export_public_snapshots()
                generate_static_html()
            except Exception:
                pass

            return {"status": "SUCCESS", "filled_count": len(filled)}
        finally:
            db.close()

    def run_afternoon_exit_job(self) -> Dict[str, Any]:
        """At 15:20 IST, evaluate open positions for target, stop, and time exits."""
        today = now_ist().date()
        if not is_trading_day(today):
            return {"status": "SKIPPED", "reason": "Market closed"}

        db: Session = SessionLocal()
        try:
            execution = ExecutionEngine(db)
            ingest = DataIngestionEngine(db)
            repo = Repository(db)

            # 1. Fetch current daily bars for open position exit evaluation
            open_positions = repo.get_open_positions()
            current_bars = {}
            current_prices = {}

            instruments = repo.get_active_instruments()
            for inst in instruments:
                p, _, _ = ingest.yahoo.fetch_latest_quote(inst.symbol)
                if p:
                    current_prices[inst.symbol] = p

            for pos in open_positions:
                df, _ = ingest.fetch_and_validate_symbol(pos.symbol, persist=False)
                if df is not None and not df.empty:
                    current_bars[pos.symbol] = {
                        "symbol": pos.symbol,
                        "open": float(df["open"].iloc[-1]),
                        "high": float(df["high"].iloc[-1]),
                        "low": float(df["low"].iloc[-1]),
                        "close": float(df["close"].iloc[-1]),
                        "date": df.index[-1].date() if hasattr(df.index[-1], "date") else df.index[-1],
                    }

            # 2. Evaluate exits
            closed_exits = execution.evaluate_all_exits(current_bars)
            for pos, reason, exit_price in closed_exits:
                pnl_pct = ((exit_price - pos.entry_price) / pos.entry_price) * 100.0 if pos.entry_price > 0 else 0.0
                if reason.startswith("TARGET_HIT"):
                    self.notifier.send_target_hit_alert(
                        symbol=pos.symbol,
                        strategy_id=pos.strategy_id,
                        entry_price=pos.entry_price,
                        exit_price=exit_price,
                        pnl_pct=pnl_pct,
                        gross_pnl=pos.realized_pnl_gross or 0.0,
                        net_pnl=pos.realized_pnl_net or 0.0,
                        holding_days=pos.sessions_held,
                    )
                elif reason.startswith("STOP_LOSS"):
                    self.notifier.send_stop_loss_alert(
                        symbol=pos.symbol,
                        strategy_id=pos.strategy_id,
                        entry_price=pos.entry_price,
                        exit_price=exit_price,
                        pnl_pct=pnl_pct,
                        gross_pnl=pos.realized_pnl_gross or 0.0,
                        net_pnl=pos.realized_pnl_net or 0.0,
                        holding_days=pos.sessions_held,
                    )

            # 3. Record marked-to-market portfolio snapshots
            execution.update_portfolio_snapshots(today, current_prices)

            try:
                export_public_snapshots()
                generate_static_html()
            except Exception:
                pass

            return {"status": "SUCCESS", "updated_snapshots_for": len(current_prices), "closed_exits": len(closed_exits)}
        finally:
            db.close()
