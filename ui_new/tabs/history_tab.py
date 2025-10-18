#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ==============================================================================
# FILE: history_tab.py
# VERSION: 2.1.0 - Fixed trade_logger parameter
# LOCATION: c:\Users\Dell\tradingbot_new\ui_new\tabs\history_tab.py
# ==============================================================================

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor

class HistoryTab(QWidget):
    """Trade History - View past trades from trade logger"""
    
    def __init__(self, parent, trade_logger=None):
        super().__init__(parent)
        self.parent = parent
        self.trade_logger = trade_logger
        
        self.init_ui()
        self.refresh_history()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        
        # Header
        header = QHBoxLayout()
        
        title = QLabel("📜 Trade History")
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: #333;")
        header.addWidget(title)
        
        header.addStretch()
        
        # Refresh button
        refresh_btn = QPushButton("🔄 Refresh")
        refresh_btn.setStyleSheet("""
            background: #2196F3; 
            color: white; 
            font-size: 16px; 
            font-weight: bold; 
            padding: 10px 25px; 
            border-radius: 8px;
        """)
        refresh_btn.clicked.connect(self.refresh_history)
        refresh_btn.setCursor(Qt.PointingHandCursor)
        header.addWidget(refresh_btn)
        
        # Export button
        export_btn = QPushButton("📥 Export")
        export_btn.setStyleSheet("""
            background: #FF9800; 
            color: white; 
            font-size: 16px; 
            font-weight: bold; 
            padding: 10px 25px; 
            border-radius: 8px;
        """)
        export_btn.clicked.connect(self.export_history)
        export_btn.setCursor(Qt.PointingHandCursor)
        header.addWidget(export_btn)
        
        layout.addLayout(header)
        
        # History table
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
                background: #607D8B; 
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
        """)
        
        self.table.setColumnCount(9)
        self.table.setHorizontalHeaderLabels([
            "Date", "Symbol", "Action", "Entry", "Exit", "Qty", "P&L ₹", "P&L %", "Status"
        ])
        
        header_view = self.table.horizontalHeader()
        header_view.setSectionResizeMode(QHeaderView.Stretch)
        
        self.table.setVerticalScrollMode(QTableWidget.ScrollPerPixel)
        self.table.setSortingEnabled(True)
        self.table.setMinimumHeight(400)
        
        layout.addWidget(self.table)
        
        # Stats footer
        self.stats_label = QLabel()
        self.stats_label.setStyleSheet("""
            font-size: 14px; 
            color: #666; 
            padding: 10px;
            background: #f9f9f9;
            border-radius: 5px;
        """)
        self.stats_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.stats_label)
    
    def refresh_history(self):
        """Refresh trade history from trade logger"""
        if not self.trade_logger or not hasattr(self.trade_logger, 'trades'):
            self.table.setRowCount(1)
            no_data = QTableWidgetItem("No trade history available")
            no_data.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(0, 0, no_data)
            self.table.setSpan(0, 0, 1, 9)
            self.stats_label.setText("No trades logged")
            return
        
        trades = self.trade_logger.trades
        
        if not trades:
            self.table.setRowCount(1)
            no_data = QTableWidgetItem("No trades found")
            no_data.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(0, 0, no_data)
            self.table.setSpan(0, 0, 1, 9)
            self.stats_label.setText("No trades logged")
            return
        
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(trades))
        
        total_profit = 0
        winning_trades = 0
        
        for row, trade in enumerate(reversed(trades)):  # Newest first
            date = trade.get('date', 'N/A')
            symbol = trade.get('symbol', 'N/A')
            action = trade.get('action', 'N/A')
            entry = trade.get('entry_price', 0)
            exit_price = trade.get('exit_price', 0)
            qty = trade.get('quantity', 0)
            profit = trade.get('profit', 0)
            profit_pct = trade.get('profit_pct', 0)
            status = trade.get('status', 'N/A')
            
            total_profit += profit
            if profit > 0:
                winning_trades += 1
            
            items = [
                QTableWidgetItem(str(date)),
                QTableWidgetItem(str(symbol)),
                QTableWidgetItem(str(action)),
                QTableWidgetItem(f"₹{entry:.2f}"),
                QTableWidgetItem(f"₹{exit_price:.2f}"),
                QTableWidgetItem(str(qty)),
                QTableWidgetItem(f"₹{profit:.2f}"),
                QTableWidgetItem(f"{profit_pct:.2f}%"),
                QTableWidgetItem(str(status))
            ]
            
            # Color action
            action_item = items[2]
            if str(action).upper() == 'BUY':
                action_item.setForeground(QColor(0, 150, 0))
            elif str(action).upper() == 'SELL':
                action_item.setForeground(QColor(200, 0, 0))
            
            # Color P&L
            pnl_item = items[6]
            pnl_pct_item = items[7]
            if profit > 0:
                pnl_item.setForeground(QColor(0, 150, 0))
                pnl_pct_item.setForeground(QColor(0, 150, 0))
            elif profit < 0:
                pnl_item.setForeground(QColor(200, 0, 0))
                pnl_pct_item.setForeground(QColor(200, 0, 0))
            
            # Center align
            for col, item in enumerate(items):
                item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row, col, item)
        
        self.table.setSortingEnabled(True)
        
        # Update stats
        total_trades = len(trades)
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        
        self.stats_label.setText(
            f"Total Trades: {total_trades} | "
            f"Winning: {winning_trades} | "
            f"Win Rate: {win_rate:.1f}% | "
            f"Total P&L: ₹{total_profit:,.2f}"
        )
        
        self.parent.statusBar().showMessage(f"✅ Loaded {total_trades} trades", 2000)
    
    def export_history(self):
        """Export trade history to Excel"""
        if not self.trade_logger or not hasattr(self.trade_logger, 'trades'):
            self.parent.statusBar().showMessage("⚠️ No trade history to export", 3000)
            return
        
        if not self.trade_logger.trades:
            self.parent.statusBar().showMessage("⚠️ No trades found", 3000)
            return
        
        try:
            from datetime import datetime
            filename = f"trade_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            
            # Use trade_logger's export functionality if available
            if hasattr(self.trade_logger, 'save_to_excel'):
                self.trade_logger.save_to_excel(filename)
                self.parent.statusBar().showMessage(f"✅ Exported to {filename}", 5000)
            else:
                self.parent.statusBar().showMessage("⚠️ Export functionality not available", 3000)
                
        except Exception as e:
            self.parent.statusBar().showMessage(f"❌ Export failed: {e}", 5000)