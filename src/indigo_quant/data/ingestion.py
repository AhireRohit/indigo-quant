"""
Market Data Ingestion Coordinator.
Coordinates fetching across TejHQ and Yahoo Finance, runs cross-validation,
applies quality rules, and caches/persists to SQLite.
"""

from __future__ import annotations

import datetime
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
from sqlalchemy.orm import Session

from indigo_quant.data.providers.tejhq import TejHQProvider
from indigo_quant.data.providers.yfinance_provider import YFinanceProvider
from indigo_quant.data.validation import (
    check_liquidity,
    reconcile_provider_prices,
    validate_ohlcv_dataframe,
)
from indigo_quant.db.repository import Repository

logger = logging.getLogger(__name__)


class DataIngestionEngine:
    """
    Orchestrates historical market data acquisition, validation, and storage.
    """

    def __init__(
        self,
        db: Session,
        cache_dir: str = "./data/cache",
        min_required_bars: int = 260,
        tolerance_pct: float = 2.0,
    ):
        self.db = db
        self.repo = Repository(db)
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.min_required_bars = min_required_bars
        self.tolerance_pct = tolerance_pct

        self.tejhq = TejHQProvider()
        self.yahoo = YFinanceProvider()

    def get_provider_health(self) -> Dict[str, bool]:
        """Check liveness of both data providers."""
        return {
            "tejhq": self.tejhq.is_healthy(),
            "yahoo": self.yahoo.is_healthy(),
        }

    def fetch_and_validate_symbol(
        self,
        symbol: str,
        exchange: str = "NSE",
        start_date: Optional[datetime.date] = None,
        end_date: Optional[datetime.date] = None,
        persist: bool = True,
    ) -> Tuple[Optional[pd.DataFrame], List[str]]:
        """
        Fetch symbol data with TejHQ as primary and Yahoo as fallback/validator.
        Returns (DataFrame or None, list_of_errors_or_warnings).
        """
        logs: List[str] = []
        df_primary: Optional[pd.DataFrame] = None
        provider_used = "none"

        # 1. Attempt TejHQ primary fetch
        try:
            df_tej = self.tejhq.fetch_ohlcv(symbol, exchange=exchange, start_date=start_date, end_date=end_date)
            if not df_tej.empty and len(df_tej) >= self.min_required_bars:
                df_primary = df_tej
                provider_used = "tejhq"
                logs.append(f"{symbol}: Retrieved {len(df_tej)} bars from TejHQ.")
            else:
                logs.append(f"{symbol}: TejHQ returned insufficient bars ({len(df_tej) if not df_tej.empty else 0}).")
        except Exception as e:
            logs.append(f"{symbol}: TejHQ fetch exception: {e}")

        # 2. Attempt Yahoo Finance fetch
        df_yahoo = pd.DataFrame()
        try:
            df_yahoo = self.yahoo.fetch_ohlcv(symbol, exchange=exchange, start_date=start_date, end_date=end_date)
        except Exception as e:
            logs.append(f"{symbol}: Yahoo fetch exception: {e}")

        # If primary failed, fallback to Yahoo
        if df_primary is None or df_primary.empty:
            if not df_yahoo.empty and len(df_yahoo) >= self.min_required_bars:
                df_primary = df_yahoo
                provider_used = "yahoo"
                logs.append(f"{symbol}: Successfully fell back to Yahoo Finance ({len(df_yahoo)} bars).")
            else:
                logs.append(f"{symbol}: Both TejHQ and Yahoo failed or returned insufficient bars.")
                return None, logs
        else:
            # If both are present, run cross-validation reconciliation
            if not df_yahoo.empty:
                ok, discrepancies = reconcile_provider_prices(
                    df_primary, df_yahoo, symbol, tolerance_pct=self.tolerance_pct
                )
                if not ok:
                    logs.extend(discrepancies)
                else:
                    logs.append(f"{symbol}: Cross-provider price reconciliation verified successfully.")

                # If Yahoo Finance has newer completed bars (e.g. today after market close), augment df_primary
                newer_bars = df_yahoo[df_yahoo.index > df_primary.index[-1]]
                if not newer_bars.empty:
                    df_primary = pd.concat([df_primary, newer_bars])
                    logs.append(f"{symbol}: Augmented {len(newer_bars)} newer completed bar(s) from Yahoo Finance.")

        # 3. Quality Validation
        is_valid, val_errors = validate_ohlcv_dataframe(
            df_primary, symbol, min_required_bars=self.min_required_bars, check_freshness=False
        )
        if not is_valid:
            logs.extend(val_errors)
            return None, logs

        # 4. Liquidity check
        is_liquid, liq_msg = check_liquidity(df_primary)
        if not is_liquid:
            logs.append(f"{symbol}: Liquidity filter failed: {liq_msg}")
            # Note: We still return data for research/backtests, but mark warning
            df_primary.attrs["is_liquid"] = False
            df_primary.attrs["liquidity_reason"] = liq_msg
        else:
            df_primary.attrs["is_liquid"] = True

        df_primary.attrs["provider"] = provider_used

        # 5. Persist to DB if requested
        if persist:
            try:
                bars_to_save = []
                for idx, row in df_primary.iterrows():
                    bar_date = idx.date() if hasattr(idx, "date") else idx
                    bars_to_save.append({
                        "symbol": symbol,
                        "exchange": exchange,
                        "date": bar_date,
                        "open": row["open"],
                        "high": row["high"],
                        "low": row["low"],
                        "close": row["close"],
                        "volume": row["volume"],
                        "turnover": row.get("turnover"),
                        "adj_close": row.get("adj_close", row["close"]),
                        "provider": provider_used,
                        "is_validated": True,
                    })
                saved_count = self.repo.save_bars(bars_to_save)
                logs.append(f"{symbol}: Persisted {saved_count} historical bars to database.")
            except Exception as e:
                logs.append(f"{symbol}: Database persistence error: {e}")

        # 6. Cache to local file
        try:
            cache_file = self.cache_dir / f"{symbol}_{exchange}.csv"
            df_primary.to_csv(cache_file)
        except Exception as e:
            logger.debug("Failed saving cache file: %s", e)

        return df_primary, logs

    def fetch_benchmark(
        self,
        symbol: str = "^NSEI",
        start_date: Optional[datetime.date] = None,
        end_date: Optional[datetime.date] = None,
    ) -> Optional[pd.DataFrame]:
        """Fetch NIFTY 50 benchmark data and persist to database."""
        df = self.yahoo.fetch_ohlcv(symbol, start_date=start_date, end_date=end_date)
        if df.empty:
            logger.error("Failed to fetch benchmark %s", symbol)
            return None

        # Persist benchmark bars
        try:
            bars_to_save = []
            for idx, row in df.iterrows():
                bar_date = idx.date() if hasattr(idx, "date") else idx
                bars_to_save.append({
                    "symbol": symbol,
                    "exchange": "NSE",
                    "date": bar_date,
                    "open": row["open"],
                    "high": row["high"],
                    "low": row["low"],
                    "close": row["close"],
                    "volume": row["volume"],
                    "turnover": row.get("turnover"),
                    "adj_close": row.get("adj_close", row["close"]),
                    "provider": "yahoo",
                    "is_validated": True,
                })
            self.repo.save_bars(bars_to_save)
        except Exception as e:
            logger.debug("Failed persisting benchmark bars: %s", e)

        return df
