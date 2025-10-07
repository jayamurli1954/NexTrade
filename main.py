"""
COMPLETE FIXED main.py - Angel One Trading Bot v3.1.0-FIXED
NO PATCHING REQUIRED - Replace your entire main.py with this file

CRITICAL FIX INCLUDED:
- Line 151: paper_trader.set_data_provider(broker) 
  This enables real-time price monitoring for SL/Target/3:15PM exits
"""

import sys
import logging
import signal
import atexit
from datetime import datetime
import tkinter as tk

# Import enhanced logging and trade logger
try:
    from trade_logger import TradeLogger
    from console_handler import setup_enhanced_logging, TradingBotLogger
except ImportError:
    print("WARNING: trade_logger.py or console_handler.py not found")
    print("Running without enhanced logging features")
    TradeLogger = None
    TradingBotLogger = None
    setup_enhanced_logging = None

# Import your existing modules
from ui.professional_trading_ui import ProfessionalTradingUI

# Try different names for broker class
try:
    from data_provider.angel_provider import AngelBroker
except ImportError:
    try:
        from data_provider.angel_provider import AngelProvider as AngelBroker
    except ImportError:
        try:
            from data_provider.angel_provider import AngelOneProvider as AngelBroker
        except ImportError:
            print("\nERROR: Could not import broker class from angel_provider.py")
            print("Looking for one of: AngelBroker, AngelProvider, or AngelOneProvider")
            sys.exit(1)

from order_manager.paper_trader import PaperTrader
from analyzer.enhanced_analyzer import EnhancedAnalyzer

# Try to import credentials manager
try:
    from config.credentials_manager import CredentialsManager
except ImportError:
    try:
        from config.credentials_manager import CredentialManager as CredentialsManager
    except ImportError:
        print("\nWARNING: Could not import CredentialsManager")
        print("Will run without credential management")
        CredentialsManager = None


