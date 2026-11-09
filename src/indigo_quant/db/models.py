"""
SQLAlchemy relational database models for Indigo Quant.
"""

from __future__ import annotations

import datetime
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from indigo_quant.db.session import Base


class Instrument(Base):
    __tablename__ = "instruments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    exchange: Mapped[str] = mapped_column(String(16), default="NSE", nullable=False)
    bse_code: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    isin: Mapped[Optional[str]] = mapped_column(String(32), index=True, nullable=True)
    company_name: Mapped[str] = mapped_column(String(128), nullable=False)
    sector: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False
    )


class HistoricalBar(Base):
    __tablename__ = "historical_bars"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    exchange: Mapped[str] = mapped_column(String(16), default="NSE", nullable=False)
    date: Mapped[datetime.date] = mapped_column(Date, index=True, nullable=False)
    open: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[float] = mapped_column(Float, nullable=False)
    turnover: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    adj_close: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    is_validated: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (
        UniqueConstraint("symbol", "exchange", "date", name="uq_symbol_exchange_date"),
        Index("ix_bars_symbol_date", "symbol", "date"),
    )


class CorporateAction(Base):
    __tablename__ = "corporate_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    exchange: Mapped[str] = mapped_column(String(16), default="NSE", nullable=False)
    ex_date: Mapped[datetime.date] = mapped_column(Date, index=True, nullable=False)
    record_date: Mapped[Optional[datetime.date]] = mapped_column(Date, nullable=True)
    action_type: Mapped[str] = mapped_column(String(32), nullable=False)  # dividend, bonus, split, rights
    cash_amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ratio_num: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ratio_den: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    raw_subject: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)

    __table_args__ = (
        UniqueConstraint("symbol", "exchange", "ex_date", "action_type", name="uq_corp_action"),
    )


class IndicatorSnapshot(Base):
    __tablename__ = "indicator_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    date: Mapped[datetime.date] = mapped_column(Date, index=True, nullable=False)
    data_json: Mapped[str] = mapped_column(Text, nullable=False)  # Serialized dictionary of indicator metrics
    calculated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("symbol", "date", name="uq_snapshot_symbol_date"),
    )


class StrategyAccount(Base):
    __tablename__ = "strategy_accounts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # trend_momentum, volume_breakout, etc.
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False, default="1.0.0")
    initial_capital: Mapped[float] = mapped_column(Float, default=100000.0, nullable=False)
    current_cash: Mapped[float] = mapped_column(Float, default=100000.0, nullable=False)
    current_equity: Mapped[float] = mapped_column(Float, default=100000.0, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False
    )

    cash_ledgers: Mapped[List[CashLedger]] = relationship(
        "CashLedger", back_populates="account", cascade="all, delete-orphan"
    )
    orders: Mapped[List[PaperOrder]] = relationship(
        "PaperOrder", back_populates="account", cascade="all, delete-orphan"
    )
    positions: Mapped[List[PaperPosition]] = relationship(
        "PaperPosition", back_populates="account", cascade="all, delete-orphan"
    )


class CashLedger(Base):
    __tablename__ = "cash_ledgers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[str] = mapped_column(String(64), ForeignKey("strategy_accounts.id"), index=True, nullable=False)
    timestamp: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow, index=True, nullable=False
    )
    transaction_type: Mapped[str] = mapped_column(String(32), nullable=False)  # INITIAL_FUNDING, BUY_DEBIT, SELL_CREDIT, FEE_DEBIT
    amount: Mapped[float] = mapped_column(Float, nullable=False)  # positive for credit, negative for debit
    balance_after: Mapped[float] = mapped_column(Float, nullable=False)
    reference_order_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    description: Mapped[str] = mapped_column(String(256), nullable=False)

    account: Mapped[StrategyAccount] = relationship("StrategyAccount", back_populates="cash_ledgers")


class SignalRecord(Base):
    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    strategy_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    strategy_version: Mapped[str] = mapped_column(String(32), nullable=False)
    signal_date: Mapped[datetime.date] = mapped_column(Date, index=True, nullable=False)
    evaluation_timestamp: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow, nullable=False
    )
    decision: Mapped[str] = mapped_column(String(16), nullable=False)  # BUY, NO_TRADE
    rule_quality_score: Mapped[float] = mapped_column(Float, nullable=False)
    reference_close: Mapped[float] = mapped_column(Float, nullable=False)
    target_gain_pct: Mapped[float] = mapped_column(Float, default=10.0, nullable=False)
    target_price_estimate: Mapped[float] = mapped_column(Float, nullable=False)
    initial_stop_estimate: Mapped[float] = mapped_column(Float, nullable=False)
    stop_distance_pct: Mapped[float] = mapped_column(Float, nullable=False)
    reward_to_risk_ratio: Mapped[float] = mapped_column(Float, nullable=False)
    rules_passed_json: Mapped[str] = mapped_column(Text, nullable=False)
    rules_failed_json: Mapped[str] = mapped_column(Text, nullable=False)
    regime_status: Mapped[str] = mapped_column(String(32), nullable=False)  # BULLISH, DEFENSIVE, UNKNOWN
    execution_status: Mapped[str] = mapped_column(String(32), default="PENDING", nullable=False)  # PENDING, QUEUED, FILLED, REJECTED, EXPIRED
    data_source: Mapped[str] = mapped_column(String(32), nullable=False)
    data_timestamp: Mapped[str] = mapped_column(String(64), nullable=False)

    __table_args__ = (
        UniqueConstraint("symbol", "strategy_id", "signal_date", name="uq_signal_symbol_strategy_date"),
        Index("ix_signals_date_strat", "signal_date", "strategy_id"),
    )


