"""
Historical Intraday Market Data Adapter and Persistent Cache Engine.
Fetches, validates, normalizes, and stores real intraday bars (1m, 5m, 15m, 30m, 60m)
from legitimate free providers (yfinance) for Indian equities (NSE/BSE).

Strict Rules:
- Never fabricate partial or missing candles into fake intraday data.
- Never interpolate missing bars to create fictitious trading observations.
- Cache datasets as Parquet with structured metadata.
- Offer clean daily replay fallback when intraday data is out of retention.
"""

from __future__ import annotations

import datetime
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import yfinance as yf

from indigo_quant.data.calendar import (
    IST,
    is_market_open,
    is_trading_day,
    now_ist,
)
from indigo_quant.data.validation import validate_ohlcv_dataframe

logger = logging.getLogger(__name__)

DEFAULT_CACHE_DIR = Path("data/intraday_cache")
PUBLIC_REPLAY_DIR = Path("public_data/replay")

# Top liquid NSE equities supported out of the box
SUPPORTED_NSE_TICKERS = {
    "RELIANCE": {"name": "Reliance Industries Ltd", "exchange": "NSE", "symbol_yf": "RELIANCE.NS"},
    "TCS": {"name": "Tata Consultancy Services Ltd", "exchange": "NSE", "symbol_yf": "TCS.NS"},
    "INFY": {"name": "Infosys Ltd", "exchange": "NSE", "symbol_yf": "INFY.NS"},
    "HDFCBANK": {"name": "HDFC Bank Ltd", "exchange": "NSE", "symbol_yf": "HDFCBANK.NS"},
    "ICICIBANK": {"name": "ICICI Bank Ltd", "exchange": "NSE", "symbol_yf": "ICICIBANK.NS"},
    "SBIN": {"name": "State Bank of India", "exchange": "NSE", "symbol_yf": "SBIN.NS"},
    "BHARTIARTL": {"name": "Bharti Airtel Ltd", "exchange": "NSE", "symbol_yf": "BHARTIARTL.NS"},
    "ITC": {"name": "ITC Ltd", "exchange": "NSE", "symbol_yf": "ITC.NS"},
    "LT": {"name": "Larsen & Toubro Ltd", "exchange": "NSE", "symbol_yf": "LT.NS"},
    "KOTAKBANK": {"name": "Kotak Mahindra Bank Ltd", "exchange": "NSE", "symbol_yf": "KOTAKBANK.NS"},
    "^NSEI": {"name": "NIFTY 50 Benchmark Index", "exchange": "NSE", "symbol_yf": "^NSEI"},
}

VALID_INTERVALS = ["1m", "5m", "15m", "30m", "60m", "1d"]


