#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
                    ANGEL ONE TRADING BOT - MODULAR ARCHITECTURE
================================================================================
File Name:      main.py (MODULAR VERSION - DO NOT RENAME THIS FILE)
Version:        3.0.0 - MODULAR ARCHITECTURE WITH ENHANCED RELIABILITY
Release Date:   September 24, 2025
Author:         Trading Bot System - Modular Architecture Team
License:        Personal Use Only

--------------------------------------------------------------------------------
VERSION HISTORY:
--------------------------------------------------------------------------------
v3.0.0 (2025-09-24) - COMPLETE MODULAR ARCHITECTURE IMPLEMENTATION
    ✓ MODULAR DESIGN - Separated into independent, testable modules
    ✓ ENHANCED GOLDEN RATIO ANALYZER - Real technical analysis implementation
    ✓ REAL-TIME WEBSOCKET DATA - Live market data feeds
    ✓ IMPROVED PAPER TRADING - Full portfolio tracking with P&L calculations
    ✓ TECHNICAL INDICATORS MODULE - RSI, EMA, Fibonacci, Bollinger Bands
    ✓ ROBUST ERROR HANDLING - Module-level error isolation
    ✓ ENHANCED LOGGING - Comprehensive audit trail
    ✓ SAFE TESTING FRAMEWORK - Each module independently testable

v2.1.10 (2024-09-21) - MONOLITHIC VERSION (DEPRECATED)
    × Single file architecture (3500+ lines - maintenance issues)
    × Missing WebSocket implementation
    × Broken pre-market analysis functions
    × Incomplete technical indicators
    × Risk of system-wide crashes

--------------------------------------------------------------------------------
MODULAR ARCHITECTURE BENEFITS:
--------------------------------------------------------------------------------
    ✓ FINANCIAL SAFETY - Module failures don't crash entire system
    ✓ MAINTAINABILITY - Each module under 200 lines, easy to debug
    ✓ TESTABILITY - Individual components can be unit tested
    ✓ SCALABILITY - Add new strategies without affecting core system
    ✓ RELIABILITY - Better error isolation and recovery
    ✓ REAL-TIME DATA - Proper WebSocket implementation for live feeds
    ✓ PERFORMANCE - Optimized data flow and processing

--------------------------------------------------------------------------------
MODULE STRUCTURE:
--------------------------------------------------------------------------------
    indicators/
    ├── ta.py                   # Technical analysis functions (RSI, EMA, MACD)
    
    data_provider/
    ├── angel_provider.py       # Angel One API with WebSocket support
    
    analyzer/
    ├── enhanced_analyzer.py    # Golden Ratio strategy implementation
    
    order_manager/
    ├── paper_trader.py         # Safe paper trading with portfolio tracking
    ├── broker_trader.py        # Live trading wrapper (future)
    
    config/
    ├── settings.py             # Configuration management
    ├── credentials.json        # Encrypted credential storage
    
    ui/
    ├── trading_ui.py           # Modern Tkinter interface
    
    main.py                     # This file - orchestration and entry point

--------------------------------------------------------------------------------
NEW FEATURES (v3.0.0):
--------------------------------------------------------------------------------
    - REAL GOLDEN RATIO CALCULATIONS using Fibonacci retracements
    - LIVE WEBSOCKET DATA FEEDS for real-time market updates
    - MODULAR PRE-MARKET ANALYSIS with proper technical indicators
    - ENHANCED PAPER TRADING with complete P&L tracking
    - TECHNICAL INDICATOR LIBRARY (RSI, EMA, SMA, MACD, Bollinger Bands)
    - MODULE-LEVEL ERROR ISOLATION preventing system crashes
    - COMPREHENSIVE LOGGING for debugging and audit trails
    - INDEPENDENT TESTING FRAMEWORK for each module

--------------------------------------------------------------------------------
SECURITY ENHANCEMENTS:
--------------------------------------------------------------------------------
    - SECURE CREDENTIAL MANAGEMENT with encrypted storage
    - MODULE-LEVEL ERROR BOUNDARIES preventing cascade failures
    - COMPREHENSIVE AUDIT LOGGING for all trading activities
    - PAPER TRADING DEFAULTS for safe operation
    - REAL-TIME DATA VALIDATION and error checking
    - ISOLATED ORDER EXECUTION preventing accidental live trades

