"""
Isolated In-Memory Replay Broker and Simulation Portfolio Engine.
Strictly decoupled from production databases, production accounts, and Telegram alerts.

Implements:
- BUY-only entries, Next-Bar-Open execution model
- Conservative intra-bar stop/target collision resolution (Stop assumed hit first)
- Mandatory 15:25 IST end-of-session square-off for intraday mode
- Accurate Indian fee models (Delivery vs Intraday)
- Comprehensive trade logs (MAE, MFE, holding duration, return metrics)
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, List, Literal, Optional, Tuple
from pydantic import BaseModel

from indigo_quant.paper.fees import IndianDeliveryCostModel
from indigo_quant.paper.intraday_fees import IndianIntradayCostModel


class ReplayPosition(BaseModel):
    position_id: str
    strategy_id: str
    symbol: str
    quantity: int
    entry_time: datetime.datetime
    entry_price: float
    raw_entry_price: float = 0.0
    stop_price: float
    target_price: float
    current_price: float
    unrealized_pnl: float = 0.0
    highest_price_seen: float
    lowest_price_seen: float
    mae_pct: float = 0.0  # Max Adverse Excursion (%)
    mfe_pct: float = 0.0  # Max Favorable Excursion (%)
    holding_candles: int = 0
    buy_fee: float = 0.0
    buy_slippage: float = 0.0
    entry_cash_outlay: float = 0.0

    @property
    def shares(self) -> int:
        return self.quantity

    @property
    def unrealized_pnl_pct(self) -> float:
        if self.entry_price > 0:
            return round(((self.current_price - self.entry_price) / self.entry_price) * 100.0, 2)
        return 0.0


class ReplayTrade(BaseModel):
    trade_id: str
    strategy_id: str
    symbol: str
    quantity: int
    entry_time: datetime.datetime
    entry_price: float
    raw_entry_price: float = 0.0
    exit_time: datetime.datetime
    exit_price: float
    raw_exit_price: float = 0.0
    exit_reason: str  # "TARGET_HIT", "STOP_LOSS", "END_OF_SESSION_EXIT", "TIME_EXPIRATION"
    gross_pnl: float
    buy_fee: float = 0.0
    sell_fee: float = 0.0
    total_charges: float
    net_pnl: float
    return_pct: float
    target_achieved: bool
    mae_pct: float
    mfe_pct: float
    holding_candles: int

    @property
    def shares(self) -> int:
        return self.quantity

    @property
    def net_return_pct(self) -> float:
        return self.return_pct


class ReplayOrder(BaseModel):
    order_id: str
    strategy_id: str
    symbol: str
    side: Literal["BUY", "SELL"]
    signal_time: datetime.datetime
    signal_price: float
    stop_price: float
    target_price: float
    status: Literal["PENDING", "FILLED", "CANCELLED", "REJECTED"]
    fill_time: Optional[datetime.datetime] = None
    fill_price: Optional[float] = None
    quantity: int = 0
    rejection_reason: Optional[str] = None


class ReplayAccount:
    """Manages virtual capital and trade ledger for a strategy during replay."""

    def __init__(
        self,
        strategy_id: str,
        initial_capital: float = 100000.0,
        mode: Literal["INTRADAY", "SWING"] = "INTRADAY",
    ):
        self.strategy_id = strategy_id
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.mode = mode
        self.open_positions: List[ReplayPosition] = []
        self.closed_trades: List[ReplayTrade] = []
        self.orders: List[ReplayOrder] = []
        self.peak_equity = initial_capital
        self.max_drawdown_pct = 0.0
        self.equity_curve: List[Dict[str, Any]] = [
            {"time": "START", "equity": initial_capital, "cash": initial_capital}
        ]

    @property
    def total_equity(self) -> float:
        pos_val = sum(p.quantity * p.current_price for p in self.open_positions)
        return round(self.cash + pos_val, 2)

    @property
    def active_positions(self) -> Dict[str, ReplayPosition]:
        return {p.symbol: p for p in self.open_positions}

    @property
    def unrealized_pnl(self) -> float:
        return round(sum(p.unrealized_pnl for p in self.open_positions), 2)

    @property
    def realized_pnl(self) -> float:
        return round(sum(t.net_pnl for t in self.closed_trades), 2)

    def update_metrics(self, current_time: str) -> None:
        eq = self.total_equity
        if eq > self.peak_equity:
            self.peak_equity = eq
        dd = ((self.peak_equity - eq) / self.peak_equity) * 100.0 if self.peak_equity > 0 else 0.0
        if dd > self.max_drawdown_pct:
            self.max_drawdown_pct = dd
        self.equity_curve.append({
            "time": current_time,
            "equity": eq,
            "cash": round(self.cash, 2),
        })


class ReplayBroker:
    """
    Simulated Paper Broker dedicated to Market Replay sessions.
    Completely in-memory and isolated from production database.
    """

    def __init__(
        self,
        strategies: List[str],
        initial_capital_per_agent: float = 100000.0,
        mode: Literal["INTRADAY", "SWING"] = "INTRADAY",
        risk_per_trade_pct: float = 0.0025,  # 0.25% risk per trade for intraday
        max_positions_per_strategy: int = 2,
    ):
        self.mode = mode
        self.risk_per_trade_pct = risk_per_trade_pct
        self.max_positions = max_positions_per_strategy
        self.intraday_cost_model = IndianIntradayCostModel(slippage_pct=0.0005)
        self.delivery_cost_model = IndianDeliveryCostModel(slippage_pct=0.001)

        # Initialize accounts
        self.accounts: Dict[str, ReplayAccount] = {
            sid: ReplayAccount(sid, initial_capital_per_agent, mode=mode)
            for sid in strategies
        }
        self.pending_orders: List[ReplayOrder] = []
        self._order_counter = 1
        self._pos_counter = 1
        self._trade_counter = 1

    def queue_buy_order(
        self,
        strategy_id: str,
        symbol: str,
        signal_price: float,
        stop_price: float,
        target_price: float,
        signal_time: datetime.datetime,
    ) -> ReplayOrder:
        """Queue a BUY order from candle K close to be executed at candle K+1 open."""
        order_id = f"ord_replay_{self._order_counter:04d}_{strategy_id[:4]}"
        self._order_counter += 1

        order = ReplayOrder(
            order_id=order_id,
            strategy_id=strategy_id,
            symbol=symbol,
            side="BUY",
            signal_time=signal_time,
            signal_price=signal_price,
            stop_price=stop_price,
            target_price=target_price,
            status="PENDING",
        )
        self.pending_orders.append(order)
        acc = self.accounts.get(strategy_id)
        if acc:
            acc.orders.append(order)
        return order

    def process_pending_orders_at_open(
        self,
        symbol: str,
        candle_open: float,
        candle_time: datetime.datetime,
    ) -> List[Tuple[ReplayOrder, str]]:
        """
        Execute pending BUY orders at the open of the next candle.
        Rechecks available capital and risk limits.
        """
        results: List[Tuple[ReplayOrder, str]] = []
        remaining: List[ReplayOrder] = []

        for order in self.pending_orders:
            if order.symbol != symbol:
                remaining.append(order)
                continue

            acc = self.accounts.get(order.strategy_id)
            if not acc:
                order.status = "REJECTED"
                order.rejection_reason = "Strategy account not found."
                results.append((order, "Account not found"))
                continue

            # Check max positions limit
            if len(acc.open_positions) >= self.max_positions:
                order.status = "REJECTED"
                order.rejection_reason = f"Max positions reached ({self.max_positions})."
                results.append((order, "Max positions reached"))
                continue

            # Calculate position size based on risk
            risk_amt = acc.total_equity * self.risk_per_trade_pct
            risk_per_share = max(candle_open - order.stop_price, candle_open * 0.002)
            qty = int(risk_amt / risk_per_share)

            # Cap by available cash
            max_cash_qty = int(acc.cash * 0.95 / candle_open)  # leave buffer for charges
            final_qty = min(qty, max_cash_qty)

            if final_qty <= 0:
                order.status = "REJECTED"
                order.rejection_reason = f"Insufficient cash (Available: ₹{acc.cash:,.2f}) or invalid sizing."
                results.append((order, "Insufficient cash"))
                continue

            # Calculate charges & fill
            if self.mode == "INTRADAY":
                cost = self.intraday_cost_model.calculate_charges("BUY", candle_open, final_qty)
                effective_buy_price = cost.effective_execution_price
                buy_fee = cost.total_statutory_and_brokerage
                buy_slippage = cost.slippage
            else:
                cost = self.delivery_cost_model.calculate_charges("BUY", candle_open, final_qty)
                effective_buy_price = round(candle_open * (1.0 + self.delivery_cost_model.slippage_pct), 2)
                buy_fee = round(cost.total_charges - cost.slippage, 2)
                buy_slippage = round(cost.slippage, 2)

            buy_amount = round(effective_buy_price * final_qty, 2)
            total_required = round(buy_amount + buy_fee, 2)

            if acc.cash < total_required:
                order.status = "REJECTED"
                order.rejection_reason = f"Cash ₹{acc.cash:.2f} insufficient for total required ₹{total_required:.2f}."
                results.append((order, "Insufficient cash for fees"))
                continue

            # Deduct cash
            acc.cash = round(acc.cash - total_required, 2)
            order.status = "FILLED"
            order.fill_time = candle_time
            order.fill_price = effective_buy_price
            order.quantity = final_qty

            # Create Open Position
            pos_id = f"pos_replay_{self._pos_counter:04d}"
            self._pos_counter += 1
            pos = ReplayPosition(
                position_id=pos_id,
                strategy_id=order.strategy_id,
                symbol=symbol,
                quantity=final_qty,
                entry_time=candle_time,
                entry_price=effective_buy_price,
                raw_entry_price=candle_open,
                stop_price=order.stop_price,
                target_price=order.target_price,
                current_price=candle_open,
                highest_price_seen=candle_open,
                lowest_price_seen=candle_open,
                buy_fee=buy_fee,
                buy_slippage=buy_slippage,
                entry_cash_outlay=total_required,
            )
            acc.open_positions.append(pos)
            results.append((order, f"FILLED {final_qty} shares @ ₹{effective_buy_price:.2f} (Fees: ₹{buy_fee:.2f})"))

        self.pending_orders = remaining
        return results

    def evaluate_candle_exits(
        self,
        symbol: str,
        candle: Dict[str, Any],
        is_end_of_session: bool = False,
    ) -> List[Tuple[ReplayTrade, str]]:
        """
        Evaluate stop loss, profit target, and end-of-session square-offs for open positions.
        Conservative Policy: If both target and stop are touched in the same candle, STOP HIT FIRST.
        """
        closed_trades: List[Tuple[ReplayTrade, str]] = []
        c_open = float(candle["open"])
        c_high = float(candle["high"])
        c_low = float(candle["low"])
        c_close = float(candle["close"])
        c_time = candle["time"] if isinstance(candle["time"], datetime.datetime) else pd.to_datetime(candle["time"]).to_pydatetime()

        for sid, acc in self.accounts.items():
            remaining_positions: List[ReplayPosition] = []

            for pos in acc.open_positions:
                if pos.symbol != symbol:
                    remaining_positions.append(pos)
                    continue

                pos.holding_candles += 1
                pos.current_price = c_close
                pos.unrealized_pnl = (c_close - pos.entry_price) * pos.quantity

                # Track MAE & MFE
                if c_high > pos.highest_price_seen:
                    pos.highest_price_seen = c_high
                if c_low < pos.lowest_price_seen:
                    pos.lowest_price_seen = c_low

                pos.mae_pct = min(pos.mae_pct, ((pos.lowest_price_seen - pos.entry_price) / pos.entry_price) * 100.0)
                pos.mfe_pct = max(pos.mfe_pct, ((pos.highest_price_seen - pos.entry_price) / pos.entry_price) * 100.0)

                hit_stop = c_low <= pos.stop_price
                hit_target = c_high >= pos.target_price
                exit_triggered = False
                exit_price = c_close
                exit_reason = ""

                # 1. Conservative collision rule: Stop assumed hit first
                if hit_stop and hit_target:
                    exit_triggered = True
                    exit_price = min(c_open, pos.stop_price)  # handles gaps down
                    exit_reason = "STOP_LOSS"
                elif hit_stop:
                    exit_triggered = True
                    exit_price = min(c_open, pos.stop_price)
                    exit_reason = "STOP_LOSS"
                elif hit_target:
                    exit_triggered = True
                    exit_price = max(c_open, pos.target_price)  # handles gaps up
                    exit_reason = "TARGET_HIT"
                elif is_end_of_session and self.mode == "INTRADAY":
                    # Mandatory 15:25 square-off
                    exit_triggered = True
                    exit_price = c_close
                    exit_reason = "END_OF_SESSION_EXIT"

                if exit_triggered:
                    # Execute sell
                    if self.mode == "INTRADAY":
                        sell_cost = self.intraday_cost_model.calculate_charges("SELL", exit_price, pos.quantity)
                        effective_sell_price = sell_cost.effective_execution_price
                        sell_fee = sell_cost.total_statutory_and_brokerage
                        sell_slippage = sell_cost.slippage
                    else:
                        sell_cost = self.delivery_cost_model.calculate_charges("SELL", exit_price, pos.quantity)
                        effective_sell_price = round(exit_price * (1.0 - self.delivery_cost_model.slippage_pct), 2)
                        sell_fee = round(sell_cost.total_charges - sell_cost.slippage, 2)
                        sell_slippage = round(sell_cost.slippage, 2)

                    sell_amount = round(effective_sell_price * pos.quantity, 2)
                    sell_cash_inflow = round(sell_amount - sell_fee, 2)

                    # Update cash
                    acc.cash = round(acc.cash + sell_cash_inflow, 2)

                    # Gross PnL strictly calculated from effective execution prices: (exit_price - entry_price) * quantity
                    buy_amount = round(pos.entry_price * pos.quantity, 2)
                    gross_pnl = round(sell_amount - buy_amount, 2)

                    # Total charges include BOTH buy-side and sell-side statutory fees
                    total_charges = round(pos.buy_fee + sell_fee, 2)

                    # Net PnL = Gross PnL - Total Fees = sell_cash_inflow - pos.entry_cash_outlay
                    net_pnl = round(gross_pnl - total_charges, 2)
                    ret_pct = round((net_pnl / buy_amount) * 100.0, 2) if buy_amount > 0 else 0.0

                    trade_id = f"trd_replay_{self._trade_counter:04d}"
                    self._trade_counter += 1

                    trade = ReplayTrade(
                        trade_id=trade_id,
                        strategy_id=sid,
                        symbol=symbol,
                        quantity=pos.quantity,
                        entry_time=pos.entry_time,
                        entry_price=pos.entry_price,
                        raw_entry_price=pos.raw_entry_price,
                        exit_time=c_time,
                        exit_price=effective_sell_price,
                        raw_exit_price=exit_price,
                        exit_reason=exit_reason,
                        gross_pnl=gross_pnl,
                        buy_fee=pos.buy_fee,
                        sell_fee=sell_fee,
                        total_charges=total_charges,
                        net_pnl=net_pnl,
                        return_pct=ret_pct,
                        target_achieved=(exit_reason == "TARGET_HIT"),
                        mae_pct=round(pos.mae_pct, 2),
                        mfe_pct=round(pos.mfe_pct, 2),
                        holding_candles=pos.holding_candles,
                    )
                    acc.closed_trades.append(trade)
                    closed_trades.append((trade, f"CLOSED {pos.quantity} shares @ ₹{effective_sell_price:.2f} ({exit_reason}) Net PnL: ₹{net_pnl:,.2f}"))
                else:
                    remaining_positions.append(pos)

            acc.open_positions = remaining_positions

        return closed_trades

    def get_summary(self, strategy_id: str) -> Dict[str, Any]:
        """Generate high-level performance metrics for a strategy's replay session."""
        acc = self.accounts.get(strategy_id)
        if not acc:
            return {}

        trades = acc.closed_trades
        total_trades = len(trades)
        wins = [t for t in trades if t.net_pnl > 0]
        losses = [t for t in trades if t.net_pnl <= 0]
        target_hits = [t for t in trades if t.target_achieved]

        total_net_pnl = sum(t.net_pnl for t in trades)
        total_gross_pnl = sum(t.gross_pnl for t in trades)
        total_buy_fees = sum(t.buy_fee for t in trades)
        total_sell_fees = sum(t.sell_fee for t in trades)
        total_charges = sum(t.total_charges for t in trades)

        win_rate = (len(wins) / total_trades * 100.0) if total_trades > 0 else 0.0
        target_hit_rate = (len(target_hits) / total_trades * 100.0) if total_trades > 0 else 0.0

        gross_profits = sum(t.gross_pnl for t in wins)
        gross_losses = abs(sum(t.gross_pnl for t in losses))
        profit_factor = round(gross_profits / gross_losses, 2) if gross_losses > 0 else (99.0 if gross_profits > 0 else 0.0)

        avg_win = (sum(t.net_pnl for t in wins) / len(wins)) if wins else 0.0
        avg_loss = (sum(t.net_pnl for t in losses) / len(losses)) if losses else 0.0

        ret_pct = ((acc.total_equity - acc.initial_capital) / acc.initial_capital) * 100.0

        return {
            "strategy_id": strategy_id,
            "initial_capital": acc.initial_capital,
            "current_equity": acc.total_equity,
            "cash": round(acc.cash, 2),
            "net_return_pct": round(ret_pct, 2),
            "total_net_pnl": round(total_net_pnl, 2),
            "total_gross_pnl": round(total_gross_pnl, 2),
            "total_buy_fees": round(total_buy_fees, 2),
            "total_sell_fees": round(total_sell_fees, 2),
            "total_charges": round(total_charges, 2),
            "total_trades": total_trades,
            "winning_trades": len(wins),
            "losing_trades": len(losses),
            "win_rate_pct": round(win_rate, 1),
            "target_hits_count": len(target_hits),
            "target_hit_rate_pct": round(target_hit_rate, 1),
            "profit_factor": profit_factor,
            "max_drawdown_pct": round(acc.max_drawdown_pct, 2),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "open_positions_count": len(acc.open_positions),
        }
