# Angel One Trading Bot

## Setup
1. Install dependencies: `pip install -r requirements.txt`
2. Configure credentials in Settings
3. Run: `python main.py`

## Features
- Real-time portfolio tracking
- Paper trading simulation
- Technical analysis with Golden Ratio strategy
- Pre-market scanner
# You can copy the README content from the artifact above and save it
# Or create it directly in your editor

# Verify it's saved
dir README.md# Angel One Trading Bot

A professional automated trading system for Angel One broker with advanced technical analysis, portfolio management, and paper trading capabilities.

## 🚀 Features

### Core Functionality
- **Live Market Data Integration** - Real-time price feeds from Angel One API
- **Portfolio Management** - Track holdings, positions, and P&L
- **Paper Trading Mode** - Test strategies without real money
- **Technical Analysis** - Built-in indicators (RSI, MACD, Bollinger Bands, etc.)
- **Order Management** - Automated order placement and tracking
- **Professional UI** - PyQt5-based interface with real-time updates

### Advanced Features
- **Contract-based Architecture** - Pluggable data provider system
- **Enhanced Market Analysis** - Multi-timeframe analysis
- **Risk Management** - Position sizing and stop-loss automation
- **Trade Logging** - Comprehensive trade history and analytics
- **Credential Management** - Secure storage of API credentials

## 📋 Prerequisites

- **Python**: 3.8 or higher
- **Operating System**: Windows 10/11 (Linux/Mac compatible with minor adjustments)
- **Angel One Account**: Active trading account with API access
- **API Credentials**: API Key, Client ID, Password, TOTP Secret

## 🔧 Installation

### Step 1: Clone Repository
```bash
git clone <repository-url>
cd tradingbot_new
```

### Step 2: Create Virtual Environment
```bash
# Create virtual environment
python -m venv angelbot

# Activate environment
# Windows:
angelbot\Scripts\activate
# Linux/Mac:
source angelbot/bin/activate
```

### Step 3: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 4: Configure Credentials
1. Run the bot for first-time setup:
   ```bash
   python main.py
   ```
2. Enter credentials in Settings tab:
   - API Key
   - Client ID
   - Password
   - TOTP Secret
3. Credentials are securely saved in `config/` directory

## 🎯 Usage

### Starting the Bot

**Method 1: Command Line**
```bash
# Activate virtual environment first
angelbot\Scripts\activate

# Run main program
python main.py
```

**Method 2: Batch File**
```bash
# Double-click or run:
run_bot.bat
```

### Initial Setup Workflow

1. **Launch Application** → `python main.py`
2. **Configure Settings** → Enter API credentials
3. **Download Tokens** → Click "Download Tokens" to fetch instrument list
4. **Verify Connection** → Check Portfolio tab for live data
5. **Start Trading** → Switch to Paper Trading mode for testing

### Main Interface Tabs

#### 1. Dashboard
- Market overview and key metrics
- Active positions summary
- Quick access controls

#### 2. Portfolio
- Live holdings display
- Real-time P&L tracking
- Position details and average prices

#### 3. Analysis
- Technical indicators and charts
- Market scanner results
- Signal generation

#### 4. Orders
- View and manage active orders
- Order history and execution log
- Manual order placement

#### 5. Settings
- API credential configuration
- Trading parameters setup
- System preferences

## 📁 Project Structure

```
tradingbot_new/
│
├── main.py                      # Main entry point
├── requirements.txt             # Python dependencies
├── README.md                    # This file
│
├── analyzer/                    # Market analysis module
│   ├── __init__.py
│   └── enhanced_analyzer.py    # Technical analysis engine
│
├── config/                      # Configuration files
│   ├── __init__.py
│   ├── credentials_manager.py  # Secure credential storage
│   └── credentials_path.txt    # Credential file location
│
├── contracts/                   # Interface definitions
│   ├── __init__.py
│   └── data_provider_v1.py     # Data provider contract
│
├── data/                        # Data files
│   ├── angel_tokens_map.json   # Token/symbol mappings
│   ├── OpenAPIScripMaster.json # Complete instrument list
│   └── watchlist.json          # User watchlist
│
├── data_provider/              # Data source implementations
│   ├── __init__.py
│   └── angel_provider.py       # Angel One API integration
│
├── indicators/                 # Technical indicators
│   ├── __init__.py
│   └── ta.py                   # Technical analysis library
│
├── order_manager/              # Order execution
│   ├── __init__.py
│   └── paper_trader.py         # Paper trading engine
│
├── ui/                         # User interface
│   ├── __init__.py
│   └── professional_trading_ui.py  # Main UI implementation
│
└── logs/                       # Application logs
    ├── YYYY-MM-DD/            # Daily log folders
    └── trades/                # Trade-specific logs
```

