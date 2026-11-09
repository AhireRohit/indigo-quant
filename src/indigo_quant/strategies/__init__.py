from indigo_quant.strategies.base import BaseStrategy, ConditionResult, StrategyEvaluationResult
from indigo_quant.strategies.breakout import VolumeBreakoutStrategy
from indigo_quant.strategies.consensus import ConsensusStrategy
from indigo_quant.strategies.momentum import TrendMomentumStrategy
from indigo_quant.strategies.pullback import BullishPullbackStrategy
from indigo_quant.strategies.squeeze import BollingerSqueezeStrategy

__all__ = [
    "BaseStrategy",
    "StrategyEvaluationResult",
    "ConditionResult",
    "TrendMomentumStrategy",
    "VolumeBreakoutStrategy",
    "BullishPullbackStrategy",
    "BollingerSqueezeStrategy",
    "ConsensusStrategy",
]
