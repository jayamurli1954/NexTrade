# 📚 NexTrade Setup & Installation Guide

Complete step-by-step guide to get NexTrade up and running on your system.

---

## Table of Contents
1. [System Requirements](#system-requirements)
2. [Installation Steps](#installation-steps)
3. [Angel One API Setup](#angel-one-api-setup)
4. [Verification](#verification)
5. [Troubleshooting](#troubleshooting)
6. [Development Setup](#development-setup)

---

## 🖥️ System Requirements

### Operating System
- ✅ Windows 10+ (Recommended)
- ✅ macOS 10.14+
- ✅ Linux (Ubuntu 18.04+, Fedora, etc.)

### Hardware
- **Processor**: Dual-core or better
- **RAM**: 4GB minimum (8GB recommended)
- **Disk**: 500MB free space
- **Internet**: Stable connection required

### Software
- **Python**: 3.10 or higher
- **Git**: For version control
- **Conda**: For environment management (recommended)

---

## 📦 Installation Steps

### Step 1: Clone Repository

```bash
# Open terminal/command prompt
# Navigate to desired location

# Clone repository
git clone https://github.com/yourusername/nextrade.git

# Navigate to project
cd nextrade

# Verify directory structure
ls -la  # On macOS/Linux
dir     # On Windows
```

Expected output:
```
nextrade/
├── README.md
├── requirements.txt
├── test_new_ui.py
├── config.json (will create)
├── ui_new/
├── analyzer/
├── indicators/
└── ... (other folders)
```

### Step 2: Install Python (if needed)

#### Option A: Using Conda (Recommended)

```bash
# Download Anaconda from https://www.anaconda.com/
# Install Anaconda (follow installer instructions)

# Verify installation
conda --version

# Should show: conda X.XX.X
```

#### Option B: Using Official Python

```bash
# Download Python 3.10+ from https://www.python.org/
# Run installer
# ✅ Check "Add Python to PATH" during installation

# Verify installation
python --version

# Should show: Python 3.10.X or higher
```

### Step 3: Create Virtual Environment

#### Using Conda (Recommended)

```bash
# Create environment
conda create -n nextrade python=3.10

# Verify environment created
conda env list

# Activate environment (you'll see (nextrade) in terminal)
conda activate nextrade

# On Windows:
# conda activate nextrade

# On macOS/Linux:
# source activate nextrade
```

#### Using venv (Alternative)

```bash
# Create virtual environment
python -m venv nextrade_env

# Activate environment
# On Windows:
nextrade_env\Scripts\activate

# On macOS/Linux:
source nextrade_env/bin/activate

# You should see (nextrade_env) in terminal
```

### Step 4: Install Dependencies

```bash
# Make sure you're in the nextrade directory
cd nextrade

# Verify environment is active (should see (nextrade) prefix)

# Install required packages
pip install -r requirements.txt

# Expected packages:
# - PyQt5
# - requests
# - pandas
# - numpy
# - openpyxl
# - pyotp
# - websocket-client
# - yfinance

# Verify installation
pip list

# Should show all packages installed
```

### Step 5: Configure Angel One API

#### Get API Credentials

1. **Log in to Angel One**: https://www.angelone.in/
2. **Go to Settings** → **Profile** → **API Profile**
3. **Get These Values**:
   - Client ID
   - Password
   - API Key
   - TOTP Secret

#### Create config.json

```bash
# Navigate to project root
cd nextrade

# Create config.json file
# You can use any text editor (VS Code, Notepad++, etc.)
```

**Windows (Command Prompt)**:
```cmd
copy NUL config.json
# Opens in Notepad, paste below content
```

**macOS/Linux (Terminal)**:
```bash
touch config.json
# Open with: nano config.json, then paste content
```

#### Add API Credentials

Paste this into `config.json`:

```json
{
  "angel_one": {
    "client_id": "your_client_id_here",
    "password": "your_password_here",
    "api_key": "your_api_key_here",
    "totp_secret": "your_totp_secret_here"
  },
  "paper_trading": {
    "initial_capital": 100000,
    "risk_per_trade": 0.02,
    "slippage": 0.001
  },
  "analyzer": {
    "rsi_period": 14,
    "rsi_overbought": 70,
    "rsi_oversold": 30,
    "ema_fast": 12,
    "ema_slow": 26,
    "bb_period": 20,
    "bb_std_dev": 2
  }
}
```

#### Environment Variables (Optional but Recommended)

Create `.env` file for sensitive data:

```bash
# Create .env file
# Windows: copy NUL .env
# macOS/Linux: touch .env

# Add to .env:
ANGEL_CLIENT_ID=your_client_id
ANGEL_PASSWORD=your_password
ANGEL_API_KEY=your_api_key
ANGEL_TOTP_SECRET=your_totp_secret
```

**Add to .gitignore**:
```
# Exclude sensitive files from Git
config.json
.env
trades_log.xlsx
```

### Step 6: Launch Application

```bash
# Make sure you're in the nextrade directory
cd nextrade

# Make sure environment is activated
# You should see (nextrade) in your terminal

# Run the application
python test_new_ui.py
```

**Expected Output**:
```
Initializing NexTrade...
Loading configuration...
Connecting to Angel One API...
Initializing WebSocket connection...
[Application window opens with 8 tabs]
```

---

## 🔑 Angel One API Setup

### Getting Your API Credentials

#### Step 1: Log in to Angel One
```
1. Go to https://www.angelone.in/
2. Login with your credentials
```

#### Step 2: Access API Settings
```
1. Click on your Profile (top-right)
2. Select "Settings"
3. Go to "API Settings" or "Smart API"
4. Generate API Key (if not already generated)
```

#### Step 3: Copy Required Values

You'll need:
```
Client ID:    xxxxxxx
Password:     xxxxxxx (your Angel One password)
API Key:      xxxxxxx
TOTP Secret:  xxxxxxx (for 2FA)
```

#### Step 4: Add to Configuration

Update your `config.json`:
```json
{
  "angel_one": {
    "client_id": "YOUR_CLIENT_ID",
    "password": "YOUR_PASSWORD",
    "api_key": "YOUR_API_KEY",
    "totp_secret": "YOUR_TOTP_SECRET"
  }
}
```

### TOTP Secret Handling

The TOTP (Time-based One-Time Password) is used for 2-factor authentication.

```python
# NexTrade automatically handles TOTP generation
# No manual action needed
# The code uses pyotp library to generate codes

# For manual verification (optional):
import pyotp
totp = pyotp.TOTP('YOUR_TOTP_SECRET')
print(totp.now())  # Generates current 6-digit code
```

---

## ✅ Verification

### Test 1: Check Python Installation

```bash
python --version
# Should show: Python 3.10.X or higher
```

### Test 2: Check Environment

```bash
# Activate environment
conda activate nextrade

# Verify (should see (nextrade) prefix)
python -c "import sys; print(sys.prefix)"
```

### Test 3: Check Dependencies

```bash
python -c "import PyQt5; import pandas; import requests; print('All imports OK')"
# Should print: All imports OK
```

### Test 4: Test API Connection

```bash
python -c "
from ui_new.connection_manager import ConnectionManager
conn = ConnectionManager()
conn.connect()
print('Connected to Angel One!' if conn.is_connected else 'Connection failed')
"
```

### Test 5: Launch Application

```bash
python test_new_ui.py

# Should open a window with:
# - Green "Broker: Connected" status
# - 8 tabs (Dashboard, Holdings, Watchlist, etc.)
# - Real-time price data
```

---

## 🐛 Troubleshooting

### Issue 1: "Python command not found"

**Cause**: Python not in PATH
**Solution**:
```bash
# Windows: Reinstall Python, check "Add Python to PATH"
# macOS/Linux: Use full path or install via Homebrew
/usr/local/bin/python3.10 --version
```

### Issue 2: "conda: command not found"

**Cause**: Conda not installed
**Solution**:
```bash
# Install Anaconda from https://www.anaconda.com/
# Then restart terminal
```

### Issue 3: "ModuleNotFoundError: No module named 'PyQt5'"

**Cause**: Dependencies not installed
**Solution**:
```bash
# Verify environment is activated
conda activate nextrade  # or source venv/bin/activate

# Reinstall requirements
pip install -r requirements.txt

# Verify installation
pip show PyQt5
```

### Issue 4: "Connection Failed" to Angel One

**Cause**: Invalid credentials
**Solution**:
```bash
# Verify config.json has correct values:
# 1. Check client_id is correct
# 2. Check password is correct
# 3. Check api_key is correct
# 4. Check totp_secret is correct
# 5. Ensure Angel One account is active
```

### Issue 5: "QXcbConnection: Could not connect to display" (Linux)

**Cause**: No display server available
**Solution**:
```bash
# Install Qt dependencies
sudo apt-get install libqt5gui5 libqt5core5a

# Or use Xvfb for headless mode
xvfb-run python test_new_ui.py
```

### Issue 6: "Port already in use" or "WebSocket connection failed"

**Cause**: Another instance running or port conflict
**Solution**:
```bash
# Find process using port (Linux/macOS)
lsof -i :port_number

# Kill process
kill -9 process_id

# Or simply restart the application
```

### Issue 7: "SSL: CERTIFICATE_VERIFY_FAILED"

**Cause**: SSL certificate verification issue
**Solution**:
```bash
# Update certificates (macOS)
/Applications/Python\ 3.10/Install\ Certificates.command

# For Linux:
pip install --upgrade certifi

# For Windows:
# Usually resolves after Python reinstallation
```

---

## 🔧 Development Setup

### For Contributing to NexTrade

#### Step 1: Clone Your Fork

```bash
# Fork on GitHub first
# Then clone your fork
git clone https://github.com/yourname/nextrade.git
cd nextrade

# Add upstream repository
git remote add upstream https://github.com/original/nextrade.git
```

#### Step 2: Create Development Environment

```bash
# Create development environment
conda create -n nextrade-dev python=3.10

# Activate it
conda activate nextrade-dev

# Install development dependencies
pip install -r requirements-dev.txt

# Includes:
# - pytest (testing)
# - pylint (linting)
# - black (formatting)
# - sphinx (documentation)
```

#### Step 3: Install Pre-commit Hooks (Optional)

```bash
# Install pre-commit
pip install pre-commit

# Setup hooks
pre-commit install

# Now hooks run automatically on commit
```

#### Step 4: Create Feature Branch

```bash
# Update from upstream
git fetch upstream
git rebase upstream/main

# Create feature branch
git checkout -b feature/your-feature

# Make your changes...

# Run tests
pytest tests/

# Run linter
pylint nextrade/

# Commit and push
git add .
git commit -m "feature: your description"
git push origin feature/your-feature
```

#### Step 5: Make Pull Request

1. Go to GitHub
2. Click "New Pull Request"
3. Select your branch
4. Fill in description
5. Submit!

---

## 📝 Project Structure

After successful installation, you should have:

```
nextrade/
├── README.md                 # Project overview
├── requirements.txt          # Python dependencies
├── requirements-dev.txt      # Development dependencies
├── LICENSE                   # MIT License
├── .gitignore               # Git ignore rules
├── config.json              # Your configuration (don't commit)
├── trades_log.xlsx          # Trade history (auto-generated)
├── watchlist.json           # Watched stocks
│
├── test_new_ui.py           # 🚀 Main launcher
│
├── ui_new/                  # UI Components
│   ├── connection_manager.py
│   ├── main_window.py
│   ├── data_handler.py
│   └── tabs/
│       ├── dashboard_tab.py
│       ├── holdings_tab.py
│       ├── watchlist_tab.py
│       ├── analyzer_tab.py
│       ├── positions_tab.py
│       ├── paper_trading_tab.py
│       ├── history_tab.py
│       ├── premarket_tab.py
│       └── settings_tab.py
│
├── analyzer/                # Trading Logic
│   ├── enhanced_analyzer.py
│   └── fundamentals_analyzer.py
│
├── indicators/              # Technical Indicators
│   └── ta.py
│
├── order_manager/           # Trading Execution
│   └── paper_trader.py
│
├── data_provider/           # Data Sources
│   └── angel_provider.py
│
├── docs/                    # Documentation
│   ├── SETUP.md            # This file
│   ├── API_REFERENCE.md
│   ├── CONTRIBUTING.md
│   └── ARCHITECTURE.md
│
└── tests/                   # Test Files
    ├── test_analyzer.py
    ├── test_paper_trader.py
    └── test_indicators.py
```

---

## ✨ Quick Verification Checklist

- [ ] Python 3.10+ installed
- [ ] Git installed
- [ ] Repository cloned
- [ ] Virtual environment created and activated
- [ ] Dependencies installed (`pip list` shows PyQt5, pandas, etc.)
- [ ] `config.json` created with API credentials
- [ ] Application launches without errors
- [ ] Green "Broker: Connected" status shows
- [ ] Real-time prices visible in Watchlist
- [ ] No error messages in console

---

## 🚀 Next Steps

1. ✅ **Installation Complete**: You have NexTrade ready!
2. 📖 **Read Documentation**: Check [README.md](../README.md)
3. 🎯 **Explore Features**: Try each tab
4. 📊 **Start Paper Trading**: Begin with virtual trading
5. 🤝 **Contribute**: Submit improvements!

---

## 💡 Pro Tips

- **Keep Dependencies Updated**: Periodically run `pip install --upgrade -r requirements.txt`
- **Regular Backups**: Back up your `trades_log.xlsx` regularly
- **Monitor API Usage**: Check Angel One dashboard for API call counts
- **Join Community**: Star the GitHub repository for updates

---

## 📞 Need Help?

- **GitHub Issues**: Report bugs or ask questions
- **Documentation**: Check docs/ folder
- **Community**: Discussions section on GitHub

---

**Successfully installed NexTrade? Great! Now start trading! 🚀**
