#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ==============================================================================
# FILE: analyzer_tab.py
# LOCATION: c:\Users\Dell\tradingbot_new\ui_new\tabs\analyzer_tab.py
# VERSION: 1.3.0 - Deterministic analyzer (consistent results)
# LAST UPDATED: 2025-10-13
#
# FEATURES:
# - Top 10 stocks only
# - Single action button (BUY or SELL based on signal)
# - Deterministic algorithm (same results every time)
# - No random behavior
# ==============================================================================

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QPushButton, QTableWidget, QTableWidgetItem, 
                             QHeaderView, QSpinBox, QMessageBox)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from analyzer.enhanced_analyzer import EnhancedAnalyzer

class AnalyzerTab(QWidget):
    """
    Stock Analyzer with Direct Trade Execution
    
    Features:
    - Shows TOP 10 stocks only
    - Single action button (BUY or SELL based on signal)
    - Ranked by confidence score
    - Deterministic analysis (consistent results)
    """
    
    def __init__(self, parent, conn_mgr, paper_trading_tab=None):
        super().__init__(parent)
        self.parent = parent
        self.conn_mgr = conn_mgr
        self.paper_trading_tab = paper_trading_tab
        
        self.scan_results = []
        self.analyzer = EnhancedAnalyzer(data_provider=self.conn_mgr)
        
        self.init_ui()
    
    def set_paper_trading_tab(self, paper_trading_tab):
        """Set reference to paper trading tab"""
        self.paper_trading_tab = paper_trading_tab
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        
        # Header
        header = QHBoxLayout()
        
        title = QLabel("🔍 Stock Analyzer")
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: #333;")
        header.addWidget(title)
        
        header.addStretch()
        
        # Confidence threshold
        threshold_label = QLabel("Min Confidence:")
        threshold_label.setStyleSheet("font-size: 16px;")
        header.addWidget(threshold_label)
        
        self.threshold_spin = QSpinBox()
        self.threshold_spin.setRange(0, 100)
        self.threshold_spin.setValue(65)
        self.threshold_spin.setSuffix("%")
        self.threshold_spin.setStyleSheet("font-size: 16px; padding: 5px;")
        header.addWidget(self.threshold_spin)
        
        # Scan button
        scan_btn = QPushButton("🔍 Scan Now")
        scan_btn.setStyleSheet("""
            background: #2196F3; 
            color: white; 
            font-size: 16px; 
            font-weight: bold; 
            padding: 10px 25px; 
            border-radius: 8px;
            border: none;
        """)
        scan_btn.clicked.connect(self.scan_stocks)
        scan_btn.setCursor(Qt.PointingHandCursor)
        header.addWidget(scan_btn)
        
        layout.addLayout(header)
        
        # Results table
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
                background: #2196F3; 
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
        
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "Rank", "Symbol", "LTP", "Confidence", "Signal", "Target / SL", "Action"
        ])
        
        header_view = self.table.horizontalHeader()
        header_view.setSectionResizeMode(0, QHeaderView.Fixed)  # Rank
        header_view.setSectionResizeMode(1, QHeaderView.Stretch)  # Symbol
        header_view.setSectionResizeMode(2, QHeaderView.Stretch)  # LTP
        header_view.setSectionResizeMode(3, QHeaderView.Stretch)  # Confidence
        header_view.setSectionResizeMode(4, QHeaderView.Stretch)  # Signal
        header_view.setSectionResizeMode(5, QHeaderView.Stretch)  # Target/SL
        header_view.setSectionResizeMode(6, QHeaderView.Fixed)    # Action
        
        self.table.setColumnWidth(0, 60)   # Rank
        self.table.setColumnWidth(6, 140)  # Action button
        
        self.table.setVerticalScrollMode(QTableWidget.ScrollPerPixel)
        self.table.setMinimumHeight(400)
        
        layout.addWidget(self.table)
        
        # Status
        self.status_label = QLabel("Click 'Scan Now' to analyze stocks from watchlist")
        self.status_label.setStyleSheet("""
            font-size: 14px; 
            color: #666; 
            padding: 10px;
            background: #f9f9f9;
            border-radius: 5px;
        """)
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)
    
    def scan_stocks(self):
        """Scan stocks and show TOP 10 results only - DETERMINISTIC"""
        self.status_label.setText("🔍 Scanning stocks...")
        self.parent.statusBar().showMessage("🔍 Analyzing stocks...", 2000)
        
        threshold = self.threshold_spin.value()
        watchlist = self.conn_mgr.get_stock_list()
        ltp_data = self.conn_mgr.get_ltp_batch(watchlist)
        
