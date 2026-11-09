"""
Telegram Notification Engine for INDIGO QUANT.
Provides idempotent, structured alerts for BUY signals, simulated order fills,
target achievements (+10%), stop losses, order expirations, system errors,
and end-of-day summary recaps.

Safely handles absent credentials or disabled state without throwing exceptions.
Tokens are strictly masked in logs and console output.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional, Set, Tuple

import requests

from indigo_quant.data.calendar import now_ist

logger = logging.getLogger(__name__)


def mask_token(token: Optional[str]) -> str:
    """Mask bot token for safe display/logging (e.g. 123456****:****abcd)."""
    if not token or len(token) < 10:
        return "********"
    prefix = token[:6]
    suffix = token[-4:]
    return f"{prefix}****:****{suffix}"


class TelegramNotifier:
    """Dispatches quantitative alerts to Telegram Bot API with persistent deduplication."""

    def __init__(
        self,
        bot_token: Optional[str] = None,
        chat_id: Optional[str] = None,
        enabled: Optional[bool] = None,
        cache_path: str = "data/sent_alerts.json",
    ):
        self.bot_token = (bot_token or os.getenv("TELEGRAM_BOT_TOKEN", "")).strip() or None
        self.chat_id = (chat_id or os.getenv("TELEGRAM_CHAT_ID", "")).strip() or None

        env_enabled = os.getenv("TELEGRAM_ENABLED", "true").lower() in ("true", "1", "yes")
        self.enabled = (enabled if enabled is not None else env_enabled) and bool(self.bot_token and self.chat_id)

        self.cache_path = Path(cache_path)
        self._sent_keys: Set[str] = self._load_cache()

    @property
    def is_configured(self) -> bool:
        """Returns True if valid token and chat_id are present and notifications are enabled."""
        return self.enabled and bool(self.bot_token and self.chat_id)

    def _load_cache(self) -> Set[str]:
        """Load set of previously dispatched message dedup keys."""
        if not self.cache_path.exists():
            return set()
        try:
            with open(self.cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return set(data)
        except Exception as e:
            logger.debug("Could not read sent alerts cache (%s): %s", self.cache_path, e)
        return set()

    def _save_cache(self) -> None:
        """Persist set of sent message keys to disk."""
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.cache_path, "w", encoding="utf-8") as f:
                # Keep last 1,000 sent keys to prevent unbounded file growth
                recent = sorted(list(self._sent_keys))[-1000:]
                json.dump(recent, f, indent=2)
        except Exception as e:
            logger.debug("Could not save sent alerts cache: %s", e)

    def _dispatch(self, text: str, dedup_key: Optional[str] = None) -> Tuple[bool, str]:
        """Internal dispatch with deduplication, error handling, and timeout."""
        if not self.is_configured:
            return False, "Telegram notifications disabled or credentials missing."

        if dedup_key and dedup_key in self._sent_keys:
            logger.debug("Deduplication: Alert already sent for key %s. Skipping.", dedup_key)
            return True, f"Skipped duplicate alert ({dedup_key})"

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }

        try:
            resp = requests.post(url, json=payload, timeout=10)
            if resp.status_code == 200:
                if dedup_key:
                    self._sent_keys.add(dedup_key)
                    self._save_cache()
                logger.info("Dispatched Telegram alert successfully (key=%s)", dedup_key)
                return True, "Alert sent successfully (HTTP 200)"
            else:
                err_msg = f"HTTP {resp.status_code}: {resp.text}"
                logger.warning("Telegram API dispatch failed: %s", err_msg)
                return False, err_msg
        except Exception as e:
            err_msg = f"Network or connection error: {str(e)}"
            logger.warning("Telegram request exception: %s", err_msg)
            return False, err_msg

    def send_test_message(self) -> Tuple[bool, str]:
        """
        Sends an operational diagnostic test message to verify the bot and chat connectivity.
        Never prints or exposes the actual bot token.
        """
        if not self.is_configured:
            return False, f"Telegram is not configured. Token present: {bool(self.bot_token)}, Chat ID: {bool(self.chat_id)}, Enabled: {self.enabled}"

        ist_now = now_ist().strftime("%Y-%m-%d %H:%M:%S IST")
        msg = (
            "🔔 *INDIGO QUANT — TELEGRAM NOTIFICATION TEST*\n\n"
            "✓ *Status*: Connection established successfully\n"
            f"• *Timestamp*: `{ist_now}`\n"
            "• *Platform*: Windows 11 Autonomous Trading Engine\n"
            "• *Chat ID*: `" + str(self.chat_id) + "`\n"
            "• *Timezone*: `Asia/Kolkata`\n"
            "• *Execution*: Paper-Trading Simulation Mode\n\n"
            "_This bot will send real-time alerts for verified BUY signals, paper order fills, target hits (+10%), stop-losses, and daily EOD recaps._"
        )
        return self._dispatch(msg)

    def send_buy_alert(self, signal: Dict[str, Any]) -> bool:
        """
        Send a formatted BUY candidate alert with exact numerical condition audit.
        Idempotent by symbol, strategy, and date.
        """
        symbol = signal.get("symbol", "UNKNOWN")
        strat_id = signal.get("strategy_id", "unknown")
        sig_date = signal.get("signal_date", str(now_ist().date()))
        dedup_key = f"BUY:{symbol}:{strat_id}:{sig_date}"

        strat_name = strat_id.replace("_", " ").title()
        ref_price = signal.get("reference_close", 0.0)
        target = signal.get("target_price_estimate", ref_price * 1.10)
        stop = signal.get("initial_stop_estimate", ref_price * 0.96)
        score = signal.get("rule_quality_score", 0.0)
        rules_passed = signal.get("rules_passed", [])
        qty = signal.get("recommended_quantity", 0)

        rules_list = "\n".join([f"  ✓ `{r}`" for r in rules_passed[:6]])

        msg = (
            "🎯 *INDIGO QUANT — QUALIFIED BUY SIGNAL*\n\n"
            f"• *Ticker*: `{symbol}`\n"
            f"• *Strategy*: {strat_name}\n"
            f"• *Reference Close*: ₹{ref_price:,.2f}\n"
            f"• *10% Target Estimate*: ₹{target:,.2f} (+10.0%)\n"
            f"• *Initial Stop Estimate*: ₹{stop:,.2f}\n"
            f"• *Recommended Qty*: {qty} shares\n"
            f"• *Rule Quality Score*: *{score:.1f}/100*\n"
            f"• *Signal Date*: `{sig_date}`\n\n"
            f"*Numerical Conditions Passed*:\n{rules_list}\n\n"
            "_Paper order queued for simulated execution at next session open. Zero real money._"
        )

        ok, _ = self._dispatch(msg, dedup_key=dedup_key)
        return ok

    def send_order_filled_alert(self, order_dict: Dict[str, Any]) -> bool:
        """Alert when a pending paper order executes at the market open."""
        order_id = order_dict.get("id", "N/A")
        dedup_key = f"FILL:{order_id}"

        symbol = order_dict.get("symbol", "UNKNOWN")
        side = order_dict.get("order_side", "BUY")
        qty = order_dict.get("quantity", 0)
        fill_price = order_dict.get("fill_price", 0.0)
        fill_date = order_dict.get("fill_date", str(now_ist().date()))
        strat = str(order_dict.get("strategy_id", "")).replace("_", " ").title()
        total_val = qty * fill_price

        msg = (
            "⚡ *INDIGO QUANT — PAPER ORDER FILLED*\n\n"
            f"• *Order ID*: `#{order_id}`\n"
            f"• *Action*: {side} `{symbol}`\n"
            f"• *Quantity*: {qty} shares\n"
            f"• *Fill Price*: ₹{fill_price:,.2f} (Simulated delayed fill)\n"
            f"• *Execution Value*: ₹{total_val:,.2f}\n"
            f"• *Strategy Portfolio*: {strat}\n"
            f"• *Execution Date*: `{fill_date}`\n\n"
            "_Delivery brokerage, STT, exchange charges, SEBI fee, GST, and stamp duty debited to virtual account._"
        )
        ok, _ = self._dispatch(msg, dedup_key=dedup_key)
        return ok

    def send_target_hit_alert(
        self,
        symbol: str,
        strategy_id: str,
        entry_price: float,
        exit_price: float,
        pnl_pct: float,
        gross_pnl: float,
        net_pnl: float,
        holding_days: int,
    ) -> bool:
        """Celebratory alert when a swing position hits the +10% target objective."""
        dedup_key = f"TARGET:{symbol}:{strategy_id}:{exit_price}:{now_ist().date()}"
        strat_name = strategy_id.replace("_", " ").title()

        msg = (
            "🎉 *INDIGO QUANT — 10% TARGET HIT ACHIEVED!*\n\n"
            f"• *Stock*: `{symbol}`\n"
            f"• *Strategy*: {strat_name}\n"
            f"• *Entry Price*: ₹{entry_price:,.2f}\n"
            f"• *Exit Price*: ₹{exit_price:,.2f}\n"
            f"• *Gross Gain*: *+{pnl_pct:.2f}%*\n"
            f"• *Net Realized PnL*: ₹{net_pnl:+,.2f} (after ₹{gross_pnl - net_pnl:,.2f} fees/taxes)\n"
            f"• *Holding Duration*: {holding_days} trading sessions\n"
            f"• *Exit Reason*: `TARGET_HIT` (+10% threshold reached)\n\n"
            "_Virtual position closed. Capital freed for next qualifying swing setup._"
        )
        ok, _ = self._dispatch(msg, dedup_key=dedup_key)
        return ok

    def send_stop_loss_alert(
        self,
        symbol: str,
        strategy_id: str,
        entry_price: float,
        exit_price: float,
        pnl_pct: float,
        gross_pnl: float,
        net_pnl: float,
        holding_days: int,
    ) -> bool:
        """Risk alert when a position hits its initial ATR/volatility stop loss."""
        dedup_key = f"STOP:{symbol}:{strategy_id}:{exit_price}:{now_ist().date()}"
        strat_name = strategy_id.replace("_", " ").title()

        msg = (
            "🛡️ *INDIGO QUANT — STOP LOSS TRIGGERED*\n\n"
            f"• *Stock*: `{symbol}`\n"
            f"• *Strategy*: {strat_name}\n"
            f"• *Entry Price*: ₹{entry_price:,.2f}\n"
            f"• *Exit Price*: ₹{exit_price:,.2f}\n"
            f"• *Realized Loss*: *{pnl_pct:.2f}%*\n"
            f"• *Net PnL*: ₹{net_pnl:,.2f}\n"
            f"• *Holding Duration*: {holding_days} sessions\n"
            f"• *Exit Reason*: `STOP_LOSS` (Capital protection rule)\n\n"
            "_Position terminated strictly to protect strategy capital._"
        )
        ok, _ = self._dispatch(msg, dedup_key=dedup_key)
        return ok

    def send_order_expired_alert(self, order_dict: Dict[str, Any]) -> bool:
        """Alert when an unfilled paper order expires after its validity window."""
        order_id = order_dict.get("id", "N/A")
        dedup_key = f"EXPIRE:{order_id}"

        symbol = order_dict.get("symbol", "UNKNOWN")
        strat = str(order_dict.get("strategy_id", "")).replace("_", " ").title()

        msg = (
            "⏳ *INDIGO QUANT — ORDER EXPIRED*\n\n"
            f"• *Order ID*: `#{order_id}`\n"
            f"• *Stock*: `{symbol}`\n"
            f"• *Strategy*: {strat}\n"
            f"• *Status*: EXPIRED (No fill within 2 trading sessions)\n\n"
            "_Pending order cancelled. Capital unreserved._"
        )
        ok, _ = self._dispatch(msg, dedup_key=dedup_key)
        return ok

    def send_error_alert(self, context: str, error_msg: str) -> bool:
        """Alert on critical runtime exceptions, ingestion failures, or scheduler errors."""
        now_str = now_ist().strftime("%Y-%m-%d %H:%M:%S IST")
        dedup_key = f"ERR:{context}:{error_msg[:30]}:{now_ist().date()}"

        msg = (
            "⚠️ *INDIGO QUANT — SYSTEM INCIDENT ALERT*\n\n"
            f"• *Context*: `{context}`\n"
            f"• *Timestamp*: `{now_str}`\n"
            f"• *Error*: `{error_msg[:300]}`\n\n"
            "_Automatic recovery mechanisms active. Check local logs for details._"
        )
        ok, _ = self._dispatch(msg, dedup_key=dedup_key)
        return ok

    def send_daily_summary(self, summary: Dict[str, Any]) -> bool:
        """Dispatches an end-of-day summary recap to Telegram."""
        date_str = summary.get("date", str(now_ist().date()))
        dedup_key = f"SUMMARY:{date_str}"

        regime = summary.get("regime", "UNKNOWN")
        nifty_close = summary.get("nifty_close", 0.0)
        scanned = summary.get("scanned_count", 0)
        signals_cnt = summary.get("signals_count", 0)
        open_pos = summary.get("open_positions_count", 0)
        total_equity = summary.get("total_equity", 500000.0)
        initial_cap = summary.get("initial_capital", 500000.0)
        total_ret = ((total_equity - initial_cap) / initial_cap) * 100.0

        leaders = summary.get("strategy_rankings", [])
        leader_lines = []
        for ldr in leaders[:5]:
            name = ldr.get("name", "")
            eq = ldr.get("equity", 100000.0)
            ret = ((eq - 100000.0) / 100000.0) * 100.0
            leader_lines.append(f"  • {name}: ₹{eq:,.0f} ({ret:+.1f}%)")
        leader_block = "\n".join(leader_lines) if leader_lines else "  • All strategies at baseline ₹1,00,000"

        msg = (
            f"📊 *INDIGO QUANT — DAILY RECAP ({date_str})*\n\n"
            f"• *Market Regime*: *{regime}* (NIFTY 50: {nifty_close:,.1f})\n"
            f"• *Universe Scanned*: {scanned} stocks\n"
            f"• *BUY Signals Generated*: {signals_cnt}\n"
            f"• *Active Open Positions*: {open_pos}\n"
            f"• *Total Portfolio Equity*: ₹{total_equity:,.2f} ({total_ret:+.2f}%)\n\n"
            f"*Strategy Performance*:\n{leader_block}\n\n"
            "_View live charts and analytics on the Indigo Quant interactive dashboard._"
        )

        ok, _ = self._dispatch(msg, dedup_key=dedup_key)
        return ok
