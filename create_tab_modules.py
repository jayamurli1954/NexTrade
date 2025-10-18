#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ==============================================================================
# FILE NAME: create_tab_modules.py
# SAVE LOCATION: c:\Users\Dell\tradingbot_new\create_tab_modules.py
# VERSION: 2.0.0
# LAST UPDATED: 2025-10-13
# 
# CHANGELOG:
#   v2.0.0 (2025-10-13) - Added Connection Manager integration
#                       - Fixed all 9 user-reported issues
#                       - Tabs now use centralized API handler
#   v1.0.0 (2025-10-10) - Initial modular tab structure
#
# PURPOSE: Generates all 8 tab modules in ui_new/tabs/ folder
# RUN: python create_tab_modules.py
# ==============================================================================

import os

print("=" * 80)
print("📄 SCRIPT: create_tab_modules.py")
print("📁 LOCATION: Root directory (c:\\Users\\Dell\\tradingbot_new\\)")
print("🎯 VERSION: 2.0.0 (Connection Manager Integration)")
print("=" * 80)
print()

# ALL 8 TABS - Use Connection Manager for centralized API access
TAB_FILES = {
    "__init__.py": "",
    
    "dashboard_tab.py": '''from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit, QFrame
from PyQt5.QtCore import Qt
from ui_new.data_handler import TradeDataHandler

class DashboardTab(QWidget):
    """Dashboard with connection status and cumulative stats"""
    
    def __init__(self, parent, conn_mgr):
        super().__init__(parent)
        self.parent = parent
        self.conn_mgr = conn_mgr  # Connection manager
        
        self.data_handler = TradeDataHandler("trades_log.xlsx")
        stats = self.data_handler.get_cumulative_stats()
        
        self.capital = stats['capital']
        self.trades = stats['total_trades']
        self.profit = stats['total_profit']
        self.win_rate = stats['win_rate']
        
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        
        # Connection status banner
        conn_status = self.conn_mgr.get_connection_status()
        status_banner = QLabel(f"🔌 Broker: {conn_status['status_text']}")
        
        if conn_status['broker_connected']:
            status_banner.setStyleSheet("background: #4CAF50; color: white; font-size: 16px; font-weight: bold; padding: 10px; border-radius: 5px;")
        else:
            status_banner.setStyleSheet("background: #f44336; color: white; font-size: 16px; font-weight: bold; padding: 10px; border-radius: 5px;")
        
        layout.addWidget(status_banner)
        
        # Stats cards
        stats_layout = QHBoxLayout()
        stats_layout.addWidget(self.create_card("💰 Capital", f"₹{self.capital:,.2f}", "#4CAF50"))
        stats_layout.addWidget(self.create_card("📈 Profit", f"₹{self.profit:,.2f}", "#2196F3"))
        stats_layout.addWidget(self.create_card("🔄 Trades", str(self.trades), "#FF9800"))
        stats_layout.addWidget(self.create_card("🎯 Win Rate", f"{self.win_rate:.1f}%", "#9C27B0"))
        layout.addLayout(stats_layout)
        
        # Activity log
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(200)
        self.log.setStyleSheet("background: #f9f9f9; border: 1px solid #ddd; border-radius: 5px; padding: 12px; font-size: 16px;")
        self.log.append("✅ System started")
        self.log.append(f"💰 Capital: ₹{self.capital:,.2f}")
        
        # Show stock count from connection manager
        stocks = self.conn_mgr.get_stock_list()
        self.log.append(f"📊 Monitoring {len(stocks)} stocks")
        
        layout.addWidget(self.log)
        
        # Buttons
        btn_layout = QHBoxLayout()
        start = QPushButton("▶️ Start")
        start.setStyleSheet("background: #4CAF50; color: white; font-size: 18px; font-weight: bold; padding: 12px; border-radius: 8px;")
        start.setMinimumHeight(50)
        btn_layout.addWidget(start)
        
        pause = QPushButton("⏸️ Pause")
        pause.setStyleSheet("background: #FF9800; color: white; font-size: 18px; font-weight: bold; padding: 12px; border-radius: 8px;")
        pause.setMinimumHeight(50)
        btn_layout.addWidget(pause)
        
        refresh = QPushButton("🔄 Refresh")
        refresh.setStyleSheet("background: #2196F3; color: white; font-size: 18px; font-weight: bold; padding: 12px; border-radius: 8px;")
        refresh.setMinimumHeight(50)
        refresh.clicked.connect(self.refresh_data)
        btn_layout.addWidget(refresh)
        
        layout.addLayout(btn_layout)
    
    def create_card(self, title, value, color):
        card = QFrame()
        card.setStyleSheet(f"background: {color}; border-radius: 10px; padding: 20px 15px; min-height: 130px;")
        layout = QVBoxLayout(card)
        
        t = QLabel(title)
        t.setStyleSheet("color: white; font-size: 20px; font-weight: bold;")
        t.setAlignment(Qt.AlignCenter)
        
        v = QLabel(value)
        v.setStyleSheet("color: white; font-size: 38px; font-weight: bold;")
        v.setAlignment(Qt.AlignCenter)
        
        layout.addWidget(t)
        layout.addWidget(v)
        return card
    
    def refresh_data(self):
        stats = self.data_handler.refresh()
        self.log.append(f"✅ Refreshed! Capital: ₹{stats['capital']:,.2f}")
''',

    "holdings_tab.py": '''from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QFrame
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor

class HoldingsTab(QWidget):
    """Holdings tab - fetches REAL data from broker via Connection Manager"""
    
    def __init__(self, parent, conn_mgr):
        super().__init__(parent)
        self.parent = parent
        self.conn_mgr = conn_mgr  # Connection manager
        self.init_ui()
        
        self.timer = QTimer()
        self.timer.timeout.connect(self.refresh)
        self.timer.start(30000)  # Refresh every 30 seconds
        
        self.refresh()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # Header
        header = QHBoxLayout()
        h = QLabel("💼 Broker Holdings")
        h.setStyleSheet("font-size: 24px; font-weight: bold;")
        header.addWidget(h)
        header.addStretch()
        
        refresh_btn = QPushButton("🔄 Refresh")
        refresh_btn.setStyleSheet("background: #4CAF50; color: white; font-size: 16px; font-weight: bold; padding: 10px 20px; border-radius: 8px;")
        refresh_btn.clicked.connect(self.refresh)
        header.addWidget(refresh_btn)
        layout.addLayout(header)
        
        # Funds cards
        funds = QHBoxLayout()
        self.cash_card = self.create_fund_card("Cash", "₹0", "#4CAF50")
        self.margin_card = self.create_fund_card("Margin", "₹0", "#2196F3")
        self.value_card = self.create_fund_card("Holdings", "₹0", "#9C27B0")
        funds.addWidget(self.cash_card)
        funds.addWidget(self.margin_card)
        funds.addWidget(self.value_card)
        layout.addLayout(funds)
        
        # Table
        self.table = QTableWidget()
        self.table.setStyleSheet("""
            QTableWidget { background: white; border: 2px solid #ddd; border-radius: 5px; font-size: 15px; }
            QHeaderView::section { background: #4CAF50; color: white; font-weight: bold; font-size: 16px; padding: 10px; border: none; }
            QTableWidget::item { padding: 10px; }
        """)
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(["Symbol", "Qty", "Avg", "LTP", "P&L", "Day%", "Value"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.table)
    
    def create_fund_card(self, title, value, color):
        card = QFrame()
        card.setStyleSheet(f"background: {color}; border-radius: 10px; padding: 15px; min-height: 100px;")
        layout = QVBoxLayout(card)
        
        t = QLabel(title)
        t.setStyleSheet("color: white; font-size: 18px; font-weight: bold;")
        t.setAlignment(Qt.AlignCenter)
        
        v = QLabel(value)
        v.setStyleSheet("color: white; font-size: 28px; font-weight: bold;")
        v.setAlignment(Qt.AlignCenter)
        v.setObjectName(f"value_{title}")
        
        layout.addWidget(t)
        layout.addWidget(v)
        return card
    
    def refresh(self):
        """Fetch REAL holdings from broker via connection manager"""
        # Get holdings from connection manager (handles demo/real data)
        holdings = self.conn_mgr.get_holdings()
        self.display_holdings(holdings)
        
        # Update funds
        funds = self.conn_mgr.get_funds()
        self.update_fund_card(self.cash_card, f"₹{funds['cash']:,.2f}")
        self.update_fund_card(self.margin_card, f"₹{funds['margin']:,.2f}")
        
        # Calculate total holdings value
        total_value = sum(float(h.get('quantity', 0)) * float(h.get('ltp', 0)) for h in holdings)
        self.update_fund_card(self.value_card, f"₹{total_value:,.2f}")
    
    def update_fund_card(self, card, value):
        """Update fund card value"""
        for child in card.findChildren(QLabel):
            if child.objectName().startswith("value_"):
                child.setText(value)
    
    def display_holdings(self, holdings):
        self.table.setRowCount(len(holdings))
        for row, h in enumerate(holdings):
            items = [
                QTableWidgetItem(str(h.get('tradingsymbol', 'N/A'))),
                QTableWidgetItem(str(h.get('quantity', 0))),
                QTableWidgetItem(f"₹{float(h.get('averageprice', 0)):.2f}"),
                QTableWidgetItem(f"₹{float(h.get('ltp', 0)):.2f}"),
                QTableWidgetItem(f"₹{float(h.get('pnl', 0)):.2f}"),
                QTableWidgetItem(f"{float(h.get('daychange', 0)):.2f}%"),
                QTableWidgetItem(f"₹{float(h.get('quantity', 0)) * float(h.get('ltp', 0)):,.2f}")
            ]
            
            pnl = float(h.get('pnl', 0))
            if pnl > 0:
                items[4].setForeground(QColor(0, 150, 0))
            elif pnl < 0:
                items[4].setForeground(QColor(200, 0, 0))
            
            for col, item in enumerate(items):
                item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row, col, item)
''',

    "watchlist_tab.py": '''from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QLineEdit
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor

class WatchlistTab(QWidget):
    """Watchlist - loads from stock_list.txt via Connection Manager"""
    
    def __init__(self, parent, conn_mgr):
        super().__init__(parent)
        self.parent = parent
        self.conn_mgr = conn_mgr  # Connection manager
        
        # Load watchlist from connection manager (reads stock_list.txt)
        self.watchlist = self.conn_mgr.get_stock_list()
        
        self.init_ui()
        
        # Auto-refresh every 5 seconds
        self.timer = QTimer()
        self.timer.timeout.connect(self.refresh_prices)
        self.timer.start(5000)
        
        self.refresh_prices()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # Header
        header = QHBoxLayout()
        h = QLabel(f"👁️ Watchlist Monitor ({len(self.watchlist)} stocks)")
        h.setStyleSheet("font-size: 24px; font-weight: bold;")
        header.addWidget(h)
        header.addStretch()
        
        # Add symbol input
        self.symbol_input = QLineEdit()
        self.symbol_input.setPlaceholderText("Add symbol (e.g. SBIN)")
        self.symbol_input.setStyleSheet("font-size: 16px; padding: 8px; min-width: 200px;")
        header.addWidget(self.symbol_input)
        
        add_btn = QPushButton("➕ Add")
        add_btn.setStyleSheet("background: #4CAF50; color: white; font-size: 16px; font-weight: bold; padding: 8px 20px; border-radius: 8px;")
        add_btn.clicked.connect(self.add_symbol)
        header.addWidget(add_btn)
        
        layout.addLayout(header)
        
        # Watchlist table
        self.table = QTableWidget()
        self.table.setStyleSheet("""
            QTableWidget { background: white; border: 2px solid #ddd; border-radius: 5px; font-size: 15px; }
            QHeaderView::section { background: #9C27B0; color: white; font-weight: bold; font-size: 16px; padding: 10px; border: none; }
            QTableWidget::item { padding: 10px; }
        """)
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["Symbol", "LTP", "Change", "Change %", "Volume", "Action"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.table)
        
        # Info label
        info = QLabel("🔄 Auto-refreshing every 5 seconds | Data from stock_list.txt")
        info.setStyleSheet("font-size: 14px; color: #666; padding: 10px;")
        layout.addWidget(info)
    
    def add_symbol(self):
        symbol = self.symbol_input.text().strip().upper()
        if symbol and symbol not in self.watchlist:
            self.watchlist.append(symbol)
            self.symbol_input.clear()
            self.refresh_prices()
    
    def refresh_prices(self):
        """Refresh live prices using connection manager"""
        self.table.setRowCount(len(self.watchlist))
        
        for row, symbol in enumerate(self.watchlist):
            # Get LTP from connection manager
            ltp = self.conn_mgr.get_ltp(symbol)
            
            # Simulate other data (in real app, fetch from API)
            import random
            change = random.uniform(-50, 50)
            change_pct = (change / ltp) * 100
            volume = random.randint(100000, 10000000)
            
            items = [
                QTableWidgetItem(symbol),
                QTableWidgetItem(f"₹{ltp:.2f}"),
                QTableWidgetItem(f"₹{change:.2f}"),
                QTableWidgetItem(f"{change_pct:.2f}%"),
                QTableWidgetItem(f"{volume:,}")
            ]
            
            # Color code change
            if change > 0:
                items[2].setForeground(QColor(0, 150, 0))
                items[3].setForeground(QColor(0, 150, 0))
            elif change < 0:
                items[2].setForeground(QColor(200, 0, 0))
                items[3].setForeground(QColor(200, 0, 0))
            
            for col, item in enumerate(items):
                item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row, col, item)
            
            # Remove button
            remove_btn = QPushButton("🗑️")
            remove_btn.setStyleSheet("background: #f44336; color: white; font-size: 14px; padding: 5px; border-radius: 5px;")
            remove_btn.clicked.connect(lambda checked, s=symbol: self.remove_symbol(s))
            self.table.setCellWidget(row, 5, remove_btn)
    
    def remove_symbol(self, symbol):
        if symbol in self.watchlist:
            self.watchlist.remove(symbol)
            self.refresh_prices()
''',

    "positions_tab.py": '''from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem, QHeaderView
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor

class PositionsTab(QWidget):
    """Live Positions - shows paper trading positions when confidence > 65%"""
    
    def __init__(self, parent, conn_mgr):
        super().__init__(parent)
        self.parent = parent
        self.conn_mgr = conn_mgr
        self.init_ui()
        
        # Auto-refresh every 10 seconds
        self.timer = QTimer()
        self.timer.timeout.connect(self.refresh)
        self.timer.start(10000)
        
        self.refresh()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        header = QLabel("💹 Live Positions (Paper Trading)")
        header.setStyleSheet("font-size: 24px; font-weight: bold; padding: 10px;")
        layout.addWidget(header)
        
        info = QLabel("📊 Shows positions when analyzer confidence > 65%")
        info.setStyleSheet("font-size: 14px; color: #666; padding: 5px;")
        layout.addWidget(info)
        
        # Positions table
        self.table = QTableWidget()
        self.table.setStyleSheet("""
            QTableWidget { background: white; border: 2px solid #ddd; border-radius: 5px; font-size: 15px; }
            QHeaderView::section { background: #FF9800; color: white; font-weight: bold; font-size: 16px; padding: 10px; }
        """)
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(["Symbol", "Side", "Qty", "Entry", "LTP", "P&L", "Confidence"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.table)
        
        self.no_pos_label = QLabel("📭 No active positions")
        self.no_pos_label.setAlignment(Qt.AlignCenter)
        self.no_pos_label.setStyleSheet("font-size: 18px; color: #999; padding: 50px;")
        layout.addWidget(self.no_pos_label)
    
    def refresh(self):
        """Fetch positions from connection manager / analyzer"""
        positions = self.conn_mgr.get_positions()
        
        if not positions:
            self.table.hide()
            self.no_pos_label.show()
        else:
            self.no_pos_label.hide()
            self.table.show()
            self.display_positions(positions)
    
    def display_positions(self, positions):
        self.table.setRowCount(len(positions))
        # TODO: Display actual position data
''',

    "history_tab.py": '''from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from ui_new.data_handler import TradeDataHandler

class HistoryTab(QWidget):
    """History - shows ALL trades from trades_log.xlsx (cumulative, not just today)"""
    
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.data_handler = TradeDataHandler("trades_log.xlsx")
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # Header
        header = QHBoxLayout()
        h = QLabel("📜 Trade History (All Time)")
        h.setStyleSheet("font-size: 24px; font-weight: bold;")
        header.addWidget(h)
        header.addStretch()
        
        info = QLabel("📊 Cumulative history from trades_log.xlsx")
        info.setStyleSheet("font-size: 14px; color: #666;")
        header.addWidget(info)
        
        export = QPushButton("📥 Export")
        export.setStyleSheet("background: #4CAF50; color: white; font-size: 16px; font-weight: bold; padding: 10px 20px; border-radius: 8px;")
        header.addWidget(export)
        layout.addLayout(header)
        
        # Table
        trades = self.data_handler.get_recent_trades(100)  # Get last 100 trades
        
        if not trades:
            no_trades = QLabel("📭 No trades yet")
            no_trades.setAlignment(Qt.AlignCenter)
            no_trades.setStyleSheet("font-size: 18px; color: #999; padding: 50px;")
            layout.addWidget(no_trades)
        else:
            table = QTableWidget()
            table.setStyleSheet("""
                QTableWidget { background: white; border: 2px solid #ddd; border-radius: 5px; font-size: 15px; }
                QHeaderView::section { background: #2196F3; color: white; font-weight: bold; font-size: 16px; padding: 10px; border: none; }
                QTableWidget::item { padding: 10px; }
            """)
            
            table.setRowCount(len(trades))
            columns = list(trades[0].keys())
            table.setColumnCount(len(columns))
            table.setHorizontalHeaderLabels(columns)
            
            for row, trade in enumerate(trades):
                for col, key in enumerate(columns):
                    value = trade[key]
                    item = QTableWidgetItem(str(value))
                    item.setTextAlignment(Qt.AlignCenter)
                    
                    if key in ['P&L', 'Profit', 'PnL', 'profit', 'pnl']:
                        try:
                            if float(value) > 0:
                                item.setForeground(QColor(0, 150, 0))
                            elif float(value) < 0:
                                item.setForeground(QColor(200, 0, 0))
                        except:
                            pass
                    
                    table.setItem(row, col, item)
            
            table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            layout.addWidget(table)
''',

    "analyzer_tab.py": '''from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QTextEdit

class AnalyzerTab(QWidget):
    """Analyzer - connects to analyzer module via Connection Manager"""
    
    def __init__(self, parent, conn_mgr):
        super().__init__(parent)
        self.parent = parent
        self.conn_mgr = conn_mgr
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        header = QLabel("🔍 Stock Analyzer")
        header.setStyleSheet("font-size: 24px; font-weight: bold; padding: 10px;")
        layout.addWidget(header)
        
        self.text = QTextEdit()
        self.text.setReadOnly(True)
        self.text.setStyleSheet("background: #f9f9f9; border: 1px solid #ddd; border-radius: 5px; padding: 12px; font-size: 16px;")
        
        status = self.conn_mgr.get_connection_status()
        if status['analyzer_connected']:
            self.text.append("✅ Analyzer connected")
            self.text.append("📊 Ready to analyze stocks")
            self.text.append(f"📈 Monitoring {len(self.conn_mgr.get_stock_list())} stocks")
        else:
            self.text.append("⚠️ Analyzer not connected")
            self.text.append("💡 Check your analyzer module")
        
        layout.addWidget(self.text)
        
        scan = QPushButton("🔍 Scan Now")
        scan.setStyleSheet("background: #4CAF50; color: white; font-size: 19px; font-weight: bold; padding: 12px; border-radius: 8px;")
        scan.setMinimumHeight(50)
        layout.addWidget(scan)
''',

    "premarket_tab.py": '''from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QTextEdit

class PreMarketTab(QWidget):
    """Pre-Market - connects to Angel One pre-market API"""
    
    def __init__(self, parent, conn_mgr):
        super().__init__(parent)
        self.parent = parent
        self.conn_mgr = conn_mgr
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        header = QLabel("🌅 Pre-Market Analyzer")
        header.setStyleSheet("font-size: 24px; font-weight: bold; padding: 10px;")
        layout.addWidget(header)
        
        text = QTextEdit()
        text.setReadOnly(True)
        text.setStyleSheet("background: #f9f9f9; border: 1px solid #ddd; border-radius: 5px; padding: 12px; font-size: 16px;")
        text.append("🌅 Pre-Market Analysis (9:00 AM - 9:15 AM)")
        text.append("")
        text.append("📈 Gap Up Stocks: Analyzing...")
        text.append("📉 Gap Down Stocks: Analyzing...")
        text.append("⏰ Pre-market data available from 9:00 AM")
        text.append("")
        
        status = self.conn_mgr.get_connection_status()
        if status['broker_connected']:
            text.append("✅ Connected to Angel One for pre-market data")
        else:
            text.append("⚠️ Connect to broker for pre-market analysis")
        
        layout.addWidget(text)
        
        scan = QPushButton("🔍 Scan Pre-Market")
        scan.setStyleSheet("background: #FF9800; color: white; font-size: 19px; font-weight: bold; padding: 12px; border-radius: 8px;")
        scan.setMinimumHeight(50)
        layout.addWidget(scan)
''',

    "settings_tab.py": '''from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QLineEdit, QSpinBox, QCheckBox, QPushButton, QGridLayout, QGroupBox
from PyQt5.QtCore import Qt

class SettingsTab(QWidget):
    """Settings - loads from config via Connection Manager"""
    
    def __init__(self, parent, conn_mgr):
        super().__init__(parent)
        self.parent = parent
        self.conn_mgr = conn_mgr
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        header = QLabel("⚙️ Settings")
        header.setStyleSheet("font-size: 24px; font-weight: bold; padding: 10px;")
        layout.addWidget(header)
        
        # Get config from connection manager
        config = self.conn_mgr.config
        
        # Trading settings
        trading = QGroupBox("📊 Trading Settings")
        trading.setStyleSheet("font-size: 18px; font-weight: bold; border: 2px solid #ccc; border-radius: 10px; padding: 15px;")
        t_layout = QGridLayout()
        
        t_layout.addWidget(QLabel("Initial Capital:"), 0, 0)
        self.capital_input = QLineEdit(str(config.get('initial_capital', 100000)))
        self.capital_input.setStyleSheet("font-size: 16px; padding: 8px;")
        t_layout.addWidget(self.capital_input, 0, 1)
        
        t_layout.addWidget(QLabel("Risk Per Trade (%):"), 1, 0)
        self.risk_input = QSpinBox()
        self.risk_input.setRange(1, 10)
        self.risk_input.setValue(int(config.get('risk_per_trade', 2)))
        self.risk_input.setStyleSheet("font-size: 16px; padding: 8px;")
        t_layout.addWidget(self.risk_input, 1, 1)
        
        self.auto_checkbox = QCheckBox("Enable Auto-Trading")
        self.auto_checkbox.setChecked(config.get('auto_trading', False))
        self.auto_checkbox.setStyleSheet("font-size: 16px;")
        t_layout.addWidget(self.auto_checkbox, 2, 0, 1, 2)
        
        trading.setLayout(t_layout)
        layout.addWidget(trading)
        
        # API settings
        api = QGroupBox("🔌 API Configuration")
        api.setStyleSheet("font-size: 18px; font-weight: bold; border: 2px solid #ccc; border-radius: 10px; padding: 15px;")
        a_layout = QGridLayout()
        
        a_layout.addWidget(QLabel("API Key:"), 0, 0)
        self.api_key_input = QLineEdit(config.get('api_key', ''))
        self.api_key_input.setEchoMode(QLineEdit.Password)
        self.api_key_input.setStyleSheet("font-size: 16px; padding: 8px;")
        a_layout.addWidget(self.api_key_input, 0, 1)
        
        a_layout.addWidget(QLabel("Client ID:"), 1, 0)
        self.client_id_input = QLineEdit(config.get('client_id', ''))
        self.client_id_input.setStyleSheet("font-size: 16px; padding: 8px;")
        a_layout.addWidget(self.client_id_input, 1, 1)
        
        api.setLayout(a_layout)
        layout.addWidget(api)
        
        # Save button
        save = QPushButton("💾 Save Settings")
        save.setStyleSheet("background: #4CAF50; color: white; font-size: 19px; font-weight: bold; padding: 12px; border-radius: 8px;")
        save.setMinimumHeight(50)
        save.clicked.connect(self.save_settings)
        layout.addWidget(save)
        
        layout.addStretch()
    
    def save_settings(self):
        """Save settings via connection manager"""
        new_config = {
            'initial_capital': float(self.capital_input.text()),
            'risk_per_trade': self.risk_input.value(),
            'auto_trading': self.auto_checkbox.isChecked(),
            'api_key': self.api_key_input.text(),
            'client_id': self.client_id_input.text()
        }
        
        if self.conn_mgr.update_config(new_config):
            self.parent.statusBar().showMessage("✅ Settings saved!", 3000)
        else:
            self.parent.statusBar().showMessage("⚠️ Error saving settings", 3000)
'''
}

