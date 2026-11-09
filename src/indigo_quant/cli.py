"""
Command-Line Interface for Indigo Quant.
Provides terminal commands for system initialization, diagnostics, data fetching,
scanning, backtesting, portfolio inspection, dashboard launch, and tests.
"""

from __future__ import annotations

import argparse
import datetime
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from indigo_quant.backtesting.backtester import BacktestEngine
from indigo_quant.data.calendar import NSE_HOLIDAYS, is_market_open, now_ist
from indigo_quant.data.ingestion import DataIngestionEngine
from indigo_quant.db.repository import Repository, init_db, seed_universe_and_accounts
from indigo_quant.db.session import SessionLocal
from indigo_quant.engine.decision import DecisionEngine
from indigo_quant.export.public_data import export_public_snapshots
from indigo_quant.export.static_report import generate_static_html
from indigo_quant.indicators.technical import calculate_all_indicators
from indigo_quant.notifications.telegram import TelegramNotifier, mask_token

console = Console(safe_box=True)


def cmd_init(args):
    """Initialize database and seed accounts/universe."""
    console.print("[bold green]Initializing Indigo Quant database...[/bold green]")
    init_db()
    db = SessionLocal()
    seed_universe_and_accounts(db)
    repo = Repository(db)
    insts = repo.get_active_instruments()
    accs = repo.get_accounts()
    db.close()
    console.print("[bold cyan]✓ Database initialized successfully![/bold cyan]")
    console.print(f"• Seeded {len(insts)} universe instruments.")
    console.print(f"• Initialized {len(accs)} competing strategy accounts with INR 1,00,000 capital each.")


def cmd_doctor(args):
    """Perform system health check and connectivity diagnostic."""
    console.print(Panel("[bold yellow]INDIGO QUANT — System Doctor & Health Probe[/bold yellow]"))

    table = Table(title="Diagnostic Checks")
    table.add_column("Component", style="cyan")
    table.add_column("Status", style="bold")
    table.add_column("Details")

    # 1. Python version
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    py_ok = sys.version_info >= (3, 11)
    table.add_row("Python Version", "[green]PASS[/green]" if py_ok else "[red]FAIL[/red]", f"Python {py_ver}")

    # 2. Database Connection
    db = SessionLocal()
    try:
        repo = Repository(db)
        acc_cnt = len(repo.get_accounts())
        table.add_row("SQLite Database", "[green]PASS[/green]", f"Connected (WAL Mode, {acc_cnt} accounts)")
    except Exception as e:
        table.add_row("SQLite Database", "[red]FAIL[/red]", str(e))

    # 3. Data Providers
    ingest = DataIngestionEngine(db)
    health = ingest.get_provider_health()
    table.add_row("TejHQ Provider", "[green]PASS[/green]" if health["tejhq"] else "[yellow]OFFLINE/DEGRADED[/yellow]", "https://api.tejhq.dev")
    table.add_row("Yahoo Finance", "[green]PASS[/green]" if health["yahoo"] else "[yellow]OFFLINE/DEGRADED[/yellow]", "yfinance (^NSEI benchmark)")

    # 4. Exchange Calendar
    now_ist().date()
    market_open = is_market_open()
    holidays_count = len(NSE_HOLIDAYS)
    table.add_row("NSE Calendar", "[green]PASS[/green]", f"{holidays_count} registered holidays; Market is {'OPEN' if market_open else 'CLOSED'}")

    db.close()
    console.print(table)


def cmd_fetch(args):
    """Fetch market data for active universe or a specific symbol."""
    db = SessionLocal()
    repo = Repository(db)
    ingest = DataIngestionEngine(db)

    symbol = args.symbol
    if symbol:
        console.print(f"[bold cyan]Fetching market data for {symbol}...[/bold cyan]")
        df, logs = ingest.fetch_and_validate_symbol(symbol.upper(), persist=True)
        for log in logs:
            console.print(f"  {log}")
    else:
        console.print("[bold cyan]Fetching benchmark ^NSEI...[/bold cyan]")
        ingest.fetch_benchmark("^NSEI")
        insts = repo.get_active_instruments()[:args.limit]
        console.print(f"[bold cyan]Fetching market data for top {len(insts)} universe equities...[/bold cyan]")
        for i, inst in enumerate(insts, 1):
            console.print(f"[{i}/{len(insts)}] Fetching {inst.symbol}...")
            ingest.fetch_and_validate_symbol(inst.symbol, exchange=inst.exchange, persist=True)

    db.close()
    console.print("[bold green]Data fetch complete![/bold green]")


