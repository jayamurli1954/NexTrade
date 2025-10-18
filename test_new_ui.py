#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ==============================================================================
# FILE: test_new_ui.py
# LOCATION: c:\Users\Dell\tradingbot_new\test_new_ui.py
# VERSION: 4.2.0 - Super fast startup with lazy token loading
# LAST UPDATED: 2025-10-13
#
# FEATURES:
# - Instant UI startup (no delays!)
# - Lazy token loading (only when connecting)
# - Manual connect via dashboard button
# ==============================================================================

import sys
import os

# Add paths
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'ui_new'))
sys.path.insert(0, os.path.dirname(__file__))

from PyQt5.QtWidgets import QApplication
from ui_new.main_window import MainWindow
from ui_new.connection_manager import get_connection_manager
from trade_logger import TradeLogger

def main():
    print("🚀 Launching New Trading Bot UI...")
    print("=" * 50)
    
    # Initialize connection manager (singleton) - INSTANT!
    # Token loading is deferred until connection
    conn_mgr = get_connection_manager()
    
    # Initialize trade logger
    trade_logger = TradeLogger()
    print(f"✅ Loaded {len(trade_logger.trades)} trades from trades_log.xlsx")
    
    print("✅ UI Ready to launch (instant startup)!")
    print("💡 Symbol tokens will load automatically when connecting to broker")
    print("=" * 50)
    
    # Create Qt application
    app = QApplication(sys.argv)
    
    # Create and show window IMMEDIATELY
    window = MainWindow(conn_mgr, trade_logger)
    window.show()
    
    print("✅ UI Launched instantly!")
    print("\n📊 Dashboard Features:")
    print("   - Capital tracking")
    print("   - Trade statistics")
    
    # Calculate quick stats
    capital = conn_mgr.config.get('initial_capital', 100000)
    trades_count = len(trade_logger.trades)
    
    if trades_count > 0:
        total_profit = sum(t.get('profit', 0) for t in trade_logger.trades if t.get('profit'))
        winning_trades = sum(1 for t in trade_logger.trades if t.get('profit', 0) > 0)
        win_rate = (winning_trades / trades_count * 100) if trades_count > 0 else 0
        
        print(f"   - Current Capital: ₹{capital:,.0f}")
        print(f"   - Total Trades: {trades_count}")
        print(f"   - Total Profit: ₹{total_profit:,.0f}")
        print(f"   - Win Rate: {win_rate:.1f}%")
    else:
        print(f"   - Initial Capital: ₹{capital:,.0f}")
        print(f"   - No trades yet")
    
    print("\n💡 Next Steps:")
    print("   1. Click 'Connect' button in Dashboard to connect to broker")
    print("   2. Tokens will load automatically (first time only)")
    print("   3. WebSocket will start streaming real-time data")
    print("   4. Use Analyzer tab to scan and trade")
    print("\nClose the window to exit.")
    print("=" * 50)
    
    # Run application
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()