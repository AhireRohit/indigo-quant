"""
Deterministic Decision Engine.
Coordinates: MARKET DATA -> INDICATORS -> STRATEGY RULES -> MARKET REGIME -> RISK ENGINE -> SIGNAL RANKING -> SIGNALS.
Zero subjectivity. Zero LLM override of numerical rules. Fully reproducible.
"""

from __future__ import annotations

import datetime
import logging
from typing import Any, Dict, List, Optional

import pandas as pd
from sqlalchemy.orm import Session

from indigo_quant.db.repository import Repository
from indigo_quant.engine.market_regime import MarketRegimeEngine, MarketRegimeStatus
from indigo_quant.engine.ranking import RuleRankingEngine
from indigo_quant.engine.risk import RiskEngine
from indigo_quant.indicators.technical import calculate_all_indicators
from indigo_quant.paper.portfolio import PortfolioManager
from indigo_quant.strategies.base import StrategyEvaluationResult
from indigo_quant.strategies.breakout import VolumeBreakoutStrategy
from indigo_quant.strategies.consensus import ConsensusStrategy
from indigo_quant.strategies.momentum import TrendMomentumStrategy
from indigo_quant.strategies.pullback import BullishPullbackStrategy
from indigo_quant.strategies.squeeze import BollingerSqueezeStrategy

logger = logging.getLogger(__name__)


