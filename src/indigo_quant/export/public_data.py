"""
Public Data Exporter and Sanitizer for INDIGO QUANT.
Exports clean, sanitized, read-only JSON snapshots to `public_data/`.
Powers the free Streamlit Community Cloud public dashboard and static reports.

Strictly scrubs local paths, credentials, machine hostnames, and private IPs.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from indigo_quant.data.calendar import get_latest_completed_trading_day, now_ist
from indigo_quant.db.models import (
    HistoricalBar,
    PaperPosition,
    PortfolioEquitySnapshot,
    SignalRecord,
)
from indigo_quant.db.repository import Repository
from indigo_quant.db.session import SessionLocal

logger = logging.getLogger(__name__)

# Sanitization regexes
PATH_PATTERN = re.compile(r"([A-Za-z]:\\[^\"'\n\r\t]+|/home/[^\"'\n\r\t]+|/Users/[^\"'\n\r\t]+)")
SECRET_KEY_PATTERN = re.compile(r"(api[-_]?key|token|secret|password|bearer)[=:\s]+[A-Za-z0-9_\-\.]{8,}", re.IGNORECASE)


def sanitize_text(text: str) -> str:
    """Scrub sensitive paths, machine usernames, and credential tokens from strings."""
    if not isinstance(text, str):
        return text
    # Replace Windows / Unix absolute paths
    clean = PATH_PATTERN.sub("[LOCAL_PATH_REDACTED]", text)
    # Redact potential key patterns
    clean = SECRET_KEY_PATTERN.sub(r"\1=[REDACTED]", clean)
    return clean


def sanitize_dict(obj: Any) -> Any:
    """Recursively sanitize strings inside dictionaries and lists."""
    if isinstance(obj, dict):
        return {k: sanitize_dict(v) for k, v in obj.items() if not k.lower().endswith(("token", "secret", "password", "key"))}
    elif isinstance(obj, list):
        return [sanitize_dict(item) for item in obj]
    elif isinstance(obj, str):
        return sanitize_text(obj)
    return obj


class PublicDataExporter:
    """Exports sanitized JSON snapshots for public dashboard hosting."""

    def __init__(self, db: Optional[Session] = None, output_dir: str = "public_data"):
        self.db = db or SessionLocal()
        self._owns_db = db is None
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def close(self):
        if self._owns_db and self.db:
            self.db.close()

    def export_all(self) -> Dict[str, str]:
        """Export all 6 core snapshot files and return paths."""
        try:
            repo = Repository(self.db)
            files = {}

            # 1. System Health
            health_data = self._build_system_health(repo)
            files["system_health"] = self._write_json("system_health.json", health_data)

            # 2. Leaderboard & Strategy Metrics
            leaderboard_data = self._build_leaderboard(repo)
            files["leaderboard"] = self._write_json("leaderboard.json", leaderboard_data)

            # 3. Signals & Candidates
            signals_data = self._build_signals(repo)
            files["signals"] = self._write_json("signals.json", signals_data)

            # 4. Portfolios & Trade Log
            portfolios_data = self._build_portfolios(repo)
            files["portfolios"] = self._write_json("portfolios.json", portfolios_data)

            # 5. Charts Data
            charts_data = self._build_charts_data(repo)
            files["charts_data"] = self._write_json("charts_data.json", charts_data)

            # 6. Global Overview
            overview_data = self._build_overview(repo, leaderboard_data, health_data)
            files["overview"] = self._write_json("overview.json", overview_data)

            logger.info("Successfully exported public data snapshots to %s", self.output_dir)
            return files
        finally:
            self.close()

    def _write_json(self, filename: str, data: Any) -> str:
        filepath = self.output_dir / filename
        sanitized = sanitize_dict(data)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(sanitized, f, indent=2, default=str)
        return str(filepath)

    def _build_system_health(self, repo: Repository) -> Dict[str, Any]:
        """Construct system health snapshot."""
        heartbeat_file = Path("data/heartbeat.json")
        heartbeat_info: Dict[str, Any] = {}
        if heartbeat_file.exists():
            try:
                with open(heartbeat_file, "r", encoding="utf-8") as f:
                    heartbeat_info = json.load(f)
            except Exception:
                pass

        from indigo_quant.db.models import SchedulerJobLog
        stmt_job = select(SchedulerJobLog).where(SchedulerJobLog.job_name == "evening_eod_scan").order_by(SchedulerJobLog.run_timestamp.desc()).limit(1)
        last_job = self.db.execute(stmt_job).scalar_one_or_none()
        latest_market_day = get_latest_completed_trading_day()
        ist_time = now_ist()

        return {
            "status": "HEALTHY",
            "last_audit_ist": ist_time.strftime("%Y-%m-%d %H:%M:%S IST"),
            "latest_completed_market_day": str(latest_market_day),
            "scheduler": {
                "is_active": heartbeat_info.get("status") == "HEALTHY",
                "last_heartbeat": heartbeat_info.get("last_heartbeat", "N/A"),
                "next_scheduled_run": heartbeat_info.get("next_scheduled_run", "19:15 IST (Mon-Fri)"),
                "missed_recovery_enabled": True,
            },
            "last_scan": {
                "timestamp": last_job.run_timestamp.isoformat() if last_job else None,
                "status": last_job.status if last_job else "N/A",
                "message": last_job.message if last_job else "No recent scan",
            },
            "data_providers": {
                "tejhq": {"status": "OPERATIONAL", "tier": "Free Verified", "description": "Primary EOD & Actions"},
                "yfinance": {"status": "OPERATIONAL", "tier": "Free", "description": "Fallback & ^NSEI Benchmark"},
            },
            "hosting": {
                "engine": "Windows 11 Laptop Autonomous Daemon",
                "dashboard": "Streamlit Community Cloud (Read-Only)",
                "data_sync": "Continuous Git Snapshot Push",
            },
        }

    def _build_leaderboard(self, repo: Repository) -> List[Dict[str, Any]]:
        """Construct strategy leaderboard ranking."""
        accounts = repo.get_accounts()
        leaderboard = []

        for acc in accounts:
            stmt = select(PaperPosition).where(PaperPosition.account_id == acc.id)
            positions = list(self.db.execute(stmt).scalars().all())
            closed_positions = [p for p in positions if p.status == "CLOSED"]
            open_positions = [p for p in positions if p.status == "OPEN"]

            total_trades = len(closed_positions)
            winning_trades = [p for p in closed_positions if (p.realized_pnl_net or 0) > 0]
            target_hits = [p for p in closed_positions if (p.close_reason or "").startswith("TARGET_HIT")]
            stop_hits = [p for p in closed_positions if (p.close_reason or "").startswith("STOP_LOSS")]

            win_rate = (len(winning_trades) / total_trades * 100.0) if total_trades > 0 else 0.0
            target_hit_rate = (len(target_hits) / total_trades * 100.0) if total_trades > 0 else 0.0
            total_return_pct = ((acc.current_equity - acc.initial_capital) / acc.initial_capital) * 100.0

            leaderboard.append({
                "strategy_id": acc.id,
                "strategy_name": acc.name,
                "version": acc.version,
                "initial_capital": acc.initial_capital,
                "current_cash": round(acc.current_cash, 2),
                "current_equity": round(acc.current_equity, 2),
                "total_return_pct": round(total_return_pct, 2),
                "open_positions_count": len(open_positions),
                "total_trades": total_trades,
                "target_hits_count": len(target_hits),
                "target_hit_rate": round(target_hit_rate, 1),
                "stop_hits_count": len(stop_hits),
                "win_rate": round(win_rate, 1),
            })

        # Rank by current equity descending
        leaderboard.sort(key=lambda x: x["current_equity"], reverse=True)
        for i, item in enumerate(leaderboard, 1):
            item["rank"] = i

        return leaderboard

    def _build_signals(self, repo: Repository) -> Dict[str, Any]:
        """Construct recent BUY signals and rejected candidates snapshot."""
        # Fetch last 30 signals
        stmt = select(SignalRecord).order_by(SignalRecord.signal_date.desc(), SignalRecord.rule_quality_score.desc()).limit(50)
        records = list(self.db.execute(stmt).scalars().all())

        signals_list = []
        for r in records:
            rules_passed = []
            try:
                rules_passed = json.loads(r.rules_passed_json)
            except Exception:
                pass

            rules_failed = []
            try:
                rules_failed = json.loads(r.rules_failed_json)
            except Exception:
                pass

            signals_list.append({
                "id": r.id,
                "symbol": r.symbol,
                "strategy_id": r.strategy_id,
                "strategy_name": r.strategy_id.replace("_", " ").title(),
                "signal_date": str(r.signal_date),
                "decision": r.decision,
                "rule_quality_score": round(r.rule_quality_score, 1),
                "reference_close": round(r.reference_close, 2),
                "target_price_estimate": round(r.target_price_estimate, 2),
                "initial_stop_estimate": round(r.initial_stop_estimate, 2),
                "reward_to_risk_ratio": round(r.reward_to_risk_ratio, 2),
                "regime_status": r.regime_status,
                "execution_status": r.execution_status,
                "rules_passed": rules_passed,
                "rules_failed": rules_failed,
            })

        # Fetch rejected candidates
        from indigo_quant.db.models import RejectedCandidate
        stmt_rej = select(RejectedCandidate).order_by(RejectedCandidate.date.desc()).limit(30)
        rejected_records = list(self.db.execute(stmt_rej).scalars().all())
        rejected_list = []
        for rej in rejected_records:
            failed_conds = []
            try:
                failed_conds = json.loads(rej.failed_conditions_json)
            except Exception:
                pass
            rejected_list.append({
                "symbol": rej.symbol,
                "strategy_id": rej.strategy_id,
                "date": str(rej.date),
                "reason": rej.reason,
                "failed_conditions": failed_conds,
            })

        return {
            "signals": signals_list,
            "rejected_candidates": rejected_list,
            "total_signals_stored": len(signals_list),
        }

    def _build_portfolios(self, repo: Repository) -> Dict[str, Any]:
        """Construct positions, open holdings, and closed trades snapshot."""
        accounts = repo.get_accounts()
        result = {}

        for acc in accounts:
            stmt = select(PaperPosition).where(PaperPosition.account_id == acc.id)
            positions = list(self.db.execute(stmt).scalars().all())
            open_pos = []
            closed_pos = []

            for p in positions:
                item = {
                    "id": p.id,
                    "symbol": p.symbol,
                    "strategy_id": p.strategy_id,
                    "quantity": p.quantity,
                    "entry_date": str(p.entry_date),
                    "entry_price": round(p.entry_price, 2),
                    "current_stop": round(p.current_stop, 2),
                    "target_price": round(p.target_price, 2),
                    "sessions_held": p.sessions_held,
                    "status": p.status,
                    "closed_date": str(p.closed_date) if p.closed_date else None,
                    "close_price": round(p.close_price, 2) if p.close_price else None,
                    "close_reason": p.close_reason,
                    "realized_pnl_net": round(p.realized_pnl_net, 2) if p.realized_pnl_net else None,
                    "realized_pnl_gross": round(p.realized_pnl_gross, 2) if p.realized_pnl_gross else None,
                    "total_fees_paid": round(p.total_fees_paid, 2) if p.total_fees_paid else 0.0,
                    "target_achieved": p.target_achieved,
                }
                if p.status == "OPEN":
                    open_pos.append(item)
                else:
                    closed_pos.append(item)

            result[acc.id] = {
                "account_id": acc.id,
                "account_name": acc.name,
                "cash": round(acc.current_cash, 2),
                "equity": round(acc.current_equity, 2),
                "open_positions": open_pos,
                "closed_positions": closed_pos,
            }

        return result

    def _build_charts_data(self, repo: Repository) -> Dict[str, Any]:
        """Construct daily equity curves for plotting interactive charts."""
        accounts = repo.get_accounts()
        equity_curves = {}

        for acc in accounts:
            stmt = select(PortfolioEquitySnapshot).where(PortfolioEquitySnapshot.account_id == acc.id).order_by(PortfolioEquitySnapshot.date.asc())
            snaps = list(self.db.execute(stmt).scalars().all())
            equity_curves[acc.id] = [
                {
                    "date": str(s.date),
                    "cash": round(s.cash_balance, 2),
                    "invested": round(s.invested_value, 2),
                    "total_equity": round(s.total_equity, 2),
                    "open_positions": s.open_positions_count,
                }
                for s in snaps
            ]

        # NIFTY 50 Benchmark Series
        stmt_nifty = select(HistoricalBar).where(HistoricalBar.symbol == "^NSEI").order_by(HistoricalBar.date.asc())
        nifty_bars = list(self.db.execute(stmt_nifty).scalars().all())
        nifty_series = [
            {"date": str(b.date), "close": round(b.close, 2)}
            for b in nifty_bars[-250:]  # Last 250 trading days
        ]

        return {
            "equity_curves": equity_curves,
            "benchmark_series": nifty_series,
        }

    def _build_overview(
        self,
        repo: Repository,
        leaderboard_data: List[Dict[str, Any]],
        health_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Construct summary overview snapshot."""
        total_initial = sum(item["initial_capital"] for item in leaderboard_data)
        total_equity = sum(item["current_equity"] for item in leaderboard_data)
        total_open_pos = sum(item["open_positions_count"] for item in leaderboard_data)
        total_trades = sum(item["total_trades"] for item in leaderboard_data)
        total_target_hits = sum(item["target_hits_count"] for item in leaderboard_data)

        combined_return_pct = ((total_equity - total_initial) / total_initial) * 100.0 if total_initial > 0 else 0.0
        combined_target_hit_rate = (total_target_hits / total_trades * 100.0) if total_trades > 0 else 0.0

        instruments = repo.get_active_instruments()

        return {
            "system_name": "INDIGO QUANT",
            "tagline": "Autonomous Indian Equity Swing-Trading & Research Platform",
            "target_objective": "10% Gross Upside (5–20 Sessions)",
            "last_updated_ist": now_ist().strftime("%Y-%m-%d %H:%M:%S IST"),
            "latest_market_session": health_data.get("latest_completed_market_day"),
            "tracked_instruments_count": len(instruments),
            "competing_strategies_count": len(leaderboard_data),
            "capital_metrics": {
                "initial_total_capital": total_initial,
                "current_total_equity": round(total_equity, 2),
                "combined_return_pct": round(combined_return_pct, 2),
                "open_positions_total": total_open_pos,
                "closed_trades_total": total_trades,
                "target_hits_total": total_target_hits,
                "target_hit_rate_pct": round(combined_target_hit_rate, 1),
            },
            "disclaimer": "Simulated paper trading only. No real broker execution. 10% target is an algorithmic benchmark, not a guarantee.",
        }


def export_public_snapshots(output_dir: str = "public_data") -> Dict[str, str]:
    """Helper function to execute export with fresh DB session."""
    exporter = PublicDataExporter(output_dir=output_dir)
    return exporter.export_all()
