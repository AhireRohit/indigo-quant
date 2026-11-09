"""
FastAPI REST API Server for Indigo Quant.
Provides programmatic access to market regime, indicators, signals,
paper portfolio balances, positions, orders, and backtests.
Strictly paper execution only — no real-money or brokerage execution endpoints.
"""

from __future__ import annotations

import datetime
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from indigo_quant.data.calendar import is_market_open, now_ist
from indigo_quant.db.models import (
    PaperPosition,
)
from indigo_quant.db.repository import Repository, init_db
from indigo_quant.db.session import get_db
from indigo_quant.engine.market_regime import MarketRegimeEngine
from indigo_quant.indicators.technical import calculate_all_indicators
from indigo_quant.paper.broker import SimulatedPaperBroker
from indigo_quant.paper.orders import CreatePaperOrderRequest


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(
    title="INDIGO QUANT API",
    description="Autonomous Indian Equity Swing-Trading Research & Paper Brokerage Platform",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["System"])
def health_check(db: Session = Depends(get_db)):
    """Liveness probe and system health indicator."""
    repo = Repository(db)
    accounts = repo.get_accounts()
    return {
        "status": "healthy",
        "app": "INDIGO QUANT",
        "version": "1.0.0",
        "timestamp_ist": now_ist().isoformat(),
        "database_connected": True,
        "active_strategy_accounts": len(accounts),
    }


@app.get("/market/status", tags=["Market"])
def get_market_status(db: Session = Depends(get_db)):
    """Returns current market session status and NIFTY 50 benchmark regime."""
    repo = Repository(db)
    bars = repo.get_bars("^NSEI")
    if not bars:
        return {
            "is_market_open": is_market_open(),
            "regime": "UNKNOWN",
            "message": "NIFTY 50 data not yet synchronized in local database.",
        }

    import pandas as pd
    df = pd.DataFrame([
        {"date": b.date, "open": b.open, "high": b.high, "low": b.low, "close": b.close, "volume": b.volume}
        for b in bars
    ]).set_index("date")

    regime_engine = MarketRegimeEngine()
    status, details = regime_engine.evaluate(df)

    return {
        "is_market_open": is_market_open(),
        "regime": status.value,
        "details": details,
        "timestamp_ist": now_ist().isoformat(),
    }


@app.get("/market/indicators/{symbol}", tags=["Market"])
def get_indicators(symbol: str, db: Session = Depends(get_db)):
    """Retrieve the latest computed indicators for a symbol."""
    repo = Repository(db)
    clean_sym = symbol.replace(".NS", "").replace(".BO", "").upper()
    bars = repo.get_bars(clean_sym)
    if not bars or len(bars) < 30:
        raise HTTPException(
            status_code=404,
            detail=f"Insufficient historical bars for {clean_sym} in database.",
        )

    import pandas as pd
    df = pd.DataFrame([
        {"date": b.date, "open": b.open, "high": b.high, "low": b.low, "close": b.close, "volume": b.volume}
        for b in bars
    ]).set_index("date")

    ind_df = calculate_all_indicators(df)
    latest_row = ind_df.iloc[-1].to_dict()

    # Convert NaNs to None for clean JSON serialization
    clean_metrics = {k: (None if isinstance(v, float) and (v != v) else v) for k, v in latest_row.items()}

    return {
        "symbol": clean_sym,
        "date": str(ind_df.index[-1]),
        "indicators": clean_metrics,
    }


@app.get("/signals", tags=["Signals"])
def get_signals(
    signal_date: Optional[datetime.date] = Query(None),
    strategy_id: Optional[str] = Query(None),
    decision: Optional[str] = Query("BUY"),
    db: Session = Depends(get_db),
):
    """Retrieve ranked quantitative BUY signals."""
    repo = Repository(db)
    signals = repo.get_signals(signal_date=signal_date, strategy_id=strategy_id, decision_only=decision)
    return [
        {
            "symbol": s.symbol,
            "strategy_id": s.strategy_id,
            "signal_date": s.signal_date.isoformat(),
            "decision": s.decision,
            "rule_quality_score": s.rule_quality_score,
            "reference_close": s.reference_close,
            "target_price_estimate": s.target_price_estimate,
            "initial_stop_estimate": s.initial_stop_estimate,
            "stop_distance_pct": s.stop_distance_pct,
            "reward_to_risk_ratio": s.reward_to_risk_ratio,
            "regime_status": s.regime_status,
            "execution_status": s.execution_status,
        }
        for s in signals
    ]


