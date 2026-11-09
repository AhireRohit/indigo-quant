# INDIGO QUANT — COMPREHENSIVE ARCHITECTURE & RESEARCH MANUAL

This manual provides an in-depth reference for quantitative researchers, algorithm engineers, and system operators.

---

## 1. Overall System Architecture

INDIGO QUANT follows a strictly sequential, unidirectional pipeline:
```
[Market Data Ingestion]
         │ (TejHQ primary, Yahoo fallback)
         ▼
[Data Validation & Integrity Engine]
         │ (Sanity checks, nonpositive OHLC filter, liquidity filter)
         ▼
[Technical Indicator Engine]
         │ (EMA, SMA, Wilder RSI/ATR/ADX, BB, RVOL, Rolling VWAP)
         ▼
[Market Regime Agent]
         │ (NIFTY 50 close > EMA200 and EMA50 > EMA200)
         ▼
[Independent Strategy Evaluation]
         │ (Agents A, B, C, D, and Consensus E)
         ▼
[Deterministic Risk & Sizing Engine]
         │ (0.5% risk budget, 20% max allocation, ATR stops, 10% gross target)
         ▼
[Rule Quality Ranking Engine]
         │ (Deterministic 0–100 score, tie-break by turnover)
         ▼
[Simulated Paper Broker]
         │ (Idempotent orders, Indian delivery fee model, gap & conflict handling)
         ▼
[Persistence & Analytics]
         │ (SQLite WAL mode, FastAPI REST, Streamlit interactive dashboard)
```

No feedback loops alter strategy parameters during a backtest. No large language model (LLM) or generative agent is permitted to override numeric comparisons.

---

## 2. Technical Indicators & Mathematical Formulas

- **EMA (Exponential Moving Average)**:
  $$\alpha = \frac{2}{\text{span} + 1}$$
  $$\text{EMA}_t = \alpha \cdot P_t + (1 - \alpha) \cdot \text{EMA}_{t-1}$$
- **SMA (Simple Moving Average)**:
  $$\text{SMA}_t = \frac{1}{N} \sum_{i=0}^{N-1} P_{t-i}$$
- **RSI (Wilder Smoothing)**:
  $$\alpha = \frac{1}{14}$$
  $$\text{AvgGain}_t = \alpha \cdot \text{Gain}_t + (1 - \alpha) \cdot \text{AvgGain}_{t-1}$$
  $$\text{RS} = \frac{\text{AvgGain}}{\text{AvgLoss}}, \quad \text{RSI} = 100 - \frac{100}{1 + \text{RS}}$$
- **ATR (Average True Range)**:
  $$\text{TR}_t = \max(H_t - L_t, |H_t - C_{t-1}|, |L_t - C_{t-1}|)$$
  $$\text{ATR}_t = \frac{1}{14} \text{TR}_t + \frac{13}{14} \text{ATR}_{t-1}$$
- **ADX (Average Directional Index)**:
  Computes Wilder-smoothed $+DM$ and $-DM$, derives $+DI$ and $-DI$, then calculates $DX$ and smooths over 14 bars.
- **Bollinger Bands**:
  $$\text{Middle} = \text{SMA}_{20}(C), \quad \sigma = \text{std}_{20}(C)$$
  $$\text{Upper} = \text{Middle} + 2\sigma, \quad \text{Lower} = \text{Middle} - 2\sigma$$
  $$\text{BandWidth} = \frac{\text{Upper} - \text{Lower}}{\text{Middle}}, \quad \%B = \frac{C - \text{Lower}}{\text{Upper} - \text{Lower}}$$
- **Rolling VWAP (20-day)**:
  $$TP = \frac{H + L + C}{3}, \quad \text{rolling\_vwap\_20} = \frac{\sum_{i=0}^{19} (TP_{t-i} \cdot V_{t-i})}{\sum_{i=0}^{19} V_{t-i}}$$

---

## 3. Exact BUY Conditions for Strategy Agents

### Agent A — Trend Momentum
1. `EMA20 > EMA50 > EMA200`
2. `close > SMA200`
3. `close >= EMA20`
4. `52 <= RSI14 <= 68`
5. `MACD_line > MACD_signal`
6. `MACD_histogram > 0`
7. `ADX14 >= 20`
8. `RVOL20 >= 1.10`
9. `close <= EMA20 * 1.05`
10. `5-session return > 0%`

