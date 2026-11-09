# INDIGO QUANT 📈

**Autonomous Indian Equity Swing-Trading Research & Paper Brokerage Platform**

INDIGO QUANT is a production-grade, mathematically verified, fully autonomous quantitative swing-trading research and paper-trading platform tailored for NSE/BSE-listed Indian equities.

It identifies high-conviction swing-trading opportunities targeting **+10% gross upside over approximately 5–20 trading sessions** using competing independent quantitative strategies, a strict NIFTY 50 market regime filter, deterministic decision-tree logic, and an Indian delivery equity cost model.

---

## Key Highlights & Architectural Principles

- **Zero LLM Override of Numerical Rules**: All signal decisions, indicator thresholds, and risk bounds are calculated mathematically with direct numeric comparisons.
- **100% Free Software & Free Market Data**: Integrates TejHQ (`https://api.tejhq.dev`) as primary Indian EOD market data adapter and Yahoo Finance (`yfinance`) as secondary validator and NIFTY 50 (`^NSEI`) benchmark engine. No paid API keys or subscriptions required.
- **Virtual Capital Isolation**: ₹1,00,000 initial virtual capital for EACH of the 5 independent strategy portfolios.
- **Indian Regulatory Delivery Fee Model**: Realistic calculation of STT (0.1% buy & sell), Exchange charges (0.00297%), SEBI turnover fees, Stamp duty (0.015%), GST (18%), and Depository Participant (DP) charges (₹15.93 per sell).
- **Conservative Execution**: Intrabar conflict resolution assumes stop-loss was reached first; gap-down below stop fills at actual opening price, never the stop price; zero lookahead on rolling indicators (`high.shift(1).rolling(20).max()`).
- **Autonomous Scheduling**: APScheduler configured with `Asia/Kolkata` timezone runs EOD market scans, morning order executions, afternoon exit monitoring, and weekend/holiday skipping.
- **Interactive Multi-Page Dashboard**: Dark-mode Streamlit dashboard with Plotly candlestick and indicator charts, agent leaderboards, trade journals, and rejection diagnostics.

---

## Directory Structure

```text
indigo-quant/
├── .env.example              # Sample environment variables
├── .gitignore                # Git ignore patterns
├── pyproject.toml            # Project packaging & Ruff/Pytest configs
├── requirements.txt          # Pinned dependency manifest
├── README.md                 # Complete documentation
├── setup.ps1                 # Windows 11 automated setup script
├── setup_pi.sh               # Raspberry Pi 4 Debian deployment script
├── run.ps1                   # Windows launch helper script
│
├── config/
│   ├── settings.yaml         # Application & market data settings
│   ├── strategies.yaml       # Fixed versioned strategy baseline parameters
│   ├── risk.yaml             # Portfolio exposure, sizing & statutory fee rates
│   └── universe.csv          # Curated liquid NSE equities with ISIN and sector
│
├── src/
│   └── indigo_quant/
│       ├── data/
│       │   ├── providers/    # TejHQ & Yahoo Finance adapters
│       │   ├── calendar.py   # NSE holiday & market session utilities
│       │   ├── validation.py # OHLC integrity, liquidity & staleness checks
│       │   └── ingestion.py  # Data coordinator & SQLite persistence
│       │
│       ├── indicators/
│       │   └── technical.py  # Mathematically pure indicator formulas
│       │
│       ├── strategies/       # Competing quantitative trading agents
│       │   ├── base.py       # Base strategy contract & ConditionResult
│       │   ├── momentum.py   # Agent A: Trend Momentum
│       │   ├── breakout.py   # Agent B: Volume Breakout
│       │   ├── pullback.py   # Agent C: Bullish Pullback Recovery
│       │   ├── squeeze.py    # Agent D: Bollinger Squeeze Breakout
│       │   └── consensus.py  # Agent E: Multi-Agent Consensus
│       │
│       ├── engine/
│       │   ├── market_regime.py # NIFTY 50 benchmark filter
│       │   ├── ranking.py       # Deterministic rule quality score (0–100)
│       │   ├── risk.py          # ATR stops, sizing, and exposure caps
│       │   ├── decision.py      # Complete decision pipeline
│       │   └── execution.py     # Paper order management
│       │
│       ├── paper/
│       │   ├── fees.py       # Indian delivery cost model & slippage
│       │   ├── orders.py     # Idempotent order models
│       │   ├── portfolio.py  # Cash ledger & position tracking
│       │   └── broker.py     # Conservative simulated paper broker
│       │
│       ├── backtesting/
│       │   ├── metrics.py    # Win rate, Sharpe, Sortino, Drawdown, Profit Factor
│       │   ├── backtester.py # Walk-forward simulation engine
│       │   └── walkforward.py# Temporal train/validation/test split
│       │
│       ├── db/
│       │   ├── session.py    # SQLite engine with WAL mode & foreign keys
│       │   ├── models.py     # SQLAlchemy relational models
│       │   └── repository.py # Transactional persistence & query helpers
│       │
│       ├── api/
│       │   └── main.py       # FastAPI REST endpoints
│       │
│       ├── dashboard/
│       │   └── app.py        # Streamlit 8-page dark-mode dashboard
│       │
│       ├── notifications/
│       │   └── telegram.py   # Optional Telegram Bot BUY alerts
│       │
│       ├── scheduler/
│       │   └── jobs.py       # APScheduler automated cron workflows
│       │
│       └── cli.py            # Rich terminal command-line interface
│
├── deployment/
│   └── systemd/
│       └── indigo-quant.service # Systemd unit for Raspberry Pi 24/7 hosting
│
├── tests/
│   ├── conftest.py           # In-memory SQLite & synthetic price fixtures
│   ├── unit/                 # Unit tests (indicators, strategies, risk, fees, broker)
│   └── integration/          # Integration tests (FastAPI, full pipeline)
│
├── scripts/
│   ├── init_db.py            # Database initialization
│   ├── check_data.py         # Provider health checks
│   ├── backtest.py           # Historical backtest runner
│   └── smoke_test.py         # End-to-end operational verification
│
└── .github/
    └── workflows/
        └── scanner.yml       # Free scheduled GitHub Actions scanner
```

