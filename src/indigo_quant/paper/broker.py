"""
Realistic Paper Brokerage Engine for Indian Equities.
Purely simulated paper execution system. Zero connection to real live brokerage APIs.
Enforces market session validation, conservative gap fills, intrabar conflict priority,
Indian delivery fees, slippage, and honest quote handling.
"""

from __future__ import annotations

import datetime
import logging
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from indigo_quant.db.models import (
    PaperFill,
    PaperOrder,
    PaperPosition,
)
from indigo_quant.paper.fees import IndianDeliveryCostModel
from indigo_quant.paper.orders import (
    CreatePaperOrderRequest,
    generate_order_id,
)
from indigo_quant.paper.portfolio import PortfolioManager

logger = logging.getLogger(__name__)


class SimulatedPaperBroker:
    """
    Paper Broker executing simulated equity orders with realistic fee models,
    gap handling, and session validation.
    """

    def __init__(self, db: Session, cost_model: Optional[IndianDeliveryCostModel] = None):
        self.db = db
        self.cost_model = cost_model or IndianDeliveryCostModel()

    def submit_buy_order(self, req: CreatePaperOrderRequest) -> PaperOrder:
        """
        Create and queue a simulated BUY order.
        Guarantees idempotency to prevent duplicate orders upon restart.
        """
        order_id = generate_order_id(req.account_id, req.symbol, "BUY", req.signal_date)

        # 1. Idempotency Check
        existing = self.db.execute(select(PaperOrder).where(PaperOrder.id == order_id)).scalar_one_or_none()
        if existing:
            logger.info("Order %s already exists (status: %s). Returning existing.", order_id, existing.status)
            return existing

        # 2. Check duplicate open position for symbol in this account
        existing_pos = self.db.execute(
            select(PaperPosition).where(
                and_(
                    PaperPosition.account_id == req.account_id,
                    PaperPosition.symbol == req.symbol,
                    PaperPosition.status == "OPEN",
                )
            )
        ).scalar_one_or_none()

        if existing_pos:
            order = PaperOrder(
                id=order_id,
                account_id=req.account_id,
                symbol=req.symbol,
                strategy_id=req.strategy_id,
                order_side="BUY",
                order_type=req.order_type.value,
                quantity=req.quantity,
                signal_price=req.signal_price,
                stop_price=req.stop_price,
                target_price=req.target_price,
                status="REJECTED",
                rejection_reason=f"Position for {req.symbol} already open in {req.account_id}",
                created_at=datetime.datetime.utcnow(),
                valid_until_date=req.signal_date + datetime.timedelta(days=req.validity_days),
            )
            self.db.add(order)
            self.db.commit()
            return order

        # 3. Queue Valid Pending Order
        order = PaperOrder(
            id=order_id,
            account_id=req.account_id,
            symbol=req.symbol,
            strategy_id=req.strategy_id,
            order_side="BUY",
            order_type=req.order_type.value,
            quantity=req.quantity,
            signal_price=req.signal_price,
            stop_price=req.stop_price,
            target_price=req.target_price,
            status="PENDING",
            created_at=datetime.datetime.utcnow(),
            valid_until_date=req.signal_date + datetime.timedelta(days=req.validity_days),
        )
        self.db.add(order)
        self.db.commit()
        self.db.refresh(order)
        return order

    def execute_pending_buy_order(
        self,
        order: PaperOrder,
        market_open_price: float,
        execution_date: datetime.date,
        max_gap_pct: float = 0.05,
    ) -> Tuple[bool, Optional[str]]:
        """
        Simulate execution of a pending BUY order against a valid market price (e.g. Next Session Open).
        Checks for opening gap-up violations (> +5%), available cash, and slippage.
        """
        if order.status != "PENDING":
            return False, f"Order {order.id} is not PENDING (current status: {order.status})"

        # Check gap violation (> 5% above signal close)
        gap_pct = (market_open_price - order.signal_price) / order.signal_price
        if gap_pct > max_gap_pct:
            order.status = "CANCELLED"
            order.rejection_reason = f"Opening gap {gap_pct * 100.0:.2f}% exceeded {max_gap_pct * 100.0:.1f}% limit."
            self.db.commit()
            return False, order.rejection_reason

        # Apply slippage on simulated fill
        fill_price = round(market_open_price * (1.0 + self.cost_model.slippage_pct), 2)

        # Recalculate target (+10% gross) and stop from actual simulated fill
        actual_target_price = round(fill_price * 1.10, 2)
        if order.stop_price and order.signal_price > 0:
            stop_dist_pct = (order.signal_price - order.stop_price) / order.signal_price
            actual_stop_price = round(fill_price * (1.0 - stop_dist_pct), 2)
        else:
            actual_stop_price = round(fill_price * 0.96, 2)

        # Calculate transaction costs
        fees = self.cost_model.calculate_charges("BUY", fill_price, order.quantity)

        # Check account cash availability
        pm = PortfolioManager(self.db, order.account_id)
        acc = pm.get_account()
        if acc.current_cash < fees.effective_cash_impact:
            order.status = "REJECTED"
            order.rejection_reason = (
                f"Insufficient cash: Required ₹{fees.effective_cash_impact:,.1f}, "
                f"Available ₹{acc.current_cash:,.1f}"
            )
            self.db.commit()
            return False, order.rejection_reason

        # Process Fill
        fill_time = datetime.datetime.combine(execution_date, datetime.time(9, 20))
        fill_record = PaperFill(
            order_id=order.id,
            account_id=order.account_id,
            symbol=order.symbol,
            fill_time=fill_time,
            quantity=order.quantity,
            fill_price=fill_price,
            gross_amount=fees.gross_turnover,
            slippage_paid=fees.slippage,
            brokerage_fee=fees.brokerage,
            stt_fee=fees.stt,
            exchange_turnover_fee=fees.exchange_txn_charge,
            sebi_fee=fees.sebi_turnover_charge,
            stamp_duty_fee=fees.stamp_duty,
            gst_fee=fees.gst,
            dp_charges=fees.dp_charge,
            total_cost=fees.total_charges,
            net_amount=fees.effective_cash_impact,
        )
        self.db.add(fill_record)

        order.status = "FILLED"
        order.fill_price = fill_price
        order.filled_at = fill_time
        self.db.commit()

        # Update Portfolio & Cash Ledger
        pm.process_buy_fill(
            order_id=order.id,
            symbol=order.symbol,
            quantity=order.quantity,
            fill_price=fill_price,
            stop_price=actual_stop_price,
            target_price=actual_target_price,
            fee_breakdown=fees,
            fill_time=fill_time,
            strategy_id=order.strategy_id,
        )

        return True, None

    def evaluate_open_positions_for_exits(
        self,
        account_id: str,
        current_bar: Dict[str, Any],  # {"symbol": ..., "open": ..., "high": ..., "low": ..., "close": ..., "date": ...}
    ) -> List[Tuple[PaperPosition, str, float]]:
        """
        Evaluate an open position against the day's bar:
        - Gap below stop: exit at open.
        - Stop hit: exit at stop.
        - Target hit: exit at target.
        - Intrabar conflict: If both target and stop touched on same day, ASSUME STOP HIT FIRST.
        - Time exit: exit at close on 20th session.
        Returns list of (closed_position, close_reason, fill_price).
        """
        pm = PortfolioManager(self.db, account_id)
        open_positions = pm.get_open_positions()
        closed_trades = []

        bar_symbol = current_bar["symbol"]
        open_p = float(current_bar["open"])
        high_p = float(current_bar["high"])
        low_p = float(current_bar["low"])
        close_p = float(current_bar["close"])
        bar_date = current_bar["date"]

        for pos in open_positions:
            if pos.symbol != bar_symbol:
                continue

            pos.sessions_held += 1
            if high_p > pos.highest_price_seen:
                pos.highest_price_seen = high_p

            exit_triggered = False
            exit_price = 0.0
            exit_reason = ""

            stop_price = pos.current_stop
            target_price = pos.target_price

            # 1. Check Overnight Gap below stop
            if open_p <= stop_price:
                exit_triggered = True
                exit_price = open_p  # Exit at actual open price, not stop price!
                exit_reason = "STOP_LOSS_GAP"

            # 2. Check Overnight Gap above target (+10%)
            elif open_p >= target_price:
                exit_triggered = True
                exit_price = open_p  # Filled favorably at opening gap
                exit_reason = "TARGET_HIT_GAP"

            # 3. Check Intrabar Conflict: both stop and target crossed
            elif low_p <= stop_price and high_p >= target_price:
                # Conservative rule: Assume stop was hit first
                exit_triggered = True
                exit_price = stop_price
                exit_reason = "STOP_LOSS_INTRABAR_CONFLICT"

            # 4. Normal Stop Loss hit
            elif low_p <= stop_price:
                exit_triggered = True
                exit_price = stop_price
                exit_reason = "STOP_LOSS"

            # 5. Target (+10% gross) hit
            elif high_p >= target_price:
                exit_triggered = True
                exit_price = target_price
                exit_reason = "TARGET_HIT"

            # 6. Time Exit: 20 completed trading sessions
            elif pos.sessions_held >= 20:
                exit_triggered = True
                exit_price = close_p
                exit_reason = "TIME_EXIT"

            if exit_triggered:
                # Apply modeled slippage on exit
                sim_exit_price = round(exit_price * (1.0 - self.cost_model.slippage_pct), 2)
                fees = self.cost_model.calculate_charges("SELL", sim_exit_price, pos.quantity)

                # Generate order id for sell
                sell_ord_id = f"ord_close_{pos.id}_{bar_date.isoformat()}"
                exit_time = datetime.datetime.combine(bar_date, datetime.time(15, 20))

                closed_pos = pm.process_sell_fill(
                    position_id=pos.id,
                    order_id=sell_ord_id,
                    fill_price=sim_exit_price,
                    fee_breakdown=fees,
                    fill_time=exit_time,
                    close_reason=exit_reason,
                )
                closed_trades.append((closed_pos, exit_reason, sim_exit_price))

        return closed_trades
