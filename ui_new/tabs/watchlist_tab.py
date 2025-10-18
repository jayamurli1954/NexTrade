#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ==============================================================================
# FILE: watchlist_tab.py
# VERSION: 3.1.0 - Fixed scrolling + WebSocket integration
# ==============================================================================

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QPushButton, QTableWidget, QTableWidgetItem, 
                             QHeaderView, QLineEdit, QScrollBar)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor
import random

class WatchlistTab(QWidget):
    """Watchlist Monitor with working scroller"""
    
    def __init__(self, parent, conn_mgr):
        super().__init__(parent)
        self.parent = parent
        self.conn_mgr = conn_mgr
        
        self.watchlist = self.conn_mgr.get_stock_list()
        
        self.init_ui()
        
        # Auto-refresh every 30 seconds
        self.timer = QTimer()
        self.timer.timeout.connect(self.refresh_prices)
        self.timer.start(30000)
        
        self.refresh_prices()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        
        # Header
        header = QHBoxLayout()
        
        title = QLabel(f"👁️ Watchlist Monitor ({len(self.watchlist)} stocks)")
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: #333;")
        header.addWidget(title)
        
        header.addStretch()
        
        # Add symbol input
        self.symbol_input = QLineEdit()
        self.symbol_input.setPlaceholderText("Add symbol (e.g. SBIN)")
        self.symbol_input.setStyleSheet("""
            font-size: 16px; 
            padding: 8px; 
            min-width: 200px;
            border: 2px solid #ddd;
            border-radius: 5px;
        """)
        self.symbol_input.returnPressed.connect(self.add_symbol)
        header.addWidget(self.symbol_input)
        
        # Add button
        add_btn = QPushButton("➕ Add")
        add_btn.setStyleSheet("""
            background: #4CAF50; 
            color: white; 
            font-size: 16px; 
            font-weight: bold; 
            padding: 8px 20px; 
            border-radius: 8px;
            border: none;
        """)
        add_btn.clicked.connect(self.add_symbol)
        add_btn.setCursor(Qt.PointingHandCursor)
        header.addWidget(add_btn)
        
        layout.addLayout(header)
        
        # Table with FIXED scrolling
        self.table = QTableWidget()
        self.table.setStyleSheet("""
            QTableWidget { 
                background: white; 
                border: 2px solid #ddd; 
                border-radius: 5px; 
                font-size: 15px;
                gridline-color: #e0e0e0;
            }
            QHeaderView::section { 
                background: #9C27B0; 
                color: white; 
                font-weight: bold; 
                font-size: 16px; 
                padding: 10px; 
                border: none; 
            }
            QTableWidget::item { 
                padding: 10px;
                border-bottom: 1px solid #f0f0f0;
            }
            QTableWidget::item:selected {
                background: #E1BEE7;
            }
        """)
        
        # Set columns
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "Symbol", "LTP", "Change", "Change %", "Volume", "Action"
        ])
        
        # CRITICAL FIX: Enable vertical scrolling
        self.table.setVerticalScrollMode(QTableWidget.ScrollPerPixel)
        self.table.setHorizontalScrollMode(QTableWidget.ScrollPerPixel)
        
        # Column widths
        header_view = self.table.horizontalHeader()
        header_view.setSectionResizeMode(0, QHeaderView.Stretch)  # Symbol
        header_view.setSectionResizeMode(1, QHeaderView.Stretch)  # LTP
        header_view.setSectionResizeMode(2, QHeaderView.Stretch)  # Change
        header_view.setSectionResizeMode(3, QHeaderView.Stretch)  # Change %
        header_view.setSectionResizeMode(4, QHeaderView.Stretch)  # Volume
        header_view.setSectionResizeMode(5, QHeaderView.Fixed)    # Action
        self.table.setColumnWidth(5, 100)
        
        # Enable sorting
        self.table.setSortingEnabled(True)
        
        # CRITICAL: Set minimum height to show scrollbar
        self.table.setMinimumHeight(400)
        
        layout.addWidget(self.table)
        
        # Footer
        self.info_label = QLabel(
            f"🔄 Auto-refreshing every 30 seconds | "
            f"{len(self.watchlist)} stocks loaded from watchlist.json"
        )
        self.info_label.setStyleSheet("""
            font-size: 14px; 
            color: #666; 
            padding: 10px;
            background: #f9f9f9;
            border-radius: 5px;
        """)
        self.info_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.info_label)
    
    def add_symbol(self):
        """Add new symbol to watchlist"""
        symbol = self.symbol_input.text().strip().upper()
        
        if not symbol:
            self.parent.statusBar().showMessage("⚠️ Please enter a symbol", 3000)
            return
        
        if symbol in self.watchlist:
            self.parent.statusBar().showMessage(f"⚠️ {symbol} already in watchlist", 3000)
            return
        
        self.watchlist.append(symbol)
        self.conn_mgr.add_stock(symbol)
        
        self.symbol_input.clear()
        self.update_header()
        self.refresh_prices()
        
        self.parent.statusBar().showMessage(f"✅ Added {symbol} to watchlist", 3000)
    
    def remove_symbol(self, symbol):
        """Remove symbol from watchlist"""
        if symbol in self.watchlist:
            self.watchlist.remove(symbol)
            self.conn_mgr.remove_stock(symbol)
            
            self.update_header()
            self.refresh_prices()
            
            self.parent.statusBar().showMessage(f"✅ Removed {symbol}", 3000)
    
    def update_header(self):
        """Update header with current count"""
        self.info_label.setText(
            f"🔄 Auto-refreshing every 30 seconds | "
            f"{len(self.watchlist)} stocks in watchlist"
        )
    
    def refresh_prices(self):
        """Refresh prices from WebSocket cache"""
        self.parent.statusBar().showMessage("🔄 Updating prices...", 2000)
        
        # Disable sorting during update
        self.table.setSortingEnabled(False)
        
        self.table.setRowCount(len(self.watchlist))
        
        # Batch fetch LTPs from WebSocket cache
        ltp_data = self.conn_mgr.get_ltp_batch(self.watchlist)
        
        for row, symbol in enumerate(self.watchlist):
            ltp = ltp_data.get(symbol, 0)
            
            # Simulated data (you can enhance with real data)
            change = random.uniform(-50, 50)
            change_pct = (change / ltp) * 100 if ltp > 0 else 0
            volume = random.randint(100000, 10000000)
            
            # Create items
            items = [
                QTableWidgetItem(symbol),
                QTableWidgetItem(f"₹{ltp:.2f}"),
                QTableWidgetItem(f"₹{change:.2f}"),
                QTableWidgetItem(f"{change_pct:.2f}%"),
                QTableWidgetItem(f"{volume:,}")
            ]
            
            # Color coding
            if change > 0:
                items[2].setForeground(QColor(0, 150, 0))
                items[3].setForeground(QColor(0, 150, 0))
            elif change < 0:
                items[2].setForeground(QColor(200, 0, 0))
                items[3].setForeground(QColor(200, 0, 0))
            
            # Center align
            for col, item in enumerate(items):
                item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row, col, item)
            
            # Remove button
            remove_btn = QPushButton("🗑️")
            remove_btn.setStyleSheet("""
                background: #f44336; 
                color: white; 
                font-size: 14px; 
                padding: 5px; 
                border-radius: 5px;
                border: none;
            """)
            remove_btn.setCursor(Qt.PointingHandCursor)
            remove_btn.clicked.connect(lambda checked, s=symbol: self.remove_symbol(s))
            remove_btn.setToolTip(f"Remove {symbol}")
            self.table.setCellWidget(row, 5, remove_btn)
        
        # Re-enable sorting
        self.table.setSortingEnabled(True)
        
        self.parent.statusBar().showMessage(
            f"✅ Updated {len(self.watchlist)} stocks", 2000
        )