"""
Database repository providing transactional persistence and query methods.
"""

from __future__ import annotations

import csv
import datetime
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, desc, func, select
from sqlalchemy.orm import Session

from indigo_quant.db.models import (
    CashLedger,
    HistoricalBar,
    Instrument,
    PaperOrder,
    PaperPosition,
    RejectedCandidate,
    SchedulerJobLog,
    SignalRecord,
    StrategyAccount,
    SystemLog,
)
from indigo_quant.db.session import Base, engine


def init_db(engine_instance=None) -> None:
    """Initialize database tables."""
    eng = engine_instance or engine
    Base.metadata.create_all(bind=eng)


def seed_universe_and_accounts(db: Session, universe_csv_path: str = "./config/universe.csv") -> None:
    """
    Seed initial universe instruments from CSV and initialize the 5 strategy accounts
    with ₹1,00,000 virtual capital each.
    """
    # 1. Seed instruments
    csv_file = Path(universe_csv_path)
    if csv_file.exists():
        with open(csv_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                symbol = row["symbol"].strip()
                existing = db.execute(select(Instrument).where(Instrument.symbol == symbol)).scalar_one_or_none()
                if not existing:
                    inst = Instrument(
                        symbol=symbol,
                        exchange=row.get("exchange", "NSE").strip(),
                        bse_code=row.get("bse_code", "").strip() or None,
                        isin=row.get("isin", "").strip() or None,
                        company_name=row.get("company_name", "").strip(),
                        sector=row.get("sector", "").strip() or None,
                        is_active=True,
                    )
                    db.add(inst)

    # 2. Seed 5 Strategy Accounts
    strategies = [
        ("trend_momentum", "Agent A: Trend Momentum", "1.0.0"),
        ("volume_breakout", "Agent B: Volume Breakout", "1.0.0"),
        ("bullish_pullback", "Agent C: Bullish Pullback Recovery", "1.0.0"),
        ("bollinger_squeeze", "Agent D: Bollinger Squeeze Breakout", "1.0.0"),
        ("consensus", "Agent E: Multi-Agent Consensus", "1.0.0"),
    ]

    for strat_id, strat_name, version in strategies:
        existing_acc = db.execute(select(StrategyAccount).where(StrategyAccount.id == strat_id)).scalar_one_or_none()
        if not existing_acc:
            acc = StrategyAccount(
                id=strat_id,
                name=strat_name,
                version=version,
                initial_capital=100000.0,
                current_cash=100000.0,
                current_equity=100000.0,
            )
            db.add(acc)
            db.flush()

            ledger = CashLedger(
                account_id=strat_id,
                timestamp=datetime.datetime.utcnow(),
                transaction_type="INITIAL_FUNDING",
                amount=100000.0,
                balance_after=100000.0,
                description="Initial virtual capital allocation of ₹1,00,000",
            )
            db.add(ledger)

    db.commit()


class Repository:
    """Encapsulates common database queries and transactions."""

    def __init__(self, db: Session):
        self.db = db

    # Instruments
    def get_active_instruments(self) -> List[Instrument]:
        return list(self.db.execute(select(Instrument).where(Instrument.is_active)).scalars().all())

    def get_instrument_by_symbol(self, symbol: str) -> Optional[Instrument]:
        return self.db.execute(select(Instrument).where(Instrument.symbol == symbol)).scalar_one_or_none()

    # Historical Bars
    def save_bars(self, bars_data: List[Dict[str, Any]]) -> int:
        count = 0
        for b in bars_data:
            existing = self.db.execute(
                select(HistoricalBar).where(
                    and_(
                        HistoricalBar.symbol == b["symbol"],
                        HistoricalBar.exchange == b.get("exchange", "NSE"),
                        HistoricalBar.date == b["date"],
                    )
                )
            ).scalar_one_or_none()
            if not existing:
                bar = HistoricalBar(
                    symbol=b["symbol"],
                    exchange=b.get("exchange", "NSE"),
                    date=b["date"],
                    open=float(b["open"]),
                    high=float(b["high"]),
                    low=float(b["low"]),
                    close=float(b["close"]),
                    volume=float(b["volume"]),
                    turnover=float(b["turnover"]) if b.get("turnover") is not None else None,
                    adj_close=float(b["adj_close"]) if b.get("adj_close") is not None else float(b["close"]),
                    provider=b.get("provider", "unknown"),
                    is_validated=b.get("is_validated", True),
                )
                self.db.add(bar)
                count += 1
            else:
                # Update bar in case newer adjusted values or volume fixes arrived
                existing.open = float(b["open"])
                existing.high = float(b["high"])
                existing.low = float(b["low"])
                existing.close = float(b["close"])
                existing.volume = float(b["volume"])
                if b.get("turnover") is not None:
                    existing.turnover = float(b["turnover"])
                if b.get("adj_close") is not None:
                    existing.adj_close = float(b["adj_close"])
                existing.provider = b.get("provider", existing.provider)
        self.db.commit()
        return count

    def get_bars(self, symbol: str, start_date: Optional[datetime.date] = None, end_date: Optional[datetime.date] = None) -> List[HistoricalBar]:
        stmt = select(HistoricalBar).where(HistoricalBar.symbol == symbol)
        if start_date:
            stmt = stmt.where(HistoricalBar.date >= start_date)
        if end_date:
            stmt = stmt.where(HistoricalBar.date <= end_date)
        stmt = stmt.order_by(HistoricalBar.date.asc())
        return list(self.db.execute(stmt).scalars().all())

    def get_latest_bar_date(self, symbol: str) -> Optional[datetime.date]:
        stmt = select(func.max(HistoricalBar.date)).where(HistoricalBar.symbol == symbol)
        return self.db.execute(stmt).scalar()

    # Signals
    def save_signal(self, sig: Dict[str, Any]) -> SignalRecord:
        existing = self.db.execute(
            select(SignalRecord).where(
                and_(
                    SignalRecord.symbol == sig["symbol"],
                    SignalRecord.strategy_id == sig["strategy_id"],
                    SignalRecord.signal_date == sig["signal_date"],
                )
            )
        ).scalar_one_or_none()

        if existing:
            rec = existing
        else:
            rec = SignalRecord(
                symbol=sig["symbol"],
                strategy_id=sig["strategy_id"],
                strategy_version=sig.get("strategy_version", "1.0.0"),
                signal_date=sig["signal_date"],
            )
            self.db.add(rec)

        rec.evaluation_timestamp = sig.get("evaluation_timestamp", datetime.datetime.utcnow())
        rec.decision = sig["decision"]
        rec.rule_quality_score = float(sig["rule_quality_score"])
        rec.reference_close = float(sig["reference_close"])
        rec.target_gain_pct = float(sig.get("target_gain_pct", 10.0))
        rec.target_price_estimate = float(sig["target_price_estimate"])
        rec.initial_stop_estimate = float(sig["initial_stop_estimate"])
        rec.stop_distance_pct = float(sig["stop_distance_pct"])
        rec.reward_to_risk_ratio = float(sig["reward_to_risk_ratio"])
        rec.rules_passed_json = json.dumps(sig.get("rules_passed", []))
        rec.rules_failed_json = json.dumps(sig.get("rules_failed", []))
        rec.regime_status = sig.get("regime_status", "UNKNOWN")
        rec.execution_status = sig.get("execution_status", "PENDING")
        rec.data_source = sig.get("data_source", "unknown")
        rec.data_timestamp = str(sig.get("data_timestamp", datetime.datetime.utcnow().isoformat()))

        self.db.commit()
        return rec

    def get_signals(
        self,
        signal_date: Optional[datetime.date] = None,
        strategy_id: Optional[str] = None,
        symbol: Optional[str] = None,
        decision_only: Optional[str] = "BUY",
    ) -> List[SignalRecord]:
        stmt = select(SignalRecord)
        if signal_date:
            stmt = stmt.where(SignalRecord.signal_date == signal_date)
        if strategy_id:
            stmt = stmt.where(SignalRecord.strategy_id == strategy_id)
        if symbol:
            stmt = stmt.where(SignalRecord.symbol == symbol)
        if decision_only:
            stmt = stmt.where(SignalRecord.decision == decision_only)
        stmt = stmt.order_by(desc(SignalRecord.rule_quality_score))
        return list(self.db.execute(stmt).scalars().all())

    # Rejected Candidates
    def log_rejection(self, symbol: str, strategy_id: str, date: datetime.date, reason: str, failed_conditions: List[str]) -> None:
        rec = RejectedCandidate(
            symbol=symbol,
            strategy_id=strategy_id,
            date=date,
            reason=reason,
            failed_conditions_json=json.dumps(failed_conditions),
            timestamp=datetime.datetime.utcnow(),
        )
        self.db.add(rec)
        self.db.commit()

    def get_rejected_candidates(self, date: Optional[datetime.date] = None, limit: int = 100) -> List[RejectedCandidate]:
        stmt = select(RejectedCandidate)
        if date:
            stmt = stmt.where(RejectedCandidate.date == date)
        stmt = stmt.order_by(desc(RejectedCandidate.timestamp)).limit(limit)
        return list(self.db.execute(stmt).scalars().all())

    # Strategy Accounts & Portfolio
    def get_accounts(self) -> List[StrategyAccount]:
        return list(self.db.execute(select(StrategyAccount)).scalars().all())

    def get_account(self, account_id: str) -> Optional[StrategyAccount]:
        return self.db.execute(select(StrategyAccount).where(StrategyAccount.id == account_id)).scalar_one_or_none()

    def get_open_positions(self, account_id: Optional[str] = None) -> List[PaperPosition]:
        stmt = select(PaperPosition).where(PaperPosition.status == "OPEN")
        if account_id:
            stmt = stmt.where(PaperPosition.account_id == account_id)
        return list(self.db.execute(stmt).scalars().all())

    def get_orders(self, account_id: Optional[str] = None, status: Optional[str] = None) -> List[PaperOrder]:
        stmt = select(PaperOrder)
        if account_id:
            stmt = stmt.where(PaperOrder.account_id == account_id)
        if status:
            stmt = stmt.where(PaperOrder.status == status)
        stmt = stmt.order_by(desc(PaperOrder.created_at))
        return list(self.db.execute(stmt).scalars().all())

    # System Logs & Scheduler
    def log_system_event(self, level: str, component: str, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        entry = SystemLog(
            timestamp=datetime.datetime.utcnow(),
            level=level,
            component=component,
            message=message,
            details_json=json.dumps(details, default=str) if details else None,
        )
        self.db.add(entry)
        self.db.commit()

    def log_job_run(self, job_name: str, status: str, duration: float, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        rec = SchedulerJobLog(
            job_name=job_name,
            run_timestamp=datetime.datetime.utcnow(),
            status=status,
            duration_seconds=duration,
            message=message,
            details_json=json.dumps(details, default=str) if details else None,
        )
        self.db.add(rec)
        self.db.commit()