class DecisionEngine:
    """
    Evaluates market data against technical strategies, market regime, risk controls,
    and ranking logic to generate structured signals.
    """

    def __init__(self, db: Session):
        self.db = db
        self.repo = Repository(db)
        self.regime_engine = MarketRegimeEngine()
        self.risk_engine = RiskEngine()
        self.ranking_engine = RuleRankingEngine()

        # Instantiate the 4 competing baseline strategies + Consensus
        self.strategies = {
            "trend_momentum": TrendMomentumStrategy(),
            "volume_breakout": VolumeBreakoutStrategy(),
            "bullish_pullback": BullishPullbackStrategy(),
            "bollinger_squeeze": BollingerSqueezeStrategy(),
        }
        self.consensus_strategy = ConsensusStrategy()

    def run_daily_scan(
        self,
        symbols_data: Dict[str, pd.DataFrame],
        nifty_df: Optional[pd.DataFrame],
        target_date: Optional[datetime.date] = None,
    ) -> Dict[str, Any]:
        """
        Execute complete deterministic decision scan across all symbols.
        Returns a structured dictionary of qualified BUY signals and rejections.
        """
        # 1. Evaluate Market Regime
        regime_status, regime_details = self.regime_engine.evaluate(nifty_df)
        allow_entries = (regime_status == MarketRegimeStatus.BULLISH)

        logger.info("Market Regime: %s (Allow Entries: %s)", regime_status.value, allow_entries)

        all_signals: List[Dict[str, Any]] = []
        all_rejections: List[Dict[str, Any]] = []

        # 2. Iterate through each stock in the universe
        for symbol, raw_df in symbols_data.items():
            if raw_df is None or raw_df.empty or len(raw_df) < 200:
                self.repo.log_rejection(
                    symbol=symbol,
                    strategy_id="all",
                    date=target_date or datetime.date.today(),
                    reason="Insufficient history (< 200 bars).",
                    failed_conditions=["min_bars_requirement"],
                )
                continue

            # Compute indicators
            try:
                df = calculate_all_indicators(raw_df, benchmark_df=nifty_df)
            except Exception as e:
                logger.error("Failed calculating indicators for %s: %s", symbol, e)
                continue

            # Target observation row
            eval_idx = -1
            eval_dt = df.index[eval_idx]
            eval_date = eval_dt.date() if hasattr(eval_dt, "date") else pd.to_datetime(eval_dt).date()

            if target_date and eval_date != target_date:
                # If specific target date was requested, find corresponding row
                matching_rows = df.index[df.index.date == target_date] if hasattr(df.index, "date") else []
                if len(matching_rows) > 0:
                    eval_idx = df.index.get_loc(matching_rows[0])
                    eval_date = target_date

            row = df.iloc[eval_idx]
            ref_close = float(row["close"])
            atr14 = float(row["atr14"])

            # 3. Evaluate 4 independent strategies
            eval_results: List[StrategyEvaluationResult] = []
            for _strat_id, strategy in self.strategies.items():
                res = strategy.evaluate(symbol, df, idx=eval_idx)
                eval_results.append(res)

            # 4. Evaluate Consensus strategy
            consensus_res = self.consensus_strategy.evaluate_consensus(
                symbol=symbol,
                eval_date=eval_date,
                close_price=ref_close,
                strategy_results=eval_results,
            )
            eval_results.append(consensus_res)

            # 5. Process results for each strategy
            for res in eval_results:
                strat_id = res.strategy_id

                # If strategy rules failed
                if res.decision != "BUY":
                    self.repo.log_rejection(
                        symbol=symbol,
                        strategy_id=strat_id,
                        date=eval_date,
                        reason=res.rejection_reason or "Mandatory conditions failed.",
                        failed_conditions=res.rules_failed,
                    )
                    all_rejections.append({
                        "symbol": symbol,
                        "strategy_id": strat_id,
                        "date": eval_date,
                        "reason": res.rejection_reason,
                        "failed_conditions": res.rules_failed,
                    })
                    continue

                # Strategy passed numeric rules! Now check Market Regime Filter
                if not allow_entries:
                    reason = f"Market regime is {regime_status.value}. New entries blocked."
                    self.repo.log_rejection(
                        symbol=symbol,
                        strategy_id=strat_id,
                        date=eval_date,
                        reason=reason,
                        failed_conditions=["market_regime_bullish"],
                    )
                    all_rejections.append({
                        "symbol": symbol,
                        "strategy_id": strat_id,
                        "date": eval_date,
                        "reason": reason,
                        "failed_conditions": ["market_regime_bullish"],
                    })
                    continue

                # Evaluate Risk & Position Sizing constraints
                pm = PortfolioManager(self.db, strat_id)
                acc = pm.get_account()
                open_pos = pm.get_open_positions()
                invested_cap = sum(p.quantity * p.entry_price for p in open_pos)

                risk_eval = self.risk_engine.evaluate_candidate(
                    entry_price=ref_close,
                    atr14=atr14,
                    portfolio_equity=acc.current_equity,
                    available_cash=acc.current_cash,
                    current_open_positions_count=len(open_pos),
                    current_invested_capital=invested_cap,
                )

                if not risk_eval.is_approved:
                    self.repo.log_rejection(
                        symbol=symbol,
                        strategy_id=strat_id,
                        date=eval_date,
                        reason=f"Risk check rejected: {risk_eval.rejection_reason}",
                        failed_conditions=[f"risk_engine: {risk_eval.rejection_reason}"],
                    )
                    all_rejections.append({
                        "symbol": symbol,
                        "strategy_id": strat_id,
                        "date": eval_date,
                        "reason": risk_eval.rejection_reason,
                        "failed_conditions": [risk_eval.rejection_reason],
                    })
                    continue

                # Compute deterministic Rule Quality Ranking Score (0 - 100)
                rule_score, score_components = self.ranking_engine.calculate_score(row)

                # Construct Qualified BUY Signal
                turnover_20 = float(row.get("turnover", ref_close * row.get("volume", 0)))
                sig_record = {
                    "symbol": symbol,
                    "strategy_id": strat_id,
                    "strategy_version": res.strategy_version,
                    "signal_date": eval_date,
                    "evaluation_timestamp": datetime.datetime.utcnow(),
                    "decision": "BUY",
                    "rule_quality_score": rule_score,
                    "reference_close": round(ref_close, 2),
                    "target_gain_pct": 10.0,
                    "target_price_estimate": risk_eval.target_price,
                    "initial_stop_estimate": risk_eval.stop_price,
                    "stop_distance_pct": risk_eval.stop_distance_pct,
                    "reward_to_risk_ratio": risk_eval.reward_to_risk_ratio,
                    "recommended_quantity": risk_eval.recommended_quantity,
                    "rules_passed": res.rules_passed,
                    "rules_failed": res.rules_failed,
                    "score_components": score_components,
                    "regime_status": regime_status.value,
                    "execution_status": "PENDING",
                    "data_source": raw_df.attrs.get("provider", "market_data"),
                    "data_timestamp": str(eval_dt),
                    "avg_traded_value_20": turnover_20,
                }

                # Persist to DB
                self.repo.save_signal(sig_record)
                all_signals.append(sig_record)

        # 6. Rank Qualified BUY Signals deterministically
        # Tie-break rule: Rule Score DESC, Average Traded Value DESC, Symbol ASC
        all_signals.sort(
            key=lambda s: (-s["rule_quality_score"], -s["avg_traded_value_20"], s["symbol"])
        )

        return {
            "date": target_date or datetime.date.today(),
            "regime": regime_status.value,
            "regime_details": regime_details,
            "scanned_symbols_count": len(symbols_data),
            "qualified_signals_count": len(all_signals),
            "rejections_count": len(all_rejections),
            "signals": all_signals,
            "rejections": all_rejections,
        }
