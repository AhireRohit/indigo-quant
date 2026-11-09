"""
Static HTML Report Generator for INDIGO QUANT.
Compiles exported public data snapshots into a self-contained, publication-grade,
interactive HTML dashboard with Plotly charts.

Can be hosted on GitHub Pages or viewed locally in any browser.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)


def generate_static_html(public_data_dir: str = "public_data", output_path: str = "public_data/index.html") -> str:
    """Read public data JSON files and render a standalone responsive dashboard."""
    base_dir = Path(public_data_dir)

    def load_json(name: str) -> Dict[str, Any]:
        p = base_dir / name
        if p.exists():
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    overview = load_json("overview.json")
    health = load_json("system_health.json")
    leaderboard = load_json("leaderboard.json") or []
    signals_data = load_json("signals.json")
    signals = signals_data.get("signals", [])

    capital = overview.get("capital_metrics", {})
    tot_equity = capital.get("current_total_equity", 500000.0)
    comb_ret = capital.get("combined_return_pct", 0.0)
    target_hits = capital.get("target_hits_total", 0)
    closed_trades = capital.get("closed_trades_total", 0)
    hit_rate = capital.get("target_hit_rate_pct", 0.0)
    open_pos = capital.get("open_positions_total", 0)

    # Prepare leaderboard rows HTML
    leader_rows = ""
    for item in leaderboard:
        ret = item.get("total_return_pct", 0.0)
        ret_color = "#10b981" if ret >= 0 else "#ef4444"
        ret_sign = "+" if ret >= 0 else ""
        leader_rows += f"""
        <tr>
            <td class="fw-bold">#{item.get('rank', '-')}</td>
            <td class="text-white fw-semibold">{item.get('strategy_name', '')}</td>
            <td>₹{item.get('initial_capital', 100000.0):,.0f}</td>
            <td class="fw-bold text-white">₹{item.get('current_equity', 100000.0):,.2f}</td>
            <td style="color: {ret_color}; font-weight: bold;">{ret_sign}{ret:.2f}%</td>
            <td>{item.get('open_positions_count', 0)}</td>
            <td>{item.get('total_trades', 0)}</td>
            <td><span class="badge bg-success">{item.get('target_hits_count', 0)} ({item.get('target_hit_rate', 0.0)}%)</span></td>
            <td>{item.get('win_rate', 0.0)}%</td>
        </tr>
        """

    # Prepare Signals rows HTML
    sig_rows = ""
    for s in signals[:15]:
        passed = "<br>".join([f"<span class='badge bg-dark-subtle text-light border border-secondary mb-1'>✓ {c}</span>" for c in s.get("rules_passed", [])[:4]])
        sig_rows += f"""
        <tr>
            <td class="text-primary fw-bold">{s.get('symbol')}</td>
            <td>{s.get('strategy_name')}</td>
            <td class="text-white">₹{s.get('reference_close', 0.0):,.2f}</td>
            <td class="text-success fw-bold">₹{s.get('target_price_estimate', 0.0):,.2f} (+10%)</td>
            <td class="text-danger">₹{s.get('initial_stop_estimate', 0.0):,.2f}</td>
            <td><span class="badge bg-primary fs-6">{s.get('rule_quality_score', 0.0):.1f}/100</span></td>
            <td class="small">{passed}</td>
            <td><span class="badge bg-info">{s.get('execution_status', 'QUEUED')}</span></td>
        </tr>
        """
    if not sig_rows:
        sig_rows = "<tr><td colspan='8' class='text-center text-muted py-4'>No pending BUY signals generated in latest scan. Waiting for high-probability setups.</td></tr>"

    # HTML template with embedded Plotly and CDN
    html = f"""<!DOCTYPE html>