def cmd_indicators(args):
    """Calculate and display technical indicator metrics for a stock."""
    db = SessionLocal()
    repo = Repository(db)
    clean_sym = args.symbol.replace(".NS", "").replace(".BO", "").upper()
    bars = repo.get_bars(clean_sym)
    if not bars:
        console.print(f"[yellow]No data in local database for {clean_sym}. Fetching...[/yellow]")
        ingest = DataIngestionEngine(db)
        df, logs = ingest.fetch_and_validate_symbol(clean_sym, persist=True)
        bars = repo.get_bars(clean_sym)

    if not bars:
        console.print(f"[red]Could not retrieve data for {clean_sym}.[/red]")
        db.close()
        return

    import pandas as pd
    df = pd.DataFrame([
        {"date": b.date, "open": b.open, "high": b.high, "low": b.low, "close": b.close, "volume": b.volume}
        for b in bars
    ]).set_index("date")

    ind_df = calculate_all_indicators(df)
    latest = ind_df.iloc[-1]
    last_dt = ind_df.index[-1]
    dt_display = last_dt.date() if hasattr(last_dt, "date") and not isinstance(last_dt, datetime.date) else last_dt

    table = Table(title=f"Technical Indicators for {clean_sym} ({dt_display})")
    table.add_column("Indicator", style="cyan")
    table.add_column("Value", style="bold green")

    keys = [
        "close", "ema20", "ema50", "ema200", "sma200",
        "rsi14", "adx14", "macd_line", "macd_signal", "macd_hist",
        "rvol20", "atr14", "atr_pct", "previous_20_high", "bb_width", "return_5d_pct"
    ]
    for k in keys:
        if k in latest:
            v = latest[k]
            table.add_row(k.upper(), f"{v:.2f}" if isinstance(v, float) else str(v))

    console.print(table)
    db.close()


def cmd_scan(args):
    """Run deterministic decision scan across market data."""
    console.print("[bold cyan]Running deterministic decision scan...[/bold cyan]")
    db = SessionLocal()
    repo = Repository(db)
    decision = DecisionEngine(db)

    # Load cached bars
    insts = repo.get_active_instruments()
    import pandas as pd
    universe_data = {}
    for inst in insts:
        bars = repo.get_bars(inst.symbol)
        if bars and len(bars) >= 200:
            df = pd.DataFrame([
                {"date": b.date, "open": b.open, "high": b.high, "low": b.low, "close": b.close, "volume": b.volume}
                for b in bars
            ]).set_index("date")
            universe_data[inst.symbol] = df

    nifty_bars = repo.get_bars("^NSEI")
    nifty_df = pd.DataFrame([
        {"date": b.date, "open": b.open, "high": b.high, "low": b.low, "close": b.close, "volume": b.volume}
        for b in nifty_bars
    ]).set_index("date") if nifty_bars else None

    res = decision.run_daily_scan(universe_data, nifty_df=nifty_df)

    console.print(f"• Market Regime: [bold]{res['regime']}[/bold]")
    console.print(f"• Scanned Stocks: {res['scanned_symbols_count']}")
    console.print(f"• Qualified BUY Signals: [bold green]{res['qualified_signals_count']}[/bold green]")
    console.print(f"• Rejections Logged: {res['rejections_count']}")

    if res["signals"]:
        table = Table(title="Qualified BUY Signals")
        table.add_column("Symbol", style="cyan")
        table.add_column("Strategy", style="magenta")
        table.add_column("Price (INR)")
        table.add_column("Target (INR)")
        table.add_column("Stop (INR)")
        table.add_column("Rule Score", style="bold green")

        for s in res["signals"]:
            table.add_row(
                s["symbol"],
                s["strategy_id"],
                f"{s['reference_close']:.2f}",
                f"{s['target_price_estimate']:.2f}",
                f"{s['initial_stop_estimate']:.2f}",
                f"{s['rule_quality_score']:.1f}",
            )
        console.print(table)

    db.close()


