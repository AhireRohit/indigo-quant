"""
Paper Execution Engine.
Converts qualified signals into idempotent paper orders, handles simulated fills,
monitors exits, and maintains marked-to-market portfolio equity.
"""

from __future__ import annotations

import datetime
import logging
from typing import Any, Dict, List, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from indigo_quant.db.models import PaperOrder, PaperPosition, StrategyAccount
from indigo_quant.paper.broker import SimulatedPaperBroker
from indigo_quant.paper.orders import CreatePaperOrderRequest, OrderSide, OrderType
from indigo_quant.paper.portfolio import PortfolioManager

logger = logging.getLogger(__name__)


class ExecutionEngine:
    """
    Coordinates paper brokerage operations across all 5 independent portfolios.
    """

    def __init__(self, db: Session):
        self.db = db
        self.broker = SimulatedPaperBroker(db)

    def queue_orders_from_signals(self, signals: List[Dict[str, Any]]) -> List[PaperOrder]:
        """
        Create pending paper orders for ranked signals, respecting capital constraints.
        """
        queued_orders = []

        for sig in signals:
            if sig.get("decision") != "BUY":
                continue

            strat_id = sig["strategy_id"]
            qty = sig.get("recommended_quantity", 0)
            if qty < 1:
                continue

            req = CreatePaperOrderRequest(
                account_id=strat_id,
                symbol=sig["symbol"],
                strategy_id=strat_id,
                order_side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=qty,
                signal_price=sig["reference_close"],
                stop_price=sig["initial_stop_estimate"],
                target_price=sig["target_price_estimate"],
                signal_date=sig["signal_date"],
                validity_days=2,
            )

            order = self.broker.submit_buy_order(req)
            if order.status == "PENDING":
                sig["execution_status"] = "QUEUED"
            queued_orders.append(order)

        return queued_orders

    def process_pending_fills(
        self,
        current_quotes: Dict[str, float],
        execution_date: datetime.date,
    ) -> List[PaperOrder]:
        """
        Attempt fills on all PENDING BUY orders using observable market quotes (e.g. Next session open).
        """
        stmt = select(PaperOrder).where(PaperOrder.status == "PENDING")
        pending_orders = list(self.db.execute(stmt).scalars().all())
        filled_orders = []

        for order in pending_orders:
            # Check order expiration
            if execution_date > order.valid_until_date:
                order.status = "EXPIRED"
                order.rejection_reason = "Order validity expired before execution."
                self.db.commit()
                continue

            quote_price = current_quotes.get(order.symbol)
            if not quote_price or quote_price <= 0:
                logger.debug("No quote available for %s. Order %s remains PENDING.", order.symbol, order.id)
                continue

            success, reason = self.broker.execute_pending_buy_order(
                order=order,
                market_open_price=quote_price,
                execution_date=execution_date,
            )
            if success:
                filled_orders.append(order)

        return filled_orders

    def evaluate_all_exits(
        self,
        current_bars: Dict[str, Dict[str, Any]],  # symbol -> bar dict
    ) -> List[Tuple[PaperPosition, str, float]]:
        """
        Evaluate all open positions across all strategy accounts for exit conditions.
        """
        accounts = list(self.db.execute(select(StrategyAccount)).scalars().all())
        all_closed = []

        for acc in accounts:
            pm = PortfolioManager(self.db, acc.id)
            open_pos = pm.get_open_positions()
            for pos in open_pos:
                bar = current_bars.get(pos.symbol)
                if not bar:
                    continue
                closed = self.broker.evaluate_open_positions_for_exits(acc.id, bar)
                all_closed.extend(closed)

        return all_closed

    def update_portfolio_snapshots(
        self,
        date: datetime.date,
        current_prices: Dict[str, float],
    ) -> Dict[str, Dict[str, float]]:
        """
        Record end-of-session marked-to-market snapshots for all 5 accounts.
        """
        accounts = list(self.db.execute(select(StrategyAccount)).scalars().all())
        results = {}

        for acc in accounts:
            pm = PortfolioManager(self.db, acc.id)
            snap = pm.record_daily_snapshot(date, current_prices)
            results[acc.id] = {
                "cash": snap.cash_balance,
                "invested_value": snap.invested_value,
                "total_equity": snap.total_equity,
                "open_positions": snap.open_positions_count,
            }

        return results
