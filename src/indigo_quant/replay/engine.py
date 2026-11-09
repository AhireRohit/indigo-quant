"""
Causal Market Replay Engine for INDIGO QUANT.
Coordinates candle-by-candle simulation, strict no-lookahead indicator reveals,
strategy evaluations, order processing, and timeline recording.
Supports both Intraday Mode (5m) and Swing Mode (Daily).
"""

from __future__ import annotations

import datetime
import logging
from typing import Any, Dict, List, Literal, Optional, Tuple, Union

import numpy as np
import pandas as pd
from pydantic import BaseModel
import yfinance as yf

from indigo_quant.data.intraday_adapter import IntradayDataAdapter
from indigo_quant.indicators.intraday import calculate_all_intraday_indicators
from indigo_quant.indicators.technical import calculate_all_indicators
from indigo_quant.replay.broker import ReplayBroker, ReplayOrder, ReplayPosition, ReplayTrade
from indigo_quant.strategies import (
    BaseStrategy,
    BollingerSqueezeStrategy,
    BullishPullbackStrategy,
    ConsensusStrategy,
    StrategyEvaluationResult,
    TrendMomentumStrategy,
    VolumeBreakoutStrategy,
)
from indigo_quant.strategies.intraday import (
    BaseIntradayStrategy,
    IntradayEMAPullbackStrategy,
    IntradayEvaluationResult,
    IntradayOpeningRangeBreakoutStrategy,
    IntradayVolatilityBreakoutStrategy,
    IntradayVWAPMomentumStrategy,
)

logger = logging.getLogger(__name__)


class TimelineEvent(BaseModel):
    time: str
    event_type: str  # "INFO", "SIGNAL", "FILL", "EXIT", "REJECTION"
    description: str
    candle_idx: int