def cmd_portfolios(args):
    """Show current balances and positions across all 5 portfolios."""
    db = SessionLocal()
    repo = Repository(db)
    accs = repo.get_accounts()

    table = Table(title="Virtual Portfolios (Starting Capital: INR 1,00,000 each)")
    table.add_column("Agent ID", style="cyan")
    table.add_column("Agent Name")
    table.add_column("Cash (INR)")
    table.add_column("Current Equity (INR)", style="bold green")
    table.add_column("Return %")
    table.add_column("Open Positions")

    for a in accs:
        pos = repo.get_open_positions(a.id)
        ret = ((a.current_equity - a.initial_capital) / a.initial_capital) * 100.0
        table.add_row(
            a.id,
            a.name,
            f"{a.current_cash:,.2f}",
            f"{a.current_equity:,.2f}",
            f"{ret:+.2f}%",
            str(len(pos)),
        )

    console.print(table)
    db.close()


def cmd_backtest(args):
    """Run historical backtest."""
    console.print(f"[bold cyan]Running walk-forward backtest for strategy: {args.strategy}...[/bold cyan]")
    db = SessionLocal()
    repo = Repository(db)

    # Load universe data
    import pandas as pd
    insts = repo.get_active_instruments()[:30]
    universe_data = {}
    for inst in insts:
        bars = repo.get_bars(inst.symbol)
        if bars and len(bars) >= 200:
            df = pd.DataFrame([
                {"date": b.date, "open": b.open, "high": b.high, "low": b.low, "close": b.close, "volume": b.volume}
                for b in bars
            ]).set_index("date")
            universe_data[inst.symbol] = df

    nifty_bars = repo.get_bars("^NSEI")
    nifty_df = pd.DataFrame([
        {"date": b.date, "open": b.open, "high": b.high, "low": b.low, "close": b.close, "volume": b.volume}
        for b in nifty_bars
    ]).set_index("date") if nifty_bars else None

    engine = BacktestEngine(initial_capital=100000.0)
    res = engine.run(args.strategy, universe_data, nifty_df=nifty_df)

    if "metrics" in res:
        m = res["metrics"]
        console.print("\n[bold green]Backtest Completed![/bold green]")
        console.print(f"• Total Trades: {m.get('total_trades', 0)}")
        console.print(f"• Win Rate: {m.get('win_rate_pct', 0.0)}%")
        console.print(f"• Target (+10%) Hit Rate: {m.get('target_hit_rate_pct', 0.0)}%")
        console.print(f"• Total Return: {m.get('total_return_pct', 0.0)}%")
        console.print(f"• Profit Factor: {m.get('profit_factor', 0.0)}")
        console.print(f"• Max Drawdown: {m.get('max_drawdown_pct', 0.0)}%")
        console.print(f"• Sharpe Ratio: {m.get('sharpe_ratio', 0.0)}")
    elif isinstance(res, dict):
        bt_table = Table(title="Historical Backtest Performance (Real Market Data)")
        bt_table.add_column("Strategy Agent", style="cyan")
        bt_table.add_column("Total Return", style="bold")
        bt_table.add_column("Trades")
        bt_table.add_column("Win Rate")
        bt_table.add_column("10% Target Hits", style="green")
        bt_table.add_column("Max Drawdown", style="red")
        bt_table.add_column("Sharpe Ratio")
        bt_table.add_column("Total Fees (INR)")

        for sid, sres in res.items():
            if "metrics" in sres:
                sm = sres["metrics"]
                ret = sm.get("total_return_pct", 0.0)
                ret_str = f"[green]+{ret:.2f}%[/green]" if ret >= 0 else f"[red]{ret:.2f}%[/red]"
                bt_table.add_row(
                    sid.replace("_", " ").title(),
                    ret_str,
                    str(sm.get("total_trades", 0)),
                    f"{sm.get('win_rate_pct', 0.0):.1f}%",
                    f"{sm.get('target_hit_rate_pct', 0.0):.1f}%",
                    f"{sm.get('max_drawdown_pct', 0.0):.2f}%",
                    f"{sm.get('sharpe_ratio', 0.0):.2f}",
                    f"INR {sm.get('total_fees_paid', 0.0):,.1f}",
                )
        console.print(bt_table)

    db.close()


