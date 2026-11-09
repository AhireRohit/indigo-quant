"""
Quantitative Performance and Risk Metrics Calculator.
Computes comprehensive portfolio and trade statistics from actual simulated backtest returns.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd


def calculate_performance_metrics(
    trades: List[Dict[str, Any]],
    equity_series: pd.Series,
    benchmark_equity: Optional[pd.Series] = None,
    risk_free_rate: float = 0.065,  # 6.5% Indian RBI repo / T-bill benchmark rate
) -> Dict[str, Any]:
    """
    Calculate comprehensive performance metrics from closed trades and daily equity.
    """
    total_trades = len(trades)
    if total_trades == 0:
        return {
            "total_trades": 0,
            "win_rate_pct": 0.0,
            "target_hit_rate_pct": 0.0,
            "total_net_pnl": 0.0,
            "profit_factor": 0.0,
            "max_drawdown_pct": 0.0,
            "sharpe_ratio": 0.0,
            "sortino_ratio": 0.0,
            "total_return_pct": 0.0,
            "message": "No trades executed during evaluation period.",
        }

    # Trade-level statistics
    pnl_list = [float(t["net_pnl"]) for t in trades]
    pnl_pct_list = [float(t["return_pct"]) for t in trades]
    duration_list = [int(t.get("sessions_held", 1)) for t in trades]
    fees_list = [float(t.get("total_fees", 0.0)) for t in trades]

    wins = [p for p in pnl_list if p > 0]
    losses = [p for p in pnl_list if p < 0]
    target_hits = [t for t in trades if t.get("target_achieved", False)]

    win_count = len(wins)
    loss_count = len(losses)
    win_rate = (win_count / total_trades) * 100.0
    target_hit_rate = (len(target_hits) / total_trades) * 100.0

    avg_win = float(np.mean(wins)) if wins else 0.0
    avg_loss = float(np.mean(losses)) if losses else 0.0
    gross_gains = sum(wins)
    gross_losses = abs(sum(losses))
    profit_factor = round(gross_gains / gross_losses, 2) if gross_losses > 0 else 999.0

    avg_holding_period = float(np.mean(duration_list)) if duration_list else 0.0
    total_fees_paid = sum(fees_list)
    total_net_pnl = sum(pnl_list)

    worst_trade = min(pnl_pct_list) if pnl_pct_list else 0.0
    best_trade = max(pnl_pct_list) if pnl_pct_list else 0.0

    # Equity Curve Statistics
    if len(equity_series) > 1:
        initial_equity = float(equity_series.iloc[0])
        final_equity = float(equity_series.iloc[-1])
        total_return_pct = ((final_equity - initial_equity) / initial_equity) * 100.0

        # Daily returns
        daily_returns = equity_series.pct_change().dropna()

        # Maximum Drawdown
        running_max = equity_series.cummax()
        drawdowns = (equity_series - running_max) / running_max
        max_drawdown_pct = float(drawdowns.min() * 100.0)

        # Annualized metrics (252 trading sessions)
        num_sessions = len(equity_series)
        years = max(num_sessions / 252.0, 0.01)
        cagr_pct = (((final_equity / initial_equity) ** (1.0 / years)) - 1.0) * 100.0 if final_equity > 0 else -100.0

        # Daily risk-free rate
        rf_daily = (1.0 + risk_free_rate) ** (1.0 / 252.0) - 1.0
        excess_returns = daily_returns - rf_daily

        std_daily = daily_returns.std()
        if std_daily > 0:
            sharpe_ratio = float((excess_returns.mean() / std_daily) * np.sqrt(252))
        else:
            sharpe_ratio = 0.0

        downside_returns = daily_returns[daily_returns < 0]
        downside_std = downside_returns.std()
        if downside_std > 0:
            sortino_ratio = float((excess_returns.mean() / downside_std) * np.sqrt(252))
        else:
            sortino_ratio = 0.0
    else:
        total_return_pct = 0.0
        cagr_pct = 0.0
        max_drawdown_pct = 0.0
        sharpe_ratio = 0.0
        sortino_ratio = 0.0

    # Benchmark-relative comparison
    benchmark_return_pct = 0.0
    alpha_pct = 0.0
    if benchmark_equity is not None and len(benchmark_equity) > 1:
        b_init = float(benchmark_equity.iloc[0])
        b_final = float(benchmark_equity.iloc[-1])
        benchmark_return_pct = ((b_final - b_init) / b_init) * 100.0
        alpha_pct = total_return_pct - benchmark_return_pct

    # Breakdown by Year
    trades_by_year: Dict[str, Dict[str, Any]] = {}
    for t in trades:
        yr = str(t["entry_date"].year if hasattr(t["entry_date"], "year") else str(t["entry_date"])[:4])
        if yr not in trades_by_year:
            trades_by_year[yr] = {"trades": 0, "wins": 0, "pnl": 0.0}
        trades_by_year[yr]["trades"] += 1
        trades_by_year[yr]["pnl"] += t["net_pnl"]
        if t["net_pnl"] > 0:
            trades_by_year[yr]["wins"] += 1

    yearly_summary = {}
    for yr, data in trades_by_year.items():
        cnt = data["trades"]
        yearly_summary[yr] = {
            "trades": cnt,
            "win_rate_pct": round((data["wins"] / cnt) * 100.0, 1),
            "net_pnl": round(data["pnl"], 2),
        }

    return {
        "total_trades": total_trades,
        "win_count": win_count,
        "loss_count": loss_count,
        "win_rate_pct": round(win_rate, 1),
        "target_hit_rate_pct": round(target_hit_rate, 1),
        "avg_win_inr": round(avg_win, 2),
        "avg_loss_inr": round(avg_loss, 2),
        "profit_factor": profit_factor,
        "avg_holding_sessions": round(avg_holding_period, 1),
        "total_fees_paid_inr": round(total_fees_paid, 2),
        "total_net_pnl_inr": round(total_net_pnl, 2),
        "worst_trade_pct": round(worst_trade, 2),
        "best_trade_pct": round(best_trade, 2),
        "total_return_pct": round(total_return_pct, 2),
        "cagr_pct": round(cagr_pct, 2),
        "max_drawdown_pct": round(max_drawdown_pct, 2),
        "sharpe_ratio": round(sharpe_ratio, 2),
        "sortino_ratio": round(sortino_ratio, 2),
        "benchmark_return_pct": round(benchmark_return_pct, 2),
        "alpha_pct": round(alpha_pct, 2),
        "yearly_summary": yearly_summary,
    }
