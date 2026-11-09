"""
End-to-End Streamlit Application & Market Replay Lab Integration Test Suite.
Uses Streamlit AppTest framework to simulate user interactions:
- Opening Market Replay Lab
- Switching stocks and time intervals
- Step-by-step playback (+1 Bar, -1 Bar, Jump to End, Reset)
- Complete session run
- Page navigation across Overview, Signals, and Replay
- Asserts ZERO uncaught exceptions or rendering failures.
"""

from __future__ import annotations

from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest

APP_PATH = str((Path(__file__).resolve().parent.parent.parent / "public_app.py").resolve())


def test_public_dashboard_overview_and_navigation():
    """Verify that public_app.py loads cleanly and navigates between pages."""
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    assert len(at.exception) == 0, f"Exceptions on initial load: {at.exception}"

    # Navigate to Verified BUY Signals
    at.sidebar.radio[0].set_value("2. Verified BUY Signals")
    at.run()
    assert len(at.exception) == 0, f"Exceptions on Signals page: {at.exception}"

    # Navigate to Strategy Leaderboard
    at.sidebar.radio[0].set_value("3. Strategy Leaderboard")
    at.run()
    assert len(at.exception) == 0, f"Exceptions on Leaderboard page: {at.exception}"

    # Navigate to System Health & Heartbeat
    at.sidebar.radio[0].set_value("7. System Health & Heartbeat")
    at.run()
    assert len(at.exception) == 0, f"Exceptions on Health page: {at.exception}"


def test_market_replay_lab_playback_and_controls():
    """Test full interactive playback controls on Market Replay Lab with state synchronization."""
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()

    # Navigate to Market Replay Lab
    at.sidebar.radio[0].set_value("8. Market Replay Lab")
    at.run()
    assert len(at.exception) == 0, f"Exceptions entering Replay Lab: {at.exception}"

    # Verify all expected playback buttons exist
    labels = [b.label for b in at.button]
    assert any("Run Full Session" in l for l in labels)
    assert any("Start" in l for l in labels)
    assert any("+1 Bar" in l for l in labels)
    assert any("-1 Bar" in l for l in labels)
    assert any("+5 Bars" in l for l in labels)
    assert any("End" in l for l in labels)
    assert any("Reset" in l for l in labels)

    # 1. Click Start (bar 1)
    btn_start = [b for b in at.button if "Start" in b.label][0]
    btn_start.click().run()
    assert len(at.exception) == 0, f"Exceptions clicking Start: {at.exception}"
    assert at.session_state["replay_step"] == 1

    # 2. Advance 1 bar (moves bar 1 to 2)
    btn_next = [b for b in at.button if "+1 Bar" in b.label][0]
    btn_next.click().run()
    assert len(at.exception) == 0, f"Exceptions clicking +1 Bar: {at.exception}"
    assert at.session_state["replay_step"] == 2

    # 3. Advance 5 bars (moves bar 2 to 7)
    btn_plus5 = [b for b in at.button if "+5 Bars" in b.label][0]
    btn_plus5.click().run()
    assert len(at.exception) == 0, f"Exceptions clicking +5 Bars: {at.exception}"
    assert at.session_state["replay_step"] == 7

    # 4. Step backwards 1 bar (moves bar 7 to 6)
    btn_prev = [b for b in at.button if "-1 Bar" in b.label][0]
    btn_prev.click().run()
    assert len(at.exception) == 0, f"Exceptions clicking -1 Bar: {at.exception}"
    assert at.session_state["replay_step"] == 6

    # 5. Jump to End of Session (reaches last available candle)
    btn_end = [b for b in at.button if "End" in b.label][0]
    btn_end.click().run()
    assert len(at.exception) == 0, f"Exceptions clicking End: {at.exception}"
    end_step = at.session_state["replay_step"]
    assert end_step > 20

    # Capture equity after stepping to End
    engine_key = at.session_state["current_engine_key"]
    stepped_engine = at.session_state[engine_key]
    primary_sid = list(stepped_engine.broker.accounts.keys())[0]
    stepped_trades = len(stepped_engine.broker.accounts[primary_sid].closed_trades)
    stepped_equity = stepped_engine.broker.accounts[primary_sid].total_equity

    # 6. Click Run Full Session: verify it yields identical trades and ending equity
    btn_full = [b for b in at.button if "Run Full Session" in b.label][0]
    btn_full.click().run()
    assert len(at.exception) == 0, f"Exceptions clicking Run Full Session: {at.exception}"
    assert at.session_state["replay_step"] == end_step
    full_engine = at.session_state[engine_key]
    full_trades = len(full_engine.broker.accounts[primary_sid].closed_trades)
    full_equity = full_engine.broker.accounts[primary_sid].total_equity

    assert full_trades == stepped_trades
    assert full_equity == stepped_equity

    # 7. Reset Broker
    btn_reset = [b for b in at.button if "Reset" in b.label][0]
    btn_reset.click().run()
    assert len(at.exception) == 0, f"Exceptions clicking Reset: {at.exception}"
    assert at.session_state["replay_step"] == 1


def test_market_replay_lab_asset_switching():
    """Verify switching assets (RELIANCE -> TCS) and intervals (5m -> 15m) renders without exceptions."""
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()

    at.sidebar.radio[0].set_value("8. Market Replay Lab")
    at.run()
    assert len(at.exception) == 0

    # Switch asset to TCS
    # The first selectbox in main area is Asset
    select_asset = at.selectbox[0]
    assert "RELIANCE" in select_asset.options
    assert "TCS" in select_asset.options
    select_asset.set_value("TCS")
    at.run()
    assert len(at.exception) == 0, f"Exceptions switching asset to TCS: {at.exception}"

    # Switch interval to 15m
    select_interval = [s for s in at.selectbox if "5m" in s.options][0]
    select_interval.set_value("15m")
    at.run()
    assert len(at.exception) == 0, f"Exceptions switching interval to 15m: {at.exception}"

    # Advance 1 bar in 15m mode
    btn_next = [b for b in at.button if "+1 Bar" in b.label][0]
    btn_next.click()
    at.run()
    assert len(at.exception) == 0, f"Exceptions advancing in 15m mode: {at.exception}"

    # Switch back to Overview
    at.sidebar.radio[0].set_value("1. Overview & Performance")
    at.run()
    assert len(at.exception) == 0, f"Exceptions switching back to Overview: {at.exception}"