---

## Quickstart on Windows 11

### 1. Automated Setup
Open PowerShell in the project directory and run:
```powershell
.\setup.ps1
```
This script will:
- Verify Python 3.11+
- Create the virtual environment `.venv`
- Install all dependencies from `requirements.txt`
- Initialize the SQLite database and seed ₹1,00,000 per agent
- Run provider connectivity diagnostics
- Run the 39-test automated test suite

### 2. Launch the Streamlit Dashboard
```powershell
.\run.ps1 -Mode dashboard
```
Or directly:
```powershell
.\.venv\Scripts\python.exe -m streamlit run src/indigo_quant/dashboard/app.py
```
Open **`http://localhost:8501`** in your browser.

### 3. Launch the FastAPI REST Server
```powershell
.\run.ps1 -Mode api
```
Access interactive OpenAPI documentation at **`http://127.0.0.1:8000/docs`**.

---

## Command Line Interface (`indigo`)

The platform includes a CLI:
```powershell
# Run system doctor diagnostics
.\.venv\Scripts\python.exe -m indigo_quant.cli doctor

# Inspect virtual portfolio balances
.\.venv\Scripts\python.exe -m indigo_quant.cli portfolios

# View technical indicators for a stock
.\.venv\Scripts\python.exe -m indigo_quant.cli indicators RELIANCE

# Fetch market data for active universe
.\.venv\Scripts\python.exe -m indigo_quant.cli fetch --limit 20

# Run deterministic decision scan
.\.venv\Scripts\python.exe -m indigo_quant.cli scan

# Run historical backtest
.\.venv\Scripts\python.exe -m indigo_quant.cli backtest --strategy all

# Run test suite
.\.venv\Scripts\python.exe -m indigo_quant.cli test
```

---

## Strategy Agents & Numeric Rules

### Market Regime Filter (Prerequisite for all new BUY orders)
Before any strategy may issue a BUY signal, the Market Regime Agent evaluates NIFTY 50 (`^NSEI`):
1. `NIFTY 50 close > EMA200`
2. `NIFTY 50 EMA50 > EMA200`
- Both must be true -> **BULLISH** (New BUY orders permitted).
- If either fails -> **DEFENSIVE** (New BUY orders blocked; existing positions continue to be monitored for exit).
- If benchmark data is missing or stale -> **UNKNOWN** (Fail-closed defensively).

### Competing Independent Strategies

| Strategy | Exploited Market Anomaly | Entry Criteria (ALL Mandatory) |
| :--- | :--- | :--- |
| **Agent A: Trend Momentum** | Sustained institutional trend continuation | `EMA20 > EMA50 > EMA200`, `close > SMA200`, `close >= EMA20`, `52 <= RSI14 <= 68`, `MACD > Signal`, `MACD_hist > 0`, `ADX14 >= 20`, `RVOL20 >= 1.10`, `close <= EMA20 * 1.05`, `5-day return > 0%` |
| **Agent B: Volume Breakout** | Decisive price breakout above 20-session resistance | `close >= prev_20_high * 1.005`, `close <= prev_20_high * 1.04`, `RVOL20 >= 1.50`, `EMA20 > EMA50`, `close > EMA200`, `55 <= RSI14 <= 75`, `ADX14 >= 20`, `ATR14 / close <= 0.05`, `Close in upper 25% of daily range` |
| **Agent C: Pullback Recovery** | Bullish dip-buying on controlled pullback to EMA20 | `EMA50 > EMA200`, `close > EMA50`, `prev_close <= prev_ema20`, `close > ema20` (genuine cross), `38 <= prev_rsi <= 50`, `50 <= curr_rsi <= 65`, `curr_macd_hist > prev_macd_hist`, `RVOL20 >= 0.90`, `close <= EMA20 * 1.04` |
| **Agent D: Bollinger Squeeze** | Volatility contraction followed by upward expansion | `Prior BB width <= 20th percentile of prior 120 sessions`, `close > prev_upper_BB`, `RVOL20 >= 1.50`, `EMA20 > EMA50 > EMA200`, `55 <= RSI14 <= 72`, `curr_adx > prev_adx`, `close > prev_20_high` |
| **Agent E: Multi-Agent Consensus** | High-conviction multi-system confirmation | Requires at least **2 independent strategies** to issue qualified BUY signals for the same stock on the same session. |