class RejectedCandidate(Base):
    __tablename__ = "rejected_candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    strategy_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    date: Mapped[datetime.date] = mapped_column(Date, index=True, nullable=False)
    reason: Mapped[str] = mapped_column(String(256), nullable=False)
    failed_conditions_json: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow, nullable=False
    )


class PaperOrder(Base):
    __tablename__ = "paper_orders"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # Idempotency key / UUID
    account_id: Mapped[str] = mapped_column(String(64), ForeignKey("strategy_accounts.id"), index=True, nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    strategy_id: Mapped[str] = mapped_column(String(64), nullable=False)
    order_side: Mapped[str] = mapped_column(String(8), nullable=False)  # BUY, SELL
    order_type: Mapped[str] = mapped_column(String(16), default="MARKET", nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    signal_price: Mapped[float] = mapped_column(Float, nullable=False)
    limit_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    stop_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    target_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="PENDING", nullable=False)  # PENDING, FILLED, CANCELLED, EXPIRED, REJECTED
    rejection_reason: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow, nullable=False
    )
    valid_until_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    filled_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, nullable=True)
    fill_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    account: Mapped[StrategyAccount] = relationship("StrategyAccount", back_populates="orders")
    fill: Mapped[Optional[PaperFill]] = relationship("PaperFill", back_populates="order", uselist=False)


class PaperFill(Base):
    __tablename__ = "paper_fills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[str] = mapped_column(String(64), ForeignKey("paper_orders.id"), unique=True, nullable=False)
    account_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    fill_time: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow, index=True, nullable=False
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    fill_price: Mapped[float] = mapped_column(Float, nullable=False)
    gross_amount: Mapped[float] = mapped_column(Float, nullable=False)
    slippage_paid: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    brokerage_fee: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    stt_fee: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    exchange_turnover_fee: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    sebi_fee: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    stamp_duty_fee: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    gst_fee: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    dp_charges: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    total_cost: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    net_amount: Mapped[float] = mapped_column(Float, nullable=False)

    order: Mapped[PaperOrder] = relationship("PaperOrder", back_populates="fill")


class PaperPosition(Base):
    __tablename__ = "paper_positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[str] = mapped_column(String(64), ForeignKey("strategy_accounts.id"), index=True, nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    strategy_id: Mapped[str] = mapped_column(String(64), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    entry_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    current_stop: Mapped[float] = mapped_column(Float, nullable=False)
    target_price: Mapped[float] = mapped_column(Float, nullable=False)
    sessions_held: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    highest_price_seen: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="OPEN", index=True, nullable=False)  # OPEN, CLOSED
    closed_date: Mapped[Optional[datetime.date]] = mapped_column(Date, nullable=True)
    close_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    close_reason: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)  # TARGET_HIT, STOP_LOSS, TIME_EXIT
    realized_pnl_gross: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    realized_pnl_net: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    total_fees_paid: Mapped[Optional[float]] = mapped_column(Float, default=0.0, nullable=True)
    target_achieved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False
    )

    account: Mapped[StrategyAccount] = relationship("StrategyAccount", back_populates="positions")


class PortfolioEquitySnapshot(Base):
    __tablename__ = "portfolio_equity_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[str] = mapped_column(String(64), ForeignKey("strategy_accounts.id"), index=True, nullable=False)
    date: Mapped[datetime.date] = mapped_column(Date, index=True, nullable=False)
    cash_balance: Mapped[float] = mapped_column(Float, nullable=False)
    invested_value: Mapped[float] = mapped_column(Float, nullable=False)
    total_equity: Mapped[float] = mapped_column(Float, nullable=False)
    unrealized_pnl: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    open_positions_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    recorded_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("account_id", "date", name="uq_snapshot_account_date"),
    )


class BacktestRunRecord(Base):
    __tablename__ = "backtest_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    strategy_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    start_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    end_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    universe_size: Mapped[int] = mapped_column(Integer, nullable=False)
    initial_capital: Mapped[float] = mapped_column(Float, default=100000.0, nullable=False)
    final_equity: Mapped[float] = mapped_column(Float, nullable=False)
    total_return_pct: Mapped[float] = mapped_column(Float, nullable=False)
    win_rate: Mapped[float] = mapped_column(Float, nullable=False)
    target_hit_rate: Mapped[float] = mapped_column(Float, nullable=False)
    profit_factor: Mapped[float] = mapped_column(Float, nullable=False)
    max_drawdown_pct: Mapped[float] = mapped_column(Float, nullable=False)
    sharpe_ratio: Mapped[float] = mapped_column(Float, nullable=False)
    sortino_ratio: Mapped[float] = mapped_column(Float, nullable=False)
    total_trades: Mapped[int] = mapped_column(Integer, nullable=False)
    total_fees: Mapped[float] = mapped_column(Float, nullable=False)
    metrics_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow, nullable=False
    )


class SystemLog(Base):
    __tablename__ = "system_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow, index=True, nullable=False
    )
    level: Mapped[str] = mapped_column(String(16), nullable=False)
    component: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class SchedulerJobLog(Base):
    __tablename__ = "scheduler_job_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_name: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    run_timestamp: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow, index=True, nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # SUCCESS, FAILED, SKIPPED
    duration_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
