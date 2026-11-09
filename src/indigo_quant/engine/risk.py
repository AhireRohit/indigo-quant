"""
Risk Engine and Position Sizer.
Enforces 0.5% max portfolio risk, 20% max position size, 5 max positions,
75% max exposure, 10% gross target, and 2.0-5.0% ATR-derived stops.
"""

from __future__ import annotations

import math
from typing import Optional

from pydantic import BaseModel


class RiskAssessment(BaseModel):
    is_approved: bool
    rejection_reason: Optional[str] = None
    entry_price: float
    stop_price: float
    stop_distance_pct: float
    target_price: float
    target_gain_pct: float = 10.0
    reward_to_risk_ratio: float
    recommended_quantity: int = 0
    estimated_position_value: float = 0.0
    risk_amount_inr: float = 0.0


class RiskEngine:
    """
    Evaluates swing-trading trade risk and computes deterministic position sizing.
    """

    def __init__(
        self,
        max_risk_per_trade_pct: float = 0.005,      # 0.5% of equity
        max_position_allocation_pct: float = 0.20,  # 20% of equity
        max_open_positions: int = 5,
        max_portfolio_exposure_pct: float = 0.75,   # 75% max capital deployed
        min_stop_distance_pct: float = 0.02,        # 2% minimum stop
        max_stop_distance_pct: float = 0.05,        # 5% maximum stop (volatility ceiling)
        atr_multiplier: float = 1.5,
        target_gross_pct: float = 0.10,             # 10% gross target
        min_reward_to_risk: float = 2.0,
    ):
        self.max_risk_pct = max_risk_per_trade_pct
        self.max_allocation_pct = max_position_allocation_pct
        self.max_positions = max_open_positions
        self.max_exposure_pct = max_portfolio_exposure_pct
        self.min_stop_pct = min_stop_distance_pct
        self.max_stop_pct = max_stop_distance_pct
        self.atr_multiplier = atr_multiplier
        self.target_gross_pct = target_gross_pct
        self.min_reward_to_risk = min_reward_to_risk

    def evaluate_candidate(
        self,
        entry_price: float,
        atr14: float,
        portfolio_equity: float,
        available_cash: float,
        current_open_positions_count: int,
        current_invested_capital: float,
        estimated_fee_buffer_pct: float = 0.002,  # 0.2% buffer for fees/slippage
    ) -> RiskAssessment:
        """
        Assess trade risk parameters and return sizing recommendation.
        """
        if entry_price <= 0:
            return RiskAssessment(
                is_approved=False,
                rejection_reason="Invalid nonpositive entry price.",
                entry_price=entry_price,
                stop_price=0.0,
                stop_distance_pct=0.0,
                target_price=0.0,
                reward_to_risk_ratio=0.0,
            )

        # 1. Stop Distance: max(0.02, 1.5 * ATR14 / entry_price)
        raw_stop_pct = max(self.min_stop_pct, (self.atr_multiplier * atr14) / entry_price)

        # 2. Volatility Ceiling: Reject if stop > 5.0%
        if raw_stop_pct > self.max_stop_pct:
            return RiskAssessment(
                is_approved=False,
                rejection_reason=(
                    f"Stop distance {raw_stop_pct * 100.0:.2f}% exceeds maximum allowable "
                    f"risk ceiling of {self.max_stop_pct * 100.0:.1f}%. Stock is too volatile."
                ),
                entry_price=entry_price,
                stop_price=round(entry_price * (1.0 - raw_stop_pct), 2),
                stop_distance_pct=round(raw_stop_pct, 4),
                target_price=round(entry_price * (1.0 + self.target_gross_pct), 2),
                reward_to_risk_ratio=round(self.target_gross_pct / raw_stop_pct, 2),
            )

        stop_distance_pct = raw_stop_pct
        stop_price = round(entry_price * (1.0 - stop_distance_pct), 2)
        target_price = round(entry_price * (1.0 + self.target_gross_pct), 2)

        # 3. Reward-to-Risk ratio check
        reward_to_risk = self.target_gross_pct / stop_distance_pct
        if reward_to_risk < self.min_reward_to_risk:
            return RiskAssessment(
                is_approved=False,
                rejection_reason=f"Reward-to-risk ratio {reward_to_risk:.2f} is below minimum {self.min_reward_to_risk:.1f}.",
                entry_price=entry_price,
                stop_price=stop_price,
                stop_distance_pct=round(stop_distance_pct, 4),
                target_price=target_price,
                reward_to_risk_ratio=round(reward_to_risk, 2),
            )

        # 4. Portfolio Position Count Limit
        if current_open_positions_count >= self.max_positions:
            return RiskAssessment(
                is_approved=False,
                rejection_reason=(
                    f"Portfolio has {current_open_positions_count} open positions. "
                    f"Maximum simultaneous limit of {self.max_positions} reached."
                ),
                entry_price=entry_price,
                stop_price=stop_price,
                stop_distance_pct=round(stop_distance_pct, 4),
                target_price=target_price,
                reward_to_risk_ratio=round(reward_to_risk, 2),
            )

        # 5. Position Sizing
        # 5.1 Risk Budget constraint: 0.5% equity
        risk_budget = portfolio_equity * self.max_risk_pct
        risk_per_share = entry_price - stop_price
        if risk_per_share <= 0:
            risk_per_share = entry_price * self.min_stop_pct
        risk_qty = math.floor(risk_budget / risk_per_share)

        # 5.2 Allocation constraint: 20% equity
        max_position_val = portfolio_equity * self.max_allocation_pct
        alloc_qty = math.floor(max_position_val / entry_price)

        # 5.3 Cash & Exposure constraints
        cost_per_share_with_fees = entry_price * (1.0 + estimated_fee_buffer_pct)
        cash_qty = math.floor(available_cash / cost_per_share_with_fees)

        # 5.4 Portfolio Exposure ceiling: 75% max
        remaining_exposure_cap = (portfolio_equity * self.max_exposure_pct) - current_invested_capital
        exposure_qty = math.floor(max(0.0, remaining_exposure_cap) / cost_per_share_with_fees)

        quantity = min(risk_qty, alloc_qty, cash_qty, exposure_qty)

        if quantity < 1:
            reasons = []
            if cash_qty < 1:
                reasons.append(f"Insufficient cash (₹{available_cash:,.1f}) for 1 share @ ₹{entry_price:,.1f}")
            if risk_qty < 1:
                reasons.append(f"Risk budget ₹{risk_budget:,.1f} too small for per-share risk ₹{risk_per_share:,.1f}")
            if exposure_qty < 1:
                reasons.append("Max portfolio exposure cap (75%) reached")
            reason_str = "; ".join(reasons) or "Calculated quantity is 0."

            return RiskAssessment(
                is_approved=False,
                rejection_reason=reason_str,
                entry_price=entry_price,
                stop_price=stop_price,
                stop_distance_pct=round(stop_distance_pct, 4),
                target_price=target_price,
                reward_to_risk_ratio=round(reward_to_risk, 2),
                recommended_quantity=0,
            )

        position_value = quantity * entry_price
        risk_amount = quantity * risk_per_share

        return RiskAssessment(
            is_approved=True,
            rejection_reason=None,
            entry_price=entry_price,
            stop_price=stop_price,
            stop_distance_pct=round(stop_distance_pct, 4),
            target_price=target_price,
            reward_to_risk_ratio=round(reward_to_risk, 2),
            recommended_quantity=int(quantity),
            estimated_position_value=round(position_value, 2),
            risk_amount_inr=round(risk_amount, 2),
        )
