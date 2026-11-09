"""
TejHQ Market Data Provider.
Free end-of-day market data adapter for NSE & BSE equities.
Documentation: https://tejhq.dev/docs
"""

from __future__ import annotations

import datetime
import logging
import os
import time
from typing import Any, Dict, List, Optional

import pandas as pd
import requests

from indigo_quant.data.providers.base import BaseDataProvider

logger = logging.getLogger(__name__)


class TejHQProvider(BaseDataProvider):
    """
    Adapter for TejHQ REST API (https://api.tejhq.dev).
    Accesses keyless free endpoints for daily OHLCV and corporate actions.
    Uses optional free API key for adjusted prices if provided.
    """

    def __init__(
        self,
        base_url: str = "https://api.tejhq.dev",
        api_key: Optional[str] = None,
        timeout: int = 15,
        max_retries: int = 3,
    ):
        self.base_url = (api_key and os.getenv("TEJHQ_BASE_URL")) or base_url.rstrip("/")
        self.api_key = api_key or os.getenv("TEJHQ_API_KEY", "").strip() or None
        self.timeout = timeout
        self.max_retries = max_retries
        self._last_request_time = 0.0
        self._min_interval = 0.20  # Max 5 req/s to respect provider limits

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "IndigoQuant/1.0 (+https://github.com/indigo-quant; research)",
            "Accept": "application/json",
        })
        if self.api_key:
            self.session.headers.update({"Authorization": f"Bearer {self.api_key}"})

    @property
    def provider_name(self) -> str:
        return "tejhq"

    def _rate_limit(self) -> None:
        """Enforce rate limiting between outgoing API calls."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_request_time = time.time()

    def _get_with_retry(self, url: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        for attempt in range(1, self.max_retries + 1):
            try:
                self._rate_limit()
                resp = self.session.get(url, params=params, timeout=self.timeout)
                if resp.status_code == 200:
                    return resp.json()
                elif resp.status_code == 404:
                    logger.debug("TejHQ 404 Not Found: %s", url)
                    return None
                elif resp.status_code == 429:
                    wait_time = 2.0 * attempt
                    logger.warning("TejHQ Rate limited (429). Backing off for %.1fs...", wait_time)
                    time.sleep(wait_time)
                else:
                    logger.warning("TejHQ HTTP %s on %s: %s", resp.status_code, url, resp.text[:200])
            except requests.RequestException as e:
                logger.warning("TejHQ connection attempt %d failed: %s", attempt, e)
                if attempt < self.max_retries:
                    time.sleep(1.0 * attempt)

        return None

    def is_healthy(self) -> bool:
        """Probe TejHQ /health endpoint."""
        try:
            self._rate_limit()
            resp = self.session.get(f"{self.base_url}/health", timeout=5)
            return resp.status_code == 200
        except Exception as e:
            logger.debug("TejHQ health check failed: %s", e)
            return False

    def fetch_ohlcv(
        self,
        symbol: str,
        exchange: str = "NSE",
        start_date: Optional[datetime.date] = None,
        end_date: Optional[datetime.date] = None,
    ) -> pd.DataFrame:
        """
        Fetch historical daily OHLCV from TejHQ.
        URL pattern: /v1/ohlcv/{exchange}/{symbol}?from=YYYY-MM-DD&to=YYYY-MM-DD
        """
        clean_symbol = symbol.replace(".NS", "").replace(".BO", "").strip().upper()
        clean_exchange = exchange.strip().lower()

        # Default to 3 years if not specified
        if not start_date:
            start_date = datetime.date.today() - datetime.timedelta(days=365 * 3)
        if not end_date:
            end_date = datetime.date.today()

        url = f"{self.base_url}/v1/ohlcv/{clean_exchange}/{clean_symbol}"
        params = {
            "from": start_date.strftime("%Y-%m-%d"),
            "to": end_date.strftime("%Y-%m-%d"),
        }

        # If API key is present, attempt adjusted endpoint first
        if self.api_key:
            adj_url = f"{self.base_url}/v1/adjusted/{clean_exchange}/{clean_symbol}"
            adj_data = self._get_with_retry(adj_url, params=params)
            if adj_data and "data" in adj_data and adj_data["data"]:
                return self._parse_records_to_dataframe(adj_data["data"])

        raw_data = self._get_with_retry(url, params=params)
        if not raw_data or "data" not in raw_data or not raw_data["data"]:
            return pd.DataFrame()

        return self._parse_records_to_dataframe(raw_data["data"])

    def fetch_corporate_actions(
        self,
        symbol: str,
        exchange: str = "NSE",
    ) -> List[Dict[str, Any]]:
        """
        Fetch corporate actions from TejHQ: /v1/actions/{symbol}
        """
        clean_symbol = symbol.replace(".NS", "").replace(".BO", "").strip().upper()
        url = f"{self.base_url}/v1/actions/{clean_symbol}"

        data = self._get_with_retry(url)
        if not data or "data" not in data or not data["data"]:
            return []

        actions: List[Dict[str, Any]] = []
        for item in data["data"]:
            try:
                ex_date_str = item.get("ex_date")
                if not ex_date_str:
                    continue
                ex_date = datetime.datetime.strptime(ex_date_str, "%Y-%m-%d").date()
                actions.append({
                    "symbol": item.get("symbol", clean_symbol),
                    "exchange": item.get("exchange", exchange),
                    "ex_date": ex_date,
                    "record_date": datetime.datetime.strptime(item["record_date"], "%Y-%m-%d").date() if item.get("record_date") else None,
                    "action_type": item.get("type", "unknown").lower(),
                    "cash_amount": float(item["cash_amount"]) if item.get("cash_amount") is not None else None,
                    "ratio_num": float(item["ratio_num"]) if item.get("ratio_num") is not None else None,
                    "ratio_den": float(item["ratio_den"]) if item.get("ratio_den") is not None else None,
                    "raw_subject": item.get("raw_subject"),
                    "provider": "tejhq",
                })
            except Exception as e:
                logger.debug("Failed parsing corporate action: %s: %s", item, e)

        return actions

    def _parse_records_to_dataframe(self, records: List[Dict[str, Any]]) -> pd.DataFrame:
        """Parse raw TejHQ JSON records into normalized pandas DataFrame."""
        if not records:
            return pd.DataFrame()

        rows = []
        for r in records:
            dt = pd.to_datetime(r["date"]).tz_localize(None)
            rows.append({
                "date": dt,
                "open": float(r["open"]),
                "high": float(r["high"]),
                "low": float(r["low"]),
                "close": float(r["close"]),
                "volume": float(r.get("volume", 0.0)),
                "turnover": float(r["turnover"]) if r.get("turnover") is not None else None,
                "adj_close": float(r["adj_close"]) if r.get("adj_close") is not None else float(r["close"]),
            })

        df = pd.DataFrame(rows)
        df.set_index("date", inplace=True)
        df.sort_index(inplace=True)
        df = df[~df.index.duplicated(keep="first")]
        return df
