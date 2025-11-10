# Enhanced Backtesting System v3.0

Comprehensive backtesting engine that validates your trading strategies using historical data before risking real capital.

## Features

✅ **Complete Integration** with EnhancedAnalyzer (FinBERT, Screener.in, Candlestick Patterns)
✅ **Multiple Position Sizing Methods** (Fixed ₹, Risk %, etc.)
✅ **Comprehensive Metrics** (Sharpe, Sortino, Win Rate, Profit Factor, Max Drawdown)
✅ **Trade-Level Analysis** (Entry/Exit reasons, hold times, P&L distribution)
✅ **Excel & JSON Reports** with detailed breakdown
✅ **Strategy Rating System** (EXCELLENT, GOOD, FAIR, WEAK, POOR)
✅ **Flexible Configuration** (Test any date range, symbols, intervals)

## Quick Start

### 1. Run Backtest

```bash
python run_backtest.py
```

### 2. Customize Configuration

Edit `run_backtest.py`:

```python
BACKTEST_CONFIG = {
    'initial_capital': 100000,        # Starting ₹
    'position_size_method': 'fixed_rupees',
    'position_size_value': 100000,    # ₹100,000 per trade
    'enable_fundamentals': False,     # True = Screener.in (slower but accurate)
    'start_date': '2024-01-01',
    'end_date': '2024-11-01',
    'interval': '1d',                 # '1d' or '1h'
    'symbols': ['RELIANCE', 'TCS', 'INFY', ...]
}
```

### 3. View Results

Results are saved in `backtesting/results/`:
- `backtest_YYYYMMDD_HHMMSS.json` - Full report
- `trades_YYYYMMDD_HHMMSS.xlsx` - All trades in Excel

## Position Sizing Methods

### 1. Fixed Rupees (Default)
```python
'position_size_method': 'fixed_rupees',
'position_size_value': 100000  # ₹100,000 per trade
```
**Use when:** You want consistent position sizes

### 2. Risk Percentage
```python
'position_size_method': 'risk_pct',
'position_size_value': 2.0  # Risk 2% of capital per trade
```
**Use when:** You want position size to scale with capital (better for compounding)

## Performance Metrics Explained

### Win Rate
```
Win Rate = (Winning Trades / Total Trades) × 100
```
- **Excellent:** >60%
- **Good:** 50-60%
- **Fair:** 45-50%
- **Weak:** <45%

### Profit Factor
```
Profit Factor = Total Profit / Total Loss
```
- **Excellent:** >2.0 (make ₹2 for every ₹1 lost)
- **Good:** 1.5-2.0
- **Fair:** 1.2-1.5
- **Weak:** <1.2 (barely profitable)
- **Losing:** <1.0 (losing strategy)

### Sharpe Ratio
```
Sharpe = (Average Return - Risk Free Rate) / Std Dev of Returns
```
Measures risk-adjusted returns:
- **Excellent:** >2.0 (great risk-adjusted returns)
- **Good:** 1.5-2.0
- **Fair:** 1.0-1.5
- **Weak:** 0.5-1.0
- **Poor:** <0.5

### Max Drawdown
Maximum peak-to-trough decline during backtest period.
- **Excellent:** <10%
- **Good:** 10-20%
- **Fair:** 20-30%
- **Risky:** >30%

### Expectancy
```
Expectancy = (Win Rate × Avg Win) - (Loss Rate × Avg Loss)
```
Average ₹ expected per trade:
- **Positive:** Strategy has edge
- **Negative:** Strategy loses money

## Strategy Rating

Based on combined metrics (Win Rate, Profit Factor, Sharpe, Total Return):

| Grade | Score | Recommendation |
|-------|-------|----------------|
| 🌟 EXCELLENT | 85-100 | ✅ GO LIVE with proper risk management |
| ✅ GOOD | 70-84 | ⚠️ GO LIVE with conservative sizing |
| ⚠️ FAIR | 50-69 | 🔧 Optimize before going live |
| ❌ WEAK | 30-49 | 🛑 NOT recommended for live trading |
| 🚫 POOR | <30 | 🚫 Complete overhaul needed |

## Interpreting Results

### Example: Good Strategy
```
Win Rate: 55%
Profit Factor: 1.8
Sharpe Ratio: 1.5
Total Return: +18%
Max Drawdown: -12%
Grade: GOOD ✅
```
**Interpretation:** Solid strategy with good risk-adjusted returns. Can go live with proper risk management.

### Example: Weak Strategy
```
Win Rate: 42%
Profit Factor: 1.1
Sharpe Ratio: 0.3
Total Return: +3%
Max Drawdown: -25%
Grade: WEAK ❌
```
**Interpretation:** Poor win rate, barely profitable, high risk. Needs major improvements before live trading.