--------------------------------------------------------------------------------
TECHNICAL IMPROVEMENTS:
--------------------------------------------------------------------------------
    - PROPER WEBSOCKET IMPLEMENTATION for live market data
    - REAL TECHNICAL ANALYSIS using industry-standard indicators
    - EFFICIENT DATA CACHING and processing
    - MODULAR DESIGN for easy maintenance and updates
    - COMPREHENSIVE ERROR HANDLING and recovery
    - PERFORMANCE OPTIMIZATIONS throughout the system

--------------------------------------------------------------------------------
SYSTEM REQUIREMENTS:
--------------------------------------------------------------------------------
    - Python 3.8 or higher (recommended: Python 3.11+)
    - Windows/Linux/Mac OS (tested on all platforms)
    - Internet connection (stable for WebSocket feeds)
    - Angel One trading account with API enabled
    - 4GB RAM minimum, 8GB recommended
    - Admin rights for initial setup (credential storage)

--------------------------------------------------------------------------------
DEPENDENCIES (AUTO-INSTALLED):
--------------------------------------------------------------------------------
    Core Trading:
    - smartapi-python         # Angel One API and WebSocket
    - pyotp                   # Two-factor authentication
    - pandas                  # Data manipulation and analysis
    - numpy                   # Numerical computations
    
    Security & Storage:
    - keyring                 # Secure credential storage
    - cryptography           # Encryption for sensitive data
    
    User Interface:
    - tkinter                 # GUI framework (built-in)
    
    Utilities:
    - requests               # HTTP requests
    - websocket-client       # WebSocket support
    - python-dateutil        # Date/time utilities

--------------------------------------------------------------------------------
INSTALLATION & SETUP:
--------------------------------------------------------------------------------
    1. Clone/download the modular trading bot
    2. Navigate to the project directory:
       cd c:\\users\\dell\\tradingbot_new
    3. Run the main script:
       c:\\users\\dell\\anaconda3\\python.exe main.py
    4. First-time setup will automatically:
       - Create all necessary directories
       - Install missing dependencies
       - Set up secure credential storage
       - Initialize paper trading environment
       - Launch the trading dashboard

--------------------------------------------------------------------------------
USAGE INSTRUCTIONS:
--------------------------------------------------------------------------------
    PAPER TRADING (Recommended for testing):
    1. Launch the application with: python main.py
    2. Configure your Angel One credentials in Settings
    3. Select Paper Trading mode (default)
    4. Run Enhanced Analysis to generate signals
    5. Execute trades using individual BUY/SELL buttons
    6. Monitor performance in Portfolio and Paper Trading tabs
    
    LIVE TRADING (Only after thorough testing):
    1. Test thoroughly in Paper Trading mode first
    2. Switch to Live Trading mode in Settings
    3. Confirm all signals and analysis accuracy
    4. Start with small position sizes
    5. Monitor all trades closely

--------------------------------------------------------------------------------
GOLDEN RATIO STRATEGY DETAILS:
--------------------------------------------------------------------------------
    Technical Analysis Components:
    - Fibonacci Retracements: 23.6%, 38.2%, 50%, 61.8%, 78.6%
    - RSI Analysis: Oversold (<30), Overbought (>70)
    - EMA Crossovers: 8-period vs 21-period trend confirmation
    - Volume Analysis: Above-average volume confirmation
    - Bollinger Bands: Price extremes identification
    
    Signal Generation Criteria:
    BUY Signals:
    - Price near Golden Ratio support (61.8% retracement)
    - RSI oversold or approaching oversold
    - EMA showing upward trend or bullish crossover
    - Above-average volume confirmation
    - Price at lower Bollinger Band
    
    SELL Signals:
    - Price near Golden Ratio resistance (61.8% extension)
    - RSI overbought or approaching overbought  
    - EMA showing downward trend or bearish crossover
    - Above-average volume confirmation
    - Price at upper Bollinger Band

--------------------------------------------------------------------------------
SAFETY FEATURES:
--------------------------------------------------------------------------------
    - PAPER TRADING DEFAULT: No real money risk during testing
    - MODULE ISOLATION: Individual component failures won't crash system
    - COMPREHENSIVE LOGGING: Full audit trail of all activities
    - ERROR RECOVERY: Automatic error handling and system recovery
    - POSITION LIMITS: Configurable maximum position sizes
    - STOP-LOSS AUTOMATION: Automatic exit trigger monitoring
    - REAL-TIME MONITORING: Continuous system health checks

