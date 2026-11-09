"""
Portfolio Management and Cash Ledger Tracker.
Maintains independent equity accounts, tracks positions, and guarantees strict cash invariants.
"""

from __future__ import annotations

import datetime
from typing import Dict, List

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from indigo_quant.db.models import (
    CashLedger,
    PaperPosition,
    PortfolioEquitySnapshot,
    StrategyAccount,
)
from indigo_quant.paper.fees import FeeBreakdown


class PortfolioManager:
    """Manages independent cash ledgers, positions, and equity snapshots for a strategy account."""

    def __init__(self, db: Session, account_id: str):
        self.db = db
        self.account_id = account_id

    def get_account(self) -> StrategyAccount:
        acc = self.db.execute(
            select(StrategyAccount).where(StrategyAccount.id == self.account_id)
        ).scalar_one_or_none()
        if not acc:
            raise ValueError(f"StrategyAccount '{self.account_id}' does not exist.")
        return acc

    def get_open_positions(self) -> List[PaperPosition]:
        return list(
            self.db.execute(
                select(PaperPosition).where(
                    and_(
                        PaperPosition.account_id == self.account_id,
                        PaperPosition.status == "OPEN",
                    )
                )
            ).scalars().all()
        )

    def calculate_total_equity(self, current_prices: Dict[str, float]) -> Dict[str, float]:
        """
        Calculate marked-to-market equity = current_cash + sum(quantity * current_price).
        """
        acc = self.get_account()
        cash = acc.current_cash
        open_positions = self.get_open_positions()

        invested_value = 0.0
        unrealized_pnl = 0.0

        for pos in open_positions:
            price = current_prices.get(pos.symbol, pos.entry_price)
            pos_market_val = pos.quantity * price
            invested_value += pos_market_val
            cost_basis = pos.quantity * pos.entry_price
            unrealized_pnl += (pos_market_val - cost_basis)

        total_equity = cash + invested_value
        acc.current_equity = total_equity
        self.db.commit()

        return {
            "cash": round(cash, 2),
            "invested_value": round(invested_value, 2),
            "total_equity": round(total_equity, 2),
            "unrealized_pnl": round(unrealized_pnl, 2),
            "open_positions_count": len(open_positions),
        }

    def process_buy_fill(
        self,
        order_id: str,
        symbol: str,
        quantity: int,
        fill_price: float,
        stop_price: float,
        target_price: float,
        fee_breakdown: FeeBreakdown,
        fill_time: datetime.datetime,
        strategy_id: str,
    ) -> PaperPosition:
        """
        Debit cash, create open position, and log ledger transaction.
        """
        acc = self.get_account()
        total_cash_needed = fee_breakdown.effective_cash_impact

        if acc.current_cash < total_cash_needed:
            raise ValueError(
                f"Insufficient funds in {self.account_id}: "
                f"Available ₹{acc.current_cash:.2f} < Required ₹{total_cash_needed:.2f}"
            )

        # Debit cash
        acc.current_cash -= total_cash_needed
        acc.updated_at = datetime.datetime.utcnow()

        # Log ledger entry
        ledger = CashLedger(
            account_id=self.account_id,
            timestamp=fill_time,
            transaction_type="BUY_DEBIT",
            amount=-total_cash_needed,
            balance_after=round(acc.current_cash, 2),
            reference_order_id=order_id,
            description=f"BUY {quantity} {symbol} @ ₹{fill_price:.2f} (Charges: ₹{fee_breakdown.total_charges:.2f}, Slippage: ₹{fee_breakdown.slippage:.2f})",
        )
        self.db.add(ledger)

        # Create Position
        entry_date = fill_time.date() if hasattr(fill_time, "date") else fill_time
        pos = PaperPosition(
            account_id=self.account_id,
            symbol=symbol,
            strategy_id=strategy_id,
            quantity=quantity,
            entry_date=entry_date,
            entry_price=fill_price,
            current_stop=stop_price,
            target_price=target_price,
            sessions_held=0,
            highest_price_seen=fill_price,
            status="OPEN",
            total_fees_paid=fee_breakdown.total_charges + fee_breakdown.slippage,
            target_achieved=False,
        )
        self.db.add(pos)
        self.db.commit()
        self.db.refresh(pos)
        return pos

    def process_sell_fill(
        self,
        position_id: int,
        order_id: str,
        fill_price: float,
        fee_breakdown: FeeBreakdown,
        fill_time: datetime.datetime,
        close_reason: str,
    ) -> PaperPosition:
        """
        Credit cash from sell proceeds, close position, and record realized P&L.
        """
        pos = self.db.execute(select(PaperPosition).where(PaperPosition.id == position_id)).scalar_one_or_none()
        if not pos or pos.status != "OPEN":
            raise ValueError(f"Position {position_id} is not open.")

        acc = self.get_account()
        net_cash_received = fee_breakdown.effective_cash_impact

        # Credit cash
        acc.current_cash += net_cash_received
        acc.updated_at = datetime.datetime.utcnow()

        # Realized P&L calculations
        cost_basis = pos.quantity * pos.entry_price
        gross_exit_val = pos.quantity * fill_price
        gross_pnl = gross_exit_val - cost_basis

        total_trade_fees = (pos.total_fees_paid or 0.0) + fee_breakdown.total_charges + fee_breakdown.slippage
        net_pnl = gross_pnl - total_trade_fees

        target_hit = (
            close_reason.startswith("TARGET_HIT")
            or fill_price >= (pos.target_price * 0.998)
            or (gross_pnl / cost_basis) >= 0.098
        )

        pos.status = "CLOSED"
        pos.closed_date = fill_time.date() if hasattr(fill_time, "date") else fill_time
        pos.close_price = fill_price
        pos.close_reason = close_reason
        pos.realized_pnl_gross = round(gross_pnl, 2)
        pos.realized_pnl_net = round(net_pnl, 2)
        pos.total_fees_paid = round(total_trade_fees, 2)
        pos.target_achieved = target_hit
        pos.updated_at = datetime.datetime.utcnow()

        # Log ledger entry
        ledger = CashLedger(
            account_id=self.account_id,
            timestamp=fill_time,
            transaction_type="SELL_CREDIT",
            amount=net_cash_received,
            balance_after=round(acc.current_cash, 2),
            reference_order_id=order_id,
            description=f"SELL {pos.quantity} {pos.symbol} @ ₹{fill_price:.2f} ({close_reason}) - Net PnL: ₹{net_pnl:,.2f}",
        )
        self.db.add(ledger)
        self.db.commit()
        self.db.refresh(pos)
        return pos

    def record_daily_snapshot(self, date: datetime.date, current_prices: Dict[str, float]) -> PortfolioEquitySnapshot:
        """Save end-of-session equity snapshot."""
        equity_info = self.calculate_total_equity(current_prices)

        existing = self.db.execute(
            select(PortfolioEquitySnapshot).where(
                and_(
                    PortfolioEquitySnapshot.account_id == self.account_id,
                    PortfolioEquitySnapshot.date == date,
                )
            )
        ).scalar_one_or_none()

        if existing:
            snap = existing
        else:
            snap = PortfolioEquitySnapshot(
                account_id=self.account_id,
                date=date,
            )
            self.db.add(snap)

        snap.cash_balance = equity_info["cash"]
        snap.invested_value = equity_info["invested_value"]
        snap.total_equity = equity_info["total_equity"]
        snap.unrealized_pnl = equity_info["unrealized_pnl"]
        snap.open_positions_count = equity_info["open_positions_count"]
        snap.recorded_at = datetime.datetime.utcnow()

        self.db.commit()
        return snap