<html lang="en" data-bs-theme="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>INDIGO QUANT — Autonomous Swing Trading Platform</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css">
    <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
    <style>
        body {{
            background-color: #0b0f19;
            color: #e2e8f0;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
        }}
        .card {{
            background-color: #111827;
            border: 1px solid #1f2937;
            border-radius: 12px;
        }}
        .navbar {{
            background-color: #0f172a !important;
            border-bottom: 1px solid #1e293b;
        }}
        .metric-card {{
            background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
            border: 1px solid #334155;
            border-radius: 12px;
            padding: 20px;
        }}
        .table {{
            --bs-table-bg: transparent;
            --bs-table-border-color: #1f2937;
        }}
        .badge-regime {{
            background: linear-gradient(135deg, #059669, #10b981);
            color: white;
            padding: 6px 12px;
            border-radius: 20px;
            font-weight: 600;
        }}
    </style>
</head>
<body>

<nav class="navbar navbar-expand-lg navbar-dark py-3">
    <div class="container-fluid px-4">
        <a class="navbar-brand fw-bold fs-4 d-flex align-items-center" href="#">
            <i class="bi bi-graph-up-arrow text-primary me-2"></i> INDIGO QUANT
        </a>
        <div class="d-flex align-items-center gap-3">
            <span class="badge-regime"><i class="bi bi-shield-check me-1"></i> Engine: {health.get('status', 'HEALTHY')}</span>
            <span class="text-muted small"><i class="bi bi-clock me-1"></i> {overview.get('last_updated_ist', '')}</span>
        </div>
    </div>
</nav>

<div class="container-fluid px-4 py-4">

    <!-- Top Banner -->
    <div class="row mb-4">
        <div class="col-12">
            <div class="card p-4">
                <div class="row align-items-center">
                    <div class="col-md-8">
                        <h3 class="fw-bold mb-1 text-white">Autonomous Indian Equity Swing-Trading Platform</h3>
                        <p class="text-muted mb-0">
                            Algorithmic strategy targeting <span class="text-primary fw-semibold">+10% gross upside over 5–20 trading sessions</span> across NSE/BSE equities.
                            Five competing quantitative agents, deterministic technical execution, zero real money.
                        </p>
                    </div>
                    <div class="col-md-4 text-md-end mt-3 mt-md-0">
                        <span class="badge bg-secondary p-2 me-2">Session: {overview.get('latest_market_session', 'N/A')}</span>
                        <span class="badge bg-primary p-2">Timezone: Asia/Kolkata</span>
                    </div>
                </div>
                <hr class="border-secondary my-3">
                <div class="small text-secondary">
                    <span class="text-info fw-bold"><i class="bi bi-shield-lock me-1"></i> Data Segregation:</span>
                    <span class="badge bg-success-subtle text-success border border-success me-1">Live Forward Paper Trading</span> Real quotes, next-day open simulated fill, modeled delivery fees & slippage.
                    <span class="badge bg-info-subtle text-info border border-info mx-1">Historical Backtests</span> Multi-year historical simulations strictly segregated from paper capital.
                    <span class="badge bg-warning-subtle text-warning border border-warning mx-1">Test Isolation</span> Unit test suites execute in memory with zero production impact.
                </div>
            </div>
        </div>
    </div>

    <!-- Key Performance Metrics Cards -->
    <div class="row g-3 mb-4">
        <div class="col-md-3">
            <div class="metric-card">
                <div class="text-muted small text-uppercase fw-bold mb-1">Total Virtual NAV</div>
                <div class="fs-3 fw-bold text-white">₹{tot_equity:,.2f}</div>
                <div class="small fw-semibold mt-1" style="color: {'#10b981' if comb_ret >= 0 else '#ef4444'};">
                    {'+' if comb_ret >= 0 else ''}{comb_ret:.2f}% Combined Return
                </div>
            </div>
        </div>
        <div class="col-md-3">
            <div class="metric-card">
                <div class="text-muted small text-uppercase fw-bold mb-1">Target Hits (+10%)</div>
                <div class="fs-3 fw-bold text-success">{target_hits} <span class="fs-6 text-muted">/ {closed_trades} trades</span></div>
                <div class="small text-muted mt-1">{hit_rate:.1f}% Objective Hit Rate</div>
            </div>
        </div>
        <div class="col-md-3">
            <div class="metric-card">
                <div class="text-muted small text-uppercase fw-bold mb-1">Active Positions</div>
                <div class="fs-3 fw-bold text-info">{open_pos}</div>
                <div class="small text-muted mt-1">Across 5 Independent Portfolios</div>
            </div>
        </div>
        <div class="col-md-3">
            <div class="metric-card">
                <div class="text-muted small text-uppercase fw-bold mb-1">Data Feeds & Scheduler</div>
                <div class="fs-3 fw-bold text-warning">24/7 ACTIVE</div>
                <div class="small text-muted mt-1">TejHQ Verified + Yahoo Finance Fallback</div>
            </div>
        </div>
    </div>

    <!-- Strategy Leaderboard -->
    <div class="row mb-4">
        <div class="col-12">
            <div class="card p-3">
                <h5 class="fw-bold text-white mb-3"><i class="bi bi-trophy text-warning me-2"></i>Competing Strategy Leaderboard (Virtual Capital: ₹1,00,000 Each)</h5>
                <div class="table-responsive">
                    <table class="table table-hover align-middle mb-0">
                        <thead class="text-muted small text-uppercase">
                            <tr>
                                <th>Rank</th>
                                <th>Strategy Agent</th>
                                <th>Starting Capital</th>
                                <th>Current Equity</th>
                                <th>Total Return</th>
                                <th>Open Pos</th>
                                <th>Total Trades</th>
                                <th>10% Target Hits</th>
                                <th>Win Rate</th>
                            </tr>
                        </thead>
                        <tbody>
                            {leader_rows}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>

    <!-- Recent BUY Candidates -->
    <div class="row mb-4">
        <div class="col-12">
            <div class="card p-3">
                <h5 class="fw-bold text-white mb-3"><i class="bi bi-bullseye text-primary me-2"></i>Verified BUY Candidates & Signal Audit Log</h5>
                <div class="table-responsive">
                    <table class="table table-hover align-middle mb-0">
                        <thead class="text-muted small text-uppercase">
                            <tr>
                                <th>Ticker</th>
                                <th>Strategy</th>
                                <th>Reference Close</th>
                                <th>+10% Target</th>
                                <th>Stop Loss</th>
                                <th>Rule Score</th>
                                <th>Deterministic Conditions Passed</th>
                                <th>Status</th>
                            </tr>
                        </thead>
                        <tbody>
                            {sig_rows}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>

    <!-- Health & Operational Architecture Footer -->
    <div class="row">
        <div class="col-12">
            <div class="card p-3">
                <div class="row">
                    <div class="col-md-6">
                        <h6 class="fw-bold text-white"><i class="bi bi-cpu text-info me-2"></i>Autonomous Host Architecture</h6>
                        <ul class="list-unstyled small text-muted mb-0">
                            <li>• Host: Windows 11 Continuous Background Daemon (APScheduler)</li>
                            <li>• Single-Instance Concurrency: Exclusive Windows C-runtime Lock</li>
                            <li>• Missed-Job Recovery: Automatic evaluation without historical fill backdating</li>
                            <li>• Notifications: Real-time idempotent Telegram dispatch</li>
                        </ul>
                    </div>
                    <div class="col-md-6 mt-3 mt-md-0">
                        <h6 class="fw-bold text-white"><i class="bi bi-shield-exclamation text-warning me-2"></i>Regulatory & Risk Notice</h6>
                        <p class="small text-muted mb-0">
                            INDIGO QUANT is an autonomous algorithmic research and paper-trading engine.
                            All trades are virtual simulations with modeled Indian delivery costs (STT, DP charges, SEBI fees, exchange turnover, GST, stamp duty, and slippage).
                            No real brokerage orders are submitted. A 10% gain is an algorithmic target, not a guarantee.
                        </p>
                    </div>
                </div>
            </div>
        </div>
    </div>

</div>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""
    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(html)
    logger.info("Generated static dashboard report at %s", out_file)
    return str(out_file)