--------------------------------------------------------------------------------
TROUBLESHOOTING:
--------------------------------------------------------------------------------
    Common Issues:
    1. "Module not found" errors:
       - Ensure all folders (indicators/, data_provider/, etc.) exist
       - Check that __init__.py files are present in each module directory
       
    2. WebSocket connection issues:
       - Verify internet connection stability
       - Check Angel One API credentials
       - Ensure TOTP is correctly configured
       
    3. Analysis not generating signals:
       - Verify market hours (signals work best during trading hours)
       - Check that sufficient historical data is available
       - Ensure stock symbols are correctly configured
       
    4. Paper trading not working:
       - Check that data/ directory exists and is writable
       - Verify paper trading files are not corrupted
       - Reset paper trading if necessary

--------------------------------------------------------------------------------
DEVELOPMENT NOTES:
--------------------------------------------------------------------------------
    Module Development Guidelines:
    - Keep each module under 200 lines for maintainability
    - Implement comprehensive error handling in each module
    - Use proper logging for debugging and audit trails
    - Write unit tests for all critical functions
    - Document all public APIs and interfaces
    - Follow PEP 8 style guidelines
    - Use type hints for better code clarity

--------------------------------------------------------------------------------
SUPPORT & MAINTENANCE:
--------------------------------------------------------------------------------
    For technical support:
    1. Check the logs/ directory for detailed error information
    2. Review the troubleshooting section above
    3. Test individual modules to isolate issues
    4. Verify all dependencies are correctly installed
    
    For updates and improvements:
    - Regularly update the SmartAPI library
    - Keep Python version current (3.11+ recommended)
    - Monitor Angel One API changes and updates
    - Test new features in paper trading mode first

--------------------------------------------------------------------------------
DISCLAIMER & RISK WARNING:
--------------------------------------------------------------------------------
    IMPORTANT: This software is for educational and research purposes only.
    
    ⚠️  TRADING RISKS:
    - Trading in financial markets involves substantial risk
    - Past performance does not guarantee future results
    - You may lose some or all of your invested capital
    - Never trade with money you cannot afford to lose
    
    ⚠️  SOFTWARE RISKS:
    - This is experimental software - bugs may exist
    - Always test thoroughly in paper trading mode first
    - Verify all signals and analysis before live trading
    - The authors assume no responsibility for trading losses
    
    ⚠️  REGULATORY COMPLIANCE:
    - Ensure compliance with local financial regulations
    - Understand tax implications of your trading activities
    - Consult with financial advisors before making investment decisions

================================================================================
COPYRIGHT & LICENSE:
================================================================================
Copyright (c) 2025 Trading Bot System - Modular Architecture Team
Licensed for personal use only. Commercial use prohibited.
Redistribution and modification allowed for personal use.

