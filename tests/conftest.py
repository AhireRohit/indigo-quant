"""
Pytest configuration and global test isolation fixtures for INDIGO QUANT.

Guarantees 100% strict test isolation:
1. Every test runs against an isolated temporary SQLite database, NEVER modifying data/indigo_quant.db.
2. Production logs (logs/indigo_scheduler.log) are protected; test logs route to logs/test_runs.log.
3. External Telegram API calls are blocked and mocked.
4. Production lock, heartbeat, PID, alerts cache, and public snapshots are never overwritten.
"""

from __future__ import annotations

import datetime
import logging
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from indigo_quant.api.main import app
from indigo_quant.db.models import Base
from indigo_quant.db.repository import seed_universe_and_accounts
from indigo_quant.db.session import get_db

# Configure test logging
TEST_LOG_PATH = Path("logs/test_runs.log")
TEST_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def pytest_configure(config):
    """Ensure environment is flagged as TEST mode and strip any production log handlers."""
    os.environ["INDIGO_TEST_MODE"] = "1"
    os.environ["TELEGRAM_ENABLED"] = "false"
    os.environ["TELEGRAM_BOT_TOKEN"] = "123456:MOCK_TEST_TOKEN_FOR_TESTS"
    os.environ["TELEGRAM_CHAT_ID"] = "12345678"

    root_logger = logging.getLogger()
    # Strip any handlers that write to indigo_scheduler.log
    for h in list(root_logger.handlers):
        base_name = getattr(h, "baseFilename", "")
        if "indigo_scheduler.log" in str(base_name):
            root_logger.removeHandler(h)

    # Attach isolated test file handler
    test_formatter = logging.Formatter(
        "[%(asctime)s] [TEST] [%(levelname)s] [%(name)s]: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    test_handler = logging.FileHandler(TEST_LOG_PATH, encoding="utf-8")
    test_handler.setFormatter(test_formatter)
    test_handler.setLevel(logging.INFO)
    root_logger.addHandler(test_handler)


@pytest.fixture(scope="session")
def global_test_isolation():
    """
    Session-wide fixture that establishes a dedicated, isolated test directory and SQLite DB.
    Monkeypatches session, repository, and FastAPI dependencies to guarantee production isolation.
    """
    td = tempfile.TemporaryDirectory()
    test_dir = Path(td.name)
    test_db_path = test_dir / "test_indigo_quant.db"

    # Set environment overrides
    os.environ["DATABASE_URL"] = f"sqlite:///{test_db_path.as_posix()}"
    os.environ["INDIGO_LOCK_PATH"] = str(test_dir / "test_scheduler.lock")
    os.environ["INDIGO_PID_PATH"] = str(test_dir / "test_scheduler.pid")
    os.environ["INDIGO_HEARTBEAT_PATH"] = str(test_dir / "test_heartbeat.json")
    os.environ["INDIGO_ALERTS_CACHE_PATH"] = str(test_dir / "test_sent_alerts.json")
    os.environ["INDIGO_PUBLIC_DATA_DIR"] = str(test_dir / "test_public_data")
    os.environ["INDIGO_LOG_FILE"] = str(TEST_LOG_PATH)

    # Build isolated test database engine
    test_engine = create_engine(
        f"sqlite:///{test_db_path.as_posix()}",
        connect_args={"check_same_thread": False},
        echo=False,
    )
    Base.metadata.create_all(bind=test_engine)
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    # Seed initial test universe and accounts
    seed_db = TestSessionLocal()
    seed_universe_and_accounts(seed_db)
    seed_db.close()

    # Monkeypatch global engine and SessionLocal in db modules
    import indigo_quant.db.repository as repo_mod
    import indigo_quant.db.session as session_mod

    old_engine = session_mod.engine
    old_sessionlocal = session_mod.SessionLocal
    old_repo_engine = repo_mod.engine

    session_mod.engine = test_engine
    session_mod.SessionLocal = TestSessionLocal
    repo_mod.engine = test_engine

    # Override FastAPI get_db dependency
    def override_get_db():
        db = TestSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    # Intercept external HTTP requests during test execution
    def mock_post(url, *args, **kwargs):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '{"ok": true, "result": {"message_id": 99999}}'
        mock_resp.json.return_value = {"ok": True, "result": {"message_id": 99999}}
        return mock_resp

    patcher = patch("requests.post", side_effect=mock_post)
    patcher.start()

    yield {
        "engine": test_engine,
        "sessionmaker": TestSessionLocal,
        "test_dir": test_dir,
    }

    # Teardown: stop patcher, clear overrides, close and dispose SQLite pool
    patcher.stop()
    app.dependency_overrides.clear()
    session_mod.engine = old_engine
    session_mod.SessionLocal = old_sessionlocal
    repo_mod.engine = old_repo_engine

    test_engine.dispose()
    try:
        td.cleanup()
    except Exception:
        pass


@pytest.fixture(autouse=True)
def clean_db_per_test(global_test_isolation):
    """Ensure every individual test gets a clean database state with 5 strategy accounts and universe."""
    session_factory = global_test_isolation["sessionmaker"]
    engine = global_test_isolation["engine"]

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = session_factory()
    seed_universe_and_accounts(db)
    db.close()
    yield


@pytest.fixture
def db_session(global_test_isolation):
    """Provide a fresh isolated DB session for a unit test."""
    session_factory = global_test_isolation["sessionmaker"]
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def synthetic_ohlcv_uptrend():
    """
    Generate 300 daily bars of clean bullish trending OHLCV data.
    Designed for deterministic indicator and strategy testing.
    """
    np.random.seed(42)
    num_bars = 300

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