def main():
    """Main entry point with enhanced logging and graceful shutdown"""
    
    # Setup enhanced logging if available
    console_handler = None
    bot_logger = None
    trade_logger = None
    
    if setup_enhanced_logging and TradingBotLogger and TradeLogger:
        console_handler = setup_enhanced_logging(
            console_widget=None,
            log_level=logging.INFO
        )
        bot_logger = TradingBotLogger('TradingBot')
        trade_logger = TradeLogger(log_dir='logs/trades')
    
    # Print welcome banner
    print("\n" + "="*80)
    print(f"{'ANGEL ONE TRADING BOT - v3.1.0-FIXED':^80}")
    print(f"{'With Real-Time Monitoring & Threading Fixes':^80}")
    print("="*80)
    
    if bot_logger:
        bot_logger.system_status('STARTUP', 'System initialization in progress...')
    
    # Setup graceful exit handler
    def signal_handler(sig, frame):
        """Handle Ctrl+C and clean shutdown"""
        print("\n" + "="*80)
        print(f"{'Shutting Down Gracefully...':^80}")
        print("="*80)
        
        if bot_logger:
            bot_logger.system_status('SHUTDOWN', 'Shutdown signal received')
        
        # Stop console handler
        if console_handler:
            try:
                console_handler.stop()
            except:
                pass
        
        # Get and display trade summary
        if trade_logger:
            try:
                summary = trade_logger.get_trade_summary()
                print(f"\nToday's Trading Summary:")
                print(f"   {'-'*50}")
                print(f"   Total Trades: {summary['total_trades']}")
                print(f"   Open Trades: {summary['open_trades']}")
                print(f"   Closed Trades: {summary['closed_trades']}")
                print(f"   Winning Trades: {summary['winning_trades']}")
                print(f"   Losing Trades: {summary['losing_trades']}")
                print(f"   Win Rate: {summary['win_rate']:.1f}%")
                print(f"   {'-'*50}")
                
                pnl = summary['total_pnl']
                print(f"   Total P&L: ₹{pnl:,.2f}")
                print(f"   {'-'*50}")
            except Exception as e:
                print(f"   Error generating summary: {e}")
        
        print(f"\nAll logs saved successfully!")
        if trade_logger:
            print(f"   Trade Journal: logs/trades/trades_{datetime.now().strftime('%Y-%m-%d')}.xlsx")
        print(f"   System Logs: logs/app.log")
        print("="*80)
        print(f"{'Thank you for using Angel One Trading Bot!':^80}")
        print("="*80 + "\n")
        
        sys.exit(0)
    
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    atexit.register(lambda: print("\nTrading bot stopped.\n"))
    
    try:
        # Load credentials
        if bot_logger:
            bot_logger.system_status('INIT', 'Loading credentials...')
        
        credentials = None
        if CredentialsManager:
            try:
                creds_manager = CredentialsManager()
                credentials = creds_manager.load_credentials()
            except Exception as e:
                print(f"Warning: Could not load credentials: {e}")
        
        if not credentials:
            print("\nWARNING: No credentials found!")
            print("You can configure them later through Settings in the UI")
            credentials = {
                'api_key': '',
                'client_id': '',
                'password': '',
                'totp': ''
            }
        
        if bot_logger:
            bot_logger.system_status('INIT', 'Credentials loaded')
        
        # Initialize broker
        if bot_logger:
            bot_logger.system_status('INIT', 'Connecting to Angel One API...')
        
        try:
            # Try keyword argument first
            broker = AngelBroker(credentials, paper_mode=True)
        except TypeError:
            # If that fails, try positional argument
            try:
                broker = AngelBroker(credentials, True)
            except TypeError:
                # Last attempt - just credentials
                broker = AngelBroker(credentials)
                if hasattr(broker, 'paper_mode'):
                    broker.paper_mode = True
        
        if broker.is_connected:
            if bot_logger:
                bot_logger.connection_status('connected', 'Angel One API')
            print("✅ Connected to Angel One API")
        else:
            if bot_logger:
                bot_logger.connection_status('disconnected', 'Angel One API - Using fallback mode')
            print("⚠️  Running in offline mode - will connect later")
        
        # Initialize analyzer
        if bot_logger:
            bot_logger.system_status('INIT', 'Initializing analyzer...')
        analyzer = EnhancedAnalyzer(broker)
        print("✅ Analyzer initialized")
        
        # Initialize paper trader with trade logger
        if bot_logger:
            bot_logger.system_status('INIT', 'Initializing paper trading system...')
        
        paper_trader = PaperTrader(
            initial_cash=100000,
            leverage=5.0,
            enable_intraday=True,
            trade_logger=trade_logger if trade_logger else None
        )
        print("✅ Paper trader initialized")
        
        # ⚡ CRITICAL FIX: Connect paper_trader to broker for real-time monitoring
        paper_trader.set_data_provider(broker)
        print("✅ Real-time monitoring enabled")
        
        # Try to get real portfolio and funds
        if broker.is_connected:
            try:
                holdings = broker.get_holdings()
                funds = broker.get_funds()
                if bot_logger:
                    bot_logger.portfolio_update(
                        holdings_count=len(holdings) if isinstance(holdings, list) else len(holdings.get('holdings', [])),
                        total_value=0,
                        available_funds=funds
                    )
                print(f"✅ Portfolio synced: {len(holdings) if isinstance(holdings, list) else len(holdings.get('holdings', []))} holdings")
            except Exception as e:
                if bot_logger:
                    bot_logger.warning(f"Could not fetch portfolio: {e}")
                print(f"⚠️  Could not fetch portfolio: {e}")
        
        if bot_logger:
            bot_logger.system_status('READY', 'All systems initialized successfully')
        
        print("\n" + "="*80)
        print(f"{'SYSTEM READY - Starting GUI...':^80}")
        print("="*80 + "\n")
        
        # Create Tkinter root window
        root = tk.Tk()
        
        # Create and show main UI
        app = ProfessionalTradingUI(
            root,
            analyzer=analyzer,
            provider=broker,
            paper_trader=paper_trader,
            paper_mode=True,
            version="3.1.0",
            build="FIXED-20251007",
            title="Angel One Trading Bot - FIXED"
        )
        
        print("="*80)
        print("✅ ALL CRITICAL FIXES ACTIVE:")
        print("   • Real-time SL/Target monitoring every 10 seconds")
        print("   • Exact 3:15 PM auto-exit (checks from 3:14:50)")
        print("   • Network retry logic (never uses entry price)")
        print("   • Non-blocking UI (all API calls in background)")
        print("   • Complete Excel trade logging")
        print("="*80 + "\n")
        
        # Start Tkinter event loop
        root.mainloop()
        
    except KeyboardInterrupt:
        signal_handler(None, None)
        
    except ImportError as e:
        print("\n" + "="*80)
        print(f"{'IMPORT ERROR':^80}")
        print("="*80)
        print(f"\nMissing required module: {e}")
        print("\nPlease ensure all dependencies are installed:")
        print("  pip install openpyxl pandas")
        print("\nAnd all project files are present:")
        print("  - ui/professional_trading_ui.py")
        print("  - data_provider/angel_provider.py")
        print("  - order_manager/paper_trader.py")
        print("  - analyzer/enhanced_analyzer.py")
        print("\n" + "="*80 + "\n")
        sys.exit(1)
        
    except Exception as e:
        if bot_logger:
            bot_logger.error(f"Critical error: {e}")
        print("\n" + "="*80)
        print(f"{'CRITICAL ERROR':^80}")
        print("="*80)
        print(f"\nError: {e}")
        print("\nFull traceback:")
        import traceback
        traceback.print_exc()
        print("\n" + "="*80 + "\n")
        sys.exit(1)


