"""
Walk-Forward Split and Out-of-Sample Partitioning.
Strictly preserves temporal ordering. No random shuffling of time series data.
"""

from __future__ import annotations

import datetime
from typing import List, Tuple


def get_train_val_test_splits(
    dates: List[datetime.date],
    train_ratio: float = 0.60,
    val_ratio: float = 0.20,
) -> Tuple[Tuple[datetime.date, datetime.date], Tuple[datetime.date, datetime.date], Tuple[datetime.date, datetime.date]]:
    """
    Compute chronological non-overlapping date ranges:
    - In-Sample Training (e.g. 60%)
    - In-Sample Validation (e.g. 20%)
    - Out-of-Sample Test (e.g. 20%)
    """
    sorted_dates = sorted(dates)
    n = len(sorted_dates)
    if n < 30:
        raise ValueError("Insufficient date points for walk-forward splitting (< 30).")

    train_end_idx = int(n * train_ratio)
    val_end_idx = int(n * (train_ratio + val_ratio))

    train_split = (sorted_dates[0], sorted_dates[train_end_idx - 1])
    val_split = (sorted_dates[train_end_idx], sorted_dates[val_end_idx - 1])
    test_split = (sorted_dates[val_end_idx], sorted_dates[-1])

    return train_split, val_split, test_split