## 🔐 Security

### Credential Storage
- Credentials encrypted and stored locally in `config/` directory
- Never commit credentials to Git
- Use environment variables for additional security (optional)

### API Safety
- Rate limiting implemented to prevent API throttling
- Automatic reconnection on connection loss
- Error handling for all API calls

## 📊 Trading Modes

### Paper Trading (Recommended for Testing)
- Simulated trading with virtual capital
- No real money at risk
- Full feature testing environment
- Performance tracking and analytics

### Live Trading (Use with Caution)
- Real order placement to exchange
- Actual capital at risk
- Requires careful configuration
- Always start with small position sizes

## 🛠️ Configuration

### Key Parameters (in Settings Tab)

```python
# Risk Management
MAX_POSITIONS = 5              # Maximum concurrent positions
RISK_PER_TRADE = 0.015        # 1.5% risk per trade
REWARD_RATIO = 2.0            # Risk:Reward ratio

# Capital Allocation
BASE_CAPITAL = 50000          # Starting capital (paper trading)
POSITION_SIZE_METHOD = "percentage"  # or "fixed"

# Trading Hours
MARKET_START = "09:15"
MARKET_END = "15:30"
PREMARKET_ANALYSIS = "08:30"
```

## 📈 Strategy Development

### Adding Custom Strategies

1. Create strategy file in `analyzer/` directory
2. Implement signal generation logic
3. Import in `main.py`
4. Configure in Settings tab

### Example Strategy Template
```python
def custom_strategy(df, params):
    """
    Custom trading strategy
    
    Args:
        df: OHLCV dataframe
        params: Strategy parameters
    
    Returns:
        signal: BUY/SELL/HOLD
    """
    # Your strategy logic here
    signal = "HOLD"
    return signal
```

## 🐛 Troubleshooting

### Common Issues

**1. Import Errors**
```bash
# Solution: Reinstall dependencies
pip install -r requirements.txt --force-reinstall
```

**2. API Connection Failed**
- Verify credentials in Settings tab
- Check internet connection
- Ensure Angel One API is active
- Verify TOTP secret is correct

**3. Token Download Issues**
- Run `download_tokens.py` separately
- Check data folder permissions
- Verify API rate limits not exceeded

**4. UI Not Loading**
```bash
# Check PyQt5 installation
pip install PyQt5 --upgrade
```

### Debug Mode
```bash
# Run with verbose logging
python main.py --debug
```

## 📝 Version History

### v1.0.3-decluttered (Current)
- Cleaned project structure
- Improved documentation
- Enhanced error handling

### v1.0.2-portfolio-complete
- Portfolio management features
- Real-time data updates
- P&L tracking

### v1.0.0-baseline
- Initial release
- Basic trading functionality
- Paper trading mode

## 🤝 Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to branch (`git push origin feature/AmazingFeature`)
5. Open Pull Request

## ⚠️ Disclaimer

**IMPORTANT**: This software is for educational and research purposes only.

- Trading involves substantial risk of loss
- Past performance does not guarantee future results
- Test thoroughly in paper trading mode before live trading
- Only trade with capital you can afford to lose
- Consult a financial advisor before making investment decisions
- The developers are not responsible for any financial losses

## 📞 Support

### Getting Help
- Check documentation in `/docs` folder (if available)
- Review logs in `/logs` directory
- Open issue on GitHub with error details

### Useful Resources
- [Angel One API Documentation](https://smartapi.angelbroking.com/)
- [PyQt5 Documentation](https://www.riverbankcomputing.com/static/Docs/PyQt5/)
- [TA-Lib Technical Analysis](https://mrjbq7.github.io/ta-lib/)

## 📄 License

This project is licensed under the MIT License - see LICENSE file for details.

## 🙏 Acknowledgments

- Angel One for providing API access
- PyQt5 team for excellent UI framework
- Technical analysis community for indicators
- Open source contributors

---

**Happy Trading! 📈**

*Remember: Always test in paper trading mode first!*