This software is provided "as is" without warranty of any kind.
Use at your own risk. The authors are not responsible for any losses.
================================================================================
"""

# Standard library imports
import sys
import os
import logging
import tkinter as tk
from pathlib import Path
from datetime import datetime
import threading
import time

# Add project root to Python path for module imports
project_root = Path(__file__).parent.absolute()
sys.path.insert(0, str(project_root))

# Version and build information
__version__ = "3.0.0"
__build_date__ = "2025-09-24"
__build_number__ = "20250924001"
__architecture__ = "Modular"
__python_minimum__ = "3.8"
__author__ = "Trading Bot System - Modular Architecture Team"

def setup_logging():
    """Configure comprehensive logging system"""
    try:
        # Create logs directory
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        
        # Configure logging
        log_file = log_dir / f"trading_bot_{datetime.now().strftime('%Y%m%d')}.log"
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ]
        )
        
        logger = logging.getLogger("TradingBot")
        logger.info(f"Logging initialized - Version {__version__} Build {__build_number__}")
        return True
        
    except Exception as e:
        print(f"Warning: Could not setup logging: {e}")
        return False

def create_directory_structure():
    """Create necessary directory structure"""
    directories = [
        "config",
        "data", 
        "logs",
        "indicators",
        "data_provider",
        "analyzer", 
        "order_manager",
        "ui"
    ]
    
    created_dirs = []
    for directory in directories:
        try:
            Path(directory).mkdir(exist_ok=True)
            created_dirs.append(directory)
        except Exception as e:
            print(f"Warning: Could not create directory {directory}: {e}")
    
    return created_dirs

def check_python_version():
    """Verify Python version compatibility"""
    required_version = tuple(map(int, __python_minimum__.split('.')))
    current_version = sys.version_info[:2]
    
    if current_version < required_version:
        print(f"ERROR: Python {__python_minimum__} or higher required.")
        print(f"Current version: {sys.version}")
        return False
    
    return True

def install_dependencies():
    """Install required dependencies"""
    dependencies = [
        "smartapi-python",
        "pyotp", 
        "pandas",
        "numpy",
        "keyring",
        "cryptography",
        "requests",
        "websocket-client",
        "python-dateutil"
    ]
    
    import subprocess
    
    installed = []
    failed = []
    
    for package in dependencies:
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", package], 
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            installed.append(package)
        except subprocess.CalledProcessError:
            failed.append(package)
            print(f"Warning: Could not install {package}")
    
    return installed, failed

def create_init_files():
    """Create __init__.py files for module directories"""
    module_dirs = ["indicators", "data_provider", "analyzer", "order_manager", "ui"]
    
    for module_dir in module_dirs:
        init_file = Path(module_dir) / "__init__.py"
        if not init_file.exists():
            try:
                init_file.write_text("# Module initialization file\n")
            except Exception as e:
                print(f"Warning: Could not create {init_file}: {e}")

def display_startup_banner():
    """Display startup banner with system information"""
    banner = f"""
{'='*80}
   ANGEL ONE TRADING BOT - MODULAR ARCHITECTURE v{__version__}
{'='*80}
   Build: {__build_number__} | Date: {__build_date__}
   Architecture: {__architecture__} | Python: {sys.version.split()[0]}
   
   🔧 MODULAR DESIGN - Reliable & Maintainable
   📈 REAL GOLDEN RATIO ANALYSIS - Fibonacci + RSI + EMA
   ⚡ LIVE WEBSOCKET DATA - Real-time market feeds  
   📝 ENHANCED PAPER TRADING - Complete P&L tracking
   🛡️  MODULE ISOLATION - Crash-resistant architecture
   
   Project Directory: {project_root}
   
   Starting system initialization...
{'='*80}
"""
    print(banner)

def main():
    """Main entry point for the modular trading bot"""
    
    # Display startup information
    display_startup_banner()
    
    # Check system requirements
    print("🔍 Checking system requirements...")
    if not check_python_version():
        input("Press Enter to exit...")
        return 1
    
    # Setup directory structure
    print("📁 Creating directory structure...")
    created_dirs = create_directory_structure()
    create_init_files()
    print(f"   Created directories: {', '.join(created_dirs)}")
    
    # Setup logging
    print("📋 Initializing logging system...")
    logging_ok = setup_logging()
    logger = logging.getLogger("TradingBot.Main")
    
    if logging_ok:
        logger.info("Trading Bot startup initiated")
        logger.info(f"Version: {__version__} | Build: {__build_number__}")
        logger.info(f"Python: {sys.version}")
        logger.info(f"Working Directory: {project_root}")
    
    # Install dependencies
    print("📦 Checking dependencies...")
    try:
        installed, failed = install_dependencies()
        if failed:
            print(f"   Warning: Failed to install: {', '.join(failed)}")
            logger.warning(f"Failed dependencies: {failed}")
    except Exception as e:
        print(f"   Warning: Dependency check failed: {e}")
        if logging_ok:
            logger.exception("Dependency installation error")
    
    # Import and initialize modules
    print("🔧 Loading trading modules...")
    try:
        # Import core modules
        from data_provider.angel_provider import AngelProvider
        from analyzer.enhanced_analyzer import EnhancedAnalyzer  
        from order_manager.intraday_paper_trader import PaperTrader
        
        print("   ✓ Core modules loaded successfully")
        logger.info("Core trading modules imported successfully")
        
        # Initialize components
        print("🚀 Initializing trading system...")
        
        # Initialize data provider
        angel_api = AngelProvider()
        
        # Initialize analyzer with data provider
        analyzer = EnhancedAnalyzer(angel_api)
        
        # Initialize paper trader
        paper_trader = PaperTrader(initial_balance=100000.0)
        
        # Load default watchlist
        default_watchlist = [
            "RELIANCE", "TCS", "HDFCBANK", "ICICIBANK", "SBIN",
            "AXISBANK", "KOTAKBANK", "INFY", "WIPRO", "HCLTECH", 
            "BHARTIARTL", "ADANIPORTS", "ASIANPAINT", "BAJFINANCE", "ITC"
        ]
        
        print("   ✓ Trading system initialized")
        logger.info("Trading system components initialized successfully")
        
      # Create and start UI
        print("🖥️  Loading user interface...")
        
        # Simple UI for now - you can replace with more sophisticated UI later
        root = tk.Tk()
        root.title(f"Angel One Trading Bot v{__version__} - Modular Architecture")
        root.geometry("1200x800")
        root.configure(bg="#2c3e50")
        
        # Create professional UI
        print("🖥️  Loading professional interface...")
        from ui.professional_trading_ui import ProfessionalTradingUI
        
        # Initialize professional UI
        professional_ui = ProfessionalTradingUI(
            angel_api=angel_api,
            analyzer=analyzer,
            paper_trader=paper_trader,
            version=__version__
        )
        
        print("   ✅ Professional interface ready")
        logger.info("Professional UI initialized successfully")
        
        print(f"\n✅ STARTUP COMPLETE")
        print(f"🚀 Trading Bot v{__version__} ready for operation")
        print(f"📝 Paper Trading Mode active (₹{paper_trader.balance:,.2f} virtual balance)")
        print("-" * 80)
        
        logger.info("Startup sequence completed successfully")
        
        # Start the professional interface
        professional_ui.run()
        
        logger.info("Application shutdown initiated")
        
    except ImportError as e:
        error_msg = f"Module import error: {e}"
        print(f"❌ {error_msg}")
        
        missing_module = str(e).split("'")[1] if "'" in str(e) else "unknown"
        print(f"\n🔧 TROUBLESHOOTING:")
        print(f"   The '{missing_module}' module is missing or incomplete.")
        print(f"   Please ensure all module files are saved in the correct directories:")
        print(f"   - indicators/ta.py")
        print(f"   - data_provider/angel_provider.py") 
        print(f"   - analyzer/enhanced_analyzer.py")
        print(f"   - order_manager/paper_trader.py")
        print(f"   - __init__.py files in each module directory")
        
        if logging_ok:
            logger.error(error_msg)
            logger.error("Module structure incomplete - check file installation")
        
        input("\nPress Enter to exit...")
        return 1
        
    except Exception as e:
        error_msg = f"Startup error: {e}"
        print(f"❌ {error_msg}")
        
        if logging_ok:
            logger.exception("Critical startup error")
        
        print(f"\n🔧 TROUBLESHOOTING:")
        print(f"   1. Check that all module files exist and are not corrupted")
        print(f"   2. Verify Python version is {__python_minimum__} or higher")
        print(f"   3. Ensure all dependencies are installed")
        print(f"   4. Check logs directory for detailed error information")
        print(f"   5. Try running individual modules to isolate the issue")
        
        input("\nPress Enter to exit...")
        return 1

def test_modules():
    """Test individual modules for debugging"""
    print("🧪 TESTING INDIVIDUAL MODULES")
    print("-" * 40)
    
    modules_to_test = [
        ("indicators.ta", "Technical Analysis"),
        ("data_provider.angel_provider", "Angel One API Provider"),
        ("analyzer.enhanced_analyzer", "Enhanced Analyzer"),
        ("order_manager.paper_trader", "Paper Trader")
    ]
    
    results = {}
    
    for module_name, description in modules_to_test:
        try:
            __import__(module_name)
            results[module_name] = "✅ OK"
            print(f"✅ {description}: OK")
        except Exception as e:
            results[module_name] = f"❌ ERROR: {e}"
            print(f"❌ {description}: ERROR - {e}")
    
    print("\n" + "=" * 50)
    print("MODULE TEST SUMMARY:")
    for module, result in results.items():
        print(f"{module}: {result}")
    
    return results

if __name__ == "__main__":
    # Handle command line arguments
    if len(sys.argv) > 1:
        if sys.argv[1] == "--test":
            # Test mode - check individual modules
            test_results = test_modules()
            failed_modules = [k for k, v in test_results.items() if "ERROR" in v]
            
            if failed_modules:
                print(f"\n❌ {len(failed_modules)} modules failed testing")
                sys.exit(1)
            else:
                print(f"\n✅ All modules passed testing")
                sys.exit(0)
                
        elif sys.argv[1] == "--version":
            # Version information
            print(f"Angel One Trading Bot v{__version__}")
            print(f"Build: {__build_number__} | Architecture: {__architecture__}")
            print(f"Build Date: {__build_date__}")
            print(f"Python Required: {__python_minimum__}+")
            sys.exit(0)
            
        elif sys.argv[1] == "--help":
            # Help information
            print(f"Angel One Trading Bot v{__version__} - Usage")
            print("=" * 50)
            print("python main.py           # Start the trading bot")
            print("python main.py --test    # Test all modules")
            print("python main.py --version # Show version info")
            print("python main.py --help    # Show this help")
            sys.exit(0)
    
    # Normal startup
    try:
        exit_code = main()
        sys.exit(exit_code or 0)
    except KeyboardInterrupt:
        print(f"\n👋 Trading bot shutdown by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n💥 Critical error: {e}")
        sys.exit(1)