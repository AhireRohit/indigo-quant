"""
Yahoo Finance Market Data Provider via yfinance.
Secondary / fallback provider and NIFTY 50 benchmark engine.
"""

from __future__ import annotations

import datetime
import logging
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import yfinance as yf

from indigo_quant.data.providers.base import BaseDataProvider

logger = logging.getLogger(__name__)


class YFinanceProvider(BaseDataProvider):
    """
    Adapter using yfinance for Indian equities (e.g. RELIANCE.NS) and ^NSEI.
    """

    def __init__(self, timeout: int = 15):
        self.timeout = timeout

    @property
    def provider_name(self) -> str:
        return "yahoo"

    def _format_ticker(self, symbol: str, exchange: str = "NSE") -> str:
        """Ensure standard Indian ticker format (e.g. RELIANCE.NS, ^NSEI)."""
        clean = symbol.strip().upper()
        if clean.startswith("^"):
            return clean
        if clean.endswith(".NS") or clean.endswith(".BO"):
            return clean
        suffix = ".NS" if exchange.upper() == "NSE" else ".BO"
        return f"{clean}{suffix}"

    def is_healthy(self) -> bool:
        """Check liveness by downloading 1 day of NIFTY 50 benchmark."""
        try:
            df = yf.download("^NSEI", period="1d", progress=False, timeout=self.timeout)
            return not df.empty
        except Exception as e:
            logger.debug("Yahoo health probe failed: %s", e)
            return False

    def fetch_ohlcv(
        self,
        symbol: str,
        exchange: str = "NSE",
        start_date: Optional[datetime.date] = None,
        end_date: Optional[datetime.date] = None,
    ) -> pd.DataFrame:
        """
        Download historical OHLCV via yfinance.
        Preserves raw OHLC alongside adj_close.
        """
        ticker_str = self._format_ticker(symbol, exchange)

        if not start_date:
            start_date = datetime.date.today() - datetime.timedelta(days=365 * 5)  # 5 years
        if not end_date:
            end_date = datetime.date.today()

        try:
            # We use yf.Ticker to get raw unadjusted bars and actions cleanly
            t = yf.Ticker(ticker_str)
            hist = t.history(
                start=start_date.strftime("%Y-%m-%d"),
                end=(end_date + datetime.timedelta(days=1)).strftime("%Y-%m-%d"),
                auto_adjust=False,
                actions=True,
                timeout=self.timeout,
            )

            if hist.empty:
                logger.warning("YFinance returned empty history for %s", ticker_str)
                return pd.DataFrame()

            # Flatten multi-index columns if present
            if isinstance(hist.columns, pd.MultiIndex):
                hist.columns = [col[0].lower() for col in hist.columns]
            else:
                hist.columns = [col.lower() for col in hist.columns]

            # Normalize index to timezone-naive naive DatetimeIndex
            if hist.index.tz is not None:
                hist.index = hist.index.tz_convert("Asia/Kolkata").tz_localize(None)

            hist.index.name = "date"

            # Rename columns to standard names
            rename_map = {
                "open": "open",
                "high": "high",
                "low": "low",
                "close": "close",
                "adj close": "adj_close",
                "volume": "volume",
            }
            df = hist.rename(columns=rename_map)

            # Ensure all required columns exist
            for c in ["open", "high", "low", "close", "volume"]:
                if c not in df.columns:
                    logger.error("Missing expected column %s in %s data", c, ticker_str)
                    return pd.DataFrame()

            if "adj_close" not in df.columns:
                df["adj_close"] = df["close"]

            df["turnover"] = df["close"] * df["volume"]
            df.sort_index(inplace=True)
            df = df[~df.index.duplicated(keep="first")]

            return df[["open", "high", "low", "close", "volume", "turnover", "adj_close"]]

        except Exception as e:
            logger.error("YFinance download error for %s: %s", ticker_str, e)
            return pd.DataFrame()

    def fetch_corporate_actions(
        self,
        symbol: str,
        exchange: str = "NSE",
    ) -> List[Dict[str, Any]]:
        """Fetch dividends and splits from yfinance."""
        ticker_str = self._format_ticker(symbol, exchange)
        actions: List[Dict[str, Any]] = []

        try:
            t = yf.Ticker(ticker_str)
            raw_actions = t.actions
            if raw_actions is not None and not raw_actions.empty:
                for idx, row in raw_actions.iterrows():
                    ex_date = idx.date() if hasattr(idx, "date") else idx
                    div = row.get("Dividends", 0.0)
                    split = row.get("Stock Splits", 0.0)

                    if div and div > 0:
                        actions.append({
                            "symbol": symbol.replace(".NS", "").replace(".BO", ""),
                            "exchange": exchange,
                            "ex_date": ex_date,
                            "record_date": None,
                            "action_type": "dividend",
                            "cash_amount": float(div),
                            "ratio_num": None,
                            "ratio_den": None,
                            "raw_subject": f"Dividend ₹{div:.2f}",
                            "provider": "yahoo",
                        })
                    if split and split > 0:
                        actions.append({
                            "symbol": symbol.replace(".NS", "").replace(".BO", ""),
                            "exchange": exchange,
                            "ex_date": ex_date,
                            "record_date": None,
                            "action_type": "split",
                            "cash_amount": None,
                            "ratio_num": float(split),
                            "ratio_den": 1.0,
                            "raw_subject": f"Stock Split {split}:1",
                            "provider": "yahoo",
                        })
        except Exception as e:
            logger.debug("Failed fetching corporate actions for %s via yfinance: %s", ticker_str, e)

        return actions

    def fetch_latest_quote(self, symbol: str, exchange: str = "NSE") -> Tuple[Optional[float], Optional[datetime.datetime], bool]:
        """
        Fetch latest available quote for paper trading simulation.
        Returns (price, timestamp, is_delayed).
        Discloses if price is a delayed snapshot rather than real-time tick.
        """
        ticker_str = self._format_ticker(symbol, exchange)
        try:
            t = yf.Ticker(ticker_str)
            fast_info = getattr(t, "fast_info", None)
            if fast_info:
                last_price = fast_info.last_price
                if last_price and last_price > 0:
                    return float(last_price), datetime.datetime.utcnow(), True

            # Fallback to 1d 1m or 1d history
            df = t.history(period="1d", interval="1m", auto_adjust=False)
            if not df.empty:
                last_price = df["Close"].iloc[-1]
                ts = df.index[-1].to_pydatetime()
                return float(last_price), ts, True

            df_daily = t.history(period="1d", auto_adjust=False)
            if not df_daily.empty:
                last_price = df_daily["Close"].iloc[-1]
                ts = df_daily.index[-1].to_pydatetime()
                return float(last_price), ts, True
        except Exception as e:
            logger.debug("Could not fetch latest quote for %s: %s", ticker_str, e)

        return None, None, True
