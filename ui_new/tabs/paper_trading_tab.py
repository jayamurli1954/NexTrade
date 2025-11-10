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
                             QHeaderView, QTabWidget, QMessageBox, QComboBox,
                             QDialog, QTextEdit, QScrollArea)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor, QFont
from datetime import datetime
import json
import os
import sys

# ✅ NEW: Performance analytics integration
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
try:
    from enhancements.order_manager.performance_analyzer import PerformanceAnalyzer
    PERFORMANCE_ANALYTICS_AVAILABLE = True
except ImportError:
    PERFORMANCE_ANALYTICS_AVAILABLE = False
    print("⚠️ Performance analytics not available - install with: pip install pandas numpy")

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
        
        # ✅ NEW: Performance Report button
        if PERFORMANCE_ANALYTICS_AVAILABLE:
            perf_btn = QPushButton("📊 Performance")
            perf_btn.setStyleSheet("""
                font-size: 14px;
                font-weight: bold;
                padding: 8px 20px;
                border-radius: 6px;
                background-color: #4CAF50;
                color: white;
            """)
            perf_btn.clicked.connect(self.show_performance_report)
            perf_btn.setCursor(Qt.PointingHandCursor)
            header.addWidget(perf_btn)

        # Export button
        export_btn = QPushButton("📥 Export")
        export_btn.setStyleSheet("""
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
            }
            QTabBar::tab {
                padding: 10px 20px;
                margin-right: 2px;
                border-top-left-radius: 5px;
                border-top-right-radius: 5px;
                font-size: 14px;
                font-weight: bold;
            }
            QTabBar::tab:selected {
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
                gridline-color: #e0e0e0;
                font-size: 14px;
            }
            QHeaderView::section { 
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
                gridline-color: #e0e0e0;
                font-size: 14px;
            }
            QHeaderView::section { 
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
        # Check if trading is allowed (before 3:15 PM)
        current_time = datetime.now().time()
        market_close_time = datetime.strptime("15:15", "%H:%M").time()

        if current_time >= market_close_time:
            QMessageBox.warning(
                self,
                "Trading Closed",
                "⏰ Trading is not allowed after 3:15 PM!\n\nMarket hours: 9:15 AM - 3:15 PM"
            )
            return None

        # Generate order ID
        order_id = f"ORD{datetime.now().strftime('%Y%m%d%H%M%S%f')[:17]}"
        
        # Create trade entry - CONVERT ALL NUMPY TYPES TO PYTHON FLOATS
        trade = {
            'order_id': order_id,
            'symbol': str(trade_data['symbol']),
            'action': str(trade_data['action']),
            'entry_price': float(trade_data['entry_price']),
            'entry_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'target': float(trade_data['target']),
            'stop_loss': float(trade_data['stop_loss']),
            'quantity': int(trade_data.get('quantity', 1)),
            'status': 'OPEN',
            'exit_price': None,
            'exit_time': None,
            'exit_reason': None,
            'pnl': 0.0,
            'pnl_pct': 0.0,
            'confidence': float(trade_data.get('confidence', 0))
        }
        
        print(f"🔍 DEBUG: Trade created - Entry: ₹{trade['entry_price']:.2f}, Target: ₹{trade['target']:.2f}, SL: ₹{trade['stop_loss']:.2f}")
        
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
        """Monitor active trades and auto-exit on target/SL/3:15 PM"""
        if not self.active_trades:
            return

        # Check if it's 3:15 PM or later
        from datetime import datetime
        current_time = datetime.now().time()
        auto_exit_time = datetime.strptime("15:15", "%H:%M").time()
        is_post_market = current_time >= auto_exit_time

        # Get current LTPs
        symbols = [trade['symbol'] for trade in self.active_trades]
        ltp_data = self.conn_mgr.get_ltp_batch(symbols)

        trades_to_close = []

        for trade in self.active_trades:
            symbol = trade['symbol']
            current_ltp = ltp_data.get(symbol)

            if current_ltp is None:
                # If post-market and no LTP, use entry price for exit
                if is_post_market:
                    current_ltp = trade['entry_price']
                else:
                    continue

            entry_price = trade['entry_price']
            target = trade['target']
            stop_loss = trade['stop_loss']
            action = trade['action']

            # Check exit conditions
            should_exit = False
            exit_reason = None

            # Priority 1: Force exit at 3:15 PM
            if is_post_market:
                should_exit = True
                exit_reason = "TIME 3:15 PM"

            # Priority 2: Check target/stop loss
            elif action == 'BUY':
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
                # Close trade - ENSURE PROPER TYPES
                trade['exit_price'] = float(current_ltp)
                trade['exit_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                trade['exit_reason'] = str(exit_reason)
                trade['status'] = 'CLOSED'

                print(f"🔍 DEBUG: Closing {trade['symbol']} - Entry: ₹{trade['entry_price']:.2f}, Exit: ₹{trade['exit_price']:.2f}, Reason: {exit_reason}")

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
        """Refresh active trades table - FIXED for SELL trades + Auto-Exit"""
        self.active_table.setSortingEnabled(False)
        # Note: Row count will be adjusted dynamically as trades are processed

        if not self.active_trades:
            self.active_table.setRowCount(1)
            no_data = QTableWidgetItem("No active trades")
            no_data.setTextAlignment(Qt.AlignCenter)
            self.active_table.setItem(0, 0, no_data)
            self.active_table.setSpan(0, 0, 1, 11)
            return

        # Check if we need to auto-exit trades at 3:15 PM
        from datetime import datetime
        current_time = datetime.now().time()
        auto_exit_time = datetime.strptime("15:15", "%H:%M").time()

        # Get current LTPs
        symbols = [trade['symbol'] for trade in self.active_trades]
        ltp_data = self.conn_mgr.get_ltp_batch(symbols)

        # List to track trades that need to be closed
        trades_to_close = []

        # Track display row (may differ from enumeration if trades are skipped)
        display_row = 0

        for trade_idx, trade in enumerate(self.active_trades):
            current_ltp = ltp_data.get(trade['symbol'])
            if current_ltp is None:
                current_ltp = trade['entry_price']
            
            # Calculate current P&L
            if trade['action'] == 'BUY':
                pnl = (current_ltp - trade['entry_price']) * trade['quantity']
            else:  # SELL
                pnl = (trade['entry_price'] - current_ltp) * trade['quantity']

            pnl_pct = (pnl / (trade['entry_price'] * trade['quantity'])) * 100

            # Check auto-exit conditions (Target, Stop Loss, or 3:15 PM)
            exit_reason = None

            # Check if 3:15 PM or later
            if current_time >= auto_exit_time:
                exit_reason = "Time 3:15 PM"
            # Check target hit
            elif trade['action'] == 'BUY' and current_ltp >= trade['target']:
                exit_reason = "Target Hit"
            elif trade['action'] == 'SELL' and current_ltp <= trade['target']:
                exit_reason = "Target Hit"
            # Check stop loss hit
            elif trade['action'] == 'BUY' and current_ltp <= trade['stop_loss']:
                exit_reason = "Stop Loss Hit"
            elif trade['action'] == 'SELL' and current_ltp >= trade['stop_loss']:
                exit_reason = "Stop Loss Hit"

            # If exit condition met, add to closure list
            if exit_reason:
                trades_to_close.append({
                    'trade': trade,
                    'current_ltp': current_ltp,
                    'pnl': pnl,
                    'reason': exit_reason
                })
                # Skip displaying this trade as it will be closed
                continue

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
            
            # Set row count if needed (first valid row)
            if display_row == 0:
                # Estimate max rows needed (will be trimmed later if needed)
                self.active_table.setRowCount(len(self.active_trades) - len(trades_to_close))

            # Center align and set all items
            for col, item in enumerate(items):
                item.setTextAlignment(Qt.AlignCenter)
                self.active_table.setItem(display_row, col, item)

            # Exit button
            exit_btn = QPushButton("❌ Exit")
            exit_btn.setStyleSheet("""
                font-size: 12px;
                padding: 5px 10px;
                border-radius: 4px;
            """)
            exit_btn.clicked.connect(lambda checked, t=trade: self.manual_exit(t))
            exit_btn.setCursor(Qt.PointingHandCursor)
            self.active_table.setCellWidget(display_row, 10, exit_btn)

            # Increment display row
            display_row += 1

        # Process automatic exits (Target, Stop Loss, 3:15 PM)
        if trades_to_close:
            for item in trades_to_close:
                trade = item['trade']
                current_ltp = item['current_ltp']
                pnl = item['pnl']
                reason = item['reason']

                # Update trade with exit details
                trade['exit_price'] = current_ltp
                trade['exit_time'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                trade['pnl'] = pnl
                trade['status'] = f'Closed - {reason}'

                # Move to closed trades
                self.active_trades.remove(trade)
                self.closed_trades.append(trade)

                # Show notification
                self.parent.statusBar().showMessage(
                    f"🔔 Auto-Exit: {trade['symbol']} | {reason} | P&L: ₹{pnl:.2f}",
                    5000
                )

            # Save and refresh
            self.save_trades()
            self.refresh_active_trades()  # Recursive call to refresh display
            self.refresh_history()
            self.update_stats()
            return  # Exit after processing closures

        self.active_table.setSortingEnabled(True)
    
    def refresh_history(self):
        """Refresh trade history table - Shows ALL trades (active + closed)"""
        self.history_table.setSortingEnabled(False)

        # Combine active and closed trades
        all_trades = []

        # Add active trades with current LTP for P&L calculation
        if self.active_trades:
            symbols = [trade['symbol'] for trade in self.active_trades]
            ltp_data = self.conn_mgr.get_ltp_batch(symbols)

            for trade in self.active_trades:
                # Create a copy to avoid modifying the original
                trade_copy = trade.copy()
                current_ltp = ltp_data.get(trade['symbol'], trade['entry_price'])

                # Calculate current P&L for active trades
                if trade['action'] == 'BUY':
                    pnl = (current_ltp - trade['entry_price']) * trade['quantity']
                else:  # SELL
                    pnl = (trade['entry_price'] - current_ltp) * trade['quantity']

                pnl_pct = (pnl / (trade['entry_price'] * trade['quantity'])) * 100

                trade_copy['current_pnl'] = pnl
                trade_copy['current_pnl_pct'] = pnl_pct
                trade_copy['is_active'] = True
                all_trades.append(trade_copy)

        # Add closed trades
        for trade in self.closed_trades:
            trade_copy = trade.copy()
            trade_copy['is_active'] = False
            all_trades.append(trade_copy)

        # Sort by entry time (newest first)
        all_trades.sort(key=lambda x: x.get('entry_time', ''), reverse=True)

        self.history_table.setRowCount(len(all_trades))

        if not all_trades:
            self.history_table.setRowCount(1)
            no_data = QTableWidgetItem("No trades yet")
            no_data.setTextAlignment(Qt.AlignCenter)
            self.history_table.setItem(0, 0, no_data)
            self.history_table.setSpan(0, 0, 1, 12)
            return

        for row, trade in enumerate(all_trades):
            if trade['is_active']:
                # Active trade
                items = [
                    QTableWidgetItem(trade['order_id'][-8:]),
                    QTableWidgetItem(trade['symbol']),
                    QTableWidgetItem(trade['action']),
                    QTableWidgetItem(trade['entry_time']),
                    QTableWidgetItem(f"₹{trade['entry_price']:.2f}"),
                    QTableWidgetItem('-'),  # No exit time yet
                    QTableWidgetItem('-'),  # No exit price yet
                    QTableWidgetItem('-'),  # No exit reason yet
                    QTableWidgetItem(str(trade['quantity'])),
                    QTableWidgetItem(f"₹{trade['current_pnl']:.2f}"),  # Current P&L
                    QTableWidgetItem(f"{trade['current_pnl_pct']:.2f}%"),  # Current P&L %
                    QTableWidgetItem("OPEN")  # Status
                ]

                # Color status as blue for open
                status_item = items[11]
                status_item.setForeground(QColor(0, 100, 200))
                status_item.setFont(QFont("Arial", 10, QFont.Bold))
            else:
                # Closed trade
                items = [
                    QTableWidgetItem(trade['order_id'][-8:]),
                    QTableWidgetItem(trade['symbol']),
                    QTableWidgetItem(trade['action']),
                    QTableWidgetItem(trade['entry_time']),
                    QTableWidgetItem(f"₹{trade['entry_price']:.2f}"),
                    QTableWidgetItem(trade.get('exit_time', '-')),
                    QTableWidgetItem(f"₹{trade['exit_price']:.2f}" if trade.get('exit_price') else '-'),
                    QTableWidgetItem(trade.get('exit_reason', '-')),
                    QTableWidgetItem(str(trade['quantity'])),
                    QTableWidgetItem(f"₹{trade.get('pnl', 0):.2f}"),
                    QTableWidgetItem(f"{trade.get('pnl_pct', 0):.2f}%"),
                    QTableWidgetItem("CLOSED")  # Status
                ]

                # Color status as gray for closed
                status_item = items[11]
                status_item.setForeground(QColor(100, 100, 100))
                status_item.setFont(QFont("Arial", 10, QFont.Bold))

                # Exit reason color
                reason_item = items[7]
                if trade.get('exit_reason') == "TARGET HIT":
                    reason_item.setForeground(QColor(0, 150, 0))
                elif trade.get('exit_reason') == "STOP LOSS HIT":
                    reason_item.setForeground(QColor(200, 0, 0))

            # Color coding for action
            action_item = items[2]
            if trade['action'] == 'BUY':
                action_item.setForeground(QColor(0, 150, 0))
            else:
                action_item.setForeground(QColor(200, 0, 0))

            # P&L color
            pnl_item = items[9]
            pnl_pct_item = items[10]
            pnl_value = trade.get('current_pnl') if trade['is_active'] else trade.get('pnl', 0)
            if pnl_value > 0:
                pnl_item.setForeground(QColor(0, 150, 0))
                pnl_pct_item.setForeground(QColor(0, 150, 0))
            elif pnl_value < 0:
                pnl_item.setForeground(QColor(200, 0, 0))
                pnl_pct_item.setForeground(QColor(200, 0, 0))

            # Center align all items
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
            if ltp is None:
                QMessageBox.warning(self, "Price Unavailable", f"Could not retrieve the current price for {trade['symbol']}. Please try again.")
                return            
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
    
    
    
    def open_manual_trade_dialog(self):
        """Open dialog for manual trade entry"""
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox, QPushButton, QMessageBox
        
        dialog = QDialog(self)
        dialog.setWindowTitle("Manual Trade Entry")
        dialog.setMinimumWidth(400)
        
        layout = QVBoxLayout(dialog)
        
        # Symbol
        symbol_layout = QHBoxLayout()
        symbol_layout.addWidget(QLabel("Symbol:"))
        symbol_input = QLineEdit()
        symbol_input.setPlaceholderText("e.g., RELIANCE")
        symbol_layout.addWidget(symbol_input)
        layout.addLayout(symbol_layout)
        
        # Action
        action_layout = QHBoxLayout()
        action_layout.addWidget(QLabel("Action:"))
        action_input = QComboBox()
        action_input.addItems(["BUY", "SELL"])
        action_layout.addWidget(action_input)
        layout.addLayout(action_layout)
        
        # Entry Price
        entry_layout = QHBoxLayout()
        entry_layout.addWidget(QLabel("Entry Price:"))
        entry_input = QLineEdit()
        entry_input.setPlaceholderText("e.g., 2500.50")
        entry_layout.addWidget(entry_input)
        layout.addLayout(entry_layout)
        
        # Target
        target_layout = QHBoxLayout()
        target_layout.addWidget(QLabel("Target:"))
        target_input = QLineEdit()
        target_input.setPlaceholderText("e.g., 2600.00")
        target_layout.addWidget(target_input)
        layout.addLayout(target_layout)
        
        # Stop Loss
        sl_layout = QHBoxLayout()
        sl_layout.addWidget(QLabel("Stop Loss:"))
        sl_input = QLineEdit()
        sl_input.setPlaceholderText("e.g., 2450.00")
        sl_layout.addWidget(sl_input)
        layout.addLayout(sl_layout)
        
        # Quantity
        qty_layout = QHBoxLayout()
        qty_layout.addWidget(QLabel("Quantity:"))
        qty_input = QLineEdit()
        qty_input.setText("1")
        qty_layout.addWidget(qty_input)
        layout.addLayout(qty_layout)
        
        # Buttons
        button_layout = QHBoxLayout()
        submit_btn = QPushButton("Add Trade")
        submit_btn.setStyleSheet("padding: 8px 20px; border-radius: 4px;")
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet("padding: 8px 20px; border-radius: 4px;")
        
        button_layout.addWidget(submit_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)
        
        # Connect buttons
        def submit_trade():
            try:
                symbol = symbol_input.text().strip().upper()
                action = action_input.currentText()
                entry_price = float(entry_input.text())
                target = float(target_input.text())
                stop_loss = float(sl_input.text())
                quantity = int(qty_input.text())
                
                if not symbol:
                    QMessageBox.warning(dialog, "Error", "Please enter a symbol")
                    return
                
                # Create trade data
                trade_data = {
                    'symbol': symbol,
                    'action': action,
                    'entry_price': entry_price,
                    'target': target,
                    'stop_loss': stop_loss,
                    'quantity': quantity,
                    'confidence': 0.0
                }
                
                # Add trade
                self.add_trade(trade_data)
                
                QMessageBox.information(dialog, "Success", f"Manual trade added: {action} {symbol}")
                dialog.accept()
                
            except ValueError as e:
                QMessageBox.warning(dialog, "Error", f"Invalid input: {str(e)}")
        
        submit_btn.clicked.connect(submit_trade)
        cancel_btn.clicked.connect(dialog.reject)
        
        dialog.exec_()

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

    def show_performance_report(self):
        """
        ✅ NEW: Show advanced performance analytics report

        Displays:
        - Sharpe Ratio, Sortino Ratio, Calmar Ratio
        - Maximum Drawdown
        - Win Rate & Profit Factor
        - Average Win/Loss
        - Trade Duration Analysis
        - BUY vs SELL performance
        """
        if not PERFORMANCE_ANALYTICS_AVAILABLE:
            QMessageBox.warning(
                self,
                "Not Available",
                "Performance analytics not available.\n"
                "Install required packages:\n"
                "pip install pandas numpy"
            )
            return

        if not self.closed_trades:
            QMessageBox.information(
                self,
                "No Data",
                "No closed trades to analyze.\n"
                "Complete some trades first to see performance metrics."
            )
            return

        try:
            # Generate performance report
            analyzer = PerformanceAnalyzer(self.closed_trades)
            report = analyzer.generate_report()

            # Create dialog
            dialog = QDialog(self)
            dialog.setWindowTitle("📊 Performance Analytics Report")
            dialog.setMinimumSize(900, 700)

            layout = QVBoxLayout(dialog)

            # Report text display
            text_edit = QTextEdit()
            text_edit.setReadOnly(True)
            text_edit.setFont(QFont("Courier New", 10))

            # Format report as HTML
            html = self._format_performance_report_html(report)
            text_edit.setHtml(html)

            layout.addWidget(text_edit)

            # Close button
            close_btn = QPushButton("Close")
            close_btn.setStyleSheet("padding: 10px 30px; font-size: 14px;")
            close_btn.clicked.connect(dialog.accept)
            layout.addWidget(close_btn)

            dialog.exec_()

        except Exception as e:
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to generate performance report:\n{str(e)}"
            )
            import traceback
            traceback.print_exc()

    def _format_performance_report_html(self, report):
        """Format performance report as HTML"""
        if report.get('status') == 'NO_DATA':
            return "<h2>No data available for analysis</h2>"

        summary = report.get('summary', {})
        risk_adj = report.get('risk_adjusted_returns', {})
        dd = report.get('drawdown', {})
        win = report.get('win_metrics', {})
        dur = report.get('duration_analysis', {})
        action = report.get('action_analysis', {})

        html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; padding: 20px; }}
                h1 {{ color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 10px; }}
                h2 {{ color: #34495e; margin-top: 30px; border-bottom: 2px solid #95a5a6; padding-bottom: 5px; }}
                .metric {{ margin: 10px 0; padding: 10px; background: #ecf0f1; border-left: 4px solid #3498db; }}
                .good {{ color: #27ae60; font-weight: bold; }}
                .bad {{ color: #e74c3c; font-weight: bold; }}
                .neutral {{ color: #7f8c8d; }}
                .highlight {{ background: #fff3cd; padding: 5px; border-radius: 3px; }}
                table {{ width: 100%; border-collapse: collapse; margin: 15px 0; }}
                th {{ background: #34495e; color: white; padding: 12px; text-align: left; }}
                td {{ padding: 10px; border-bottom: 1px solid #ddd; }}
                tr:hover {{ background: #f5f5f5; }}
            </style>
        </head>
        <body>
            <h1>📊 Trading Performance Report</h1>

            <h2>📈 Summary</h2>
            <div class="metric">
                <strong>Total Trades:</strong> {summary.get('total_trades', 0)}
            </div>
            <div class="metric">
                <strong>Total P&L:</strong> <span class="{'good' if summary.get('total_pnl', 0) > 0 else 'bad'}">
                ₹{summary.get('total_pnl', 0):.2f}</span>
            </div>
            <div class="metric">
                <strong>Total P&L %:</strong> <span class="{'good' if summary.get('total_pnl_pct', 0) > 0 else 'bad'}">
                {summary.get('total_pnl_pct', 0):.2f}%</span>
            </div>

            <h2>💎 Risk-Adjusted Returns</h2>
            <div class="metric">
                <strong>Sharpe Ratio:</strong> <span class="highlight">{risk_adj.get('sharpe_ratio', 0):.3f}</span>
                <br><small>Higher is better. &gt;1 is good, &gt;2 is excellent</small>
            </div>
            <div class="metric">
                <strong>Sortino Ratio:</strong> {risk_adj.get('sortino_ratio', 0):.3f}
                <br><small>Focuses on downside risk only</small>
            </div>
            <div class="metric">
                <strong>Calmar Ratio:</strong> {risk_adj.get('calmar_ratio', 0):.3f}
                <br><small>Return / Max Drawdown. Higher is better.</small>
            </div>

            <h2>📉 Drawdown Analysis</h2>
            <div class="metric">
                <strong>Maximum Drawdown:</strong> <span class="bad">{dd.get('max_dd_pct', 0):.2f}%</span>
                (₹{dd.get('max_dd_amount', 0):.2f})
            </div>
            <div class="metric">
                <strong>Peak:</strong> ₹{dd.get('peak', 0):.2f}
            </div>
            <div class="metric">
                <strong>Trough:</strong> ₹{dd.get('trough', 0):.2f}
            </div>
            <div class="metric">
                <strong>Recovery Time:</strong> {dd.get('recovery_time', 'N/A')}
            </div>

            <h2>🎯 Win/Loss Metrics</h2>
            <table>
                <tr>
                    <th>Metric</th>
                    <th>Value</th>
                </tr>
                <tr>
                    <td>Win Rate</td>
                    <td class="{'good' if win.get('win_rate', 0) >= 50 else 'bad'}">
                    {win.get('win_rate', 0):.2f}%</td>
                </tr>
                <tr>
                    <td>Winning Trades</td>
                    <td>{win.get('winning_trades', 0)}</td>
                </tr>
                <tr>
                    <td>Losing Trades</td>
                    <td>{win.get('losing_trades', 0)}</td>
                </tr>
                <tr>
                    <td>Profit Factor</td>
                    <td class="{'good' if win.get('profit_factor', 0) > 1 else 'bad'}">
                    {win.get('profit_factor', 0):.3f}</td>
                </tr>
                <tr>
                    <td>Average Win</td>
                    <td class="good">₹{win.get('avg_win', 0):.2f}</td>
                </tr>
                <tr>
                    <td>Average Loss</td>
                    <td class="bad">₹{win.get('avg_loss', 0):.2f}</td>
                </tr>
                <tr>
                    <td>Largest Win</td>
                    <td class="good">₹{win.get('largest_win', 0):.2f}</td>
                </tr>
                <tr>
                    <td>Largest Loss</td>
                    <td class="bad">₹{win.get('largest_loss', 0):.2f}</td>
                </tr>
            </table>

            <h2>⏱️ Trade Duration</h2>
            <div class="metric">
                <strong>Average Duration:</strong> {dur.get('avg_duration_hours', 0):.2f} hours
            </div>
            <div class="metric">
                <strong>Median Duration:</strong> {dur.get('median_duration_hours', 0):.2f} hours
            </div>
            <div class="metric">
                <strong>Winning Trades Avg:</strong> {dur.get('winning_avg_duration', 0):.2f} hours
            </div>
            <div class="metric">
                <strong>Losing Trades Avg:</strong> {dur.get('losing_avg_duration', 0):.2f} hours
            </div>

            <h2>🔄 BUY vs SELL Analysis</h2>
            <table>
                <tr>
                    <th>Action</th>
                    <th>Count</th>
                    <th>Win Rate</th>
                    <th>Total P&L</th>
                    <th>Avg P&L</th>
                </tr>
        """

        if action and 'buy' in action:
            buy = action['buy']
            html += f"""
                <tr>
                    <td><strong>BUY</strong></td>
                    <td>{buy.get('count', 0)}</td>
                    <td>{buy.get('win_rate', 0):.2f}%</td>
                    <td class="{'good' if buy.get('total_pnl', 0) > 0 else 'bad'}">
                    ₹{buy.get('total_pnl', 0):.2f}</td>
                    <td>₹{buy.get('avg_pnl', 0):.2f}</td>
                </tr>
            """

        if action and 'sell' in action:
            sell = action['sell']
            html += f"""
                <tr>
                    <td><strong>SELL</strong></td>
                    <td>{sell.get('count', 0)}</td>
                    <td>{sell.get('win_rate', 0):.2f}%</td>
                    <td class="{'good' if sell.get('total_pnl', 0) > 0 else 'bad'}">
                    ₹{sell.get('total_pnl', 0):.2f}</td>
                    <td>₹{sell.get('avg_pnl', 0):.2f}</td>
                </tr>
            """

        html += """
            </table>

            <div style="margin-top: 30px; padding: 15px; background: #d4edda; border-left: 4px solid #28a745;">
                <strong>💡 Interpretation Guide:</strong><br>
                • <strong>Sharpe Ratio &gt; 1:</strong> Good risk-adjusted returns<br>
                • <strong>Win Rate &gt; 50%:</strong> Majority of trades profitable<br>
                • <strong>Profit Factor &gt; 1.5:</strong> Strong trading strategy<br>
                • <strong>Max Drawdown &lt; 20%:</strong> Good risk management
            </div>
        </body>
        </html>
        """

        return html