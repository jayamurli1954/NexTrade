"""
COMPLETE SCRIPT - main.py
Angel One Trading Bot - Main Entry Point with Enhanced Features
Save this as: c:/Users/Dell/tradingbot_new/main.py

NO PATCHING REQUIRED - This is the complete file
Replace your existing main.py with this entire script
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
    print("ERROR: Missing required files!")
    print("Please ensure trade_logger.py and console_handler.py exist in the project folder")
    sys.exit(1)

# Import your existing modules
from ui.professional_trading_ui import ProfessionalTradingUI

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

try:
    from config.credentials_manager import CredentialsManager
except ImportError:
    try:
        from config.credentials_manager import CredentialManager as CredentialsManager
    except ImportError:
        print("\nWARNING: Could not import CredentialsManager")
        print("Will try to run without credential management")
        CredentialsManager = None


def main():
    """Main entry point with enhanced logging and graceful shutdown"""
    
    # Setup enhanced logging first
    console_handler = setup_enhanced_logging(
        console_widget=None,
        log_level=logging.INFO
    )
    
    # Create specialized bot logger
    bot_logger = TradingBotLogger('TradingBot')
    
    # Initialize trade logger for Excel tracking
    trade_logger = TradeLogger(log_dir='logs/trades')
    
    # Print welcome banner
    print("\n" + "="*80)
    print(f"{'ANGEL ONE TRADING BOT - v3.0.0':^80}")
    print(f"{'Modular Architecture with Enhanced Features':^80}")
    print("="*80)
    bot_logger.system_status('STARTUP', 'System initialization in progress...')
    
    # Setup graceful exit handler
    def signal_handler(sig, frame):
        """Handle Ctrl+C and clean shutdown"""
        print("\n" + "="*80)
        bot_logger.system_status('SHUTDOWN', 'Shutdown signal received')
        print(f"{'Shutting Down Gracefully...':^80}")
        print("="*80)
        
        # Stop console handler
        try:
            console_handler.stop()
        except:
            pass
        
        # Get and display trade summary
        try:
            summary = trade_logger.get_trade_summary()
            print(f"\nToday's Trading Summary:")
            print(f"   {'─'*50}")
            print(f"   Total Trades: {summary['total_trades']}")
            print(f"   Open Trades: {summary['open_trades']}")
            print(f"   Closed Trades: {summary['closed_trades']}")
            print(f"   Winning Trades: {summary['winning_trades']}")
            print(f"   Losing Trades: {summary['losing_trades']}")
            print(f"   Win Rate: {summary['win_rate']:.1f}%")
            print(f"   {'─'*50}")
            
            pnl = summary['total_pnl']
            print(f"   Total P&L: Rs.{pnl:,.2f}")
            print(f"   {'─'*50}")
        except Exception as e:
            print(f"   Error generating summary: {e}")
        
        print(f"\nAll logs saved successfully!")
        print(f"   Trade Journal: logs/trades/trades_{datetime.now().strftime('%Y-%m-%d')}.xlsx")
        print(f"   System Logs: logs/{datetime.now().strftime('%Y-%m-%d')}/app.log")
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
        bot_logger.system_status('INIT', 'Loading credentials...')
        
        if CredentialsManager is None:
            print("\nWARNING: Running without credentials manager")
            print("Using default/fallback credentials")
            credentials = {
                'api_key': '',
                'client_id': '',
                'password': '',
                'totp': ''
            }
        else:
            creds_manager = CredentialsManager()
            credentials = creds_manager.load_credentials()
            
            if not credentials:
                print("\nWARNING: No credentials found!")
                print("You can configure them later through Settings in the UI")
                credentials = {
                    'api_key': '',
                    'client_id': '',
                    'password': '',
                    'totp': ''
                }
        
        bot_logger.system_status('INIT', 'Credentials loaded')
        
        # Initialize broker
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
            bot_logger.connection_status('connected', 'Angel One API')
        else:
            bot_logger.connection_status('disconnected', 'Angel One API - Using fallback mode')
        
        # Initialize analyzer
        bot_logger.system_status('INIT', 'Initializing analyzer...')
        analyzer = EnhancedAnalyzer(broker)
        
        # Initialize paper trader with trade logger
        bot_logger.system_status('INIT', 'Initializing paper trading system...')
        paper_trader = PaperTrader(
            initial_cash=100000,
            leverage=5.0,
            trade_logger=trade_logger
        )
        
        # Try to get real portfolio and funds
        try:
            holdings = broker.get_holdings()
            funds = broker.get_funds()
            bot_logger.portfolio_update(
                holdings_count=len(holdings.get('holdings', [])),
                total_value=holdings.get('total_value', 0),
                available_funds=funds
            )
        except Exception as e:
            bot_logger.warning(f"Could not fetch portfolio: {e}")
        
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
            version="3.0.0",
            build="20250926001"
        )
        
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
        print("  - trade_logger.py")
        print("  - console_handler.py")
        print("  - ui/professional_trading_ui.py")
        print("  - data_provider/angel_provider.py")
        print("  - order_manager/paper_trader.py")
        print("  - analyzer/enhanced_analyzer.py")
        print("  - config/credentials_manager.py")
        print("\n" + "="*80 + "\n")
        sys.exit(1)
        
    except Exception as e:
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
    print("\nPerforming pre-flight checks...")
    
    # Check required Python packages
    required_packages = ['openpyxl', 'pandas', 'tkinter']
    missing_packages = []
    
    for package in required_packages:
        try:
            if package == 'tkinter':
                import tkinter
            else:
                __import__(package)
            print(f"[OK] {package} is installed")
        except ImportError:
            missing_packages.append(package)
            print(f"[MISSING] {package} is NOT installed")
    
    if missing_packages:
        print("\n" + "="*80)
        print(f"{'MISSING PACKAGES':^80}")
        print("="*80)
        print("\nPlease install missing packages:")
        pkg_list = [p for p in missing_packages if p != 'tkinter']
        if pkg_list:
            print(f"  pip install {' '.join(pkg_list)}")
        if 'tkinter' in missing_packages:
            print("  tkinter: Usually comes with Python. Try reinstalling Python with tkinter support.")
        print("\n" + "="*80 + "\n")
        sys.exit(1)
    
    # Check required project files
    import os
    required_files = [
        'trade_logger.py',
        'console_handler.py',
        'ui/professional_trading_ui.py',
        'data_provider/angel_provider.py',
        'order_manager/paper_trader.py',
        'analyzer/enhanced_analyzer.py',
        'config/credentials_manager.py'
    ]
    
    missing_files = []
    for file in required_files:
        if os.path.exists(file):
            print(f"[OK] {file} exists")
        else:
            missing_files.append(file)
            print(f"[MISSING] {file} is MISSING")
    
    if missing_files:
        print("\n" + "="*80)
        print(f"{'MISSING FILES':^80}")
        print("="*80)
        print("\nThe following files are missing:")
        for file in missing_files:
            print(f"  - {file}")
        print("\nPlease ensure all required files are in place.")
        print("="*80 + "\n")
        sys.exit(1)
    
    print("\n[OK] All pre-flight checks passed!")
    print("="*80 + "\n")
    
    # All checks passed - run main
    main()



def main():
    """Main entry point with enhanced logging and graceful shutdown"""
    
    # Setup enhanced logging first
    console_handler = setup_enhanced_logging(
        console_widget=None,  # Will be connected to GUI later if needed
        log_level=logging.INFO
    )
    
    # Create specialized bot logger
    bot_logger = TradingBotLogger('TradingBot')
    
    # Initialize trade logger for Excel tracking
    trade_logger = TradeLogger(log_dir='logs/trades')
    
    # Print welcome banner
    print("\n" + "="*80)
    print(f"{'ANGEL ONE TRADING BOT - v3.0.0':^80}")
    print(f"{'Modular Architecture with Enhanced Features':^80}")
    print("="*80)
    bot_logger.system_status('STARTUP', 'System initialization in progress...')
    
    # Setup graceful exit handler
    def signal_handler(sig, frame):
        """Handle Ctrl+C and clean shutdown"""
        print("\n" + "="*80)
        bot_logger.system_status('SHUTDOWN', 'Shutdown signal received')
        print(f"{'🛑 Shutting Down Gracefully...':^80}")
        print("="*80)
        
        # Stop console handler
        try:
            console_handler.stop()
        except:
            pass
        
        # Get and display trade summary
        try:
            summary = trade_logger.get_trade_summary()
            print(f"\n📊 Today's Trading Summary:")
            print(f"   {'─'*50}")
            print(f"   Total Trades: {summary['total_trades']}")
            print(f"   Open Trades: {summary['open_trades']}")
            print(f"   Closed Trades: {summary['closed_trades']}")
            print(f"   Winning Trades: {summary['winning_trades']}")
            print(f"   Losing Trades: {summary['losing_trades']}")
            print(f"   Win Rate: {summary['win_rate']:.1f}%")
            print(f"   {'─'*50}")
            
            # Color code P&L
            pnl = summary['total_pnl']
            pnl_emoji = '🟢' if pnl >= 0 else '🔴'
            print(f"   {pnl_emoji} Total P&L: ₹{pnl:,.2f}")
            print(f"   {'─'*50}")
        except Exception as e:
            print(f"   Error generating summary: {e}")
        
        print(f"\n✅ All logs saved successfully!")
        print(f"   📁 Trade Journal: logs/trades/trades_{datetime.now().strftime('%Y-%m-%d')}.xlsx")
        print(f"   📝 System Logs: logs/{datetime.now().strftime('%Y-%m-%d')}/app.log")
        print("="*80)
        print(f"{'Thank you for using Angel One Trading Bot!':^80}")
        print("="*80 + "\n")
        
        # Clean exit
        sys.exit(0)
    
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Also register atexit handler for any unhandled exits
    atexit.register(lambda: print("\n✓ Trading bot stopped.\n"))
    
    try:
        # Load credentials
        bot_logger.system_status('INIT', 'Loading credentials...')
        creds_manager = CredentialsManager()
        credentials = creds_manager.load_credentials()
        
        if not credentials:
            print("\n❌ ERROR: No credentials found!")
            print("Please configure your Angel One credentials first.")
            print("Check config/credentials_path.txt\n")
            sys.exit(1)
        
        bot_logger.system_status('INIT', 'Credentials loaded successfully')
        
        # Initialize broker
        bot_logger.system_status('INIT', 'Connecting to Angel One API...')
        broker = AngelBroker(credentials, paper_mode=True)
        
        if broker.is_connected:
            bot_logger.connection_status('connected', 'Angel One API')
        else:
            bot_logger.connection_status('disconnected', 'Angel One API - Using fallback mode')
        
        # Initialize paper trader with trade logger
        bot_logger.system_status('INIT', 'Initializing paper trading system...')
        paper_trader = PaperTrader(
            initial_cash=100000,
            leverage=5.0,
            trade_logger=trade_logger  # Pass trade logger for Excel tracking
        )
        
        # Try to get real portfolio and funds
        try:
            holdings = broker.get_holdings()
            funds = broker.get_funds()
            bot_logger.portfolio_update(
                holdings_count=len(holdings.get('holdings', [])),
                total_value=holdings.get('total_value', 0),
                available_funds=funds
            )
        except Exception as e:
            bot_logger.warning(f"Could not fetch portfolio: {e}")
        
        bot_logger.system_status('READY', '✓ All systems initialized successfully')
        print("\n" + "="*80)
        print(f"{'🚀 SYSTEM READY - Starting GUI...':^80}")
        print("="*80 + "\n")
        
        # Create Qt Application
        app = QApplication(sys.argv)
        
        # Create and show main window
        window = TradingBotApp(
            broker=broker,
            paper_trader=paper_trader,
            trade_logger=trade_logger  # Pass to UI for display
        )
        
        window.show()
        
        # Start Qt event loop
        sys.exit(app.exec_())
        
    except KeyboardInterrupt:
        # This will trigger signal_handler
        pass
        
    except ImportError as e:
        print("\n" + "="*80)
        print(f"{'❌ IMPORT ERROR':^80}")
        print("="*80)
        print(f"\nMissing required module: {e}")
        print("\nPlease ensure all dependencies are installed:")
        print("  pip install PyQt5 openpyxl pandas")
        print("\nAnd all project files are present:")
        print("  - trade_logger.py")
        print("  - console_handler.py")
        print("  - ui/professional_trading_ui.py")
        print("  - data_provider/angel_provider.py")
        print("  - order_manager/paper_trader.py")
        print("  - config/credentials_manager.py")
        print("\n" + "="*80 + "\n")
        sys.exit(1)
        
    except Exception as e:
        bot_logger.error(f"Critical error: {e}")
        print("\n" + "="*80)
        print(f"{'❌ CRITICAL ERROR':^80}")
        print("="*80)
        print(f"\nError: {e}")
        print("\nFull traceback:")
        import traceback
        traceback.print_exc()
        print("\n" + "="*80 + "\n")
        sys.exit(1)


if __name__ == '__main__':
    # Pre-flight checks
    print("\nPerforming pre-flight checks...")
    
    # Check required Python packages
    required_packages = ['PyQt5', 'openpyxl', 'pandas']
    missing_packages = []
    
    for package in required_packages:
        try:
            __import__(package)
            print(f"✓ {package} is installed")
        except ImportError:
            missing_packages.append(package)
            print(f"✗ {package} is NOT installed")
    
    if missing_packages:
        print("\n" + "="*80)
        print(f"{'❌ MISSING PACKAGES':^80}")
        print("="*80)
        print("\nPlease install missing packages:")
        print(f"  pip install {' '.join(missing_packages)}")
        print("\n" + "="*80 + "\n")
        sys.exit(1)
    
    # Check required project files
    import os
    required_files = [
        'trade_logger.py',
        'console_handler.py',
        'ui/professional_trading_ui.py',
        'data_provider/angel_provider.py',
        'order_manager/paper_trader.py',
        'config/credentials_manager.py'
    ]
    
    missing_files = []
    for file in required_files:
        if os.path.exists(file):
            print(f"✓ {file} exists")
        else:
            missing_files.append(file)
            print(f"✗ {file} is MISSING")
    
    if missing_files:
        print("\n" + "="*80)
        print(f"{'❌ MISSING FILES':^80}")
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


import sys
import logging
import signal
import atexit
from datetime import datetime
from PyQt5.QtWidgets import QApplication

# Import enhanced logging and trade logger
try:
    from trade_logger import TradeLogger
    from console_handler import setup_enhanced_logging, TradingBotLogger
except ImportError:
    print("ERROR: Missing required files!")
    print("Please ensure trade_logger.py and console_handler.py exist in the project folder")
    sys.exit(1)

# Import your existing modules
from ui.professional_trading_ui import TradingBotApp
from data_provider.angel_provider import AngelBroker
from order_manager.paper_trader import PaperTrader
from config.credentials_manager import CredentialsManager


def main():
    """Main entry point with enhanced logging and graceful shutdown"""
    
    # Setup enhanced logging first
    console_handler = setup_enhanced_logging(
        console_widget=None,  # Will be connected to GUI later if needed
        log_level=logging.INFO
    )
    
    # Create specialized bot logger
    bot_logger = TradingBotLogger('TradingBot')
    
    # Initialize trade logger for Excel tracking
    trade_logger = TradeLogger(log_dir='logs/trades')
    
    # Print welcome banner
    print("\n" + "="*80)
    print(f"{'ANGEL ONE TRADING BOT - v3.0.0':^80}")
    print(f"{'Modular Architecture with Enhanced Features':^80}")
    print("="*80)
    bot_logger.system_status('STARTUP', 'System initialization in progress...')
    
    # Setup graceful exit handler
    def signal_handler(sig, frame):
        """Handle Ctrl+C and clean shutdown"""
        print("\n" + "="*80)
        bot_logger.system_status('SHUTDOWN', 'Shutdown signal received')
        print(f"{'🛑 Shutting Down Gracefully...':^80}")
        print("="*80)
        
        # Stop console handler
        try:
            console_handler.stop()
        except:
            pass
        
        # Get and display trade summary
        try:
            summary = trade_logger.get_trade_summary()
            print(f"\n📊 Today's Trading Summary:")
            print(f"   {'─'*50}")
            print(f"   Total Trades: {summary['total_trades']}")
            print(f"   Open Trades: {summary['open_trades']}")
            print(f"   Closed Trades: {summary['closed_trades']}")
            print(f"   Winning Trades: {summary['winning_trades']}")
            print(f"   Losing Trades: {summary['losing_trades']}")
            print(f"   Win Rate: {summary['win_rate']:.1f}%")
            print(f"   {'─'*50}")
            
            # Color code P&L
            pnl = summary['total_pnl']
            pnl_emoji = '🟢' if pnl >= 0 else '🔴'
            print(f"   {pnl_emoji} Total P&L: ₹{pnl:,.2f}")
            print(f"   {'─'*50}")
        except Exception as e:
            print(f"   Error generating summary: {e}")
        
        print(f"\n✅ All logs saved successfully!")
        print(f"   📁 Trade Journal: logs/trades/trades_{datetime.now().strftime('%Y-%m-%d')}.xlsx")
        print(f"   📝 System Logs: logs/{datetime.now().strftime('%Y-%m-%d')}/app.log")
        print("="*80)
        print(f"{'Thank you for using Angel One Trading Bot!':^80}")
        print("="*80 + "\n")
        
        # Clean exit
        sys.exit(0)
    
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Also register atexit handler for any unhandled exits
    atexit.register(lambda: print("\n✓ Trading bot stopped.\n"))
    
    try:
        # Load credentials
        bot_logger.system_status('INIT', 'Loading credentials...')
        creds_manager = CredentialsManager()
        credentials = creds_manager.load_credentials()
        
        if not credentials:
            print("\n❌ ERROR: No credentials found!")
            print("Please configure your Angel One credentials first.")
            print("Check config/credentials_path.txt\n")
            sys.exit(1)
        
        bot_logger.system_status('INIT', 'Credentials loaded successfully')
        
        # Initialize broker
        bot_logger.system_status('INIT', 'Connecting to Angel One API...')
        broker = AngelBroker(credentials, paper_mode=True)
        
        if broker.is_connected:
            bot_logger.connection_status('connected', 'Angel One API')
        else:
            bot_logger.connection_status('disconnected', 'Angel One API - Using fallback mode')
        
        # Initialize paper trader with trade logger
        bot_logger.system_status('INIT', 'Initializing paper trading system...')
        paper_trader = PaperTrader(
            initial_cash=100000,
            leverage=5.0,
            trade_logger=trade_logger  # Pass trade logger for Excel tracking
        )
        
        # Try to get real portfolio and funds
        try:
            holdings = broker.get_holdings()
            funds = broker.get_funds()
            bot_logger.portfolio_update(
                holdings_count=len(holdings.get('holdings', [])),
                total_value=holdings.get('total_value', 0),
                available_funds=funds
            )
        except Exception as e:
            bot_logger.warning(f"Could not fetch portfolio: {e}")
        
        bot_logger.system_status('READY', '✓ All systems initialized successfully')
        print("\n" + "="*80)
        print(f"{'🚀 SYSTEM READY - Starting GUI...':^80}")
        print("="*80 + "\n")
        
        # Create Qt Application
        app = QApplication(sys.argv)
        
        # Create and show main window
        window = TradingBotApp(
            broker=broker,
            paper_trader=paper_trader,
            trade_logger=trade_logger  # Pass to UI for display
        )
        
        window.show()
        
        # Start Qt event loop
        sys.exit(app.exec_())
        
    except KeyboardInterrupt:
        # This will trigger signal_handler
        pass
        
    except ImportError as e:
        print("\n" + "="*80)
        print(f"{'❌ IMPORT ERROR':^80}")
        print("="*80)
        print(f"\nMissing required module: {e}")
        print("\nPlease ensure all dependencies are installed:")
        print("  pip install PyQt5 openpyxl pandas")
        print("\nAnd all project files are present:")
        print("  - trade_logger.py")
        print("  - console_handler.py")
        print("  - ui/professional_trading_ui.py")
        print("  - data_provider/angel_provider.py")
        print("  - order_manager/paper_trader.py")
        print("  - config/credentials_manager.py")
        print("\n" + "="*80 + "\n")
        sys.exit(1)
        
    except Exception as e:
        bot_logger.error(f"Critical error: {e}")
        print("\n" + "="*80)
        print(f"{'❌ CRITICAL ERROR':^80}")
        print("="*80)
        print(f"\nError: {e}")
        print("\nFull traceback:")
        import traceback
        traceback.print_exc()
        print("\n" + "="*80 + "\n")
        sys.exit(1)


if __name__ == '__main__':
    # Pre-flight checks
    print("\nPerforming pre-flight checks...")
    
    # Check required Python packages
    required_packages = ['PyQt5', 'openpyxl', 'pandas']
    missing_packages = []
    
    for package in required_packages:
        try:
            __import__(package)
            print(f"✓ {package} is installed")
        except ImportError:
            missing_packages.append(package)
            print(f"✗ {package} is NOT installed")
    
    if missing_packages:
        print("\n" + "="*80)
        print(f"{'❌ MISSING PACKAGES':^80}")
        print("="*80)
        print("\nPlease install missing packages:")
        print(f"  pip install {' '.join(missing_packages)}")
        print("\n" + "="*80 + "\n")
        sys.exit(1)
    
    # Check required project files
    import os
    required_files = [
        'trade_logger.py',
        'console_handler.py',
        'ui/professional_trading_ui.py',
        'data_provider/angel_provider.py',
        'order_manager/paper_trader.py',
        'config/credentials_manager.py'
    ]
    
    missing_files = []
    for file in required_files:
        if os.path.exists(file):
            print(f"✓ {file} exists")
        else:
            missing_files.append(file)
            print(f"✗ {file} is MISSING")
    
    if missing_files:
        print("\n" + "="*80)
        print(f"{'❌ MISSING FILES':^80}")
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