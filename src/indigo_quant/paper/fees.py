"""
Realistic Indian Equity Delivery Transaction Fee and Slippage Model.
Calculates official regulatory charges, exchange levies, and taxes for delivery trades.
As-of Date: 2024-10-01 (Verified against NSE, SEBI circulars & standard discount broker schedules).
"""

from __future__ import annotations

from pydantic import BaseModel


class FeeBreakdown(BaseModel):
    gross_turnover: float
    slippage: float
    brokerage: float
    stt: float
    exchange_txn_charge: float
    sebi_turnover_charge: float
    stamp_duty: float
    gst: float
    dp_charge: float
    total_charges: float
    effective_cash_impact: float  # For BUY: gross + slippage + charges; For SELL: gross - slippage - charges


class IndianDeliveryCostModel:
    """
    Computes exact regulatory and exchange transaction charges for Indian cash equity delivery.
    """

    def __init__(
        self,
        brokerage_pct: float = 0.0,
        brokerage_max_inr: float = 20.0,
        stt_buy_pct: float = 0.0010,                # 0.10% on BUY
        stt_sell_pct: float = 0.0010,               # 0.10% on SELL
        exchange_txn_pct: float = 0.0000297,        # 0.00297% NSE charge
        sebi_turnover_pct: float = 0.000001,        # ₹10 per crore (0.0001%)
        stamp_duty_buy_pct: float = 0.00015,        # 0.015% on BUY only
        gst_pct: float = 0.18,                      # 18% on (brokerage + exchange + sebi)
        dp_charge_sell_flat: float = 15.93,         # ₹13.50 + 18% GST flat per sell
        slippage_pct: float = 0.0010,               # 0.10% modeled slippage
    ):
        self.brokerage_pct = brokerage_pct
        self.brokerage_max = brokerage_max_inr
        self.stt_buy_pct = stt_buy_pct
        self.stt_sell_pct = stt_sell_pct
        self.exchange_txn_pct = exchange_txn_pct
        self.sebi_turnover_pct = sebi_turnover_pct
        self.stamp_duty_buy_pct = stamp_duty_buy_pct
        self.gst_pct = gst_pct
        self.dp_charge_sell_flat = dp_charge_sell_flat
        self.slippage_pct = slippage_pct

    def calculate_charges(self, side: str, price: float, quantity: int) -> FeeBreakdown:
        """
        Compute all charges for a trade.
        side: 'BUY' or 'SELL'
        """
        gross = price * quantity
        side_upper = side.upper()

        # 1. Slippage (cost incurred)
        slippage = gross * self.slippage_pct

        # 2. Brokerage
        raw_brokerage = gross * self.brokerage_pct
        brokerage = min(raw_brokerage, self.brokerage_max) if self.brokerage_pct > 0 else 0.0

        # 3. Securities Transaction Tax (STT)
        # Rounded to nearest rupee per standard exchange convention
        if side_upper == "BUY":
            stt = round(gross * self.stt_buy_pct)
            stamp_duty = round(gross * self.stamp_duty_buy_pct)
            dp_charge = 0.0
        else:  # SELL
            stt = round(gross * self.stt_sell_pct)
            stamp_duty = 0.0
            dp_charge = self.dp_charge_sell_flat

        # 4. Exchange Transaction Charge
        exchange_txn = gross * self.exchange_txn_pct

        # 5. SEBI Turnover Charge
        sebi = gross * self.sebi_turnover_pct

        # 6. Goods and Services Tax (GST: 18% on brokerage + exchange + sebi)
        gst = (brokerage + exchange_txn + sebi) * self.gst_pct

        # Total statutory and broker fees
        total_charges = round(brokerage + stt + exchange_txn + sebi + stamp_duty + gst + dp_charge, 2)

        # Net cash flow:
        # BUY requires cash outlay = gross + slippage + total_charges
        # SELL generates net proceeds = gross - slippage - total_charges
        if side_upper == "BUY":
            effective_cash_impact = round(gross + slippage + total_charges, 2)
        else:
            effective_cash_impact = round(gross - slippage - total_charges, 2)

        return FeeBreakdown(
            gross_turnover=round(gross, 2),
            slippage=round(slippage, 2),
            brokerage=round(brokerage, 2),
            stt=float(stt),
            exchange_txn_charge=round(exchange_txn, 2),
            sebi_turnover_charge=round(sebi, 2),
            stamp_duty=float(stamp_duty),
            gst=round(gst, 2),
            dp_charge=round(dp_charge, 2),
            total_charges=total_charges,
            effective_cash_impact=effective_cash_impact,
        )
