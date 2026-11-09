"""
Dedicated Scheduler Entrypoint and Process Runner for INDIGO QUANT.
Provides 24/7 autonomous scheduling on Windows with single-instance locking,
heartbeat tracking, crash recovery, missed job detection, and signal handling.
"""

from __future__ import annotations

import datetime
import json
import logging
import logging.handlers
import os
import signal
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

if sys.platform == "win32":
    import msvcrt
else:
    msvcrt = None  # type: ignore

from indigo_quant.data.calendar import (
    is_trading_day,
    now_ist,
)
from indigo_quant.db.models import SchedulerJobLog
from indigo_quant.db.session import SessionLocal
from indigo_quant.export.public_data import export_public_snapshots
from indigo_quant.export.static_report import generate_static_html
from indigo_quant.scheduler.jobs import IndigoScheduler

# Setup persistent rotating logger
LOG_DIR = Path("logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "indigo_scheduler.log"

formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

file_handler = logging.handlers.RotatingFileHandler(
    LOG_FILE, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
)
file_handler.setFormatter(formatter)
file_handler.setLevel(logging.INFO)

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(formatter)
console_handler.setLevel(logging.INFO)

root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.addHandler(file_handler)
if not any(isinstance(h, logging.StreamHandler) and h.stream == sys.stdout for h in root_logger.handlers):
    root_logger.addHandler(console_handler)

logger = logging.getLogger("indigo_quant.scheduler.runner")


class SchedulerLock:
    """
    Guarantees that strictly only ONE scheduler daemon instance runs against the database.
    Uses exclusive Windows C-runtime locking with PID tracking.
    """

    def __init__(self, lock_path: str = "data/indigo_scheduler.lock", pid_path: str = "data/indigo_scheduler.pid"):
        self.lock_path = Path(lock_path)
        self.pid_path = Path(pid_path)
        self.lock_file: Optional[Any] = None
        self.acquired = False

    def acquire(self) -> bool:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.lock_file = open(self.lock_path, "a+")
            if sys.platform == "win32" and msvcrt:
                # Seek to beginning and attempt non-blocking exclusive 1-byte lock
                self.lock_file.seek(0)
                msvcrt.locking(self.lock_file.fileno(), msvcrt.LK_NBLCK, 1)

            # Write current PID
            pid = os.getpid()
            with open(self.pid_path, "w", encoding="utf-8") as pf:
                pf.write(str(pid))

            self.acquired = True
            logger.info("Acquired single-instance scheduler lock (PID=%d)", pid)
            return True
        except (IOError, OSError) as e:
            existing_pid = "unknown"
            if self.pid_path.exists():
                try:
                    with open(self.pid_path, "r", encoding="utf-8") as pf:
                        existing_pid = pf.read().strip()
                except Exception:
                    pass
            logger.warning(
                "Could not acquire single-instance lock. Another scheduler is already running (PID=%s): %s",
                existing_pid,
                e,
            )
            return False

    def release(self) -> None:
        if self.acquired and self.lock_file:
            try:
                if sys.platform == "win32" and msvcrt:
                    self.lock_file.seek(0)
                    msvcrt.locking(self.lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                self.lock_file.close()
            except Exception as e:
                logger.debug("Error releasing file lock: %s", e)

            if self.pid_path.exists():
                try:
                    self.pid_path.unlink()
                except Exception:
                    pass
            self.acquired = False
            logger.info("Released single-instance scheduler lock.")


class HeartbeatWatchdog:
    """
    Maintains a regular heartbeat file (data/heartbeat.json).
    Allows external processes (CLI doctor, dashboard, Task Scheduler watchdog) to verify liveness.
    """

    def __init__(
        self,
        scheduler_engine: IndigoScheduler,
        heartbeat_path: str = "data/heartbeat.json",
        interval_seconds: int = 30,
    ):
        self.scheduler_engine = scheduler_engine
        self.heartbeat_path = Path(heartbeat_path)
        self.interval = interval_seconds
        self.start_time = now_ist()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self.write_heartbeat(status="STARTING")
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, name="HeartbeatThread", daemon=True)
        self._thread.start()
        logger.info("Heartbeat watchdog thread started (cadence: %ds).", self.interval)

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)
        self.write_heartbeat(status="STOPPED")
        logger.info("Heartbeat watchdog stopped.")

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            self.write_heartbeat(status="HEALTHY")
            self._stop_event.wait(self.interval)

    def write_heartbeat(self, status: str = "HEALTHY") -> None:
        try:
            now = now_ist()
            uptime = int((now - self.start_time).total_seconds())

            # Find next scheduled jobs
            next_runs: Dict[str, str] = {}
            if self.scheduler_engine and self.scheduler_engine.scheduler:
                for job in self.scheduler_engine.scheduler.get_jobs():
                    nxt = job.next_run_time
                    next_runs[job.id] = nxt.strftime("%Y-%m-%d %H:%M:%S IST") if nxt else "None"

            # Check last job in database
            last_run_info = None
            db = SessionLocal()
            try:
                from sqlalchemy import select
                stmt = select(SchedulerJobLog).order_by(SchedulerJobLog.run_timestamp.desc()).limit(1)
                last_log = db.execute(stmt).scalar_one_or_none()
                if last_log:
                    last_run_info = {
                        "job": last_log.job_name,
                        "status": last_log.status,
                        "timestamp": last_log.run_timestamp.strftime("%Y-%m-%d %H:%M:%S IST") if last_log.run_timestamp else None,
                    }
            finally:
                db.close()

            payload = {
                "pid": os.getpid(),
                "status": status,
                "started_at": self.start_time.strftime("%Y-%m-%d %H:%M:%S IST"),
                "last_heartbeat": now.strftime("%Y-%m-%d %H:%M:%S IST"),
                "uptime_seconds": uptime,
                "active_jobs": list(next_runs.keys()),
                "next_scheduled_runs": next_runs,
                "last_completed_job": last_run_info,
                "python_version": sys.version.split()[0],
                "platform": sys.platform,
            }

            self.heartbeat_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.heartbeat_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
        except Exception as e:
            logger.debug("Error writing heartbeat: %s", e)