@app.get("/signals/{symbol}", tags=["Signals"])
def get_signals_by_symbol(symbol: str, db: Session = Depends(get_db)):
    """Retrieve all signals generated for a specific stock."""
    clean_sym = symbol.replace(".NS", "").replace(".BO", "").upper()
    repo = Repository(db)
    signals = repo.get_signals(symbol=clean_sym, decision_only=None)
    return [
        {
            "symbol": s.symbol,
            "strategy_id": s.strategy_id,
            "signal_date": s.signal_date.isoformat(),
            "decision": s.decision,
            "rule_quality_score": s.rule_quality_score,
            "reference_close": s.reference_close,
            "target_price_estimate": s.target_price_estimate,
            "initial_stop_estimate": s.initial_stop_estimate,
            "execution_status": s.execution_status,
        }
        for s in signals
    ]


@app.get("/agents", tags=["Agents"])
def list_agents(db: Session = Depends(get_db)):
    """List all 5 competing strategy accounts."""
    repo = Repository(db)
    accounts = repo.get_accounts()
    return [
        {
            "id": a.id,
            "name": a.name,
            "version": a.version,
            "initial_capital": a.initial_capital,
            "current_cash": a.current_cash,
            "current_equity": a.current_equity,
        }
        for a in accounts
    ]


@app.get("/agents/{agent_id}/portfolio", tags=["Agents"])
def get_agent_portfolio(agent_id: str, db: Session = Depends(get_db)):
    """Get portfolio summary for a specific agent."""
    repo = Repository(db)
    acc = repo.get_account(agent_id)
    if not acc:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found.")

    positions = repo.get_open_positions(agent_id)
    invested = sum(p.quantity * p.entry_price for p in positions)

    return {
        "agent_id": acc.id,
        "name": acc.name,
        "cash": acc.current_cash,
        "invested_capital": invested,
        "total_equity": acc.current_equity,
        "open_positions_count": len(positions),
    }


@app.get("/agents/{agent_id}/positions", tags=["Agents"])
def get_agent_positions(agent_id: str, status: Optional[str] = "OPEN", db: Session = Depends(get_db)):
    """Get open or closed positions for an agent."""
    stmt = select(PaperPosition).where(PaperPosition.account_id == agent_id)
    if status:
        stmt = stmt.where(PaperPosition.status == status.upper())
    positions = list(db.execute(stmt).scalars().all())

    return [
        {
            "id": p.id,
            "symbol": p.symbol,
            "quantity": p.quantity,
            "entry_date": p.entry_date.isoformat(),
            "entry_price": p.entry_price,
            "current_stop": p.current_stop,
            "target_price": p.target_price,
            "sessions_held": p.sessions_held,
            "status": p.status,
            "realized_pnl_net": p.realized_pnl_net,
            "target_achieved": p.target_achieved,
        }
        for p in positions
    ]


@app.get("/agents/{agent_id}/orders", tags=["Agents"])
def get_agent_orders(agent_id: str, status: Optional[str] = None, db: Session = Depends(get_db)):
    """Get order history for an agent."""
    repo = Repository(db)
    orders = repo.get_orders(account_id=agent_id, status=status)
    return [
        {
            "id": o.id,
            "symbol": o.symbol,
            "side": o.order_side,
            "quantity": o.quantity,
            "signal_price": o.signal_price,
            "fill_price": o.fill_price,
            "status": o.status,
            "rejection_reason": o.rejection_reason,
            "created_at": o.created_at.isoformat(),
        }
        for o in orders
    ]


@app.post("/paper/orders", tags=["Paper Brokerage"], status_code=status.HTTP_201_CREATED)
def submit_paper_order(req: CreatePaperOrderRequest, db: Session = Depends(get_db)):
    """
    Submit a simulated paper order.
    Strictly simulated paper brokerage only.
    """
    broker = SimulatedPaperBroker(db)
    order = broker.submit_buy_order(req)
    return {
        "order_id": order.id,
        "status": order.status,
        "symbol": order.symbol,
        "quantity": order.quantity,
        "rejection_reason": order.rejection_reason,
    }


@app.get("/paper/trades", tags=["Paper Brokerage"])
def get_closed_trades(agent_id: Optional[str] = None, db: Session = Depends(get_db)):
    """List all closed paper trades."""
    stmt = select(PaperPosition).where(PaperPosition.status == "CLOSED")
    if agent_id:
        stmt = stmt.where(PaperPosition.account_id == agent_id)
    stmt = stmt.order_by(desc(PaperPosition.closed_date))
    trades = list(db.execute(stmt).scalars().all())

    return [
        {
            "id": t.id,
            "account_id": t.account_id,
            "symbol": t.symbol,
            "entry_date": t.entry_date.isoformat(),
            "closed_date": t.closed_date.isoformat() if t.closed_date else None,
            "entry_price": t.entry_price,
            "close_price": t.close_price,
            "quantity": t.quantity,
            "sessions_held": t.sessions_held,
            "realized_pnl_gross": t.realized_pnl_gross,
            "realized_pnl_net": t.realized_pnl_net,
            "total_fees_paid": t.total_fees_paid,
            "close_reason": t.close_reason,
            "target_achieved": t.target_achieved,
        }
        for t in trades
    ]
