"""
Pytest configuration and synthetic fixtures for Indigo Quant tests.
Uses an isolated in-memory SQLite database and deterministic synthetic price generators.
"""

from __future__ import annotations

import datetime

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from indigo_quant.db.repository import seed_universe_and_accounts
from indigo_quant.db.session import Base


@pytest.fixture
def db_session():
    """Create a fresh in-memory SQLite database for test isolation."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    seed_universe_and_accounts(session)
    yield session
    session.close()


@pytest.fixture
def synthetic_ohlcv_uptrend():
    """
    Generate 300 daily bars of clean bullish trending OHLCV data.
    Designed for deterministic indicator and strategy testing.
    """
    np.random.seed(42)
    num_bars = 300

    # Strong steady uptrend with gentle noise
    trend = np.linspace(100.0, 300.0, num_bars)
    noise = np.random.normal(0, 0.5, num_bars)
    closes = trend + noise

    start_date = datetime.date(2023, 1, 1)
    dates = [start_date + datetime.timedelta(days=i) for i in range(num_bars)]

    rows = []
    for i in range(num_bars):
        c = closes[i]
        o = c - np.random.uniform(-0.5, 0.5)
        h = max(o, c) + np.random.uniform(0.5, 2.0)
        low_val = min(o, c) - np.random.uniform(0.5, 2.0)
        v = 1000000.0 + np.random.uniform(-50000, 50000)
        rows.append({
            "date": pd.to_datetime(dates[i]),
            "open": round(o, 2),
            "high": round(h, 2),
            "low": round(low_val, 2),
            "close": round(c, 2),
            "volume": round(v, 0),
        })

    df = pd.DataFrame(rows).set_index("date")
    df["turnover"] = df["close"] * df["volume"]
    return df