class SchedulerService:
    """Autonomous trading engine service coordinator."""

    def __init__(self):
        self.lock = SchedulerLock()
        self.scheduler = IndigoScheduler()
        self.watchdog: Optional[HeartbeatWatchdog] = None
        self._shutdown_requested = False

    def recover_missed_jobs(self) -> None:
        """
        Check if any scheduled jobs were missed due to laptop sleep or downtime.
        Never backdates paper fills or invents executions.
        """
        now = now_ist()
        today = now.date()

        if not is_trading_day(today):
            logger.info("Today (%s) is a market holiday or weekend. No missed job recovery needed.", today)
            return

        db = SessionLocal()
        try:
            from sqlalchemy import select
            # Check if evening scan was already completed today
            stmt = select(SchedulerJobLog).where(
                SchedulerJobLog.job_name == "evening_eod_scan",
                SchedulerJobLog.status == "SUCCESS",
            ).order_by(SchedulerJobLog.run_timestamp.desc()).limit(1)
            last_scan = db.execute(stmt).scalar_one_or_none()

            last_scan_date = last_scan.run_timestamp.date() if last_scan and last_scan.run_timestamp else None

            # If it's evening (> 19:15 IST) and today's scan hasn't run yet, trigger it
            if now.time() >= datetime.time(19, 15) and last_scan_date != today:
                logger.info("Missed Job Recovery: Triggering missed evening scan for today (%s)...", today)
                self.scheduler.run_evening_scan_job(force=False)
                # Export public snapshots immediately after recovery
                export_public_snapshots()
                generate_static_html()
            else:
                logger.info("No missed trading jobs detected. Systems synchronized.")
        except Exception as e:
            logger.error("Error during missed job recovery check: %s", e)
        finally:
            db.close()

    def run(self) -> None:
        """Main service entrypoint."""
        logger.info("Starting INDIGO QUANT Autonomous Scheduler Daemon...")

        # 1. Acquire single-instance lock
        if not self.lock.acquire():
            logger.error("Single-instance check failed. Another instance is already running. Exiting.")
            sys.exit(0)

        # 2. Register signal handlers
        def handle_signal(sig, frame):
            logger.info("Received termination signal (%s). Initiating graceful shutdown...", sig)
            self.stop()
            sys.exit(0)

        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)

        try:
            # 3. Start APScheduler engine
            self.scheduler.start()

            # 4. Start Heartbeat Watchdog
            self.watchdog = HeartbeatWatchdog(self.scheduler)
            self.watchdog.start()

            # 5. Export initial public data snapshots
            try:
                export_public_snapshots()
                generate_static_html()
                logger.info("Initial public data snapshots and static HTML generated.")
            except Exception as e:
                logger.warning("Could not export initial public snapshots: %s", e)

            # 6. Check and recover missed jobs
            self.recover_missed_jobs()

            logger.info("INDIGO QUANT Scheduler is RUNNING AUTONOMOUSLY in background. Press Ctrl+C to stop.")

            # 7. Main persistence loop
            while not self._shutdown_requested:
                time.sleep(1)

        except (KeyboardInterrupt, SystemExit):
            logger.info("Shutdown requested.")
        except Exception as e:
            logger.critical("Unhandled exception in scheduler daemon: %s", e, exc_info=True)
            self.scheduler.notifier.send_error_alert("Scheduler Daemon Crash", str(e))
        finally:
            self.stop()

    def stop(self) -> None:
        """Gracefully stop all scheduler threads and release lock."""
        self._shutdown_requested = True
        logger.info("Shutting down IndigoScheduler...")
        if self.watchdog:
            self.watchdog.stop()
        if self.scheduler:
            self.scheduler.stop()
        self.lock.release()
        logger.info("INDIGO QUANT Scheduler stopped gracefully.")


def main():
    service = SchedulerService()
    service.run()


if __name__ == "__main__":
    main()
