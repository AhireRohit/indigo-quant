"""
INDIGO QUANT — Public Streamlit Cloud Dashboard.
Purely read-only, cloud-native quantitative dashboard powered by sanitized JSON snapshots.
Designed for 100% free hosting on Streamlit Community Cloud (https://share.streamlit.io).

Strictly contains ZERO secrets, ZERO private paths, ZERO database dependencies, and ZERO broker execution.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from indigo_quant.replay.ui import render_market_replay_lab

# Page Configuration
st.set_page_config(
    page_title="INDIGO QUANT — Public Research & Paper Trading",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Dark theme CSS styling
st.markdown("""
<style>
    .main { background-color: #0b0f19; color: #e2e8f0; }
    .stMetric { background-color: #111827; padding: 14px; border-radius: 10px; border: 1px solid #1f2937; }
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] { background-color: #111827; border-radius: 6px; padding: 8px 16px; color: #94a3b8; }
    .stTabs [aria-selected="true"] { background-color: #2563eb !important; color: white !important; font-weight: bold; }
    .badge-bullish { background-color: #10b981; color: white; padding: 4px 8px; border-radius: 4px; font-weight: bold; }
    .badge-defensive { background-color: #ef4444; color: white; padding: 4px 8px; border-radius: 4px; font-weight: bold; }
    .badge-pill { background-color: #1e293b; color: #cbd5e1; border: 1px solid #334155; padding: 4px 10px; border-radius: 20px; font-size: 0.85rem; }
</style>
""", unsafe_allow_html=True)


DATA_DIR = Path("public_data")


@st.cache_data(ttl=60)
def load_public_json(filename: str) -> Any:
    """Load cached JSON snapshot from public_data directory."""
    path = DATA_DIR / filename
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        st.error(f"Error loading {filename}: {e}")
        return {}


# Load Core Snapshots
overview = load_public_json("overview.json") or {}
health = load_public_json("system_health.json") or {}
leaderboard = load_public_json("leaderboard.json") or []
signals_data = load_public_json("signals.json") or {}
signals = signals_data.get("signals", [])
rejected = signals_data.get("rejected_candidates", [])
charts_data = load_public_json("charts_data.json") or {}
portfolios = load_public_json("portfolios.json") or {}

# Sidebar Branding & Navigation
st.sidebar.markdown("## 🎯 INDIGO QUANT")
st.sidebar.caption("Autonomous Indian Equity Swing-Trading Platform")

status_str = health.get("status", "HEALTHY")
status_color = "🟢" if status_str == "HEALTHY" else "🟡"
st.sidebar.markdown(f"**Engine Status**: {status_color} `{status_str}`")
st.sidebar.markdown(f"**Last Sync**: `{overview.get('last_updated_ist', 'N/A')}`")

nav = st.sidebar.radio(
    "Navigation",
    [
        "1. Overview & Performance",
        "2. Verified BUY Signals",
        "3. Strategy Leaderboard",
        "4. Virtual Portfolios",
        "5. Technical Charts",
        "6. Deterministic Rejections",
        "7. System Health & Heartbeat",
        "8. Market Replay Lab",
    ],
)

st.sidebar.markdown("---")
st.sidebar.info(
    "🛡️ **System Classification**\n\n"
    "• **Forward Paper Trading**: Live simulated portfolio tracking with realistic delivery costs\n"
    "• **Historical Backtesting**: Historical simulation (strictly separated from paper records)\n"
    "• **Deterministic Rules**: Zero black-box AI overrides\n"
    "• **Zero Real Capital**: Academic and algorithmic research only"
)


# ==============================================================================
# PAGE 1 — OVERVIEW & PERFORMANCE
# ==============================================================================
if nav == "1. Overview & Performance":
    st.title("System Overview & Live Performance")

    st.markdown("""
    <div style="background-color: #1e293b; border-left: 4px solid #3b82f6; padding: 12px 16px; border-radius: 6px; margin-bottom: 20px;">
        <span style="font-weight: bold; color: #93c5fd;">📊 Data Segregation & Integrity Notice:</span><br>
        <span style="color: #cbd5e1; font-size: 0.9rem;">
        • <b>Live Forward Paper Trading</b>: Trades executed at actual market open on next trading day with ₹1,00,000 virtual capital per strategy.<br>
        • <b>Historical Backtests</b>: Out-of-sample historical bar simulations. Never mixed with forward paper balances.<br>
        • <b>Test Isolation</b>: Development test suites run exclusively in isolated in-memory sandboxes and cannot contaminate production logs or state.
        </span>
    </div>
    """, unsafe_allow_html=True)

    cap = overview.get("capital_metrics", {})
    tot_equity = cap.get("current_total_equity", 500000.0)
    comb_ret = cap.get("combined_return_pct", 0.0)
    target_hits = cap.get("target_hits_total", 0)
    total_trades = cap.get("closed_trades_total", 0)
    hit_rate = cap.get("target_hit_rate_pct", 0.0)
    open_pos = cap.get("open_positions_total", 0)

    # Top KPI Cards
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric(
            "Combined Virtual NAV",
            f"₹{tot_equity:,.2f}",
            delta=f"{comb_ret:+.2f}%",
        )
    with col2:
        st.metric(
            "10% Target Hits",
            f"{target_hits} trades",
            delta=f"{hit_rate:.1f}% hit rate",
        )
    with col3:
        st.metric(
            "Open Positions",
            f"{open_pos} active",
            delta="Across 5 strategies",
            delta_color="off",
        )
    with col4:
        st.metric(
            "Tracked Equities",
            f"{overview.get('tracked_instruments_count', 26)} stocks",
            delta="NSE / BSE Universe",
            delta_color="off",
        )

    st.markdown("---")

    # Strategy Performance Table
    st.subheader("🏆 Competing Strategy Roster")
    if leaderboard:
        df_lead = pd.DataFrame(leaderboard)
        display_cols = [
            "rank", "strategy_name", "initial_capital", "current_equity",
            "total_return_pct", "open_positions_count", "total_trades",
            "target_hits_count", "target_hit_rate", "win_rate"
        ]
        col_names = {
            "rank": "Rank",
            "strategy_name": "Strategy Agent",
            "initial_capital": "Starting Capital (₹)",
            "current_equity": "Current Equity (₹)",
            "total_return_pct": "Return (%)",
            "open_positions_count": "Open Pos",
            "total_trades": "Trades",
            "target_hits_count": "10% Target Hits",
            "target_hit_rate": "Target Hit Rate (%)",
            "win_rate": "Win Rate (%)",
        }
        avail_cols = [c for c in display_cols if c in df_lead.columns]
        df_lead = df_lead[avail_cols].rename(columns=col_names)
        st.dataframe(df_lead, use_container_width=True, hide_index=True)
    else:
        st.info("No strategy leaderboard data available.")

    # Equity Curves
    st.subheader("📈 Multi-Strategy Equity Curves vs Benchmark")
    eq_curves = charts_data.get("equity_curves", {})
    if eq_curves:
        fig = go.Figure()
        colors = ["#2563eb", "#10b981", "#f59e0b", "#ec4899", "#8b5cf6"]
        for i, (strat_id, records) in enumerate(eq_curves.items()):
            if records:
                df_c = pd.DataFrame(records)
                strat_label = strat_id.replace("_", " ").title()
                fig.add_trace(go.Scatter(
                    x=df_c["date"],
                    y=df_c["total_equity"],
                    mode="lines",
                    name=strat_label,
                    line=dict(color=colors[i % len(colors)], width=2),
                ))
        fig.update_layout(
            template="plotly_dark",
            paper_bgcolor="#111827",
            plot_bgcolor="#111827",
            yaxis_title="Total Equity (₹)",
            xaxis_title="Trading Session",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            margin=dict(l=20, r=20, t=30, b=20),
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Equity curve history will display here after initial trading sessions.")


# ==============================================================================
# PAGE 2 — VERIFIED BUY SIGNALS
# ==============================================================================
elif nav == "2. Verified BUY Signals":
    st.title("🎯 Today's Qualified BUY Signals")
    st.caption("Deterministic mathematical conditions verified after EOD market close.")

    if signals:
        for sig in signals:
            score = sig.get("rule_quality_score", 0.0)
            score_color = "🟢" if score >= 80 else ("🟡" if score >= 60 else "🔴")

            with st.expander(f"{sig.get('symbol')} — {sig.get('strategy_name')} | Score: {score:.1f}/100", expanded=True):
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Reference Close", f"₹{sig.get('reference_close', 0.0):,.2f}")
                c2.metric("Target Estimate (+10%)", f"₹{sig.get('target_price_estimate', 0.0):,.2f}", delta="+10.0%")
                c3.metric("Stop Loss Estimate", f"₹{sig.get('initial_stop_estimate', 0.0):,.2f}")
                c4.metric("Reward/Risk Ratio", f"{sig.get('reward_to_risk_ratio', 0.0):.2f}x")

                st.markdown("**Exact Numerical Conditions Passed:**")
                for r in sig.get("rules_passed", []):
                    st.markdown(f"- ✅ `{r}`")

                st.caption(f"Signal Date: {sig.get('signal_date')} | Execution Status: {sig.get('execution_status', 'QUEUED')} | Zero Real Money")
    else:
        st.info("ℹ️ No BUY signals were generated in the most recent market scan. The algorithmic criteria strictly filter for high-probability swing opportunities.")


# ==============================================================================
# PAGE 3 — STRATEGY LEADERBOARD
# ==============================================================================
elif nav == "3. Strategy Leaderboard":
    st.title("🏆 Competing Quantitative Strategies")
    st.caption("Each agent manages an isolated virtual portfolio of ₹1,00,000 capital.")

    if leaderboard:
        for item in leaderboard:
            with st.container():
                st.subheader(f"#{item.get('rank')} — {item.get('strategy_name')}")
                ret = item.get("total_return_pct", 0.0)
                col1, col2, col3, col4, col5 = st.columns(5)
                col1.metric("Equity", f"₹{item.get('current_equity', 0.0):,.2f}")
                col2.metric("Return", f"{ret:+.2f}%")
                col3.metric("Win Rate", f"{item.get('win_rate', 0.0):.1f}%")
                col4.metric("10% Target Hits", f"{item.get('target_hits_count', 0)} ({item.get('target_hit_rate', 0.0)}%)")
                col5.metric("Open Positions", item.get("open_positions_count", 0))
                st.markdown("---")
    else:
        st.info("No leaderboard data available.")


# ==============================================================================
# PAGE 4 — VIRTUAL PORTFOLIOS
# ==============================================================================
elif nav == "4. Virtual Portfolios":
    st.title("💼 Forward Paper Portfolios & Execution Logs")
    st.caption("🟢 **LIVE FORWARD PAPER TRADING**: Real-time simulated execution at actual market open. Strictly ₹0.00 real money.")

    if portfolios:
        strategy_keys = list(portfolios.keys())
        selected_strat = st.selectbox("Select Strategy Portfolio", strategy_keys, format_func=lambda x: portfolios[x].get("account_name", x))

        strat_data = portfolios[selected_strat]
        st.markdown(f"**Available Cash Balance**: ₹{strat_data.get('cash', 0.0):,.2f} | **Total Equity**: ₹{strat_data.get('equity', 0.0):,.2f}")

        st.info("💡 **Methodology**: Paper positions are opened next morning upon market open with full Indian regulatory charges (STT, stamp duty, exchange turnover fee, SEBI turnover charges, GST) and 0.1% simulated slippage. Target: +10% within ~5–20 trading sessions.")

        tab_open, tab_closed = st.tabs(["Active Forward Paper Positions", "Closed Forward Paper Trades"])

        with tab_open:
            open_pos = strat_data.get("open_positions", [])
            if open_pos:
                df_open = pd.DataFrame(open_pos)
                st.dataframe(df_open, use_container_width=True, hide_index=True)
            else:
                st.info("No open positions in this portfolio.")

        with tab_closed:
            closed_pos = strat_data.get("closed_positions", [])
            if closed_pos:
                df_closed = pd.DataFrame(closed_pos)
                st.dataframe(df_closed, use_container_width=True, hide_index=True)
            else:
                st.info("No closed trades recorded yet.")
    else:
        st.info("No portfolio snapshot data available.")


# ==============================================================================
# PAGE 5 — TECHNICAL CHARTS
# ==============================================================================
elif nav == "5. Technical Charts":
    st.title("📊 Benchmark & Market Technicals")

    bench_series = charts_data.get("benchmark_series", [])
    if bench_series:
        df_bench = pd.DataFrame(bench_series)
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df_bench["date"],
            y=df_bench["close"],
            mode="lines",
            name="NIFTY 50 (^NSEI)",
            line=dict(color="#38bdf8", width=2),
        ))
        fig.update_layout(
            title="NIFTY 50 Benchmark Daily Close (Last 250 Sessions)",
            template="plotly_dark",
            paper_bgcolor="#111827",
            plot_bgcolor="#111827",
            yaxis_title="Close Price",
            xaxis_title="Date",
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Benchmark chart data unavailable.")


# ==============================================================================
# PAGE 6 — DETERMINISTIC REJECTIONS
# ==============================================================================
elif nav == "6. Deterministic Rejections":
    st.title("🛡️ Candidate Rejection Audit Log")
    st.caption("Every rejected stock explains the exact numeric conditions that failed. Zero black box decisions.")

    if rejected:
        df_rej = pd.DataFrame(rejected)
        st.dataframe(df_rej, use_container_width=True, hide_index=True)
    else:
        st.info("No rejection log records available.")


# ==============================================================================
# PAGE 7 — SYSTEM HEALTH & HEARTBEAT
# ==============================================================================
elif nav == "7. System Health & Heartbeat":
    st.title("⚙️ System Health & Engine Diagnostics")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Autonomous Daemon Status")
        st.markdown(f"• **Engine Liveness**: `{health.get('status', 'UNKNOWN')}`")
        st.markdown(f"• **Last Heartbeat**: `{health.get('scheduler', {}).get('last_heartbeat', 'N/A')}`")
        st.markdown(f"• **Next Scheduled Run**: `{health.get('scheduler', {}).get('next_scheduled_run', 'N/A')}`")
        st.markdown(f"• **Completed Market Day**: `{health.get('latest_completed_market_day', 'N/A')}`")
        st.markdown(f"• **Missed-Job Recovery**: `Active (No Backdating)`")

    with col2:
        st.subheader("Data Feeds & Connectivity")
        providers = health.get("data_providers", {})
        for p_name, p_info in providers.items():
            st.markdown(f"• **{p_name.upper()}**: `{p_info.get('status', 'OK')}` — {p_info.get('description', '')}")

        st.subheader("Cloud Hosting Architecture")
        hosting = health.get("hosting", {})
        st.markdown(f"• **Authoritative Engine**: `{hosting.get('engine', 'Windows 11 Laptop')}`")
        st.markdown(f"• **Public Presentation**: `{hosting.get('dashboard', 'Streamlit Community Cloud')}`")
        st.markdown(f"• **Synchronization**: `{hosting.get('data_sync', 'Git Snapshot Sync')}`")

    st.markdown("---")
    st.caption("INDIGO QUANT — Automated Indian Equity Quantitative Research & Paper-Trading Engine.")

# ==============================================================================
# PAGE 8 — MARKET REPLAY LAB
# ==============================================================================
elif nav == "8. Market Replay Lab":
    render_market_replay_lab()
