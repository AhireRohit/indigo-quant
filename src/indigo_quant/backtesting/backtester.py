"""
Walk-Forward Historical Backtesting Engine.
Rigorous historical simulation with next-day open execution (T+1),
conservative intrabar conflict priority, slippage, and statutory delivery fees.
"""

from __future__ import annotations

import datetime
import logging
from typing import Any, Dict, List, Optional

import pandas as pd

from indigo_quant.backtesting.metrics import calculate_performance_metrics
from indigo_quant.engine.market_regime import MarketRegimeEngine, MarketRegimeStatus
from indigo_quant.engine.ranking import RuleRankingEngine
from indigo_quant.engine.risk import RiskEngine
from indigo_quant.indicators.technical import calculate_all_indicators
from indigo_quant.paper.fees import IndianDeliveryCostModel
from indigo_quant.strategies.breakout import VolumeBreakoutStrategy
from indigo_quant.strategies.consensus import ConsensusStrategy
from indigo_quant.strategies.momentum import TrendMomentumStrategy
from indigo_quant.strategies.pullback import BullishPullbackStrategy
from indigo_quant.strategies.squeeze import BollingerSqueezeStrategy

logger = logging.getLogger(__name__)


class BacktestEngine:
    """
    Simulates strategy execution over historical bars.
    Ensures zero forward-looking leakage.
    """

    def __init__(
        self,
        initial_capital: float = 100000.0,
        cost_model: Optional[IndianDeliveryCostModel] = None,
    ):
        self.initial_capital = initial_capital
        self.cost_model = cost_model or IndianDeliveryCostModel()
        self.regime_engine = MarketRegimeEngine()
        self.risk_engine = RiskEngine()
        self.ranking_engine = RuleRankingEngine()

        self.strategy_map = {
            "trend_momentum": TrendMomentumStrategy(),
            "volume_breakout": VolumeBreakoutStrategy(),
            "bullish_pullback": BullishPullbackStrategy(),
            "bollinger_squeeze": BollingerSqueezeStrategy(),
        }
        self.consensus_strategy = ConsensusStrategy()

    def run(
        self,
        strategy_id: str,
        universe_dfs: Dict[str, pd.DataFrame],
        nifty_df: Optional[pd.DataFrame] = None,
        start_date: Optional[datetime.date] = None,
        end_date: Optional[datetime.date] = None,
    ) -> Dict[str, Any]:
        """
        Run backtest for a specific strategy or 'all'.
        """
        if strategy_id == "all":
            results = {}
            for sid in ["trend_momentum", "volume_breakout", "bullish_pullback", "bollinger_squeeze", "consensus"]:
                results[sid] = self._run_single_strategy(sid, universe_dfs, nifty_df, start_date, end_date)
            # Add Benchmark
            results["benchmark_nifty"] = self._run_benchmark(nifty_df, start_date, end_date)
            return results

        return self._run_single_strategy(strategy_id, universe_dfs, nifty_df, start_date, end_date)

    def _run_single_strategy(
        self,
        strategy_id: str,
        universe_dfs: Dict[str, pd.DataFrame],
        nifty_df: Optional[pd.DataFrame],
        start_date: Optional[datetime.date] = None,
        end_date: Optional[datetime.date] = None,
    ) -> Dict[str, Any]:
        """Run single strategy walk-forward backtest."""
        # 1. Precalculate indicators for all symbols
        prep_dfs: Dict[str, pd.DataFrame] = {}
        all_dates_set = set()

        for sym, df in universe_dfs.items():
            if df.empty or len(df) < 200:
                continue
            ind_df = calculate_all_indicators(df, benchmark_df=nifty_df)
            prep_dfs[sym] = ind_df
            all_dates_set.update(ind_df.index)

        if not all_dates_set:
            return {"error": "No valid data available for backtesting."}

        sorted_dates = sorted(list(all_dates_set))
        if start_date:
            sorted_dates = [d for d in sorted_dates if (d.date() if hasattr(d, "date") else d) >= start_date]
        if end_date:
            sorted_dates = [d for d in sorted_dates if (d.date() if hasattr(d, "date") else d) <= end_date]

        # Simulation state
        cash = self.initial_capital
        open_positions: List[Dict[str, Any]] = []  # list of open position dicts
        closed_trades: List[Dict[str, Any]] = []
        equity_records = []
        pending_orders: List[Dict[str, Any]] = []

        # Chronological day-by-day iteration
        for _t_idx, current_ts in enumerate(sorted_dates):
            current_date = current_ts.date() if hasattr(current_ts, "date") else current_ts

            # Price map for current session
            current_bars = {}
            for sym, df in prep_dfs.items():
                if current_ts in df.index:
                    row = df.loc[current_ts]
                    current_bars[sym] = {
                        "open": float(row["open"]),
                        "high": float(row["high"]),
                        "low": float(row["low"]),
                        "close": float(row["close"]),
                    }

            # A. First, process any PENDING orders generated on previous session (T-1) at TODAY'S OPEN (T)
            new_pending = []
            for ord_req in pending_orders:
                sym = ord_req["symbol"]
                bar = current_bars.get(sym)
                if not bar:
                    # Stale or no quote today, retain pending if not expired
                    ord_req["age"] += 1
                    if ord_req["age"] <= 2:
                        new_pending.append(ord_req)
                    continue

                open_p = bar["open"]
                # Gap check: if open > 5% above signal close, cancel
                gap_pct = (open_p - ord_req["signal_close"]) / ord_req["signal_close"]
                if gap_pct > 0.05:
                    continue  # Gap violated, cancel order

                # Simulate BUY fill at open + slippage
                fill_price = round(open_p * (1.0 + self.cost_model.slippage_pct), 2)
                fees = self.cost_model.calculate_charges("BUY", fill_price, ord_req["quantity"])

                if cash >= fees.effective_cash_impact:
                    cash -= fees.effective_cash_impact
                    stop_dist_pct = ord_req["stop_distance_pct"]
                    actual_stop = round(fill_price * (1.0 - stop_dist_pct), 2)
                    actual_target = round(fill_price * 1.10, 2)

                    open_positions.append({
                        "symbol": sym,
                        "quantity": ord_req["quantity"],
                        "entry_date": current_date,
                        "entry_price": fill_price,
                        "current_stop": actual_stop,
                        "target_price": actual_target,
                        "sessions_held": 0,
                        "highest_seen": fill_price,
                        "fees_paid": fees.total_charges + fees.slippage,
                    })

            pending_orders = new_pending

            # B. Second, evaluate OPEN POSITIONS for exits on current bar
            remaining_pos = []
            for pos in open_positions:
                sym = pos["symbol"]
                bar = current_bars.get(sym)
                if not bar:
                    remaining_pos.append(pos)
                    continue

                pos["sessions_held"] += 1
                open_p = bar["open"]
                high_p = bar["high"]
                low_p = bar["low"]
                close_p = bar["close"]

                if high_p > pos["highest_seen"]:
                    pos["highest_seen"] = high_p

                exit_triggered = False
                exit_price = 0.0
                exit_reason = ""

                # 1. Overnight gap below stop
                if open_p <= pos["current_stop"]:
                    exit_triggered = True
                    exit_price = open_p
                    exit_reason = "STOP_LOSS_GAP"
                # 2. Intrabar conflict: both stop and target crossed
                elif low_p <= pos["current_stop"] and high_p >= pos["target_price"]:
                    exit_triggered = True
                    exit_price = pos["current_stop"]  # Conservative rule: stop assumed hit first
                    exit_reason = "STOP_LOSS_INTRABAR_CONFLICT"
                # 3. Normal stop
                elif low_p <= pos["current_stop"]:
                    exit_triggered = True
                    exit_price = pos["current_stop"]
                    exit_reason = "STOP_LOSS"
                # 4. Target (+10% gross) hit
                elif high_p >= pos["target_price"]:
                    exit_triggered = True
                    exit_price = pos["target_price"]
                    exit_reason = "TARGET_HIT"
                # 5. Time exit: 20 sessions
                elif pos["sessions_held"] >= 20:
                    exit_triggered = True
                    exit_price = close_p
                    exit_reason = "TIME_EXIT"

                if exit_triggered:
                    sim_exit_price = round(exit_price * (1.0 - self.cost_model.slippage_pct), 2)
                    sell_fees = self.cost_model.calculate_charges("SELL", sim_exit_price, pos["quantity"])
                    cash += sell_fees.effective_cash_impact

                    cost_basis = pos["quantity"] * pos["entry_price"]
                    gross_pnl = (pos["quantity"] * sim_exit_price) - cost_basis
                    total_fees = pos["fees_paid"] + sell_fees.total_charges + sell_fees.slippage
                    net_pnl = gross_pnl - total_fees
                    ret_pct = (net_pnl / cost_basis) * 100.0

                    closed_trades.append({
                        "symbol": sym,
                        "entry_date": pos["entry_date"],
                        "exit_date": current_date,
                        "sessions_held": pos["sessions_held"],
                        "entry_price": pos["entry_price"],
                        "exit_price": sim_exit_price,
                        "quantity": pos["quantity"],
                        "gross_pnl": round(gross_pnl, 2),
                        "net_pnl": round(net_pnl, 2),
                        "return_pct": round(ret_pct, 2),
                        "total_fees": round(total_fees, 2),
                        "close_reason": exit_reason,
                        "target_achieved": (exit_reason == "TARGET_HIT") or (ret_pct >= 9.5),
                    })
                else:
                    remaining_pos.append(pos)

            open_positions = remaining_pos

            # C. Third, compute Marked-to-Market Equity at end of current day
            invested_val = sum(
                p["quantity"] * current_bars.get(p["symbol"], {}).get("close", p["entry_price"])
                for p in open_positions
            )
            total_equity = cash + invested_val
            equity_records.append({"date": current_date, "equity": total_equity, "cash": cash})

            # D. Fourth, evaluate signals on completed session T to queue orders for T+1
            # Check market regime on NIFTY up to current_ts
            allow_entries = True
            if nifty_df is not None:
                nifty_slice = nifty_df.loc[:current_ts]
                regime_status, _ = self.regime_engine.evaluate(nifty_slice)
                allow_entries = (regime_status == MarketRegimeStatus.BULLISH)

            if allow_entries and len(open_positions) < 5:
                # Scan universe candidates
                candidate_signals = []
                for sym, df in prep_dfs.items():
                    if current_ts not in df.index:
                        continue
                    # Skip if already holding this symbol
                    if any(p["symbol"] == sym for p in open_positions):
                        continue

                    df_slice = df.loc[:current_ts]
                    if len(df_slice) < 200:
                        continue

                    # Evaluate strategy
                    if strategy_id == "consensus":
                        # Run all 4 and see if >= 2 agree
                        sub_results = [
                            strat.evaluate(sym, df_slice)
                            for strat in self.strategy_map.values()
                        ]
                        c_res = self.consensus_strategy.evaluate_consensus(
                            symbol=sym,
                            eval_date=current_date,
                            close_price=float(df.loc[current_ts]["close"]),
                            strategy_results=sub_results,
                        )
                        res = c_res
                    else:
                        strat = self.strategy_map[strategy_id]
                        res = strat.evaluate(sym, df_slice)

                    if res.decision == "BUY":
                        row = df.loc[current_ts]
                        close_p = float(row["close"])
                        atr14 = float(row["atr14"])

                        risk_eval = self.risk_engine.evaluate_candidate(
                            entry_price=close_p,
                            atr14=atr14,
                            portfolio_equity=total_equity,
                            available_cash=cash,
                            current_open_positions_count=len(open_positions),
                            current_invested_capital=invested_val,
                        )
                        if risk_eval.is_approved:
                            score, _ = self.ranking_engine.calculate_score(row)
                            turnover = float(row.get("turnover", close_p * row.get("volume", 0)))
                            candidate_signals.append({
                                "symbol": sym,
                                "signal_close": close_p,
                                "quantity": risk_eval.recommended_quantity,
                                "stop_distance_pct": risk_eval.stop_distance_pct,
                                "score": score,
                                "turnover": turnover,
                            })

                # Rank candidates
                candidate_signals.sort(key=lambda x: (-x["score"], -x["turnover"]))

                # Queue top candidates that fit available slots
                available_slots = 5 - len(open_positions)
                for cand in candidate_signals[:available_slots]:
                    pending_orders.append({
                        "symbol": cand["symbol"],
                        "signal_close": cand["signal_close"],
                        "quantity": cand["quantity"],
                        "stop_distance_pct": cand["stop_distance_pct"],
                        "age": 0,
                    })

        # Calculate final performance metrics
        eq_df = pd.DataFrame(equity_records)
        eq_series = eq_df.set_index("date")["equity"] if not eq_df.empty else pd.Series([self.initial_capital])
        metrics = calculate_performance_metrics(closed_trades, eq_series)

        return {
            "strategy_id": strategy_id,
            "initial_capital": self.initial_capital,
            "final_equity": round(float(eq_series.iloc[-1]), 2) if not eq_series.empty else self.initial_capital,
            "metrics": metrics,
            "trades_count": len(closed_trades),
            "trades": closed_trades,
            "equity_curve": eq_df.to_dict(orient="records"),
        }

    def _run_benchmark(
        self,
        nifty_df: Optional[pd.DataFrame],
        start_date: Optional[datetime.date] = None,
        end_date: Optional[datetime.date] = None,
    ) -> Dict[str, Any]:
        """Compute simple NIFTY 50 buy & hold performance over the same period."""
        if nifty_df is None or nifty_df.empty:
            return {"error": "Benchmark data unavailable."}

        df = nifty_df.copy()
        dates_idx = [d.date() if hasattr(d, "date") else d for d in df.index]
        if start_date:
            df = df[[d >= start_date for d in dates_idx]]
            dates_idx = [d.date() if hasattr(d, "date") else d for d in df.index]
        if end_date:
            df = df[[d <= end_date for d in dates_idx]]
            dates_idx = [d.date() if hasattr(d, "date") else d for d in df.index]

        if df.empty:
            return {"error": "No overlapping benchmark bars."}

        init_close = float(df["close"].iloc[0])
        eq_series = (df["close"] / init_close) * self.initial_capital
        eq_df = pd.DataFrame({"date": dates_idx, "equity": eq_series.values})
        metrics = calculate_performance_metrics([], eq_series)

        return {
            "strategy_id": "benchmark_nifty",
            "initial_capital": self.initial_capital,
            "final_equity": round(float(eq_series.iloc[-1]), 2),
            "metrics": metrics,
            "equity_curve": eq_df.to_dict(orient="records"),
        }