---

## 10% Gross Profit Target & Risk Rules

- **Target**: +10.0% GROSS from actual simulated entry fill. (This is a fixed objective, NOT a guarantee).
- **Stop-Loss**: `stop_distance_pct = max(0.02, 1.5 * ATR14 / entry_price)`. If > 5.0%, rejected as too volatile. Initial stop is `entry_price * (1 - stop_distance_pct)`.
- **Time Exit**: Close position at market close on the **20th completed trading session** if neither target nor stop triggered.
- **Position Sizing**:
  - Max risk per trade: 0.5% of current portfolio equity.
  - Max position allocation: 20% of current portfolio equity.
  - Max simultaneous positions: 5.
  - Max aggregate portfolio exposure: 75%.
  - `quantity = min(risk_qty, alloc_qty, cash_qty, exposure_qty)`.
  - Zero fractional shares, no leverage, no averaging down.

---

## Indian Regulatory Delivery Fee Model

Modeled strictly after official circulars from NSE, SEBI, and standard discount brokers (as of October 2024):
- **Brokerage**: ₹0 (or 0.03% capped at ₹20 per trade).
- **STT (Securities Transaction Tax)**: 0.10% on BUY and 0.10% on SELL (delivery).
- **Exchange Transaction Charges**: 0.00297% (NSE).
- **SEBI Turnover Charge**: ₹10 per crore (0.0001%).
- **Stamp Duty**: 0.015% on BUY only.
- **GST**: 18% on (brokerage + exchange txn charges + SEBI charges).
- **Depository Participant (DP) Charges**: ₹15.93 flat per SELL trade.
- **Slippage**: 0.10% modeled on simulated fills.

---

## 24/7 Deployment on Raspberry Pi 4

1. Clone or copy this repository to your Raspberry Pi:
   ```bash
   git clone <repo-url> ~/TRADER
   cd ~/TRADER
   ```
2. Run the automated deployment script:
   ```bash
   chmod +x setup_pi.sh
   ./setup_pi.sh
   ```
3. Enable and start the systemd background service:
   ```bash
   sudo systemctl enable --now indigo-quant
   ```
4. Check running status and logs:
   ```bash
   sudo systemctl status indigo-quant
   tail -f logs/indigo.log
   ```
5. Open the dashboard on any device connected to your local WiFi/LAN:
   ```text
   http://<raspberry-pi-ip>:8501
   ```

---

## Testing & Verification

Run the test suite with pytest:
```powershell
.\.venv\Scripts\python.exe -m pytest tests -v
```
All **39 automated tests** verify:
- Indicator calculations against mathematical baselines.
- Wilder smoothing for RSI and ATR.
- Zero lookahead on historical breakout levels.
- Every condition for Agents A, B, C, D, and E.
- Market regime blocking and fail-closed behavior.
- Position sizing, risk limits, and exposure ceilings.
- Indian delivery cost calculations and DP charges.
- Conservative order execution (gaps, intrabar conflicts, time exits).
- Database persistence and session isolation.
- FastAPI REST endpoints.

Run the end-to-end smoke test:
```powershell
.\.venv\Scripts\python.exe scripts/smoke_test.py
```

---

## Transparency, Limitations & Safeguards

1. **Paper Trading Only**: This software is built for quantitative research and simulated paper trading. It contains NO real-money order routing code and cannot connect to live broker order endpoints.
2. **10% Upside is a Target, Not a Guarantee**: Markets involve risk of principal loss. A 10% profit target is an objective used for reward-to-risk sizing and simulated exit logic, not a prediction or promise.
3. **Free Data Limitations**: Free EOD data from TejHQ refreshes after 18:30 IST. Yahoo Finance delayed snapshots are used for daytime simulation. Real-time sub-second tick execution is not supported by free providers.
4. **Survivorship Bias Disclosure**: Historical backtests run against a fixed universe of liquid stocks may exhibit survivorship bias compared to point-in-time index constituent histories.

---

*INDIGO QUANT — Quantitative Research Team*
