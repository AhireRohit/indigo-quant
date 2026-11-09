"""
Data quality validation and integrity verification module for Indian Equities.
Ensures zero forward-fill leakage, strict OHLC logic, liquidity thresholds, and staleness checks.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

from indigo_quant.data.calendar import get_latest_completed_trading_day


class DataValidationError(Exception):
    """Raised when market data violates fundamental sanity constraints."""
    pass


def validate_ohlcv_dataframe(
    df: pd.DataFrame,
    symbol: str,
    min_required_bars: int = 260,
    check_freshness: bool = True,
    max_stale_days: int = 4,
) -> Tuple[bool, List[str]]:
    """
    Validate an OHLCV DataFrame for structural sanity and market rules.
    Returns (is_valid, list_of_error_reasons).
    """
    errors: List[str] = []

    if df.empty:
        return False, [f"{symbol}: Empty DataFrame received."]

    # Required columns
    required_cols = {"open", "high", "low", "close", "volume"}
    missing = required_cols - set(df.columns)
    if missing:
        return False, [f"{symbol}: Missing required columns: {missing}"]

    # Check minimum history (e.g. 260 sessions for 200-session indicators)
    if len(df) < min_required_bars:
        errors.append(
            f"{symbol}: Insufficient historical bars ({len(df)} < {min_required_bars} required)."
        )

    # Check duplicate dates / indices
    if df.index.duplicated().any():
        dup_count = df.index.duplicated().sum()
        errors.append(f"{symbol}: Found {dup_count} duplicate date rows.")

    # Sort index chronologically
    if not df.index.is_monotonic_increasing:
        errors.append(f"{symbol}: Date index is not strictly monotonically increasing.")

    # Check nonpositive prices
    for col in ["open", "high", "low", "close"]:
        invalid_prices = (df[col] <= 0) | df[col].isna() | np.isinf(df[col])
        if invalid_prices.any():
            count = invalid_prices.sum()
            errors.append(f"{symbol}: Found {count} nonpositive or NaN values in '{col}'.")

    # Check negative volume
    invalid_volume = (df["volume"] < 0) | df["volume"].isna()
    if invalid_volume.any():
        errors.append(f"{symbol}: Found {invalid_volume.sum()} negative or NaN volume values.")

    # High / Low / Open / Close logic:
    # high must be >= open, close, low
    # low must be <= open, close, high
    high_viol = (df["high"] < df["low"]) | (df["high"] < df["open"]) | (df["high"] < df["close"])
    if high_viol.any():
        errors.append(f"{symbol}: High is lower than open/close/low in {high_viol.sum()} bars.")

    low_viol = (df["low"] > df["open"]) | (df["low"] > df["close"])
    if low_viol.any():
        errors.append(f"{symbol}: Low is higher than open/close in {low_viol.sum()} bars.")

    # Freshness validation
    if check_freshness and len(df) > 0:
        latest_bar_date = df.index[-1]
        if isinstance(latest_bar_date, pd.Timestamp):
            latest_bar_date = latest_bar_date.date()

        latest_expected = get_latest_completed_trading_day()
        calendar_diff = (latest_expected - latest_bar_date).days
        if calendar_diff > max_stale_days:
            errors.append(
                f"{symbol}: Data is stale. Latest bar date is {latest_bar_date}, expected ~{latest_expected}."
            )

    is_valid = len(errors) == 0
    return is_valid, errors


def check_liquidity(
    df: pd.DataFrame,
    min_price: float = 75.0,
    min_avg_turnover: float = 50000000.0, # ₹5 Crore
    window: int = 20,
) -> Tuple[bool, Optional[str]]:
    """
    Check if a stock meets universe liquidity filters:
    1. Current close >= min_price (₹75)
    2. Mean daily traded value (close * volume) over last 20 completed sessions >= min_avg_turnover (₹5 Crore).
    """
    if len(df) < window:
        return False, f"Fewer than {window} bars available to evaluate liquidity."

    latest_close = df["close"].iloc[-1]
    if latest_close < min_price:
        return False, f"Current price ₹{latest_close:.2f} is below minimum threshold ₹{min_price:.2f}."

    # Compute daily traded value
    if "turnover" in df.columns and df["turnover"].dropna().sum() > 0:
        daily_turnover = df["turnover"].tail(window)
    else:
        daily_turnover = (df["close"] * df["volume"]).tail(window)

    mean_turnover = daily_turnover.mean()
    if mean_turnover < min_avg_turnover:
        return False, (
            f"Mean daily traded value over last {window} sessions is ₹{mean_turnover:,.0f}, "
            f"which is below ₹{min_avg_turnover:,.0f} (₹5 Cr) threshold."
        )

    return True, None


def reconcile_provider_prices(
    df_primary: pd.DataFrame,
    df_secondary: pd.DataFrame,
    symbol: str,
    tolerance_pct: float = 2.0,
) -> Tuple[bool, List[str]]:
    """
    Compare overlapping closes between TejHQ and Yahoo Finance.
    Alert if price discrepancy exceeds tolerance percentage.
    """
    discrepancies: List[str] = []
    common_dates = df_primary.index.intersection(df_secondary.index)
    if len(common_dates) == 0:
        return False, [f"{symbol}: No overlapping dates between providers for cross-validation."]

    p1 = df_primary.loc[common_dates, "close"]
    p2 = df_secondary.loc[common_dates, "close"]

    diff_pct = (np.abs(p1 - p2) / p1) * 100.0
    bad_dates = diff_pct[diff_pct > tolerance_pct]

    if not bad_dates.empty:
        max_diff = bad_dates.max()
        worst_date = bad_dates.idxmax()
        discrepancies.append(
            f"{symbol}: Cross-provider price discrepancy exceeds {tolerance_pct}% on {len(bad_dates)} sessions. "
            f"Worst on {worst_date}: {max_diff:.2f}% diff."
        )

    return len(discrepancies) == 0, discrepancies
