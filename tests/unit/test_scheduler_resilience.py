"""
Unit and regression tests for Scheduler Resilience, Single-Instance Locking,
Heartbeat Watchdog, and Missed Job Recovery Logic.
"""

import datetime
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from indigo_quant.data.calendar import is_trading_day
from indigo_quant.scheduler.runner import HeartbeatWatchdog, SchedulerLock, SchedulerService


def test_scheduler_single_instance_lock():
    """Verify that only one scheduler can acquire the lock simultaneously."""
    with tempfile.TemporaryDirectory() as td:
        tmp_path = Path(td)
        lock_file = tmp_path / "test_scheduler.lock"
        pid_file = tmp_path / "test_scheduler.pid"

        lock1 = SchedulerLock(lock_path=str(lock_file), pid_path=str(pid_file))
        lock2 = SchedulerLock(lock_path=str(lock_file), pid_path=str(pid_file))

        # First lock succeeds
        assert lock1.acquire() is True
        assert pid_file.exists()

        # Second lock fails
        assert lock2.acquire() is False

        # After first releases, second succeeds
        lock1.release()
        assert lock2.acquire() is True
        lock2.release()


def test_heartbeat_payload_structure():
    """Verify heartbeat file is properly written with all required monitoring fields."""
    with tempfile.TemporaryDirectory() as td:
        tmp_path = Path(td)
        heartbeat_file = tmp_path / "heartbeat.json"
        mock_scheduler = MagicMock()
        mock_scheduler.scheduler.get_jobs.return_value = []

        watchdog = HeartbeatWatchdog(mock_scheduler, heartbeat_path=str(heartbeat_file), interval_seconds=1)
        watchdog.write_heartbeat(status="HEALTHY")

        assert heartbeat_file.exists()
        with open(heartbeat_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        assert data["status"] == "HEALTHY"
        assert "pid" in data
        assert "started_at" in data
        assert "last_heartbeat" in data
        assert "uptime_seconds" in data
        assert "active_jobs" in data
        assert "next_scheduled_runs" in data


def test_missed_job_recovery_behavior_on_trading_day():
    """Verify that November 9, 2026 triggers missed job recovery if evening scan was not yet run."""
    nov_9 = datetime.date(2026, 11, 9)
    assert is_trading_day(nov_9) is True

    service = SchedulerService()
    # Mock now_ist to return Nov 9, 2026 at 20:00 IST
    mock_now = datetime.datetime(2026, 11, 9, 20, 0, 0)

    # Mock database to simulate that no scan was run on Nov 9 (last scan was Nov 6)
    mock_db = MagicMock()
    mock_last_scan = MagicMock()
    mock_last_scan.run_timestamp = datetime.datetime(2026, 11, 6, 19, 15, 0)
    mock_db.execute.return_value.scalar_one_or_none.return_value = mock_last_scan

    with patch("indigo_quant.scheduler.runner.now_ist", return_value=mock_now):
        with patch("indigo_quant.scheduler.runner.SessionLocal", return_value=mock_db):
            with patch.object(service.scheduler, "run_evening_scan_job") as mock_scan:
                with patch("indigo_quant.scheduler.runner.export_public_snapshots"):
                    with patch("indigo_quant.scheduler.runner.generate_static_html"):
                        service.recover_missed_jobs()
                        assert mock_scan.called