class ReplayEngine:
    """
    Simulates a historical trading session candle-by-candle with zero future information leakage.
    Supports both Intraday Mode (5m) and Swing Mode (Daily).
    """

    def __init__(
        self,
        symbol: str = "RELIANCE",
        session_date: Optional[datetime.date] = None,
        interval: str = "5m",
        mode: Literal["INTRADAY", "SWING"] = "INTRADAY",
        selected_strategies: Optional[List[str]] = None,
        initial_capital: float = 100000.0,
    ):
        self.symbol = symbol.upper()
        self.session_date = session_date or datetime.date(2026, 11, 9)
        self.interval = interval
        self.mode = mode
        self.initial_capital = initial_capital

        # Strategy registries
        self.intraday_strategy_registry: Dict[str, BaseIntradayStrategy] = {
            "intraday_vwap_momentum": IntradayVWAPMomentumStrategy(),
            "intraday_opening_range_breakout": IntradayOpeningRangeBreakoutStrategy(),
            "intraday_ema_pullback": IntradayEMAPullbackStrategy(),
            "intraday_volatility_breakout": IntradayVolatilityBreakoutStrategy(),
        }

        self.swing_strategy_registry: Dict[str, BaseStrategy] = {
            "trend_momentum": TrendMomentumStrategy(),
            "bullish_pullback": BullishPullbackStrategy(),
            "volume_breakout": VolumeBreakoutStrategy(),
            "bollinger_squeeze": BollingerSqueezeStrategy(),
            "consensus": ConsensusStrategy(),
        }

        if self.mode == "INTRADAY":
            self.strategy_registry = self.intraday_strategy_registry
            self.enabled_strategies = selected_strategies or list(self.intraday_strategy_registry.keys())
        else:
            self.strategy_registry = self.swing_strategy_registry
            self.enabled_strategies = selected_strategies or list(self.swing_strategy_registry.keys())

        self.adapter = IntradayDataAdapter()
        self.target_df: Optional[pd.DataFrame] = None
        self.combined_df: Optional[pd.DataFrame] = None
        self.warmed_up_indicators_df: Optional[pd.DataFrame] = None
        self.session_candles_df: Optional[pd.DataFrame] = None
        self.metadata: Dict[str, Any] = {}

        # Simulation state
        self.current_step = 0
        self.total_steps = 0
        self.broker = ReplayBroker(
            strategies=self.enabled_strategies,
            initial_capital_per_agent=self.initial_capital,
            mode=self.mode,
        )
        self.timeline: List[Dict[str, Any]] = []
        self.latest_decisions: Dict[str, Union[IntradayEvaluationResult, StrategyEvaluationResult]] = {}
        self.is_loaded = False

    def load_data(self) -> bool:
        """Fetch and prepare warmed-up indicators for the selected session."""
        if self.mode == "SWING" or self.interval == "1d":
            return self._load_swing_data()
        return self._load_intraday_data()

    def _load_intraday_data(self) -> bool:
        target_df, combined_df, meta = self.adapter.get_warmed_up_intraday_data(
            self.symbol,
            self.session_date,
            interval=self.interval,
            warm_up_sessions=3,
        )
        self.metadata = meta

        if target_df is None or target_df.empty:
            return False

        self.target_df = target_df
        self.combined_df = combined_df

        # Compute indicators strictly causally
        self.warmed_up_indicators_df = calculate_all_intraday_indicators(combined_df)
        # Extract subset belonging exclusively to target session date
        dates = (
            self.warmed_up_indicators_df.index.date
            if hasattr(self.warmed_up_indicators_df.index, "date")
            else pd.to_datetime(self.warmed_up_indicators_df.index).dt.date
        )
        self.session_candles_df = self.warmed_up_indicators_df[dates == self.session_date].copy()

        self.total_steps = len(self.session_candles_df)
        self.current_step = 0
        self.is_loaded = True
        self.reset()
        return True

    def _load_swing_data(self) -> bool:
        """Load 1-year daily history for swing simulation."""
        clean_sym, yf_sym = self.adapter.normalize_symbol(self.symbol)
        try:
            ticker = yf.Ticker(yf_sym)
            raw = ticker.history(period="1y", interval="1d")
        except Exception as e:
            logger.error("Failed fetching daily bars for %s: %s", yf_sym, e)
            return False

        if raw is None or raw.empty:
            return False

        # Normalize columns
        raw = raw.rename(columns={
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
        })
        for c in ["open", "high", "low", "close", "volume"]:
            if c not in raw.columns:
                return False

        # Calculate daily indicators
        df_ind = calculate_all_indicators(raw)
        self.warmed_up_indicators_df = df_ind

        # Target recent 40 daily trading bars for replay
        self.session_candles_df = df_ind.tail(40).copy()
        self.total_steps = len(self.session_candles_df)
        self.current_step = 0
        self.is_loaded = True
        self.reset()
        return True

    def reset(self) -> None:
        """Reset replay state to Step 0."""
        self.current_step = 0
        self.broker = ReplayBroker(
            strategies=self.enabled_strategies,
            initial_capital_per_agent=self.initial_capital,
            mode=self.mode,
        )
        start_time_label = "09:15" if self.mode == "INTRADAY" else "Day 1"
        self.timeline = [
            {
                "time": start_time_label,
                "type": "INFO",
                "description": f"Simulation initialized for {self.symbol} ({self.mode} Mode). Virtual initial capital: ₹1,00,000.",
                "candle_idx": 0,
            }
        ]
        self.latest_decisions = {}

    def step_to(self, target_step: int) -> None:
        """
        Advance simulation forward or rewind safely to `target_step`.
        If rewinding, resets and replays up to `target_step` to guarantee causal determinism.
        """
        if not self.is_loaded or self.session_candles_df is None:
            return

        target_step = max(0, min(target_step, self.total_steps))

        if target_step < self.current_step:
            # Rewind: reset and step forward
            self.reset()

        while self.current_step < target_step:
            self._advance_one_candle()

    def _advance_one_candle(self) -> None:
        """
        Advance the simulation by exactly one completed candle.
        Strict Execution Sequence:
        1. Process pending orders at the OPEN of this new candle.
        2. Evaluate intra-bar exits on this candle's HIGH/LOW/CLOSE.
        3. Evaluate strategy rules on this newly revealed completed candle.
        4. If BUY, queue order for NEXT candle open.
        """
        if self.session_candles_df is None or self.current_step >= self.total_steps:
            return

        candle_row = self.session_candles_df.iloc[self.current_step]
        candle_ts = self.session_candles_df.index[self.current_step]
        candle_dt = candle_ts.to_pydatetime() if hasattr(candle_ts, "to_pydatetime") else pd.to_datetime(candle_ts).to_pydatetime()

        if self.mode == "INTRADAY":
            candle_time_str = candle_dt.strftime("%H:%M")
        else:
            candle_time_str = candle_dt.strftime("%Y-%m-%d")

        c_open = float(candle_row["open"])
        c_high = float(candle_row["high"])
        c_low = float(candle_row["low"])
        c_close = float(candle_row["close"])

        # 1. Execute pending orders from prior candle at THIS candle's OPEN
        fill_results = self.broker.process_pending_orders_at_open(self.symbol, c_open, candle_dt)
        for order, fill_msg in fill_results:
            self.timeline.append({
                "time": candle_time_str,
                "type": "FILL" if order.status == "FILLED" else "REJECTION",
                "description": f"[{order.strategy_id}] {fill_msg}",
                "candle_idx": self.current_step,
            })

        # 2. Evaluate intra-bar exits on open positions
        is_last_candle = (self.current_step == self.total_steps - 1)
        if self.mode == "INTRADAY":
            is_end_of_session = is_last_candle or (candle_time_str >= "15:25")
        else:
            is_end_of_session = False  # Swing positions carry over

        candle_dict = {
            "open": c_open,
            "high": c_high,
            "low": c_low,
            "close": c_close,
            "time": candle_dt,
        }
        exit_results = self.broker.evaluate_candle_exits(self.symbol, candle_dict, is_end_of_session=is_end_of_session)
        for trade, exit_msg in exit_results:
            self.timeline.append({
                "time": candle_time_str,
                "type": "EXIT",
                "description": f"[{trade.strategy_id}] {exit_msg}",
                "candle_idx": self.current_step,
            })

        # 3. Evaluate strategies on completed candle
        global_idx = self.warmed_up_indicators_df.index.get_loc(candle_ts)
        decisions: Dict[str, Union[IntradayEvaluationResult, StrategyEvaluationResult]] = {}

        for sid in self.enabled_strategies:
            strat = self.strategy_registry.get(sid)
            if not strat:
                continue

            res = strat.evaluate(self.symbol, self.warmed_up_indicators_df, idx=global_idx)
            decisions[sid] = res

            if res.decision == "BUY":
                ref_close = float(res.reference_close)
                target_p = float(res.target_price)
                stop_p = float(res.initial_stop_price)

                self.broker.queue_buy_order(
                    strategy_id=sid,
                    symbol=self.symbol,
                    signal_price=ref_close,
                    stop_price=stop_p,
                    target_price=target_p,
                    signal_time=candle_dt,
                )
                self.timeline.append({
                    "time": candle_time_str,
                    "type": "SIGNAL",
                    "description": f"[{sid}] BUY signal generated @ ₹{ref_close:.2f} (Target: ₹{target_p:.2f}, Stop: ₹{stop_p:.2f})",
                    "candle_idx": self.current_step,
                })

        # Milestone events
        if self.mode == "INTRADAY":
            if candle_time_str == "09:30" and candle_row.get("orb_complete", False):
                self.timeline.append({
                    "time": candle_time_str,
                    "type": "INFO",
                    "description": f"Opening Range Formed (09:15–09:30): High ₹{candle_row.get('orb_high', 0.0):.2f}, Low ₹{candle_row.get('orb_low', 0.0):.2f}",
                    "candle_idx": self.current_step,
                })
            elif is_end_of_session:
                self.timeline.append({
                    "time": candle_time_str,
                    "type": "INFO",
                    "description": "Session ended. All remaining intraday positions squared off.",
                    "candle_idx": self.current_step,
                })

        # 4. Update equity metrics for all accounts
        for acc in self.broker.accounts.values():
            acc.update_metrics(candle_time_str)

        self.latest_decisions = decisions
        self.current_step += 1

    def get_visible_candles_df(self) -> pd.DataFrame:
        """Returns only the candles completed up to current_step (Strictly NO LOOKAHEAD)."""
        if self.session_candles_df is None or self.current_step == 0:
            return pd.DataFrame()
        return self.session_candles_df.iloc[: self.current_step].copy()

    def get_latest_candle(self) -> Optional[pd.Series]:
        """Returns the most recently completed candle."""
        if self.session_candles_df is None or self.current_step == 0:
            return None
        return self.session_candles_df.iloc[self.current_step - 1]