### Agent B — Volume Breakout
1. `close >= previous_20_high * 1.005`
2. `close <= previous_20_high * 1.04`
3. `RVOL20 >= 1.50`
4. `EMA20 > EMA50`
5. `close > EMA200`
6. `55 <= RSI14 <= 75`
7. `ADX14 >= 20`
8. `ATR14 / close <= 0.05`
9. `(close - low) / (high - low) >= 0.75` (invalid if high == low)

### Agent C — Bullish Pullback Recovery
1. `EMA50 > EMA200`
2. `close > EMA50`
3. `prev_close <= prev_ema20`
4. `close > ema20` (genuine cross above EMA20)
5. `38 <= prev_rsi14 <= 50`
6. `50 <= curr_rsi14 <= 65`
7. `curr_macd_hist > prev_macd_hist`
8. `RVOL20 >= 0.90`
9. `close <= EMA20 * 1.04`

### Agent D — Bollinger Squeeze Breakout
1. `prev_bb_width <= 20th percentile of preceding 120 sessions`
2. `close > prev_bb_upper`
3. `RVOL20 >= 1.50`
4. `EMA20 > EMA50 > EMA200`
5. `55 <= RSI14 <= 72`
6. `curr_adx14 > prev_adx14`
7. `close > previous_20_high`

### Agent E — Multi-Agent Consensus
Requires agreement from at least 2 independent strategies on the same symbol and session.

---

## 4. Anomalies Exploited

- **Trend Momentum**: Exploits institutional post-earnings or structural momentum drifts where stocks in stage-2 markup continue higher with low relative volatility.
- **Volume Breakout**: Captures supply absorption at key psychological 20-session resistance levels accompanied by above-average volume participation.
- **Pullback Recovery**: Capitalizes on mean-reversion within an established macro uptrend, capturing favorable risk-to-reward entries near dynamic support (EMA20).
- **Bollinger Squeeze**: Exploits the cyclical alternation between volatility compression (consolidation) and volatility expansion (trend resumption).

---

## 5. Deterministic Decision Engine & Scoring

Qualified candidates are scored from 0 to 100 based on fixed, versioned weights:
1. **Trend Quality (25 pts)**: EMA alignment (10 pts), distance above SMA200 (10 pts), ADX trend strength (5 pts).
2. **Momentum Quality (20 pts)**: RSI optimality (10 pts), MACD histogram positive (5 pts), 5-day return momentum (5 pts).
3. **Volume Confirmation (20 pts)**: RVOL20 scaled linearly from 1.0x to 3.0x (5 to 20 pts).
4. **Entry Quality (20 pts)**: Proximity to EMA20 support (10 pts), upper-quartile range finish (10 pts).
5. **Volatility Quality (15 pts)**: Controlled ATR % (10 pts), volatility compression bonus (5 pts).

**Tie-Break Convention**:
1. Higher `rule_quality_score`
2. Higher 20-session average traded turnover
3. Alphabetical symbol ordering

---

## 6. Agent Disagreement Handling

Each agent operates an independent virtual portfolio with its own ₹1,00,000 capital, cash ledger, and positions. If Agent A issues a BUY on RELIANCE while Agent B rejects it, Agent A may execute the trade in its own portfolio without interference. The Consensus portfolio (Agent E) only executes when at least two independent agents agree.

---

## 7. Why +10% Profit is Not Guaranteed

A 10% profit target is a risk-engineering parameter used to calculate reward-to-risk ratios ($\ge 2.0$) and establish simulated take-profit orders. Markets are subject to macroeconomic shocks, earnings surprises, and systemic liquidity events. The stop-loss and time exits (20 sessions) limit downside and protect virtual capital when market dynamics fail to achieve the target.

---

## 8. Simulated Paper Brokerage

The paper broker runs in SQLite and validates:
- Market session hours and official exchange holidays.
- Idempotency keys (`ord_{account}_{symbol}_{hash}`) to prevent double executions upon restarts.
- Conservative opening fills with 0.10% modeled slippage.
- Intrabar conflict resolution: if both target and stop price are touched within the same daily high-low range, the broker assumes the stop-loss was triggered first.

---

## 9. Fee and Slippage Model

Verified Indian cash delivery equity statutory schedule (as of October 2024):
- **Brokerage**: ₹0 (discount broker delivery model).
- **STT**: 0.10% on BUY and 0.10% on SELL.
- **Exchange Charges**: 0.00297% (NSE).
- **SEBI Charges**: 0.0001% (₹10 per crore).
- **Stamp Duty**: 0.015% on BUY.
- **GST**: 18% on (Brokerage + Exchange + SEBI charges).
- **DP Charges**: ₹15.93 flat per SELL trade.
- **Slippage**: 0.10% on simulated fills.

