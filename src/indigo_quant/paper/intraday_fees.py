"""
Indian Equity Intraday Transaction Cost and Statutory Fee Model.
Implements official Indian exchange and regulatory rate cards:
- Brokerage: 0.03% or ₹20 (whichever is lower) per order
- STT (Securities Transaction Tax): 0.025% on SELL turnover only
- Exchange Transaction Fee: 0.00325% on total turnover
- SEBI Turnover Charges: 0.0001% (₹10 / crore)
- Stamp Duty: 0.003% on BUY turnover only
- GST: 18% on (Brokerage + Exchange Charges + SEBI Charges)
- Simulated Slippage: 0.05% of trade value
"""

from __future__ import annotations

from typing import Dict, Literal
from pydantic import BaseModel


class IntradayCostBreakdown(BaseModel):
    order_side: Literal["BUY", "SELL"]
    price: float
    quantity: int
    gross_turnover: float
    brokerage: float
    stt: float
    exchange_charges: float
    sebi_charges: float
    stamp_duty: float
    gst: float
    total_statutory_and_brokerage: float
    slippage: float
    total_effective_cost: float
    effective_execution_price: float
    net_cash_impact: float


class IndianIntradayCostModel:
    """Accurately calculates intraday transaction charges, slippage, and net cash outlay."""

    def __init__(self, slippage_pct: float = 0.0005):  # 0.05% slippage
        self.slippage_pct = slippage_pct

    def calculate_charges(
        self,
        order_side: Literal["BUY", "SELL"],
        price: float,
        quantity: int,
    ) -> IntradayCostBreakdown:
        gross_turnover = round(price * quantity, 2)

        # 1. Brokerage: min(₹20, 0.03% of turnover)
        brokerage = min(20.0, round(gross_turnover * 0.0003, 2))

        # 2. STT: 0.025% on SELL leg only for intraday equity
        stt = round(gross_turnover * 0.00025, 2) if order_side == "SELL" else 0.0

        # 3. Exchange turnover charges: 0.00325% (NSE cash)
        exchange_charges = round(gross_turnover * 0.0000325, 2)

        # 4. SEBI turnover charges: 0.0001% (₹10/crore)
        sebi_charges = round(gross_turnover * 0.000001, 2)

        # 5. Stamp duty: 0.003% on BUY leg only
        stamp_duty = round(gross_turnover * 0.00003, 2) if order_side == "BUY" else 0.0

        # 6. GST: 18% on (Brokerage + Exchange Charges + SEBI Charges)
        gst = round((brokerage + exchange_charges + sebi_charges) * 0.18, 2)

        total_statutory = round(brokerage + stt + exchange_charges + sebi_charges + stamp_duty + gst, 2)

        # 7. Slippage modeling
        slippage = round(gross_turnover * self.slippage_pct, 2)
        total_effective_cost = round(total_statutory + slippage, 2)

        if order_side == "BUY":
            effective_price = round(price * (1.0 + self.slippage_pct), 2)
            net_impact = -(gross_turnover + total_statutory + slippage)
        else:
            effective_price = round(price * (1.0 - self.slippage_pct), 2)
            net_impact = gross_turnover - total_statutory - slippage

        return IntradayCostBreakdown(
            order_side=order_side,
            price=price,
            quantity=quantity,
            gross_turnover=gross_turnover,
            brokerage=brokerage,
            stt=stt,
            exchange_charges=exchange_charges,
            sebi_charges=sebi_charges,
            stamp_duty=stamp_duty,
            gst=gst,
            total_statutory_and_brokerage=total_statutory,
            slippage=slippage,
            total_effective_cost=total_effective_cost,
            effective_execution_price=effective_price,
            net_cash_impact=round(net_impact, 2),
        )
