# Angel One Trading Bot

A professional automated trading system for Angel One broker with advanced technical analysis, portfolio management, and paper trading capabilities.

## 🚀 Features

### Core Functionality
- **Live Market Data Integration** - Real-time price feeds from Angel One API via WebSockets.
- **Modular UI** - A responsive, tab-based UI built with PyQt5.
- **Paper Trading Mode** - Test strategies without real money with a dedicated paper trading manager.
- **Advanced Stock Analysis** - A powerful analyzer that combines technical indicators, sentiment analysis, and fundamentals to generate trading signals.
- **Configuration Management** - Easy-to-use settings tab to manage API keys and trading parameters.
- **Trade Logging** - Comprehensive trade history automatically saved to `trades_log.xlsx`.

## 📋 Prerequisites

- **Python**: 3.8 or higher
- **Operating System**: Windows, Linux, or macOS.
- **Angel One Account**: Active trading account with API access.
- **API Credentials**: API Key, Client ID, Password, and TOTP Secret.
- **News API Key (Optional)**: For sentiment analysis. You can get one from [newsapi.org](https://newsapi.org).

## 🔧 Installation

### Step 1: Clone Repository
```bash
git clone <repository-url>
cd tradingbot_new
```

### Step 2: Create Virtual Environment
```bash
# Create virtual environment
python -m venv venv

# Activate environment
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate
```

### Step 3: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 4: Configure Credentials
1.  Rename `.env.example` to `.env` and fill in your Angel One credentials. This is the most secure method.
2.  Alternatively, you can launch the bot and enter your credentials in the "Settings" tab.

## 🎯 Usage

### Starting the Bot
```bash
# Activate your virtual environment first
# Run the main application
python test_new_ui.py
```

### Workflow
1.  **Launch the application**.
2.  If you haven't configured your credentials in a `.env` file, go to the **"Settings"** tab and enter your API Key, Client ID, Password, and TOTP secret.
3.  Go to the **"Dashboard"** tab and click the **"Connect"** button. The bot will connect to the broker and start the WebSocket for live data.
4.  Use the **"Analyzer"** tab to scan for trading signals.
5.  Execute trades from the Analyzer, which will be sent to the **"Paper Trading"** tab for monitoring.

### Main Interface Tabs
- **📊 Dashboard**: Overview of connection status, capital, and overall performance.
- **💼 Holdings**: Displays your stock holdings from your broker account.
- **👁️ Watchlist**: Add and monitor stocks with live price updates.
- **🟢 Live Positions**: Shows your active positions from the broker.
- **📜 History**: A log of all your past trades.
- **🔍 Analyzer**: The core of the bot, where you can scan for trading signals based on the configured strategy.
- **📊 Paper Trading**: Manage and monitor your paper trades. Trades executed from the Analyzer appear here.
- **🌅 Pre-Market**: Tools for pre-market analysis.
- **⚙️ Settings**: Configure all your API credentials and trading parameters.

## 📁 Project Structure
```
tradingbot_new/
│
├── test_new_ui.py               # Main entry point for the application
├── requirements.txt             # Python dependencies
├── README.md                    # This file
│
├── analyzer/                    # Market analysis module
│   ├── enhanced_analyzer.py     # The core analysis engine
│   └── fundamentals_analyzer.py # Fundamentals analysis
│
├── config/                      # Configuration and credential management
│   └── credentials_manager.py   # Manages loading of credentials
│
├── core/                        # Core components like capital tracking
│   └── websocket/
│       └── price_provider.py    # WebSocket price provider
│
├── data_provider/               # Data source implementations
│   └── angel_provider.py        # Angel One API integration
│
├── indicators/                  # Technical indicators library
│   └── ta.py
│
├── order_manager/               # Order execution logic
│   └── paper_trader.py          # Paper trading engine
│
└── ui_new/                      # The new PyQt5 user interface
    ├── main_window.py           # The main application window
    ├── connection_manager.py    # Manages API and WebSocket connections
    └── tabs/                    # Each tab in the UI is a separate module
        ├── dashboard_tab.py
        ├── analyzer_tab.py
        └── paper_trading_tab.py
        ...
```

## 🔐 Security

- **Credential Management**: Credentials can be stored in a `.env` file for security. The `config.json` file is also used, but `.env` is recommended.
- **API Safety**: The application includes rate limiting and automatic reconnection logic.

## ⚠️ Disclaimer

**IMPORTANT**: This software is for educational and research purposes only. Trading involves substantial risk. The developers are not responsible for any financial losses. Always test thoroughly in paper trading mode before considering live trading.
