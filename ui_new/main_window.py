#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ==============================================================================
# FILE: main_window.py
# VERSION: 4.0.0 - Complete integration with Paper Trading
# LOCATION: c:\Users\Dell\tradingbot_new\ui_new\main_window.py
# ==============================================================================

from PyQt5.QtWidgets import QMainWindow, QTabWidget, QWidget, QStatusBar
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QIcon
import qtawesome as qta

# Import tabs
from tabs.dashboard_tab import DashboardTab
from tabs.holdings_tab import HoldingsTab
from tabs.watchlist_tab import WatchlistTab
from tabs.positions_tab import PositionsTab
from tabs.history_tab import HistoryTab
from tabs.analyzer_tab import AnalyzerTab
from tabs.premarket_tab import PreMarketTab
from tabs.settings_tab import SettingsTab
from tabs.paper_trading_tab import PaperTradingTab  # NEW

class MainWindow(QMainWindow):
    """
    Main Trading Bot Window
    
    Now includes:
    - Complete paper trading integration
    - Analyzer -> Paper Trading workflow
    - Auto-monitoring of trades
    """
    
    def __init__(self, conn_mgr, trade_logger):
        super().__init__()
        self.conn_mgr = conn_mgr
        self.trade_logger = trade_logger
        
        self.setWindowTitle("Angel One Trading Bot - Modular")
        self.setGeometry(100, 100, 1600, 900)
        
        self.init_ui()
        
        # Update connection status periodically
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self.update_connection_status)
        self.status_timer.start(5000)  # Every 5 seconds
        
        self.update_connection_status()
    
    def init_ui(self):
        """Initialize UI components"""
        
        # Create tab widget
        self.tabs = QTabWidget()
        self.tabs.setTabPosition(QTabWidget.North)
        self.setCentralWidget(self.tabs)
        
        # Initialize all tabs
        self.dashboard_tab = DashboardTab(self, self.conn_mgr, self.trade_logger)
        self.holdings_tab = HoldingsTab(self, self.conn_mgr)
        self.watchlist_tab = WatchlistTab(self, self.conn_mgr)
        self.positions_tab = PositionsTab(self, self.conn_mgr)
        self.history_tab = HistoryTab(self, self.trade_logger)
        
        # CRITICAL: Create paper trading tab FIRST
        self.paper_trading_tab = PaperTradingTab(self, self.conn_mgr)
        
        # Then create analyzer tab with paper trading reference
        self.analyzer_tab = AnalyzerTab(self, self.conn_mgr, self.paper_trading_tab)
        
        self.premarket_tab = PreMarketTab(self, self.conn_mgr)
        self.settings_tab = SettingsTab(self, self.conn_mgr)
        
        # Add tabs in order
        icon_color = '#ecf0f1'  # Light gray color for icons
        self.tabs.addTab(self.dashboard_tab, qta.icon('fa5s.tachometer-alt', color=icon_color), "Dashboard")
        self.tabs.addTab(self.holdings_tab, qta.icon('fa5s.briefcase', color=icon_color), "Holdings")
        self.tabs.addTab(self.watchlist_tab, qta.icon('fa5s.eye', color=icon_color), "Watchlist")
        self.tabs.addTab(self.positions_tab, qta.icon('fa5s.chart-line', color=icon_color), "Live Positions")
        self.tabs.addTab(self.history_tab, qta.icon('fa5s.history', color=icon_color), "History")
        self.tabs.addTab(self.analyzer_tab, qta.icon('fa5s.search-dollar', color=icon_color), "Analyzer")
        self.tabs.addTab(self.paper_trading_tab, qta.icon('fa5s.file-invoice-dollar', color=icon_color), "Paper Trading")
        self.tabs.addTab(self.premarket_tab, qta.icon('fa5s.sun', color=icon_color), "Pre-Market")
        self.tabs.addTab(self.settings_tab, qta.icon('fa5s.cog', color=icon_color), "Settings")
        
        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.setStyleSheet("""
            QStatusBar {
                background: #263238;
                color: white;
                font-size: 13px;
                padding: 5px;
            }
        """)
        
        # Connection status label
        self.connection_label = QWidget()
        self.status_bar.addPermanentWidget(self.connection_label)
    
    def update_connection_status(self):
        """Update connection status in status bar"""
        status = self.conn_mgr.get_connection_status()
        
        broker_status = "✅ Broker" if status['broker_connected'] else "❌ Broker"
        ws_status = "✅ WebSocket" if status.get('websocket_connected', False) else "❌ WebSocket"
        analyzer_status = "✅ Analyzer" if status.get('analyzer_connected', False) else "⚠️ Analyzer"
        
        # Count active paper trades
        active_trades = len(self.paper_trading_tab.active_trades) if hasattr(self, 'paper_trading_tab') else 0
        
        # Get stock count
        stock_count = len(self.conn_mgr.get_stock_list())
        
        status_text = (
            f"{broker_status} | {ws_status} | {analyzer_status} | "
            f"📈 {stock_count} Stocks | 📊 {active_trades} Active Trades"
        )
        
        self.status_bar.showMessage(status_text)
    
    def closeEvent(self, event):
        """Handle window close event"""
        # Save paper trades before closing
        if hasattr(self, 'paper_trading_tab'):
            self.paper_trading_tab.save_trades()
        
        # Close WebSocket connection
        if self.conn_mgr:
            self.conn_mgr.close()
        
        event.accept()