def cmd_dashboard(args):
    """Launch Streamlit dashboard."""
    app_path = Path(__file__).parent / "dashboard" / "app.py"
    console.print("[bold green]Launching Streamlit dashboard at http://localhost:8501...[/bold green]")
    subprocess.run([sys.executable, "-m", "streamlit", "run", str(app_path), "--server.port", "8501"])


def cmd_test(args):
    """Execute pytest test suite."""
    console.print("[bold cyan]Running automated test suite via pytest...[/bold cyan]")
    subprocess.run([sys.executable, "-m", "pytest", "tests", "-v"])


def cmd_telegram_test(args):
    """Send an operational test notification to Telegram."""
    console.print(Panel("[bold yellow]INDIGO QUANT — Telegram Bot Connectivity Test[/bold yellow]"))
    notifier = TelegramNotifier()
    notifier._allow_live_network = True

    table = Table(title="Telegram Configuration Status")
    table.add_column("Property", style="cyan")
    table.add_column("Value")

    table.add_row("Bot Token", mask_token(notifier.bot_token))
    table.add_row("Chat ID", str(notifier.chat_id or "Not configured"))
    table.add_row("Enabled Flag", "[green]True[/green]" if notifier.enabled else "[yellow]False[/yellow]")
    table.add_row("Ready to Send", "[green]YES[/green]" if notifier.is_configured else "[red]NO[/red]")
    console.print(table)

    if not notifier.is_configured:
        console.print("[bold red]Telegram is not properly configured. Check TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env[/bold red]")
        return

    console.print("[bold cyan]Dispatching test message to Telegram API...[/bold cyan]")
    success, detail = notifier.send_test_message()
    if success:
        console.print(f"[bold green]✓ Telegram test notification accepted: {detail}[/bold green]")
        console.print(f"[green]Test message sent to Chat ID {notifier.chat_id}![/green]")
    else:
        console.print(f"[bold red]✗ Telegram dispatch rejected: {detail}[/bold red]")