---

## 10. Backtesting vs. Forward Paper Trading

- **Backtesting**: Operates on verified historical daily bars. Orders generated on session $T$ are simulated at session $T+1$ Open.
- **Forward Paper Trading**: Free EOD data providers do not supply a real-time opening tick during the trading day. Forward orders are executed using available delayed market snapshots with full transparency disclosures.

---

## 11. Free-Data Limitations

- **TejHQ**: End-of-Day candles are published after 18:30 IST. Adjusted prices require an optional free API key; unadjusted data is available keyless.
- **Yahoo Finance**: Subject to rate limits and delayed intraday quotes.
- **Survivorship Bias**: Universe is based on current liquid NSE constituents; historical backtests over 5 years reflect survivorship bias.

---

## 12. Interpreting Performance Metrics

- **Win Rate**: Percentage of trades with net P&L $> 0$.
- **Target Hit Rate**: Percentage of trades reaching $+10\%$ gross target.
- **Profit Factor**: Gross profits divided by gross losses. Values $> 1.5$ indicate positive expectancy after costs.
- **Sharpe Ratio**: Annualized excess return over 6.5% risk-free rate divided by return standard deviation.
- **Max Drawdown**: Peak-to-trough decline in portfolio equity.

---

## 13. How to Run on Windows 11

```powershell
# 1. Run automated setup
.\setup.ps1

# 2. Run diagnostics
.\.venv\Scripts\python.exe -m indigo_quant.cli doctor

# 3. Launch dashboard
.\run.ps1 -Mode dashboard
```

---

## 14. Raspberry Pi 4 Deployment

```bash
chmod +x setup_pi.sh
./setup_pi.sh
sudo systemctl enable --now indigo-quant
```
Access dashboard at `http://<pi-ip-address>:8501`.

---

## 15. Keeping the Platform Running After Reboot

The systemd service (`/etc/systemd/system/indigo-quant.service`) is configured with:
- `Restart=always`
- `RestartSec=10`
- `WantedBy=multi-user.target`
This guarantees automatic recovery after power interruptions or system restarts.

---

## 16. Diagnosing Stale Data and Failed Jobs

Check the system logs in SQLite:
```powershell
.\.venv\Scripts\python.exe -m indigo_quant.cli doctor
```
Or view the "System Health" page on the Streamlit dashboard to inspect the recent runs in `scheduler_job_logs`.

---

## 17. How to Add Another Strategy

1. Inherit from `BaseStrategy` in `src/indigo_quant/strategies/`.
2. Implement the `evaluate(symbol, df, idx)` method returning `StrategyEvaluationResult`.
3. Register the new strategy in `config/strategies.yaml` and `src/indigo_quant/engine/decision.py`.
4. Add unit tests in `tests/unit/test_strategies.py`.

---

## 18. How to Reset a Paper Portfolio Safely

To reinitialize all virtual portfolios back to ₹1,00,000 cash:
```powershell
.\.venv\Scripts\python.exe -c "from indigo_quant.db.session import SessionLocal; from indigo_quant.db.models import PaperPosition, PaperOrder, CashLedger, StrategyAccount; db = SessionLocal(); db.query(PaperPosition).delete(); db.query(PaperOrder).delete(); db.query(CashLedger).delete(); [setattr(a, 'current_cash', 100000.0) or setattr(a, 'current_equity', 100000.0) for a in db.query(StrategyAccount).all()]; db.commit(); db.close()"
```

---

## 19. Exporting Trading History

All trade journals and fills can be queried through the REST API (`/paper/trades`) or exported directly from the database using Python:
```python
import pandas as pd
from indigo_quant.db.session import SessionLocal
from indigo_quant.db.models import PaperPosition

db = SessionLocal()
trades = pd.read_sql(db.query(PaperPosition).filter(PaperPosition.status == 'CLOSED').statement, db.bind)
trades.to_csv("data/exports/closed_trades.csv", index=False)
db.close()
```

---

## 20. Known Limitations & Future Roadmap

- **Intraday Tick Streaming**: Future iterations may support real-time WebSocket tick feeds from discount broker market-data adapters.
- **Options & Derivatives**: The platform strictly trades delivery cash equities; derivative hedging is not in scope.
- **Point-in-Time Index Constituents**: Future research will incorporate historical survivorship-free index membership datasets.