class IntradayDataAdapter:
    """
    Adapter for historical intraday equity and benchmark data.
    Provides strict validation, persistent Parquet caching, and metadata tracking.
    """

    def __init__(
        self,
        cache_dir: Optional[Path] = None,
        public_dir: Optional[Path] = None,
    ):
        self.cache_dir = cache_dir or DEFAULT_CACHE_DIR
        self.public_dir = public_dir or PUBLIC_REPLAY_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.public_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def normalize_symbol(symbol: str) -> Tuple[str, str]:
        """
        Normalize symbol into (clean_symbol, yf_symbol).
        E.g. ('RELIANCE', 'RELIANCE.NS') or ('^NSEI', '^NSEI').
        """
        sym = symbol.strip().upper()
        if sym in SUPPORTED_NSE_TICKERS:
            return sym, SUPPORTED_NSE_TICKERS[sym]["symbol_yf"]

        if sym.endswith(".NS") or sym.endswith(".BO") or sym.startswith("^"):
            clean = sym.replace(".NS", "").replace(".BO", "")
            return clean, sym
        return sym, f"{sym}.NS"

    def _get_cache_paths(self, clean_symbol: str, interval: str, session_date: datetime.date) -> Tuple[Path, Path]:
        """Return (parquet_path, metadata_path) for an intraday session."""
        date_str = session_date.strftime("%Y-%m-%d")
        fname = f"{clean_symbol}_{interval}_{date_str}"
        parquet_file = self.cache_dir / f"{fname}.parquet"
        meta_file = self.cache_dir / f"{fname}.json"
        return parquet_file, meta_file

    def get_session_bars(
        self,
        symbol: str,
        session_date: datetime.date,
        interval: str = "5m",
        force_refresh: bool = False,
    ) -> Tuple[Optional[pd.DataFrame], Dict[str, Any]]:
        """
        Retrieve validated intraday bars for a specific stock and trading session.
        Checks local Parquet cache first, falls back to public replay directory, then fetches remotely.
        """
        clean_symbol, yf_symbol = self.normalize_symbol(symbol)
        if interval not in VALID_INTERVALS:
            return None, {"error": f"Invalid interval '{interval}'. Valid options: {VALID_INTERVALS}"}

        parquet_file, meta_file = self._get_cache_paths(clean_symbol, interval, session_date)

        # 1. Check local Parquet cache
        if not force_refresh and parquet_file.exists() and meta_file.exists():
            try:
                df = pd.read_parquet(parquet_file)
                with open(meta_file, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                return df, meta
            except Exception as e:
                logger.warning("Failed reading cached intraday file %s: %s", parquet_file, e)

        # 2. Check public pre-packaged replay directory
        date_str = session_date.strftime("%Y-%m-%d")
        pub_parquet = self.public_dir / f"{clean_symbol}_{interval}_{date_str}.parquet"
        pub_meta = self.public_dir / f"{clean_symbol}_{interval}_{date_str}.json"
        if not force_refresh and pub_parquet.exists() and pub_meta.exists():
            try:
                df = pd.read_parquet(pub_parquet)
                with open(pub_meta, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                return df, meta
            except Exception as e:
                logger.warning("Failed reading public replay file %s: %s", pub_parquet, e)

        # 3. Fetch from yfinance
        df_fetched, meta = self._fetch_and_validate(clean_symbol, yf_symbol, session_date, interval)
        if df_fetched is not None and not df_fetched.empty:
            # Save to cache
            try:
                df_fetched.to_parquet(parquet_file)
                with open(meta_file, "w", encoding="utf-8") as f:
                    json.dump(meta, f, indent=2, default=str)
            except Exception as e:
                logger.error("Failed saving intraday cache for %s: %s", clean_symbol, e)
            return df_fetched, meta

        return None, meta

    def _fetch_and_validate(
        self,
        clean_symbol: str,
        yf_symbol: str,
        session_date: datetime.date,
        interval: str,
    ) -> Tuple[Optional[pd.DataFrame], Dict[str, Any]]:
        """Download intraday history from yfinance and run strict quality checks."""
        meta: Dict[str, Any] = {
            "symbol": clean_symbol,
            "yf_symbol": yf_symbol,
            "interval": interval,
            "session_date": session_date.strftime("%Y-%m-%d"),
            "provider": "yfinance",
            "retrieval_timestamp": now_ist().strftime("%Y-%m-%d %H:%M:%S IST"),
            "timezone": "Asia/Kolkata",
            "validation_status": "PENDING",
            "bars_count": 0,
        }

        # Calculate fetch range: fetch 5 days around session_date to guarantee warm-up and exact session
        start_date = session_date - datetime.timedelta(days=7)
        end_date = session_date + datetime.timedelta(days=2)

        try:
            ticker = yf.Ticker(yf_symbol)
            # Use period or start/end depending on distance
            days_ago = (datetime.date.today() - session_date).days
            if interval == "1m" and days_ago > 7:
                meta["validation_status"] = "OUT_OF_RETENTION"
                meta["error"] = "1-minute intraday data is restricted to the last 7 calendar days by yfinance."
                return None, meta
            if interval in ["5m", "15m", "30m", "60m"] and days_ago > 59:
                meta["validation_status"] = "OUT_OF_RETENTION"
                meta["error"] = f"{interval} intraday data is restricted to the last 60 calendar days by yfinance."
                return None, meta

            raw_df = ticker.history(start=start_date.strftime("%Y-%m-%d"), end=end_date.strftime("%Y-%m-%d"), interval=interval)
        except Exception as e:
            meta["validation_status"] = "FETCH_FAILED"
            meta["error"] = str(e)
            return None, meta

        if raw_df is None or raw_df.empty:
            meta["validation_status"] = "EMPTY"
            meta["error"] = "No data returned by provider for requested date."
            return None, meta

        # Normalize columns
        raw_df = raw_df.rename(columns={
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
        })
        for c in ["open", "high", "low", "close", "volume"]:
            if c not in raw_df.columns:
                meta["validation_status"] = "MISSING_COLUMNS"
                meta["error"] = f"Missing required column: {c}"
                return None, meta

        # Timezone conversion to Asia/Kolkata
        if raw_df.index.tz is None:
            raw_df.index = raw_df.index.tz_localize("UTC").tz_convert(IST)
        else:
            raw_df.index = raw_df.index.tz_convert(IST)

        # Filter strictly to target session_date
        session_mask = raw_df.index.date == session_date
        session_df = raw_df[session_mask].copy()

        if session_df.empty:
            meta["validation_status"] = "NO_BARS_FOR_DATE"
            meta["error"] = f"No intraday bars found for {session_date}. Market may have been closed or holiday."
            return None, meta

        # Filter out pre-market / post-market if regular session
        # Standard NSE trading: 09:15 to 15:30
        session_df = session_df.between_time("09:15", "15:30")

        # Validate OHLC logic
        # 1. High >= max(Open, Close)
        # 2. Low <= min(Open, Close)
        # 3. Volume >= 0
        valid_ohlc = (
            (session_df["high"] >= session_df["open"]) &
            (session_df["high"] >= session_df["close"]) &
            (session_df["low"] <= session_df["open"]) &
            (session_df["low"] <= session_df["close"]) &
            (session_df["volume"] >= 0)
        )
        if not valid_ohlc.all():
            invalid_count = (~valid_ohlc).sum()
            logger.warning("Sanitizing %d corrupt intraday bars for %s on %s", invalid_count, clean_symbol, session_date)
            session_df = session_df[valid_ohlc].copy()

        # Remove duplicate index timestamps
        session_df = session_df[~session_df.index.duplicated(keep="first")]
        session_df = session_df.sort_index()

        meta["validation_status"] = "VERIFIED"
        meta["bars_count"] = len(session_df)
        meta["earliest_observed"] = session_df.index[0].strftime("%Y-%m-%d %H:%M:%S IST")
        meta["latest_observed"] = session_df.index[-1].strftime("%Y-%m-%d %H:%M:%S IST")

        return session_df, meta

    def get_warmed_up_intraday_data(
        self,
        symbol: str,
        session_date: datetime.date,
        interval: str = "5m",
        warm_up_sessions: int = 3,
    ) -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame], Dict[str, Any]]:
        """
        Loads the target session's intraday bars PLUS prior sessions to properly warm up
        indicators such as EMA20, EMA50, EMA200, MACD, and RVOL.
        
        Returns:
            (target_session_df, combined_warmed_up_df, metadata)
        """
        clean_symbol, yf_symbol = self.normalize_symbol(symbol)
        target_df, meta = self.get_session_bars(clean_symbol, session_date, interval=interval)
        if target_df is None or target_df.empty:
            return None, None, meta

        # Find prior trading dates
        prior_frames: List[pd.DataFrame] = []
        cur_date = session_date - datetime.timedelta(days=1)
        collected = 0

        # Look back up to 14 calendar days to find warm_up_sessions
        for _ in range(14):
            if collected >= warm_up_sessions:
                break
            if is_trading_day(cur_date):
                prior_df, _ = self.get_session_bars(clean_symbol, cur_date, interval=interval)
                if prior_df is not None and not prior_df.empty:
                    prior_frames.insert(0, prior_df)
                    collected += 1
            cur_date -= datetime.timedelta(days=1)

        if prior_frames:
            combined = pd.concat(prior_frames + [target_df]).sort_index()
            combined = combined[~combined.index.duplicated(keep="first")]
        else:
            combined = target_df.copy()

        return target_df, combined, meta

    def export_curated_replay_datasets(self) -> List[str]:
        """
        Export validated, bounded historical sessions to `public_data/replay/` for Streamlit Cloud.
        Does not redistribute sensitive keys or massive raw datasets.
        """
        exported_files: List[str] = []
        # Export recent sessions for top liquid Nifty tickers
        target_symbols = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "SBIN", "BHARTIARTL", "ITC", "KOTAKBANK", "LT"]
        # Use target dates: November 9, 2026 (and previous trading days like Nov 6)
        target_dates = [datetime.date(2026, 11, 9), datetime.date(2026, 11, 6)]

        for sym in target_symbols:
            for dt in target_dates:
                for interval in ["5m", "15m"]:
                    df, meta = self.get_session_bars(sym, dt, interval=interval)
                    if df is not None and not df.empty:
                        out_parquet = self.public_dir / f"{sym}_{interval}_{dt.strftime('%Y-%m-%d')}.parquet"
                        out_meta = self.public_dir / f"{sym}_{interval}_{dt.strftime('%Y-%m-%d')}.json"
                        df.to_parquet(out_parquet)
                        with open(out_meta, "w", encoding="utf-8") as f:
                            json.dump(meta, f, indent=2, default=str)
                        exported_files.append(str(out_parquet))
                        logger.info("Exported curated replay session: %s", out_parquet.name)

        return exported_files
