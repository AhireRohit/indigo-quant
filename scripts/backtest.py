"""Run full backtest suite script."""
import sys
from pathlib import Path
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

src_dir = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(src_dir))

from indigo_quant.db.session import SessionLocal
from indigo_quant.db.repository import Repository
from indigo_quant.backtesting.backtester import BacktestEngine

if __name__ == "__main__":
    db = SessionLocal()
    repo = Repository(db)

    print("Loading universe data from local database...")
    insts = repo.get_active_instruments()[:25]
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

    print(f"Loaded {len(universe_data)} valid equities for backtest.")
    engine = BacktestEngine(initial_capital=100000.0)
    results = engine.run("all", universe_data, nifty_df=nifty_df)

    print("\n================== BACKTEST SUMMARY ==================")
    for sid, res in results.items():
        if "metrics" in res:
            m = res["metrics"]
            print(f"Strategy: {sid.upper()}")
            print(f"  • Total Return: {m['total_return_pct']:+.2f}%")
            print(f"  • Total Trades: {m['total_trades']}")
            print(f"  • Win Rate: {m['win_rate_pct']:.1f}%")
            print(f"  • Target (+10%) Hit Rate: {m['target_hit_rate_pct']:.1f}%")
            print(f"  • Profit Factor: {m['profit_factor']}")
            print(f"  • Max Drawdown: {m['max_drawdown_pct']:.2f}%")
            print(f"  • Sharpe Ratio: {m['sharpe_ratio']:.2f}\n")
    db.close()
