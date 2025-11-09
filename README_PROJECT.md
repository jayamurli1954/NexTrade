# 📈 NexTrade - Advanced Algorithmic Trading Dashboard

> An intelligent, real-time trading dashboard with live market analysis, paper trading capabilities, and technical signal generation for the Indian stock market (NSE/BSE).

[![Python Version](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Status](https://img.shields.io/badge/status-Active%20Development-orange.svg)](https://github.com/yourusername/nextrade)
[![Code Quality](https://img.shields.io/badge/code%20quality-Production%20Ready-brightgreen.svg)](#)

---

## 🚀 Overview

**NexTrade** is a sophisticated desktop trading application designed for Indian equity market traders. It provides real-time market data streaming, technical analysis with multiple indicators, paper trading simulation, and professional portfolio management—all with a responsive, intuitive user interface.

Built for traders who want intelligent market insights without sacrificing control or reliability. NexTrade bridges the gap between professional trading platforms and DIY solutions.

### 🎯 Key Philosophy
- **No Fake Signals**: Only real technical analysis, never hash-based or arbitrary signals
- **Paper Trading First**: Validate strategies for 2-3 months before live trading
- **Conservative Approach**: Risk management baked into every trade
- **Extensible Design**: Modular architecture for easy customization

---

## ✨ Features

### 📊 Real-Time Dashboard
- **Live Market Indices**: Nifty 50, Bank Nifty, Sensex with real-time price updates (15-second refresh)
- **Portfolio Overview**: Current capital, P&L, win rate, and trade statistics
- **System Status**: Connection status, monitoring statistics, WebSocket connection indicators
- **Professional UI**: Color-coded cards, intuitive layout, responsive design

### 📁 Holdings Management
- **Broker Integration**: Real holdings fetched from Angel One API
- **Position Analytics**: Current P&L for each holding
- **Margin & Funds**: Available funds and margin display
- **Real Data**: Live portfolio value tracking

### 👁️ Watchlist Monitoring
- **93 NSE Stocks**: Curated list of major Indian stocks
- **Live Price Updates**: WebSocket streaming (no delays)
- **Volume Tracking**: Real-time volume indicators
- **Color-Coded**: Green for gains, red for losses
- **Performance Metrics**: % change and volume for each stock

### 🔍 Advanced Analysis
- **Technical Indicators**:
  - RSI (Relative Strength Index) - 14 period
  - EMA (Exponential Moving Average) - 12, 26 period
  - SMA (Simple Moving Average) - 50, 200 period
  - Bollinger Bands - 20 period with 2 standard deviations
  - Fibonacci Retracement Levels
  - Volume Analysis
  - Momentum Analysis

- **Real-Time Analysis**: Scan all 93 stocks in <30 seconds
- **Signal Generation**: BUY/SELL signals based on confirmed technical patterns
- **Confidence Scoring**: Each signal includes a confidence percentage
- **Historical Data**: Support for multiple timeframes (1min, 5min, 15min, 1hour, 1day)

### 📈 Paper Trading
- **Virtual Execution**: Execute trades with virtual capital (default: ₹100,000)
- **Realistic Slippage**: Accurate price simulation
- **Trade Logging**: Automatic Excel logging (`trades_log.xlsx`)
- **Performance Tracking**: Win rate, P&L, and statistics
- **Risk Management**: 2% stop-loss risk per trade maximum

### 💾 Historical Analysis
- **Trade History**: Complete record of all paper trades
- **Performance Metrics**: Win rate, profit/loss, average trade duration
- **Date Filtering**: View trades by date range
- **Export Ready**: Data in Excel format for further analysis

### ⚙️ System Configuration
- **API Settings**: Angel One Smart API credentials
- **Watch list Management**: Add/remove stocks from monitoring
- **Paper Trading Capital**: Adjust virtual capital
- **Technical Indicators**: Customize parameters
- **Update Intervals**: Configure refresh rates

### 🖥️ UI/UX Features
- **8 Modular Tabs**: Dashboard, Holdings, Watchlist, Analyzer, Positions, Paper Trading, History, Settings
- **Responsive Design**: Works on different screen resolutions
- **Professional Styling**: Qt-based modern UI
- **Real-Time Updates**: No blocking operations
- **Error Handling**: Graceful error messages and recovery

---

## 🏗️ Architecture

### Project Structure
```
nextrade/
├── test_new_ui.py                   # 🚀 Main application launcher
├── config.json                      # API credentials & settings
├── watchlist.json                   # Stock watchlist (93 stocks)
├── trades_log.xlsx                  # Paper trading history
│
├── ui_new/                          # Modular UI Components
│   ├── connection_manager.py        # Angel One API & WebSocket handler
│   ├── main_window.py               # Main UI container
│   ├── data_handler.py              # Data processing utilities
│   └── tabs/                        # Individual tab modules
│       ├── dashboard_tab.py         # Portfolio overview & indices
│       ├── holdings_tab.py          # Broker holdings display
│       ├── watchlist_tab.py         # Live price monitoring
│       ├── analyzer_tab.py          # Technical analysis engine
│       ├── positions_tab.py         # Active positions
│       ├── paper_trading_tab.py     # Virtual trading execution
│       ├── history_tab.py           # Trade history viewer
│       ├── premarket_tab.py         # Pre-market analysis
│       └── settings_tab.py          # Configuration
│
├── analyzer/                        # Technical Analysis
│   ├── enhanced_analyzer.py         # Real technical analysis engine
│   └── fundamentals_analyzer.py     # Fundamental analysis (future)
│
├── indicators/                      # Technical Indicators
│   └── ta.py                        # RSI, EMA, SMA, BB, Fibonacci
│
├── data_provider/                   # Data Sources
│   └── angel_provider.py            # Angel One data interface
│
├── order_manager/                   # Trading Logic
│   └── paper_trader.py              # Virtual trading engine
│
├── docs/                            # Documentation
│   ├── SETUP.md                     # Installation guide
│   ├── API_REFERENCE.md             # API documentation
│   └── CONTRIBUTING.md              # Contribution guidelines
│
└── README.md                        # This file
```

### Technology Stack
- **Frontend**: PyQt5 (Desktop GUI)
- **Backend**: Python 3.10
- **API**: Angel One Smart API (REST + WebSocket)
- **Data Storage**: JSON, Excel
- **Threading**: Python threading for background operations
- **Data Analysis**: Pandas, NumPy
- **Version Control**: Git

### System Architecture
```
┌─────────────────────────────────────────────┐
│         Angel One Smart API                  │
│  (REST for Historical + WebSocket for Live) │
└────────────────┬────────────────────────────┘
                 │
      ┌──────────┴──────────┐
      │                     │
      ▼                     ▼
┌──────────────┐   ┌──────────────────┐
│ Connection   │   │ WebSocket V2     │
│ Manager      │   │ Streaming        │
└──────────────┘   └──────────────────┘
      │                     │
      └──────────┬──────────┘
                 │
                 ▼
         ┌──────────────────┐
         │ Data Handler     │
         │ & Processors     │
         └──────────────────┘
                 │
      ┌──────────┼──────────┐
      │          │          │
      ▼          ▼          ▼
┌──────────┐ ┌───────┐ ┌─────────┐
│Analyzer  │ │Chart  │ │ History │
│ Engine   │ │ Data  │ │ Logger  │
└──────────┘ └───────┘ └─────────┘
      │
      ▼
┌──────────────────────┐
│ Paper Trading Engine │
└──────────────────────┘
      │
      ▼
┌──────────────────┐
│ Qt5 UI / Tabs    │
│ (Dashboard, etc) │
└──────────────────┘
```

---

## 🛠️ Installation

### Prerequisites
- **Python 3.10+** (recommended: 3.10 or 3.11)
- **Angel One Trading Account** (Smart API enabled)
- **Windows/macOS/Linux**
- **Git** (for version control)

### Step 1: Clone Repository
```bash
git clone https://github.com/yourusername/nextrade.git
cd nextrade
```

### Step 2: Create Conda Environment
```bash
# Create environment
conda create -n nextrade python=3.10

# Activate environment
conda activate nextrade
```

### Step 3: Install Dependencies
```bash
pip install -r requirements.txt
```

Required packages:
- PyQt5 (GUI)
- pyotp (TOTP 2FA)
- pandas (Data analysis)
- numpy (Numerical operations)
- requests (HTTP)
- websocket-client (WebSocket)
- openpyxl (Excel)
- yfinance (Financial data)

### Step 4: Configure API Credentials

Create `config.json` in the project root:

```json
{
  "angel_one": {
    "client_id": "your_client_id",
    "password": "your_password",
    "api_key": "your_api_key",
    "totp_secret": "your_totp_secret"
  },
  "paper_trading": {
    "initial_capital": 100000,
    "risk_per_trade": 0.02,
    "slippage": 0.001
  }
}
```

### Step 5: Launch Application
```bash
python test_new_ui.py
```

The application window should open immediately.

---

## 🎯 Quick Start

### First Run
1. **Launch**: `python test_new_ui.py`
2. **Check Connection**: Green "Broker: Connected" status
3. **View Holdings**: Click "Holdings" tab to see your broker holdings
4. **Watch Stocks**: Navigate to "Watchlist" to see real-time prices
5. **Analyze**: Go to "Analyzer" to scan for trading signals

### Paper Trading Workflow
1. Go to **Paper Trading** tab
2. Select a stock from dropdown
3. Set BUY/SELL, quantity, and price
4. Click **Execute Trade**
5. View in **History** tab (logged to `trades_log.xlsx`)

### Generate Trading Signals
1. Go to **Analyzer** tab
2. Click **Scan Now** button
3. Wait for analysis (~30 seconds for 93 stocks)
4. Review signals with confidence scores
5. Execute profitable trades in Paper Trading

---

## 📊 Dashboard Overview

### Real-Time Indices
- **Nifty 50**: Updates every 15 seconds
- **Bank Nifty**: Updates every 15 seconds
- **Sensex**: Updates every 15 seconds

Each card shows:
- Current price (₹)
- Price change from last update
- Last update timestamp

### Portfolio Metrics
- **Capital**: Available virtual capital
- **Profit/Loss**: Paper trading P&L
- **Trades**: Number of executed trades
- **Win Rate**: Percentage of winning trades

### System Status
- Connection status
- Stocks being monitored
- WebSocket connection status
- Last refresh time

---

## 🔧 Configuration

### Watchlist Management

Edit `watchlist.json`:
```json
{
  "stocks": [
    {"symbol": "RELIANCE", "exchange": "NSE"},
    {"symbol": "INFY", "exchange": "NSE"},
    {"symbol": "TCS", "exchange": "NSE"}
  ]
}
```

### Analyzer Settings

Customize in `analyzer/enhanced_analyzer.py`:
```python
RSI_PERIOD = 14              # RSI lookback period
RSI_OVERBOUGHT = 70          # Overbought threshold
RSI_OVERSOLD = 30            # Oversold threshold
EMA_FAST = 12                # Fast EMA period
EMA_SLOW = 26                # Slow EMA period
BB_PERIOD = 20               # Bollinger Band period
BB_STD_DEV = 2               # Standard deviations
```

### Paper Trading Settings

Edit `config.json`:
```json
{
  "paper_trading": {
    "initial_capital": 100000,
    "risk_per_trade": 0.02,
    "slippage": 0.001
  }
}
```

---

## 📈 Trading Strategy

### Signal Validation Rules
- **BUY Signal**: When price is oversold (RSI < 30) AND confirmatory indicators align
- **SELL Signal**: When price is overbought (RSI > 70) AND momentum confirms
- **Confidence Score**: 0-100% based on indicator alignment

### Risk Management
- **Maximum Risk per Trade**: 2% of capital
- **Position Sizing**: Calculated based on risk amount
- **Stop Loss**: ATR-based (adaptive to volatility)
- **Take Profit**: 3x Risk-Reward ratio

### Validation Logic
```
1. Generate technical signals
2. Calculate confidence score
3. Apply momentum validation
4. Check for trend alignment
5. Validate with fundamental scores
6. Execute if confidence > threshold
```

---

## 🧪 Testing

### Unit Tests
```bash
python -m pytest tests/
```

### Manual Testing Checklist
- [ ] Connection to Angel One API works
- [ ] WebSocket streaming starts
- [ ] Watchlist prices update
- [ ] Holdings display correctly
- [ ] Analyzer generates signals
- [ ] Paper trades execute
- [ ] History logs trades
- [ ] No UI freezing during operations

### Paper Trading Validation
Before live trading:
1. Paper trade for 2-3 months minimum
2. Achieve 55%+ win rate
3. Max drawdown < 15%
4. Consistent profitability

---

## 📝 API Reference

### Connection Manager
```python
from ui_new.connection_manager import ConnectionManager

conn_mgr = ConnectionManager()
conn_mgr.connect()

# Get LTP (Last Traded Price)
price = conn_mgr.get_ltp('RELIANCE', 'NSE')

# Get historical data
df = conn_mgr.get_historical('INFY', 'NSE', 'day', 100)

# Get holdings
holdings = conn_mgr.get_holdings()
```

### Analyzer
```python
from analyzer.enhanced_analyzer import EnhancedAnalyzer

analyzer = EnhancedAnalyzer(data_provider=conn_mgr)

# Analyze single stock
signal = analyzer.analyze_single_stock('TCS')

# Analyze watchlist
signals = analyzer.analyze_watchlist(['RELIANCE', 'INFY', 'TCS'])
```

### Paper Trader
```python
from order_manager.paper_trader import PaperTrader

trader = PaperTrader(initial_capital=100000)

# Execute trade
order_id = trader.execute_trade(
    symbol='RELIANCE',
    action='BUY',
    quantity=10,
    price=2500,
    stop_loss=2450,
    target=2600
)

# Get trades
trades = trader.get_all_trades()
```

---

## 🐛 Troubleshooting

### Connection Issues

**Problem**: "Connection Failed"
- **Solution**: Verify Angel One credentials in `config.json`
- Check API key validity
- Ensure TOTP secret is correct

**Problem**: "WebSocket Disconnected"
- **Solution**: Internet connection might be unstable
- Check firewall settings
- Restart the application

### Analyzer Issues

**Problem**: "No signals found"
- **Solution**: This is normal! Signals are selective by design
- Check console for analysis details
- Adjust confidence threshold in settings

**Problem**: "Analysis takes too long"
- **Solution**: Normal for first run (caches data)
- Subsequent scans should be faster
- Can be optimized by reducing watchlist size

### UI Issues

**Problem**: "UI Freezes during analysis"
- **Solution**: This has been fixed in v3.2.0
- If occurs, update to latest version
- Check no other heavy processes running

---

## 🚀 Roadmap

### v3.2.0 (Current - Stable)
- ✅ Real-time index data (Nifty 50, Bank Nifty, Sensex)
- ✅ Technical analysis engine
- ✅ Paper trading platform
- ✅ Holdings management
- ✅ Trade history logging

### v3.3.0 (Next Release)
- 🔄 UI threading optimization (fix analyzer freezing)
- 🔄 Signal generation tuning (reduce false positives)
- 🔄 Progress indicators during analysis

### v4.0.0 (Future)
- 🔬 Fundamental analysis integration
- 📊 Advanced charting with interactive graphs
- 💼 Portfolio backtesting engine
- 🔔 Price alerts and notifications
- 📱 Mobile app support
- 🤖 Machine learning signal validation
- 💰 Live trading mode (with caution!)

---

## 📚 Documentation

- **[SETUP.md](docs/SETUP.md)** - Detailed installation guide
- **[API_REFERENCE.md](docs/API_REFERENCE.md)** - Complete API documentation
- **[CONTRIBUTING.md](docs/CONTRIBUTING.md)** - Contribution guidelines
- **[PROJECT_SUMMARY.md](docs/PROJECT_SUMMARY.md)** - Technical overview

---

## 🤝 Contributing

Contributions are welcome! This is a learning project and improvements are encouraged.

### Steps to Contribute
1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Code Standards
- Follow PEP 8 style guide
- Add docstrings to all functions
- Include comments for complex logic
- Write tests for new features
- Update README for user-facing changes

---

## ⚠️ Disclaimer

**IMPORTANT**: This is a learning and research project.

- **Paper Trading Only**: Use paper trading mode exclusively for validation (2-3 months minimum)
- **No Live Trading**: Do NOT use for live trading without extensive testing
- **Validate Thoroughly**: Backtest strategies before considering real money
- **Risk Acknowledgment**: Trading carries inherent risk of loss
- **Do Your Research**: Never blindly follow bot signals
- **Test Period**: Complete 2-3 months of profitable paper trading before even considering live mode

The author and contributors are not responsible for any financial losses. Use at your own risk.

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

### MIT License Summary
- ✅ Commercial use allowed
- ✅ Modification allowed
- ✅ Distribution allowed
- ❌ Liability: Not included
- ❌ Warranty: None provided

---

## 👤 Author & Community

**Created by**: Your Name ([@yourtwitter](https://twitter.com/yourhandle))

**Inspired by**: 
- Technical Analysis principles
- Algorithmic Trading methodologies
- Open-source trading communities

### Community
- 💬 Issues & Discussions: [GitHub Issues](https://github.com/yourusername/nextrade/issues)
- 🤝 Contributions: Welcome!
- 📮 Contact: email@example.com

---

## 🙏 Acknowledgments

- **Angel One** - For providing a comprehensive trading API
- **PyQt5** - For the powerful GUI framework
- **Python Community** - For excellent libraries and support
- **Trading Community** - For insights and feedback

---

## 📞 Support

Need help? Check these resources:

1. **Documentation**: Read [docs/](docs/) folder
2. **Issues**: Search [GitHub Issues](https://github.com/yourusername/nextrade/issues)
3. **FAQ**: Common questions answered below

### Frequently Asked Questions

**Q: Can I use this for live trading?**
A: No, not without extensive validation. Paper trade for 2-3 months first and achieve 60%+ win rate.

**Q: How often are signals generated?**
A: Manual scan via "Scan Now" button (no automatic signals currently).

**Q: Can I modify the analyzer parameters?**
A: Yes! All parameters are in `analyzer/enhanced_analyzer.py` and `config.json`.

**Q: What's the minimum capital to start?**
A: Paper trading starts at ₹100,000 (virtual). For live trading (if ready): ₹50,000 minimum recommended.

**Q: How long until I'm ready for live trading?**
A: Minimum 2-3 months of profitable paper trading with 60%+ win rate.

---

## 🎓 Learning Resources

- [Technical Analysis Basics](https://www.investopedia.com/terms/t/technicalanalysis.asp)
- [RSI Indicator Guide](https://www.investopedia.com/terms/r/rsi.asp)
- [Algorithmic Trading](https://www.investopedia.com/terms/a/algorithmictrading.asp)
- [Angel One API Docs](https://angelone.in/api-documentation)

---

## 📊 Version History

| Version | Date | Status | Highlights |
|---------|------|--------|-----------|
| v3.2.0 | Oct 2025 | ✅ Stable | Real-time indices, enhanced analyzer |
| v3.1.0 | Sep 2025 | ✅ Stable | WebSocket integration, watchlist |
| v3.0.0 | Aug 2025 | ✅ Stable | Paper trading, modular UI |
| v2.0.0 | Jul 2025 | 🔶 Legacy | Holdings management added |
| v1.0.0 | Jun 2025 | 🔴 Old | Initial release |

---

## 🔐 Security

### Best Practices
- ✅ Store credentials in `config.json` (excluded from git)
- ✅ Add `config.json` to `.gitignore`
- ✅ Use environment variables for sensitive data (recommended)
- ✅ Never commit API keys
- ✅ Keep dependencies updated

### Recommended Setup
```bash
# Create .env file (excluded from git)
cp .env.example .env

# Edit .env with your credentials
ANGEL_CLIENT_ID=your_id
ANGEL_PASSWORD=your_password
ANGEL_API_KEY=your_key
ANGEL_TOTP_SECRET=your_secret
```

---

## 💰 Performance Metrics (Paper Trading)

Expected metrics after 2-3 months of consistent trading:

| Metric | Target | Explanation |
|--------|--------|-------------|
| Win Rate | 55-65% | % of winning trades |
| Avg Win | 3-5% | Average profit per trade |
| Avg Loss | 2-3% | Average loss per trade |
| Max Drawdown | <15% | Largest peak-to-trough decline |
| Profit Factor | 1.5+ | Total wins / Total losses |
| Sharpe Ratio | >1.0 | Risk-adjusted returns |

**Note**: These are realistic targets. Anything above these suggests strong validation for live trading consideration.

---

## 🎯 Next Steps

1. **Install**: Follow the [Installation](#-installation) section
2. **Configure**: Set up your Angel One API credentials
3. **Test**: Run the application and explore tabs
4. **Learn**: Read through the [Documentation](#-documentation)
5. **Trade**: Start with paper trading
6. **Validate**: Trade for 2-3 months
7. **Contribute**: Share improvements with the community!

---

## 📫 Newsletter & Updates

Want updates? Star ⭐ this repository to stay in the loop!

---

**Made with ❤️ by traders, for traders**

[![Star on GitHub](https://img.shields.io/github/stars/yourusername/nextrade?style=social)](https://github.com/yourusername/nextrade)
[![Fork on GitHub](https://img.shields.io/github/forks/yourusername/nextrade?style=social)](https://github.com/yourusername/nextrade)
[![Follow on Twitter](https://img.shields.io/twitter/follow/yourhandle?style=social)](https://twitter.com/yourhandle)

---

**Last Updated**: October 23, 2025  
**Current Version**: v3.2.0  
**Status**: Active Development 🚀