# Use REAL enhanced analyzer
        self.scan_results = self.analyzer.analyze_watchlist(watchlist)        
        # Sort by confidence (highest first)
        self.scan_results.sort(key=lambda x: x['confidence'], reverse=True)
        
        # ⭐ KEEP ONLY TOP 10
        total_found = len(self.scan_results)
        self.scan_results = self.scan_results[:10]
        
        # Display results
        self.display_results()
        
        # Update status
        if self.scan_results:
            self.status_label.setText(
                f"✅ Showing top 10 stocks (found {total_found} stocks with confidence ≥ {threshold}%)"
            )
            self.parent.statusBar().showMessage(
                f"✅ Found {total_found} stocks, showing top 10", 
                5000
            )
        else:
            self.status_label.setText(
                f"⚠️  No stocks found with confidence ≥ {threshold}%"
            )
            self.parent.statusBar().showMessage(
                f"⚠️  No stocks meet criteria", 
                3000
            )
    
    def display_results(self):
        """Display TOP 10 scan results"""
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(self.scan_results))
        
        if not self.scan_results:
            self.table.setRowCount(1)
            no_data = QTableWidgetItem("No stocks meet the confidence criteria")
            no_data.setTextAlignment(Qt.AlignCenter)
            no_data.setFont(no_data.font())
            self.table.setItem(0, 0, no_data)
            self.table.setSpan(0, 0, 1, 7)
            return
        
        for row, result in enumerate(self.scan_results):
            # Rank
            rank_item = QTableWidgetItem(f"#{row + 1}")
            rank_item.setTextAlignment(Qt.AlignCenter)
            rank_item.setBackground(QColor(240, 240, 240))
            rank_item.setFont(rank_item.font())
            self.table.setItem(row, 0, rank_item)
            
            # Symbol
            symbol_item = QTableWidgetItem(result['symbol'])
            symbol_item.setTextAlignment(Qt.AlignCenter)
            symbol_item.setFont(symbol_item.font())
            self.table.setItem(row, 1, symbol_item)
            
            # LTP
            ltp_item = QTableWidgetItem(f"₹{result['ltp']:.2f}")
            ltp_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 2, ltp_item)
            
            # Confidence
            conf_item = QTableWidgetItem(f"{result['confidence']}%")
            conf_item.setTextAlignment(Qt.AlignCenter)
            conf = result['confidence']
            if conf >= 80:
                conf_item.setForeground(QColor(0, 150, 0))
                conf_item.setBackground(QColor(230, 255, 230))
            elif conf >= 70:
                conf_item.setForeground(QColor(255, 140, 0))
                conf_item.setBackground(QColor(255, 245, 230))
            self.table.setItem(row, 3, conf_item)
            
            # Signal
            signal_item = QTableWidgetItem(result['signal'])
            signal_item.setTextAlignment(Qt.AlignCenter)
            if result['signal'] == 'BUY':
                signal_item.setForeground(QColor(0, 150, 0))
                signal_item.setBackground(QColor(230, 255, 230))
            else:  # SELL
                signal_item.setForeground(QColor(200, 0, 0))
                signal_item.setBackground(QColor(255, 230, 230))
            self.table.setItem(row, 4, signal_item)
            
            # Target / SL (combined)
            target_sl_item = QTableWidgetItem(
                f"T: ₹{result['target']:.2f}\nSL: ₹{result['stop_loss']:.2f}"
            )
            target_sl_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 5, target_sl_item)
            
            # ⭐ SINGLE ACTION BUTTON (based on signal)
            if result['signal'] == 'BUY':
                action_btn = QPushButton("📈 Execute BUY")
                action_btn.setStyleSheet("""
                    QPushButton {
                        background: #4CAF50; 
                        color: white; 
                        font-size: 13px; 
                        font-weight: bold;
                        padding: 8px 12px; 
                        border-radius: 5px;
                        border: none;
                    }
                    QPushButton:hover {
                        background: #45a049;
                    }
                    QPushButton:pressed {
                        background: #3d8b40;
                    }
                """)
            else:  # SELL
                action_btn = QPushButton("📉 Execute SELL")
                action_btn.setStyleSheet("""
                    QPushButton {
                        background: #f44336; 
                        color: white; 
                        font-size: 13px; 
                        font-weight: bold;
                        padding: 8px 12px; 
                        border-radius: 5px;
                        border: none;
                    }
                    QPushButton:hover {
                        background: #da190b;
                    }
                    QPushButton:pressed {
                        background: #c1170a;
                    }
                """)
            
            action_btn.clicked.connect(
                lambda checked, r=result: self.execute_trade(r, r['signal'])
            )
            action_btn.setCursor(Qt.PointingHandCursor)
            self.table.setCellWidget(row, 6, action_btn)
        
        # Don't enable sorting - keep ranked by confidence
        self.table.setSortingEnabled(False)
    
    def execute_trade(self, result, action):
        """Execute trade and send to paper trading"""
        if not self.paper_trading_tab:
            QMessageBox.warning(
                self,
                "Not Available",
                "Paper trading tab not initialized"
            )
            return
        
        # Confirm with user
        reply = QMessageBox.question(
            self,
            'Confirm Trade',
            f"Execute {action} trade?\n\n"
            f"Symbol: {result['symbol']}\n"
            f"Entry Price: ₹{result['ltp']:.2f}\n"
            f"Target: ₹{result['target']:.2f}\n"
            f"Stop Loss: ₹{result['stop_loss']:.2f}\n"
            f"Confidence: {result['confidence']}%",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.No:
            return
        
        # Prepare trade data
        trade_data = {
            'symbol': result['symbol'],
            'action': action,
            'entry_price': result['ltp'],
            'target': result['target'],
            'stop_loss': result['stop_loss'],
            'quantity': 1,
            'confidence': result['confidence']
        }
        
        # Add to paper trading
        order_id = self.paper_trading_tab.add_trade(trade_data)
        
        # Show confirmation
        QMessageBox.information(
            self,
            "Trade Executed",
            f"✅ {action} order placed successfully!\n\n"
            f"Symbol: {result['symbol']}\n"
            f"Entry: ₹{result['ltp']:.2f}\n"
            f"Target: ₹{result['target']:.2f}\n"
            f"Stop Loss: ₹{result['stop_loss']:.2f}\n"
            f"Confidence: {result['confidence']}%\n\n"
            f"Order ID: {order_id[-8:]}\n\n"
            f"Check the Paper Trading tab to monitor this trade."
        )
        
        self.parent.statusBar().showMessage(
            f"✅ {action} trade executed for {result['symbol']}", 
            5000
        )