#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ==============================================================================
# FILE: paper_trading_tab.py
# VERSION: 2.0.1 - Fixed SELL trade display issue
# LOCATION: c:\Users\Dell\tradingbot_new\ui_new\tabs\paper_trading_tab.py
# 
# FEATURES:
# - Real-time trade logging
# - Auto exit on target/stop loss
# - P&L tracking
# - Trade history
# - Export to Excel
# - FIXED: SELL trades now display correctly
# ==============================================================================

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QPushButton, QTableWidget, QTableWidgetItem, 
                             QHeaderView, QTabWidget, QMessageBox, QComboBox)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor
from datetime import datetime
import json
import os

class PaperTradingTab(QWidget):
    """
    Paper Trading Tab - Complete Trade Management
    
    Features:
    1. Active trades monitoring
    2. Auto exit on target/SL hit
    3. Trade history with P&L
    4. Statistics dashboard
    5. Export functionality
    """
    
    def __init__(self, parent, conn_mgr):
        super().__init__(parent)
        self.parent = parent
        self.conn_mgr = conn_mgr
        
        # Trade storage
        self.active_trades = []
        self.closed_trades = []
        
        # Load trades from file
        self.load_trades()
        
        self.init_ui()
        
        # Monitor active trades every 5 seconds
        self.monitor_timer = QTimer()
        self.monitor_timer.timeout.connect(self.monitor_active_trades)
        self.monitor_timer.start(5000)  # 5 seconds
    
    def init_ui(self):
        """Initialize UI components"""
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        
        # Header
        header = QHBoxLayout()
        
        title = QLabel("📊 Paper Trading")
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: #333;")
        header.addWidget(title)
        
        header.addStretch()
        
        # Statistics
        self.stats_label = QLabel()
        self.stats_label.setStyleSheet("""
            font-size: 14px; 
            color: #666; 
            padding: 8px 15px;
            background: #f0f0f0;
            border-radius: 5px;
        """)
        self.update_stats()
        header.addWidget(self.stats_label)
        
        # Export button
        export_btn = QPushButton("📥 Export")
        export_btn.setStyleSheet("""
            background: #FF9800; 
            color: white; 
            font-size: 14px; 
            font-weight: bold; 
            padding: 8px 20px; 
            border-radius: 6px;
        """)
        export_btn.clicked.connect(self.export_trades)
        export_btn.setCursor(Qt.PointingHandCursor)
        header.addWidget(export_btn)
        
        # Clear button
        clear_btn = QPushButton("🗑️ Clear History")
        clear_btn.setStyleSheet("""
            background: #f44336; 
            color: white; 
            font-size: 14px; 
            font-weight: bold; 
            padding: 8px 20px; 
            border-radius: 6px;
        """)
        clear_btn.clicked.connect(self.clear_history)
        clear_btn.setCursor(Qt.PointingHandCursor)
        header.addWidget(clear_btn)
        
        layout.addLayout(header)
        
        # Tab widget for Active/History
        self.tab_widget = QTabWidget()
        self.tab_widget.setStyleSheet("""
            QTabWidget::pane {
                border: 2px solid #ddd;
                border-radius: 5px;
                background: white;
            }
            QTabBar::tab {
                background: #f0f0f0;
                padding: 10px 20px;
                margin-right: 2px;
                border-top-left-radius: 5px;
                border-top-right-radius: 5px;
                font-size: 14px;
                font-weight: bold;
            }
            QTabBar::tab:selected {
                background: #2196F3;
                color: white;
            }
        """)
        
        # Active trades tab
        self.active_table = self.create_trades_table()
        self.tab_widget.addTab(self.active_table, "🟢 Active Trades")
        
        # History tab
        self.history_table = self.create_history_table()
        self.tab_widget.addTab(self.history_table, "📜 Trade History")
        
        layout.addWidget(self.tab_widget)
        
        # Info footer
        self.info_label = QLabel("Monitoring active trades every 5 seconds for target/SL")
        self.info_label.setStyleSheet("""
            font-size: 13px; 
            color: #666; 
            padding: 8px;
            background: #f9f9f9;
            border-radius: 5px;
        """)
        self.info_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.info_label)
        
        # Initial refresh
        self.refresh_active_trades()
        self.refresh_history()
    
    def create_trades_table(self):
        """Create active trades table"""
        table = QTableWidget()
        table.setStyleSheet("""
            QTableWidget { 
                background: white; 
                gridline-color: #e0e0e0;
                font-size: 14px;
            }
            QHeaderView::section { 
                background: #4CAF50; 
                color: white; 
                font-weight: bold; 
                font-size: 15px; 
                padding: 10px; 
                border: none; 
            }
            QTableWidget::item { 
                padding: 8px;
            }
        """)
        
        table.setColumnCount(11)
        table.setHorizontalHeaderLabels([
            "Order ID", "Symbol", "Type", "Entry Time", "Entry Price",
            "Current LTP", "Target", "Stop Loss", "Qty", "P&L", "Action"
        ])
        
        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Stretch)
        header.setSectionResizeMode(10, QHeaderView.Fixed)
        table.setColumnWidth(10, 100)
        
        table.setVerticalScrollMode(QTableWidget.ScrollPerPixel)
        table.setMinimumHeight(300)
        
        return table
    
    def create_history_table(self):
        """Create trade history table"""
        table = QTableWidget()
        table.setStyleSheet("""
            QTableWidget { 
                background: white; 
                gridline-color: #e0e0e0;
                font-size: 14px;
            }
            QHeaderView::section { 
                background: #607D8B; 
                color: white; 
                font-weight: bold; 
                font-size: 15px; 
                padding: 10px; 
                border: none; 
            }
            QTableWidget::item { 
                padding: 8px;
            }
        """)
        
        table.setColumnCount(12)
        table.setHorizontalHeaderLabels([
            "Order ID", "Symbol", "Type", "Entry Time", "Entry Price",
            "Exit Time", "Exit Price", "Exit Reason", "Qty", "P&L ₹", "P&L %", "Status"
        ])
        
        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Stretch)
        
        table.setVerticalScrollMode(QTableWidget.ScrollPerPixel)
        table.setMinimumHeight(300)
        
        return table
    
    def add_trade(self, trade_data):
        """
        Add new trade from analyzer
        
        Args:
            trade_data: dict with keys:
                - symbol: str
                - action: 'BUY' or 'SELL'
                - entry_price: float
                - target: float
                - stop_loss: float
                - quantity: int (default 1)
                - confidence: int (optional)
        """
        # Generate order ID
        order_id = f"ORD{datetime.now().strftime('%Y%m%d%H%M%S%f')[:17]}"
        
        # Create trade entry
        trade = {
            'order_id': order_id,
            'symbol': trade_data['symbol'],
            'action': trade_data['action'],
            'entry_price': trade_data['entry_price'],
            'entry_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'target': trade_data['target'],
            'stop_loss': trade_data['stop_loss'],
            'quantity': trade_data.get('quantity', 1),
            'status': 'OPEN',
            'exit_price': None,
            'exit_time': None,
            'exit_reason': None,
            'pnl': 0,
            'pnl_pct': 0,
            'confidence': trade_data.get('confidence', 0)
        }
        
        # Add to active trades
        self.active_trades.append(trade)
        
        # Save to file
        self.save_trades()
        
        # Refresh display
        self.refresh_active_trades()
        self.update_stats()
        
        # Show notification
        self.parent.statusBar().showMessage(
            f"✅ {trade['action']} trade added: {trade['symbol']} at ₹{trade['entry_price']:.2f}",
            5000
        )
        
        return order_id
    
    def monitor_active_trades(self):
        """Monitor active trades and auto-exit on target/SL"""
        if not self.active_trades:
            return
        
        # Get current LTPs
        symbols = [trade['symbol'] for trade in self.active_trades]
        ltp_data = self.conn_mgr.get_ltp_batch(symbols)
        
        trades_to_close = []
        
        for trade in self.active_trades:
            symbol = trade['symbol']
            current_ltp = ltp_data.get(symbol, 0)
            
            if current_ltp == 0:
                continue
            
            entry_price = trade['entry_price']
            target = trade['target']
            stop_loss = trade['stop_loss']
            action = trade['action']
            
            # Check exit conditions
            should_exit = False
            exit_reason = None
            
            if action == 'BUY':
                # Long position
                if current_ltp >= target:
                    should_exit = True
                    exit_reason = "TARGET HIT"
                elif current_ltp <= stop_loss:
                    should_exit = True
                    exit_reason = "STOP LOSS HIT"
            
            elif action == 'SELL':
                # Short position
                if current_ltp <= target:
                    should_exit = True
                    exit_reason = "TARGET HIT"
                elif current_ltp >= stop_loss:
                    should_exit = True
                    exit_reason = "STOP LOSS HIT"
            
            if should_exit:
                # Close trade
                trade['exit_price'] = current_ltp
                trade['exit_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                trade['exit_reason'] = exit_reason
                trade['status'] = 'CLOSED'
                
                # Calculate P&L
                if action == 'BUY':
                    pnl = (current_ltp - entry_price) * trade['quantity']
                else:  # SELL (short)
                    pnl = (entry_price - current_ltp) * trade['quantity']
                
                pnl_pct = (pnl / (entry_price * trade['quantity'])) * 100
                
                trade['pnl'] = round(pnl, 2)
                trade['pnl_pct'] = round(pnl_pct, 2)
                
                trades_to_close.append(trade)
        
        # Move closed trades to history
        for trade in trades_to_close:
            self.active_trades.remove(trade)
            self.closed_trades.append(trade)
            
            # Show notification
            emoji = "🎯" if trade['exit_reason'] == "TARGET HIT" else "🛑"
            color = "green" if trade['pnl'] > 0 else "red"
            
            self.parent.statusBar().showMessage(
                f"{emoji} {trade['symbol']} closed: {trade['exit_reason']} | "
                f"P&L: ₹{trade['pnl']:.2f} ({trade['pnl_pct']:.2f}%)",
                10000
            )
        
        if trades_to_close:
            # Save and refresh
            self.save_trades()
            self.refresh_active_trades()
            self.refresh_history()
            self.update_stats()
    
    def refresh_active_trades(self):
        """Refresh active trades table - FIXED for SELL trades"""
        self.active_table.setSortingEnabled(False)
        self.active_table.setRowCount(len(self.active_trades))
        
        if not self.active_trades:
            self.active_table.setRowCount(1)
            no_data = QTableWidgetItem("No active trades")
            no_data.setTextAlignment(Qt.AlignCenter)
            self.active_table.setItem(0, 0, no_data)
            self.active_table.setSpan(0, 0, 1, 11)
            return
        
        # Get current LTPs
        symbols = [trade['symbol'] for trade in self.active_trades]
        ltp_data = self.conn_mgr.get_ltp_batch(symbols)
        
        for row, trade in enumerate(self.active_trades):
            current_ltp = ltp_data.get(trade['symbol'], trade['entry_price'])
            
            # Calculate current P&L
            if trade['action'] == 'BUY':
                pnl = (current_ltp - trade['entry_price']) * trade['quantity']
            else:  # SELL
                pnl = (trade['entry_price'] - current_ltp) * trade['quantity']
            
            pnl_pct = (pnl / (trade['entry_price'] * trade['quantity'])) * 100
            
            # ⭐ FIX: Create all items properly
            items = [
                QTableWidgetItem(trade['order_id'][-8:]),  # Last 8 chars
                QTableWidgetItem(trade['symbol']),
                QTableWidgetItem(trade['action']),
                QTableWidgetItem(trade['entry_time']),
                QTableWidgetItem(f"₹{trade['entry_price']:.2f}"),
                QTableWidgetItem(f"₹{current_ltp:.2f}"),
                QTableWidgetItem(f"₹{trade['target']:.2f}"),
                QTableWidgetItem(f"₹{trade['stop_loss']:.2f}"),
                QTableWidgetItem(str(trade['quantity'])),
                QTableWidgetItem(f"₹{pnl:.2f} ({pnl_pct:.2f}%)")
            ]
            
            # Color coding for action
            action_item = items[2]
            if trade['action'] == 'BUY':
                action_item.setForeground(QColor(0, 150, 0))
            else:  # SELL
                action_item.setForeground(QColor(200, 0, 0))
            
            # P&L color
            pnl_item = items[9]
            if pnl > 0:
                pnl_item.setForeground(QColor(0, 150, 0))
            elif pnl < 0:
                pnl_item.setForeground(QColor(200, 0, 0))
            
            # Center align and set all items
            for col, item in enumerate(items):
                item.setTextAlignment(Qt.AlignCenter)
                self.active_table.setItem(row, col, item)
            
            # Exit button
            exit_btn = QPushButton("❌ Exit")
            exit_btn.setStyleSheet("""
                background: #FF5722; 
                color: white; 
                font-size: 12px; 
                padding: 5px 10px; 
                border-radius: 4px;
            """)
            exit_btn.clicked.connect(lambda checked, t=trade: self.manual_exit(t))
            exit_btn.setCursor(Qt.PointingHandCursor)
            self.active_table.setCellWidget(row, 10, exit_btn)
        
        self.active_table.setSortingEnabled(True)
    
    def refresh_history(self):
        """Refresh trade history table"""
        self.history_table.setSortingEnabled(False)
        self.history_table.setRowCount(len(self.closed_trades))
        
        if not self.closed_trades:
            self.history_table.setRowCount(1)
            no_data = QTableWidgetItem("No trade history")
            no_data.setTextAlignment(Qt.AlignCenter)
            self.history_table.setItem(0, 0, no_data)
            self.history_table.setSpan(0, 0, 1, 12)
            return
        
        for row, trade in enumerate(reversed(self.closed_trades)):  # Newest first
            items = [
                QTableWidgetItem(trade['order_id'][-8:]),
                QTableWidgetItem(trade['symbol']),
                QTableWidgetItem(trade['action']),
                QTableWidgetItem(trade['entry_time']),
                QTableWidgetItem(f"₹{trade['entry_price']:.2f}"),
                QTableWidgetItem(trade['exit_time'] or '-'),
                QTableWidgetItem(f"₹{trade['exit_price']:.2f}" if trade['exit_price'] else '-'),
                QTableWidgetItem(trade['exit_reason'] or '-'),
                QTableWidgetItem(str(trade['quantity'])),
                QTableWidgetItem(f"₹{trade['pnl']:.2f}"),
                QTableWidgetItem(f"{trade['pnl_pct']:.2f}%"),
                QTableWidgetItem(trade['status'])
            ]
            
            # Color coding
            action_item = items[2]
            if trade['action'] == 'BUY':
                action_item.setForeground(QColor(0, 150, 0))
            else:
                action_item.setForeground(QColor(200, 0, 0))
            
            # Exit reason color
            reason_item = items[7]
            if trade['exit_reason'] == "TARGET HIT":
                reason_item.setForeground(QColor(0, 150, 0))
            elif trade['exit_reason'] == "STOP LOSS HIT":
                reason_item.setForeground(QColor(200, 0, 0))
            
            # P&L color
            pnl_item = items[9]
            pnl_pct_item = items[10]
            if trade['pnl'] > 0:
                pnl_item.setForeground(QColor(0, 150, 0))
                pnl_pct_item.setForeground(QColor(0, 150, 0))
            elif trade['pnl'] < 0:
                pnl_item.setForeground(QColor(200, 0, 0))
                pnl_pct_item.setForeground(QColor(200, 0, 0))
            
            # Center align
            for col, item in enumerate(items):
                item.setTextAlignment(Qt.AlignCenter)
                self.history_table.setItem(row, col, item)
        
        self.history_table.setSortingEnabled(True)
    
    def manual_exit(self, trade):
        """Manually exit a trade"""
        reply = QMessageBox.question(
            self,
            'Confirm Exit',
            f"Exit trade for {trade['symbol']}?\n\n"
            f"Type: {trade['action']}\n"
            f"Entry: ₹{trade['entry_price']:.2f}\n"
            f"Current LTP: Will be captured at exit",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            # Get current LTP
            ltp = self.conn_mgr.get_ltp(trade['symbol'])
            
            # Close trade
            trade['exit_price'] = ltp
            trade['exit_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            trade['exit_reason'] = "MANUAL EXIT"
            trade['status'] = 'CLOSED'
            
            # Calculate P&L
            if trade['action'] == 'BUY':
                pnl = (ltp - trade['entry_price']) * trade['quantity']
            else:
                pnl = (trade['entry_price'] - ltp) * trade['quantity']
            
            pnl_pct = (pnl / (trade['entry_price'] * trade['quantity'])) * 100
            
            trade['pnl'] = round(pnl, 2)
            trade['pnl_pct'] = round(pnl_pct, 2)
            
            # Move to history
            self.active_trades.remove(trade)
            self.closed_trades.append(trade)
            
            # Save and refresh
            self.save_trades()
            self.refresh_active_trades()
            self.refresh_history()
            self.update_stats()
            
            self.parent.statusBar().showMessage(
                f"✅ Manually exited {trade['symbol']} | P&L: ₹{pnl:.2f}",
                5000
            )
    
    def update_stats(self):
        """Update statistics display"""
        total_trades = len(self.closed_trades)
        active_count = len(self.active_trades)
        
        if total_trades == 0:
            self.stats_label.setText(
                f"Active: {active_count} | Closed: 0 | Win Rate: N/A | Total P&L: ₹0.00"
            )
            return
        
        winning_trades = sum(1 for t in self.closed_trades if t['pnl'] > 0)
        win_rate = (winning_trades / total_trades) * 100
        total_pnl = sum(t['pnl'] for t in self.closed_trades)
        
        self.stats_label.setText(
            f"Active: {active_count} | Closed: {total_trades} | "
            f"Win Rate: {win_rate:.1f}% | Total P&L: ₹{total_pnl:.2f}"
        )
    
    def save_trades(self):
        """Save trades to file"""
        data = {
            'active_trades': self.active_trades,
            'closed_trades': self.closed_trades
        }
        
        try:
            with open('paper_trades.json', 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"⚠️  Error saving trades: {e}")
    
    def load_trades(self):
        """Load trades from file"""
        if os.path.exists('paper_trades.json'):
            try:
                with open('paper_trades.json', 'r') as f:
                    data = json.load(f)
                    self.active_trades = data.get('active_trades', [])
                    self.closed_trades = data.get('closed_trades', [])
                print(f"✅ Loaded {len(self.active_trades)} active and {len(self.closed_trades)} closed trades")
            except Exception as e:
                print(f"⚠️  Error loading trades: {e}")
    
    def export_trades(self):
        """Export trades to Excel"""
        try:
            import pandas as pd
            
            if not self.closed_trades:
                QMessageBox.information(self, "No Data", "No trade history to export")
                return
            
            # Create DataFrame
            df = pd.DataFrame(self.closed_trades)
            
            # Export to Excel
            filename = f"paper_trades_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            df.to_excel(filename, index=False)
            
            QMessageBox.information(
                self, 
                "Export Successful", 
                f"Trades exported to:\n{filename}"
            )
            
        except ImportError:
            QMessageBox.warning(
                self,
                "Export Failed",
                "pandas and openpyxl required for export.\n"
                "Install: pip install pandas openpyxl"
            )
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Error: {e}")
    
    def clear_history(self):
        """Clear trade history"""
        if not self.closed_trades:
            QMessageBox.information(self, "No History", "No trade history to clear")
            return
        
        reply = QMessageBox.question(
            self,
            'Confirm Clear',
            f"Clear all {len(self.closed_trades)} closed trades from history?\n"
            "This cannot be undone!",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.closed_trades = []
            self.save_trades()
            self.refresh_history()
            self.update_stats()
            
            QMessageBox.information(self, "Cleared", "Trade history cleared")