"""
Intraday Strategy Agents package for INDIGO QUANT.
Contains deterministic 5-minute technical research strategies:
- VWAP Momentum
- Opening Range Breakout (ORB)
- EMA Pullback Continuation
- Volatility Breakout
"""

from indigo_quant.strategies.intraday.base import BaseIntradayStrategy, IntradayEvaluationResult
from indigo_quant.strategies.intraday.ema_pullback import IntradayEMAPullbackStrategy
from indigo_quant.strategies.intraday.opening_range_breakout import IntradayOpeningRangeBreakoutStrategy
from indigo_quant.strategies.intraday.volatility_breakout import IntradayVolatilityBreakoutStrategy
from indigo_quant.strategies.intraday.vwap_momentum import IntradayVWAPMomentumStrategy

__all__ = [
    "BaseIntradayStrategy",
    "IntradayEvaluationResult",
    "IntradayVWAPMomentumStrategy",
    "IntradayOpeningRangeBreakoutStrategy",
    "IntradayEMAPullbackStrategy",
    "IntradayVolatilityBreakoutStrategy",
]
