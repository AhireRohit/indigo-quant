"""
Unit tests for the Backtesting Engine and Metrics Calculator.
"""

import datetime

import pandas as pd
import pytest

from indigo_quant.backtesting.backtester import BacktestEngine
from indigo_quant.backtesting.metrics import calculate_performance_metrics
from indigo_quant.backtesting.walkforward import get_train_val_test_splits


def test_metrics_empty_trades():
    eq = pd.Series([100000.0, 100000.0])
    res = calculate_performance_metrics([], eq)
    assert res["total_trades"] == 0
    assert res["win_rate_pct"] == 0.0


def test_metrics_calculation_with_trades():
    trades = [
        {"net_pnl": 1000.0, "return_pct": 10.0, "sessions_held": 5, "total_fees": 20.0, "entry_date": datetime.date(2024, 1, 1), "target_achieved": True},
        {"net_pnl": 1200.0, "return_pct": 10.5, "sessions_held": 8, "total_fees": 25.0, "entry_date": datetime.date(2024, 1, 15), "target_achieved": True},
        {"net_pnl": -400.0, "return_pct": -3.5, "sessions_held": 4, "total_fees": 15.0, "entry_date": datetime.date(2024, 2, 1), "target_achieved": False},
    ]
    eq_series = pd.Series([100000.0, 101000.0, 102200.0, 101800.0])
    metrics = calculate_performance_metrics(trades, eq_series)

    assert metrics["total_trades"] == 3
    assert metrics["win_count"] == 2
    assert metrics["loss_count"] == 1
    assert metrics["win_rate_pct"] == pytest.approx(66.7, abs=0.1)
    assert metrics["target_hit_rate_pct"] == pytest.approx(66.7, abs=0.1)
    assert metrics["profit_factor"] == pytest.approx(2200.0 / 400.0, abs=0.1)
    assert metrics["total_return_pct"] == pytest.approx(1.8, abs=0.1)


def test_train_val_test_split():
    dates = [datetime.date(2023, 1, 1) + datetime.timedelta(days=i) for i in range(100)]
    train, val, test = get_train_val_test_splits(dates, train_ratio=0.6, val_ratio=0.2)

    assert train[0] == dates[0]
    assert train[1] == dates[59]
    assert val[0] == dates[60]
    assert val[1] == dates[79]
    assert test[0] == dates[80]
    assert test[1] == dates[99]


def test_backtest_engine_run(synthetic_ohlcv_uptrend):
    engine = BacktestEngine(initial_capital=100000.0)
    stock_df = synthetic_ohlcv_uptrend.copy()
    nifty_df = synthetic_ohlcv_uptrend.copy()

    res = engine.run("trend_momentum", {"STOCK_A": stock_df}, nifty_df=nifty_df)
    assert "strategy_id" in res
    assert "metrics" in res
    assert "final_equity" in res
    assert res["initial_capital"] == 100000.0
