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
    """Test full interactive playback controls on Market Replay Lab."""
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()

    # Navigate to Market Replay Lab
    at.sidebar.radio[0].set_value("8. Market Replay Lab")
    at.run()
    assert len(at.exception) == 0, f"Exceptions entering Replay Lab: {at.exception}"

    # Verify buttons exist
    labels = [b.label for b in at.button]
    assert any("Start" in l for l in labels)
    assert any("+1 Bar" in l for l in labels)
    assert any("-1 Bar" in l for l in labels)
    assert any("+5 Bars" in l for l in labels)
    assert any("End" in l for l in labels)
    assert any("Reset Broker" in l for l in labels)

    # 1. Click Start (jump to bar 1)
    btn_start = [b for b in at.button if "Start" in b.label][0]
    btn_start.click()
    at.run()
    assert len(at.exception) == 0, f"Exceptions clicking Start: {at.exception}"

    # 2. Advance 1 bar
    btn_next = [b for b in at.button if "+1 Bar" in b.label][0]
    btn_next.click()
    at.run()
    assert len(at.exception) == 0, f"Exceptions clicking +1 Bar: {at.exception}"

    # 3. Advance 5 bars
    btn_plus5 = [b for b in at.button if "+5 Bars" in b.label][0]
    btn_plus5.click()
    at.run()
    assert len(at.exception) == 0, f"Exceptions clicking +5 Bars: {at.exception}"

    # 4. Step backwards 1 bar
    btn_prev = [b for b in at.button if "-1 Bar" in b.label][0]
    btn_prev.click()
    at.run()
    assert len(at.exception) == 0, f"Exceptions clicking -1 Bar: {at.exception}"

    # 5. Jump to End of Session
    btn_end = [b for b in at.button if "End" in b.label][0]
    btn_end.click()
    at.run()
    assert len(at.exception) == 0, f"Exceptions clicking End: {at.exception}"

    # 6. Reset Broker
    btn_reset = [b for b in at.button if "Reset Broker" in b.label][0]
    btn_reset.click()
    at.run()
    assert len(at.exception) == 0, f"Exceptions clicking Reset Broker: {at.exception}"


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