if __name__ == '__main__':
    # Pre-flight checks
    print("\n🔍 Performing pre-flight checks...")
    
    # Check required Python packages
    required_packages = ['tkinter', 'pandas']
    optional_packages = ['openpyxl']
    missing_packages = []
    missing_optional = []
    
    for package in required_packages:
        try:
            if package == 'tkinter':
                import tkinter
            else:
                __import__(package)
            print(f"✅ {package} is installed")
        except ImportError:
            missing_packages.append(package)
            print(f"❌ {package} is NOT installed")
    
    for package in optional_packages:
        try:
            __import__(package)
            print(f"✅ {package} is installed")
        except ImportError:
            missing_optional.append(package)
            print(f"⚠️  {package} is NOT installed (optional - needed for Excel logging)")
    
    if missing_packages:
        print("\n" + "="*80)
        print(f"{'MISSING REQUIRED PACKAGES':^80}")
        print("="*80)
        print("\nPlease install missing packages:")
        pkg_list = [p for p in missing_packages if p != 'tkinter']
        if pkg_list:
            print(f"  pip install {' '.join(pkg_list)}")
        if 'tkinter' in missing_packages:
            print("  tkinter: Usually comes with Python. Try reinstalling Python with tkinter support.")
        print("\n" + "="*80 + "\n")
        sys.exit(1)
    
    if missing_optional:
        print(f"\n⚠️  Optional packages missing: {', '.join(missing_optional)}")
        print(f"   Install with: pip install {' '.join(missing_optional)}")
        print(f"   (Excel logging will be disabled without openpyxl)\n")
    
    # Check required project files
    import os
    required_files = [
        'ui/professional_trading_ui.py',
        'data_provider/angel_provider.py',
        'order_manager/paper_trader.py',
        'analyzer/enhanced_analyzer.py'
    ]
    
    optional_files = [
        'trade_logger.py',
        'console_handler.py',
        'config/credentials_manager.py'
    ]
    
    missing_files = []
    for file in required_files:
        if os.path.exists(file):
            print(f"✅ {file} exists")
        else:
            missing_files.append(file)
            print(f"❌ {file} is MISSING")
    
    for file in optional_files:
        if os.path.exists(file):
            print(f"✅ {file} exists")
        else:
            print(f"⚠️  {file} is MISSING (optional)")
    
    if missing_files:
        print("\n" + "="*80)
        print(f"{'MISSING REQUIRED FILES':^80}")
        print("="*80)
        print("\nThe following files are missing:")
        for file in missing_files:
            print(f"  - {file}")
        print("\nPlease ensure all required files are in place.")
        print("="*80 + "\n")
        sys.exit(1)
    
    print("\n✅ All pre-flight checks passed!")
    print("="*80 + "\n")
    
    # All checks passed - run main
    main()