## Advanced Usage

### Test Different Timeframes

#### Daily Bars (Default)
```python
'interval': '1d'
```
Best for: Swing trading, multi-day holds

#### Hourly Bars
```python
'interval': '1h'
```
Best for: Intraday trading, faster signals

### Test Specific Periods

#### Last 6 Months
```python
from datetime import datetime, timedelta
BACKTEST_CONFIG.update({
    'start_date': (datetime.now() - timedelta(days=180)).strftime('%Y-%m-%d'),
    'end_date': datetime.now().strftime('%Y-%m-%d'),
})
```

#### Bull Market Only (Example: 2024)
```python
'start_date': '2024-01-01',
'end_date': '2024-12-31',
```

#### Bear Market Test (Example: 2020 COVID crash)
```python
'start_date': '2020-02-01',
'end_date': '2020-05-01',
```

### Test With/Without Fundamentals

#### Without Fundamentals (Faster)
```python
'enable_fundamentals': False
```
✅ Faster backtesting
✅ Uses technical indicators only
⚠️ Less accurate fundamental scoring

#### With Fundamentals (More Accurate)
```python
'enable_fundamentals': True
```
✅ Uses Screener.in for accurate data
✅ Better quality signals
⚠️ Slower (web scraping + caching)

## Troubleshooting

### "No data for symbol"
- Check symbol spelling (use NSE symbols: 'RELIANCE', not 'RELIANCE.NS')
- Try different date range (symbol may not have traded during that period)

### "yfinance not installed"
```bash
pip install yfinance
```

### Backtest too slow
- Reduce number of symbols
- Disable fundamentals: `'enable_fundamentals': False`
- Test shorter date range

### Poor Results
1. **Check signal frequency:** If too few trades (<20), increase symbols or date range
2. **Review individual trades:** Check Excel file for patterns
3. **Test different periods:** Bull vs Bear markets
4. **Optimize parameters:** Adjust analyzer weights in `analyzer_config.json`

## Next Steps

After running backtest:

### If Strategy is EXCELLENT/GOOD:
1. ✅ Review trade-by-trade results in Excel
2. ✅ Test on different market conditions (bull/bear/sideways)
3. ✅ Start paper trading with same parameters
4. ✅ Monitor live performance for 2-4 weeks
5. ✅ Go live with conservative position sizing

### If Strategy is FAIR:
1. 🔧 Optimize analyzer weights in `analyzer_config.json`
2. 🔧 Test different position sizing methods
3. 🔧 Enable fundamentals if disabled
4. 🔧 Review and improve entry/exit criteria
5. 🔧 Re-run backtest with changes

### If Strategy is WEAK/POOR:
1. 🛑 DO NOT go live
2. 🔧 Review individual losing trades for patterns
3. 🔧 Consider filtering signals (higher confidence threshold)
4. 🔧 Test on more symbols and longer periods
5. 🔧 May need strategy redesign

## Files Generated

```
backtesting/results/
├── backtest_20241110_143025.json    # Full report (all data)
├── trades_20241110_143025.xlsx      # Trade-by-trade Excel
└── ...
```

### JSON Report Structure
```json
{
  "summary": {
    "total_trades": 45,
    "win_rate": 55.5,
    "profit_factor": 1.8,
    ...
  },
  "trades": [
    {
      "symbol": "RELIANCE",
      "entry_date": "2024-01-15",
      "exit_date": "2024-01-22",
      "pnl": 5432.50,
      ...
    }
  ],
  "equity_curve": [...],
  "trade_analysis": {...}
}
```

## Tips for Better Results

1. **Test Multiple Symbols:** More trades = more reliable metrics
2. **Test Long Periods:** 6-12 months minimum for statistical significance
3. **Test Different Market Conditions:** Bull, bear, and sideways markets
4. **Review Individual Trades:** Look for patterns in winners/losers
5. **Optimize Gradually:** Small adjustments, re-test each time
6. **Compare Configurations:** Test conservative vs aggressive
7. **Focus on Risk-Adjusted Returns:** Sharpe ratio > total return

## Configuration Presets

### Conservative (Lower Risk)
```python
BACKTEST_CONFIG.update({
    'position_size_method': 'risk_pct',
    'position_size_value': 1.0,  # Risk 1% per trade
    'enable_fundamentals': True,
})
```

### Aggressive (Higher Risk)
```python
BACKTEST_CONFIG.update({
    'position_size_method': 'fixed_rupees',
    'position_size_value': 200000,  # ₹200,000 per trade
    'enable_fundamentals': False,
})
```

### Intraday Trading
```python
BACKTEST_CONFIG.update({
    'interval': '1h',
    'start_date': (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'),
})
```

---

**Remember:** Past performance does not guarantee future results. Always use proper risk management when going live!