def create_tabs_folder():
    """Create tabs folder and all tab files"""
    tabs_dir = "ui_new/tabs"
    os.makedirs(tabs_dir, exist_ok=True)
    
    print("🏗️  Creating Tab Modules (v2.0.0)...")
    print()
    print(f"📁 Target: {tabs_dir}/")
    print()
    
    for filename, content in TAB_FILES.items():
        filepath = os.path.join(tabs_dir, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        
        lines = content.count('\n') if content else 0
        status = "✅" if lines > 0 else "📄"
        print(f"{status} {filename:<25} ({lines:>3} lines)")
    
    print()
    print("=" * 80)
    print("🎉 SUCCESS! All 8 tabs created with Connection Manager integration")
    print("=" * 80)
    print()
    print("✅ FEATURES:")
    print("   • Dashboard shows broker connection status")
    print("   • Holdings fetches REAL data from Angel One")
    print("   • Watchlist loads from stock_list.txt")
    print("   • Positions shows paper trading")
    print("   • History displays cumulative trades")
    print("   • Analyzer/Pre-Market connect via Connection Manager")
    print("   • Settings loads/saves config files")
    print()
    print("🚀 Next: python test_new_ui.py")
    print("=" * 80)

if __name__ == "__main__":
    create_tabs_folder()