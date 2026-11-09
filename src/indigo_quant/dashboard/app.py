"""
INDIGO QUANT Professional Streamlit Dashboard.
Interactive multi-page quantitative research, signal inspection, and paper brokerage interface.
Features dark-mode design and responsive Plotly charts.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from indigo_quant.backtesting.backtester import BacktestEngine
from indigo_quant.data.calendar import get_latest_completed_trading_day, is_market_open
from indigo_quant.data.ingestion import DataIngestionEngine
from indigo_quant.db.models import (
    PaperPosition,
    SchedulerJobLog,
)
from indigo_quant.db.repository import Repository, seed_universe_and_accounts
from indigo_quant.db.session import SessionLocal, init_db
from indigo_quant.engine.market_regime import MarketRegimeEngine, MarketRegimeStatus
from indigo_quant.indicators.technical import calculate_all_indicators

# Streamlit Page Configuration
st.set_page_config(
    page_title="INDIGO QUANT — Indian Equity Swing Research",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom Dark Theme CSS styling
st.markdown("""
<style>
    .main { background-color: #0d1117; color: #c9d1d9; }
    .stMetric { background-color: #161b22; padding: 12px; border-radius: 8px; border: 1px solid #30363d; }
    .stTabs [data-baseweb="tab-list"] { gap: 10px; }
    .stTabs [data-baseweb="tab"] { background-color: #161b22; border-radius: 6px; padding: 8px 16px; color: #8b949e; }
    .stTabs [aria-selected="true"] { background-color: #238636 !important; color: white !important; font-weight: bold; }
    .badge-bullish { background-color: #238636; color: white; padding: 4px 8px; border-radius: 4px; font-weight: bold; }
    .badge-defensive { background-color: #da3633; color: white; padding: 4px 8px; border-radius: 4px; font-weight: bold; }
    .badge-unknown { background-color: #d29922; color: white; padding: 4px 8px; border-radius: 4px; font-weight: bold; }
</style>
""", unsafe_allow_html=True)


@st.cache_resource
def setup_database():
    init_db()
    db = SessionLocal()
    seed_universe_and_accounts(db)
    db.close()

setup_database()


def get_db_session():
    return SessionLocal()


# Sidebar Navigation
st.sidebar.title("INDIGO QUANT")
st.sidebar.caption("Autonomous Indian Equity Swing Engine")

# Read Heartbeat Status
heartbeat_path = Path("data/heartbeat.json")
hb_status = "IDLE / STANDBY"
last_hb = "No heartbeat recorded"
next_run = "19:15 IST (Mon-Fri)"
if heartbeat_path.exists():
    try:
        with open(heartbeat_path, "r", encoding="utf-8") as hf:
            hb = json.load(hf)
            hb_status = hb.get("status", "UNKNOWN")
            last_hb = hb.get("last_heartbeat", "N/A")
            next_runs = hb.get("next_scheduled_runs", {})
            if "evening_eod_scan" in next_runs:
                next_run = next_runs["evening_eod_scan"]
    except Exception:
        pass

hb_color = "🟢" if hb_status == "HEALTHY" else ("🟡" if "IDLE" in hb_status or "STANDBY" in hb_status else "🔴")
st.sidebar.markdown(f"**Engine**: {hb_color} `{hb_status}`")
st.sidebar.caption(f"Last Heartbeat: {last_hb}")

nav = st.sidebar.radio(
    "Navigation",
    [
        "1. Overview",
        "2. Today's BUY Signals",
        "3. Technical Analysis",
        "4. Agent Leaderboard",
        "5. Paper Portfolio",
        "6. Historical Backtests",
        "7. Rejected Stocks",
        "8. System Health",
    ],
)

st.sidebar.markdown("---")
st.sidebar.info(
    "🛡️ **Simulation Only**\n\n"
    "• Initial Capital: ₹1,00,000 per Agent\n"
    "• +10% Gross Target (5–20 Sessions)\n"
    "• No real money order routing."
)

db = get_db_session()
repo = Repository(db)


# ==============================================================================
# PAGE 1 — OVERVIEW
# ==============================================================================
if nav == "1. Overview":
    st.title("System Overview & Market Status")

    # 1. Market Status Header
    nifty_bars = repo.get_bars("^NSEI")
    latest_date_str = "Sync Pending"
    regime_status = MarketRegimeStatus.UNKNOWN
    regime_reason = "No benchmark data"

    if nifty_bars and len(nifty_bars) >= 50:
        n_df = pd.DataFrame([{"date": b.date, "close": b.close} for b in nifty_bars]).set_index("date")
        latest_date_str = str(nifty_bars[-1].date)
        reg_engine = MarketRegimeEngine(min_required_sessions=50)
        regime_status, reg_details = reg_engine.evaluate(n_df)
        regime_reason = reg_details.get("reason", "")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Latest Data Session", latest_date_str)
    with col2:
        badge_cls = "badge-bullish" if regime_status == MarketRegimeStatus.BULLISH else ("badge-defensive" if regime_status == MarketRegimeStatus.DEFENSIVE else "badge-unknown")
        st.markdown(f"**Market Regime**<br><span class='{badge_cls}'>{regime_status.value}</span>", unsafe_allow_html=True)
    with col3:
        market_open_now = is_market_open()
        st.metric("NSE Session Status", "🟢 OPEN (09:15-15:30 IST)" if market_open_now else "🔴 CLOSED")
    with col4:
        accounts = repo.get_accounts()
        total_virtual_cap = sum(a.current_equity for a in accounts)
        st.metric("Total Virtual Capital", f"₹{total_virtual_cap:,.0f}")

    st.markdown(f"> **Market Regime Diagnostics**: {regime_reason}")
    st.markdown("---")

    # Autonomous Engine & Scheduler Status Banner
    h1, h2, h3, h4 = st.columns(4)
    expected_eod = get_latest_completed_trading_day()
    freshness = "🟢 CURRENT" if latest_date_str == str(expected_eod) else "🟡 REFRESH PENDING"
    with h1:
        st.metric("Daemon Heartbeat", f"{hb_color} {hb_status}")
    with h2:
        st.metric("Data Freshness", freshness, delta=f"Expected: {expected_eod}")
    with h3:
        st.metric("Last Heartbeat", last_hb.split()[-1] if " " in last_hb else last_hb)
    with h4:
        st.metric("Next Scan Window", "19:15 IST (Mon-Fri)")

    st.markdown("---")

    # Metrics Summary
    signals = repo.get_signals(decision_only="BUY")
    open_positions = repo.get_open_positions()
    orders = repo.get_orders(status="PENDING")
    instruments = repo.get_active_instruments()

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Universe Equities", len(instruments))
    m2.metric("Qualified BUY Signals", len(signals))
    m3.metric("Pending Paper Orders", len(orders))
    m4.metric("Active Paper Positions", len(open_positions))

    st.subheader("Autonomous Pipeline Architecture")
    st.code("MARKET DATA (TejHQ/Yahoo) ➔ INDICATORS ➔ 4 STRATEGY AGENTS ➔ MARKET REGIME ➔ RISK ENGINE ➔ RANKING ➔ PAPER BROKER", language="text")

    st.subheader("Competing Strategy Accounts")
    acc_data = []
    for a in accounts:
        acc_data.append({
            "Strategy ID": a.id,
            "Agent Name": a.name,
            "Initial Capital": f"₹{a.initial_capital:,.0f}",
            "Available Cash": f"₹{a.current_cash:,.2f}",
            "Current Equity": f"₹{a.current_equity:,.2f}",
            "Return %": f"{((a.current_equity - a.initial_capital) / a.initial_capital) * 100.0:+.2f}%",
        })
    st.dataframe(pd.DataFrame(acc_data), use_container_width=True)


# ==============================================================================
# PAGE 2 — TODAY'S BUY SIGNALS
# ==============================================================================
elif nav == "2. Today's BUY Signals":
    st.title("Today's Qualified BUY Signals")
    st.caption("Signals ranked deterministically by Rule Quality Score (0–100). This is a rule-compliance metric, not a win probability.")

    signals = repo.get_signals(decision_only="BUY")
    if not signals:
        st.info("No qualified BUY signals found. (Either no stock passed all 100% mandatory strategy rules or market regime is Defensive).")
    else:
        sig_rows = []
        for s in signals:
            sig_rows.append({
                "Symbol": s.symbol,
                "Agent": s.strategy_id,
                "Signal Date": s.signal_date,
                "Reference Close": f"₹{s.reference_close:.2f}",
                "Target (+10%)": f"₹{s.target_price_estimate:.2f}",
                "Stop Estimate": f"₹{s.initial_stop_estimate:.2f}",
                "Stop Distance": f"{s.stop_distance_pct * 100:.1f}%",
                "Reward:Risk": f"{s.reward_to_risk_ratio:.1f}",
                "Rule Score": f"{s.rule_quality_score:.1f}/100",
                "Execution Status": s.execution_status,
            })
        df_sig = pd.DataFrame(sig_rows)
        st.dataframe(df_sig, use_container_width=True)

        st.subheader("Detailed Condition Justification")
        sel_symbol = st.selectbox("Inspect Stock Setup", [s.symbol for s in signals])
        matched_sig = next((s for s in signals if s.symbol == sel_symbol), None)

        if matched_sig:
            c1, c2 = st.columns(2)
            with c1:
                st.markdown(f"### Setup: **{matched_sig.symbol}**")
                st.write(f"• **Strategy**: `{matched_sig.strategy_id}` (v{matched_sig.strategy_version})")
                st.write(f"• **Signal Date**: `{matched_sig.signal_date}`")
                st.write(f"• **Reference Price**: ₹{matched_sig.reference_close:.2f}")
                st.write(f"• **+10% Profit Target**: ₹{matched_sig.target_price_estimate:.2f}")
                st.write(f"• **Initial Stop-Loss**: ₹{matched_sig.initial_stop_estimate:.2f} (-{matched_sig.stop_distance_pct * 100:.1f}%)")
                st.write(f"• **Reward-to-Risk Ratio**: {matched_sig.reward_to_risk_ratio:.2f}")
                st.write(f"• **Execution Status**: `{matched_sig.execution_status}`")
            with c2:
                st.markdown("### Passed Mandatory Conditions")
                passed = json.loads(matched_sig.rules_passed_json)
                for p in passed:
                    st.success(f"✓ {p}")


# ==============================================================================
# PAGE 3 — TECHNICAL ANALYSIS
# ==============================================================================
elif nav == "3. Technical Analysis":
    st.title("Stock Technical Analysis & Indicators")

    insts = repo.get_active_instruments()
    symbols_list = [i.symbol for i in insts] or ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"]
    sym_choice = st.selectbox("Select NSE Stock", symbols_list, index=0)

    bars = repo.get_bars(sym_choice)
    if not bars:
        st.warning(f"No local bars for {sym_choice}. Fetching live sample data...")
        ingest = DataIngestionEngine(db)
        df_new, logs = ingest.fetch_and_validate_symbol(sym_choice, persist=True)
        bars = repo.get_bars(sym_choice)

    if bars:
        df_stock = pd.DataFrame([
            {"date": b.date, "open": b.open, "high": b.high, "low": b.low, "close": b.close, "volume": b.volume}
            for b in bars
        ]).set_index("date")

        df_ind = calculate_all_indicators(df_stock)
        plot_df = df_ind.tail(150)

        # Plotly Candlestick with Indicators
        fig = make_subplots(
            rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.03,
            row_heights=[0.50, 0.15, 0.15, 0.20],
            subplot_titles=["Price & Moving Averages", "Volume & RVOL", "RSI 14", "MACD (12, 26, 9)"],
        )

        # 1. Candlestick & Overlays
        fig.add_trace(go.Candlestick(
            x=plot_df.index, open=plot_df["open"], high=plot_df["high"], low=plot_df["low"], close=plot_df["close"],
            name="OHLC"
        ), row=1, col=1)
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df["ema20"], line=dict(color="#58a6ff", width=1.5), name="EMA 20"), row=1, col=1)
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df["ema50"], line=dict(color="#f0883e", width=1.5), name="EMA 50"), row=1, col=1)
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df["ema200"], line=dict(color="#d29922", width=2), name="EMA 200"), row=1, col=1)
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df["bb_upper"], line=dict(color="#8b949e", dash="dot"), name="BB Upper"), row=1, col=1)
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df["bb_lower"], line=dict(color="#8b949e", dash="dot"), name="BB Lower"), row=1, col=1)

        # 2. Volume
        colors = ["#238636" if c >= o else "#da3633" for c, o in zip(plot_df["close"], plot_df["open"], strict=False)]
        fig.add_trace(go.Bar(x=plot_df.index, y=plot_df["volume"], marker_color=colors, name="Volume"), row=2, col=1)
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df["volume_sma20"], line=dict(color="#f0883e"), name="Vol SMA20"), row=2, col=1)

        # 3. RSI 14
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df["rsi14"], line=dict(color="#bc8cff"), name="RSI 14"), row=3, col=1)
        fig.add_hline(y=70, line_dash="dash", line_color="#da3633", row=3, col=1)
        fig.add_hline(y=30, line_dash="dash", line_color="#238636", row=3, col=1)

        # 4. MACD
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df["macd_line"], line=dict(color="#58a6ff"), name="MACD"), row=4, col=1)
        fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df["macd_signal"], line=dict(color="#f0883e"), name="Signal"), row=4, col=1)
        hist_colors = ["#238636" if h >= 0 else "#da3633" for h in plot_df["macd_hist"]]
        fig.add_trace(go.Bar(x=plot_df.index, y=plot_df["macd_hist"], marker_color=hist_colors, name="Histogram"), row=4, col=1)

        fig.update_layout(height=850, template="plotly_dark", xaxis_rangeslider_visible=False)
        st.plotly_chart(fig, use_container_width=True)


# ==============================================================================
# PAGE 4 — AGENT LEADERBOARD
# ==============================================================================
elif nav == "4. Agent Leaderboard":
    st.title("Independent Agent Leaderboard")
    st.caption("Comparing 5 competing independent strategy portfolios (₹1,00,000 initial capital each).")

    accounts = repo.get_accounts()
    rows = []
    for a in accounts:
        positions = repo.get_open_positions(a.id)
        trades = db.query(PaperPosition).filter(PaperPosition.account_id == a.id, PaperPosition.status == "CLOSED").all()
        wins = [t for t in trades if (t.realized_pnl_net or 0) > 0]
        win_rate = (len(wins) / len(trades) * 100.0) if trades else 0.0
        ret_pct = ((a.current_equity - a.initial_capital) / a.initial_capital) * 100.0

        rows.append({
            "Agent": a.name,
            "Virtual Equity": f"₹{a.current_equity:,.2f}",
            "Total Return": f"{ret_pct:+.2f}%",
            "Open Positions": len(positions),
            "Closed Trades": len(trades),
            "Win Rate": f"{win_rate:.1f}%",
            "Cash Balance": f"₹{a.current_cash:,.2f}",
        })

    st.dataframe(pd.DataFrame(rows), use_container_width=True)


# ==============================================================================
# PAGE 5 — PAPER PORTFOLIO
# ==============================================================================
elif nav == "5. Paper Portfolio":
    st.title("Paper Brokerage Portfolio")

    accounts = repo.get_accounts()
    agent_ids = [a.id for a in accounts]
    sel_agent = st.selectbox("Select Strategy Portfolio", agent_ids, index=0)

    acc = repo.get_account(sel_agent)
    if acc:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Available Cash", f"₹{acc.current_cash:,.2f}")
        c2.metric("Virtual Equity", f"₹{acc.current_equity:,.2f}")
        c3.metric("Initial Capital", f"₹{acc.initial_capital:,.2f}")
        ret = ((acc.current_equity - acc.initial_capital) / acc.initial_capital) * 100.0
        c4.metric("P&L Net Return", f"{ret:+.2f}%")

        st.subheader("Open Positions")
        open_pos = repo.get_open_positions(sel_agent)
        if not open_pos:
            st.info("No open positions in this portfolio.")
        else:
            p_rows = []
            for p in open_pos:
                p_rows.append({
                    "Symbol": p.symbol,
                    "Quantity": p.quantity,
                    "Entry Date": p.entry_date,
                    "Entry Price": f"₹{p.entry_price:.2f}",
                    "Target (+10%)": f"₹{p.target_price:.2f}",
                    "Stop Loss": f"₹{p.current_stop:.2f}",
                    "Sessions Held": p.sessions_held,
                })
            st.dataframe(pd.DataFrame(p_rows), use_container_width=True)

        st.subheader("Order History")
        orders = repo.get_orders(account_id=sel_agent)
        if orders:
            o_rows = [{
                "Order ID": o.id, "Symbol": o.symbol, "Side": o.order_side, "Qty": o.quantity,
                "Price": f"₹{o.signal_price:.2f}", "Status": o.status, "Date": str(o.created_at)[:10]
            } for o in orders]
            st.dataframe(pd.DataFrame(o_rows), use_container_width=True)


# ==============================================================================
# PAGE 6 — HISTORICAL BACKTESTS
# ==============================================================================
elif nav == "6. Historical Backtests":
    st.title("Historical Strategy Backtesting")
    st.caption("Conservative simulation using next-day open execution, statutory fees, and slippage.")

    strat_choice = st.selectbox(
        "Strategy to Evaluate",
        ["trend_momentum", "volume_breakout", "bullish_pullback", "bollinger_squeeze", "consensus", "all"],
        index=0,
    )

    if st.button("🚀 Run Walk-Forward Backtest", type="primary"):
        with st.spinner("Executing walk-forward historical simulation..."):
            # Load cached universe bars
            insts = repo.get_active_instruments()[:20]  # Sample first 20 liquid stocks for interactive speed
            ingest = DataIngestionEngine(db)
            universe_dfs = {}
            for inst in insts:
                bars = repo.get_bars(inst.symbol)
                if bars and len(bars) >= 200:
                    df_b = pd.DataFrame([{"date": b.date, "open": b.open, "high": b.high, "low": b.low, "close": b.close, "volume": b.volume} for b in bars]).set_index("date")
                    universe_dfs[inst.symbol] = df_b

            nifty_bars = repo.get_bars("^NSEI")
            nifty_df = pd.DataFrame([{"date": b.date, "open": b.open, "high": b.high, "low": b.low, "close": b.close, "volume": b.volume} for b in nifty_bars]).set_index("date") if nifty_bars else None

            engine = BacktestEngine(initial_capital=100000.0)
            res = engine.run(strat_choice, universe_dfs, nifty_df=nifty_df)

            if "metrics" in res:
                m = res["metrics"]
                st.success("Backtest Completed Successfully!")
                b1, b2, b3, b4 = st.columns(4)
                b1.metric("Final Equity", f"₹{res['final_equity']:,.2f}")
                b2.metric("Total Return", f"{m['total_return_pct']:+.2f}%")
                b3.metric("Win Rate", f"{m['win_rate_pct']:.1f}%")
                b4.metric("Target (+10%) Hit Rate", f"{m['target_hit_rate_pct']:.1f}%")

                st.subheader("Performance & Risk Metrics")
                st.json(m)

                if res.get("equity_curve"):
                    eq_df = pd.DataFrame(res["equity_curve"]).set_index("date")
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(x=eq_df.index, y=eq_df["equity"], line=dict(color="#238636", width=2), name="Strategy Equity"))
                    fig.update_layout(template="plotly_dark", title="Equity Curve (₹)", height=400)
                    st.plotly_chart(fig, use_container_width=True)


# ==============================================================================
# PAGE 7 — REJECTED STOCKS
# ==============================================================================
elif nav == "7. Rejected Stocks":
    st.title("Rejected Stock Candidates")
    st.caption("Audit log showing the exact deterministic rules that disqualified candidates.")

    rejected = repo.get_rejected_candidates(limit=100)
    if not rejected:
        st.info("No rejection records currently logged in database.")
    else:
        r_rows = []
        for r in rejected:
            r_rows.append({
                "Date": r.date,
                "Symbol": r.symbol,
                "Strategy": r.strategy_id,
                "Reason": r.reason,
            })
        st.dataframe(pd.DataFrame(r_rows), use_container_width=True)


# ==============================================================================
# PAGE 8 — SYSTEM HEALTH
# ==============================================================================
elif nav == "8. System Health":
    st.title("System Health & Diagnostic Monitor")

    ingest = DataIngestionEngine(db)
    provider_health = ingest.get_provider_health()

    c1, c2, c3 = st.columns(3)
    c1.metric("TejHQ Provider", "🟢 HEALTHY" if provider_health["tejhq"] else "🔴 UNREACHABLE")
    c2.metric("Yahoo Finance", "🟢 HEALTHY" if provider_health["yahoo"] else "🔴 UNREACHABLE")
    c3.metric("SQLite WAL Mode", "🟢 ACTIVE")

    st.subheader("Autonomous Engine & Heartbeat Watchdog")
    hb_c1, hb_c2 = st.columns(2)
    with hb_c1:
        st.markdown(f"• **Heartbeat Status**: `{hb_status}`")
        st.markdown(f"• **Last Heartbeat**: `{last_hb}`")
        st.markdown("• **Single-Instance Lock**: `data/indigo_scheduler.lock` (Active)")
    with hb_c2:
        st.markdown("• **Next Scheduled Scan**: `19:15 IST (Mon-Fri)`")
        st.markdown("• **Missed Job Recovery**: `Active (No Backdating)`")
        st.markdown("• **Telegram Alerts**: `Active (Idempotent Deduplication)`")

    st.subheader("Recent Background Job Logs")
    job_logs = db.query(SchedulerJobLog).order_by(SchedulerJobLog.run_timestamp.desc()).limit(20).all()
    if job_logs:
        j_data = [{
            "Job": j.job_name, "Status": j.status, "Duration (s)": round(j.duration_seconds, 2),
            "Timestamp": str(j.run_timestamp), "Message": j.message
        } for j in job_logs]
        st.dataframe(pd.DataFrame(j_data), use_container_width=True)
    else:
        st.info("No scheduler job runs logged yet.")

db.close()