def cmd_service(args):
    """Manage the Windows autonomous scheduler service."""
    import json
    import os
    import signal
    import time
    action = args.action
    pid_file = Path("data/indigo_scheduler.pid")
    heartbeat_file = Path("data/heartbeat.json")

    if action == "status":
        console.print(Panel("[bold cyan]INDIGO QUANT — Service Status Probe[/bold cyan]"))
        pid = None
        if pid_file.exists():
            try:
                pid = int(pid_file.read_text().strip())
            except Exception:
                pass

        table = Table(title="Autonomous Engine State")
        table.add_column("Metric", style="cyan")
        table.add_column("Value")

        is_running = False
        if pid:
            try:
                proc_check = subprocess.run(
                    ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                    capture_output=True,
                    text=True,
                )
                if str(pid) in proc_check.stdout:
                    is_running = True
            except Exception:
                pass

        table.add_row("Service Status", "[bold green]RUNNING (AUTONOMOUS)[/bold green]" if is_running else "[yellow]STOPPED / IDLE[/yellow]")
        table.add_row("Process PID", str(pid) if pid else "N/A")

        if heartbeat_file.exists():
            try:
                with open(heartbeat_file, "r", encoding="utf-8") as hf:
                    hb = json.load(hf)
                    table.add_row("Heartbeat Status", f"[bold green]{hb.get('status')}[/bold green]")
                    table.add_row("Last Heartbeat", hb.get("last_heartbeat", "N/A"))
                    table.add_row("Uptime", f"{hb.get('uptime_seconds', 0)} seconds")
            except Exception:
                pass

        console.print(table)

    elif action == "start":
        console.print("[bold cyan]Starting INDIGO QUANT autonomous scheduler...[/bold cyan]")
        runner_module = "indigo_quant.scheduler.runner"
        proc = subprocess.Popen(
            [sys.executable, "-m", runner_module],
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(1.5)
        console.print(f"[bold green]✓ Scheduler daemon launched with PID {proc.pid}![/bold green]")
        console.print("Run `indigo service status` to verify ongoing heartbeat.")

    elif action == "stop":
        console.print("[bold yellow]Stopping INDIGO QUANT autonomous scheduler...[/bold yellow]")
        if not pid_file.exists():
            console.print("[yellow]No PID file found. Scheduler may not be running.[/yellow]")
            return
        try:
            pid = int(pid_file.read_text().strip())
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
            else:
                os.kill(pid, signal.SIGTERM)
            console.print(f"[bold green]✓ Terminated scheduler process (PID {pid}).[/bold green]")
            if pid_file.exists():
                pid_file.unlink()
        except Exception as e:
            console.print(f"[bold red]Failed stopping scheduler process: {e}[/bold red]")


def cmd_export_public(args):
    """Export public sanitized JSON snapshots and static HTML report."""
    console.print("[bold cyan]Exporting sanitized public data snapshots...[/bold cyan]")
    files = export_public_snapshots()
    html_path = generate_static_html()
    console.print(f"[bold green]✓ Exported {len(files)} JSON snapshots to public_data/[/bold green]")
    console.print(f"[bold green]✓ Generated standalone static HTML report at {html_path}[/bold green]")


def main():
    parser = argparse.ArgumentParser(prog="indigo", description="INDIGO QUANT CLI")
    subparsers = parser.add_subparsers(dest="command", help="Sub-commands")

    # init
    subparsers.add_parser("init", help="Initialize database, universe, and strategy accounts")

    # doctor
    subparsers.add_parser("doctor", help="Run system diagnostics and connectivity probes")

    # telegram-test
    subparsers.add_parser("telegram-test", help="Send operational test notification to Telegram")

    # service
    service_parser = subparsers.add_parser("service", help="Manage background autonomous scheduler service")
    service_parser.add_argument("action", choices=["status", "start", "stop", "restart"], default="status", nargs="?", help="Service action")

    # export-public
    subparsers.add_parser("export-public", help="Export sanitized public snapshots and static report")

    # fetch
    fetch_parser = subparsers.add_parser("fetch", help="Fetch market data")
    fetch_parser.add_argument("--symbol", type=str, default=None, help="Specific symbol (e.g. RELIANCE)")
    fetch_parser.add_argument("--limit", type=int, default=15, help="Number of universe equities to fetch")

    # indicators
    ind_parser = subparsers.add_parser("indicators", help="Calculate indicators for a symbol")
    ind_parser.add_argument("symbol", type=str, help="Stock symbol (e.g. RELIANCE)")

    # scan
    scan_parser = subparsers.add_parser("scan", help="Run deterministic decision scan")
    scan_parser.add_argument("--strategy", type=str, default="all", help="Strategy ID filter")

    # portfolios
    subparsers.add_parser("portfolios", help="Inspect virtual portfolio balances and equity")

    # backtest
    bt_parser = subparsers.add_parser("backtest", help="Run historical backtests")
    bt_parser.add_argument("--strategy", type=str, default="trend_momentum", help="Strategy to evaluate or 'all'")

    # dashboard
    subparsers.add_parser("dashboard", help="Launch Streamlit dashboard")

    # test
    subparsers.add_parser("test", help="Run automated test suite")

    args = parser.parse_args()

    dispatch = {
        "init": cmd_init,
        "doctor": cmd_doctor,
        "telegram-test": cmd_telegram_test,
        "service": cmd_service,
        "export-public": cmd_export_public,
        "fetch": cmd_fetch,
        "indicators": cmd_indicators,
        "scan": cmd_scan,
        "portfolios": cmd_portfolios,
        "backtest": cmd_backtest,
        "dashboard": cmd_dashboard,
        "test": cmd_test,
    }

    if args.command in dispatch:
        dispatch[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
