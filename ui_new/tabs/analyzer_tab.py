#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ==============================================================================
# FILE: analyzer_tab.py
# LOCATION: c:\Users\Dell\tradingbot_new\ui_new\tabs\analyzer_tab.py
# VERSION: 1.5.0 - Background threading (NO UI FREEZING!)
# LAST UPDATED: 2025-10-18
#
# FEATURES:
# - Top 10 stocks only
# - Background thread analysis (UI stays responsive!)
# - Progress updates during scan
# - Deterministic algorithm (consistent results)
# - Can switch tabs during analysis
# ==============================================================================

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QPushButton, QTableWidget, QTableWidgetItem, 
                             QHeaderView, QSpinBox, QMessageBox, QApplication)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QColor
from analyzer.enhanced_analyzer import EnhancedAnalyzer


class AnalyzerThread(QThread):
    """
    Background thread for stock analysis
    Prevents UI freezing during long scans
    """
    # Signals to communicate with main UI
    progress_update = pyqtSignal(str)  # Progress message
    analysis_complete = pyqtSignal(list)  # Results
    analysis_error = pyqtSignal(str)  # Error message
    
    def __init__(self, analyzer, watchlist, threshold):
        super().__init__()
        self.analyzer = analyzer
        self.watchlist = watchlist
        self.threshold = threshold
        self.is_running = True
    
    def run(self):
        """Run analysis in background"""
        try:
            # Emit starting message
            self.progress_update.emit(f"🔍 Starting analysis of {len(self.watchlist)} stocks...")
            
            # Analyze all stocks
            results = self.analyzer.analyze_watchlist(self.watchlist)
            
            # Check if thread was stopped
            if not self.is_running:
                return
            
            # Sort by confidence
            results.sort(key=lambda x: x['confidence'], reverse=True)
            
            # Emit completion
            self.analysis_complete.emit(results)
            
        except Exception as e:
            # Emit error
            self.analysis_error.emit(str(e))
    
    def stop(self):
        """Stop the analysis thread"""
        self.is_running = False
        self.quit()
        self.wait()


class AnalyzerTab(QWidget):
    """
    Stock Analyzer with Direct Trade Execution
    
    Features:
    - Shows TOP 10 stocks only
    - Background thread analysis (no UI freezing!)
    - Single action button (BUY or SELL based on signal)
    - Ranked by confidence score
    - Deterministic analysis (consistent results)
    - Progress indicator during scan
    """
    
    def __init__(self, parent, conn_mgr, paper_trading_tab=None):
        super().__init__(parent)
        self.parent = parent
        self.conn_mgr = conn_mgr
        self.paper_trading_tab = paper_trading_tab

        self.scan_results = []
        # Pass config file to analyzer so it can read NEWSAPI_KEY
        self.analyzer = EnhancedAnalyzer(data_provider=self.conn_mgr, config_file="config.json")
        
        # Thread management
        self.analyzer_thread = None
        
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
        self.scan_btn = QPushButton("🔍 Scan Now")
        self.scan_btn.setStyleSheet("""
            font-size: 16px; 
            font-weight: bold; 
            padding: 10px 25px; 
            border-radius: 8px;
            border: none;
        """)
        self.scan_btn.clicked.connect(self.scan_stocks)
        self.scan_btn.setCursor(Qt.PointingHandCursor)
        header.addWidget(self.scan_btn)
        
        layout.addLayout(header)
        
        # Progress indicator
        self.progress_label = QLabel("")
        self.progress_label.setStyleSheet("font-weight: bold; font-size: 14px; padding: 5px;")
        self.progress_label.setAlignment(Qt.AlignCenter)
        self.progress_label.setMinimumHeight(30)
        layout.addWidget(self.progress_label)
        
        # Results table
        self.table = QTableWidget()
        self.table.setStyleSheet("""
            QTableWidget { 
                border: 2px solid #ddd; 
                border-radius: 5px; 
                font-size: 15px;
                gridline-color: #e0e0e0;
            }
            QHeaderView::section { 
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
        """Start background analysis - UI STAYS RESPONSIVE!"""
        
        # Check if already scanning
        if self.analyzer_thread and self.analyzer_thread.isRunning():
            QMessageBox.warning(
                self,
                "Scan in Progress",
                "Please wait for the current scan to complete."
            )
            return
        
        # Update UI
        self.status_label.setText("🔍 Preparing to scan...")
        self.progress_label.setText("🔍 Initializing analysis...")
        self.scan_btn.setEnabled(False)  # Disable button during scan
        
        # Get parameters
        threshold = self.threshold_spin.value()
        watchlist = self.conn_mgr.get_stock_list()
        
        # Create and start background thread
        self.analyzer_thread = AnalyzerThread(self.analyzer, watchlist, threshold)
        
        # Connect signals
        self.analyzer_thread.progress_update.connect(self.on_progress_update)
        self.analyzer_thread.analysis_complete.connect(self.on_analysis_complete)
        self.analyzer_thread.analysis_error.connect(self.on_analysis_error)
        
        # Start analysis in background
        self.analyzer_thread.start()
        
        # Update status
        self.parent.statusBar().showMessage("🔍 Analyzing stocks in background...", 2000)
    
    def on_progress_update(self, message):
        """Handle progress updates from thread"""
        self.progress_label.setText(message)
        QApplication.processEvents()  # Keep UI responsive
    
    def on_analysis_complete(self, results):
        """Handle completion of analysis"""
        threshold = self.threshold_spin.value()
        
        # Store results
        self.scan_results = results
        
        # Keep only top 10
        total_found = len(self.scan_results)
        self.scan_results = self.scan_results[:10]
        
        # Display results
        self.display_results()
        
        # Update progress
        self.progress_label.setText(f"✅ Analysis complete! Found {total_found} signals, showing top 10")
        
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
                f"⚠️ No stocks found with confidence ≥ {threshold}%"
            )
            self.progress_label.setText(f"⚠️ No signals found (threshold: {threshold}%)")
            self.parent.statusBar().showMessage(
                f"⚠️ No stocks meet criteria", 
                3000
            )
        
        # Re-enable scan button
        self.scan_btn.setEnabled(True)
    
    def on_analysis_error(self, error_msg):
        """Handle analysis errors"""
        self.progress_label.setText(f"❌ Error: {error_msg}")
        self.status_label.setText("❌ Analysis failed. Please try again.")
        self.scan_btn.setEnabled(True)
        
        QMessageBox.critical(
            self,
            "Analysis Error",
            f"An error occurred during analysis:\n\n{error_msg}"
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
            symbol_item = QTableWidgetItem(result.get('symbol', ''))
            symbol_item.setTextAlignment(Qt.AlignCenter)
            symbol_item.setFont(symbol_item.font())
            self.table.setItem(row, 1, symbol_item)
            
            # LTP
            ltp = result.get('ltp', result.get('current_price', 0))
            ltp_item = QTableWidgetItem(f"₹{ltp:.2f}")
            ltp_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 2, ltp_item)
            
            # Confidence
            conf_item = QTableWidgetItem(f"{result.get('confidence', 0)}%")
            conf_item.setTextAlignment(Qt.AlignCenter)
            conf = result.get('confidence', 0)
            if conf >= 80:
                conf_item.setForeground(QColor(0, 150, 0))
                conf_item.setBackground(QColor(230, 255, 230))
            elif conf >= 70:
                conf_item.setForeground(QColor(255, 140, 0))
                conf_item.setBackground(QColor(255, 245, 230))
            self.table.setItem(row, 3, conf_item)
            
            # Signal
            signal_item = QTableWidgetItem(result.get('signal', result.get('action', 'HOLD')))
            signal_item.setTextAlignment(Qt.AlignCenter)
            if result.get('signal', result.get('action', 'HOLD')) == 'BUY':
                signal_item.setForeground(QColor(0, 150, 0))
                signal_item.setBackground(QColor(230, 255, 230))
            else:  # SELL
                signal_item.setForeground(QColor(200, 0, 0))
                signal_item.setBackground(QColor(255, 230, 230))
            self.table.setItem(row, 4, signal_item)
            
            # Target / SL (combined)
            target_sl_item = QTableWidgetItem(
                f"T: ₹{result.get('target', 0):.2f}\nSL: ₹{result.get('stop_loss', 0):.2f}"
            )
            target_sl_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 5, target_sl_item)
            
            # ⭐ SINGLE ACTION BUTTON (based on signal)
            if result.get('signal', result.get('action', 'HOLD')) == 'BUY':
                action_btn = QPushButton("📈 Execute BUY")
                action_btn.setStyleSheet("""
                    QPushButton {
                        font-size: 13px; 
                        font-weight: bold;
                        padding: 8px 12px; 
                        border-radius: 5px;
                        border: none;
                    }
                """)
            else:  # SELL
                action_btn = QPushButton("📉 Execute SELL")
                action_btn.setStyleSheet("""
                    QPushButton {
                        font-size: 13px; 
                        font-weight: bold;
                        padding: 8px 12px; 
                        border-radius: 5px;
                        border: none;
                    }
                """)
            
            action_btn.clicked.connect(
                lambda checked, r=result: self.execute_trade(r, r.get('signal', r.get('action', 'HOLD')))
            )
            action_btn.setCursor(Qt.PointingHandCursor)
            self.table.setCellWidget(row, 6, action_btn)
        
        # Don't enable sorting - keep ranked by confidence
        self.table.setSortingEnabled(False)
    
    def execute_trade(self, result, action):
        """Execute trade and send to paper trading"""
        print(f"🔍 DEBUG: execute_trade called for {result.get('symbol', 'UNKNOWN')} - {action}")
        print(f"🔍 DEBUG: paper_trading_tab exists: {self.paper_trading_tab is not None}")
        
        if not self.paper_trading_tab:
            print("❌ DEBUG: paper_trading_tab is None!")
            QMessageBox.warning(
                self,
                "Not Available",
                "Paper trading tab not initialized. Please restart the application."
            )
            return
        
        print(f"✅ DEBUG: paper_trading_tab is available, proceeding...")
        
        # Confirm with user
        reply = QMessageBox.question(
            self,
            'Confirm Trade',
            f"Execute {action} trade?\n\n"
            f"Symbol: {result.get('symbol', '')}\n"
            f"Entry Price: ₹{result.get('ltp', result.get('current_price', 0)):.2f}\n"
            f"Target: ₹{result.get('target', 0):.2f}\n"
            f"Stop Loss: ₹{result.get('stop_loss', 0):.2f}\n"
            f"Confidence: {result.get('confidence', 0)}%",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.No:
            return
        
        # FETCH FRESH LTP - DON'T TRUST ANALYZER DISPLAY!
        symbol = result.get('symbol', '')
        print(f"🔍 DEBUG: Fetching FRESH LTP for {symbol}...")
        
        try:
            fresh_ltp = self.conn_mgr.get_ltp(symbol, 'NSE')
            if fresh_ltp is None:
                print(f"⚠️  DEBUG: Fresh LTP for {symbol} is None, using fallback.")
                fresh_ltp = result.get('ltp', result.get('current_price', 0))
            else:
                print(f"✅ DEBUG: Fresh LTP for {symbol}: ₹{fresh_ltp:.2f}")
        except Exception as e:
            print(f"❌ DEBUG: Error getting fresh LTP: {e}")
            fresh_ltp = result.get('ltp', result.get('current_price', 0))
            print(f"⚠️  DEBUG: Using analyzer price as fallback: ₹{fresh_ltp:.2f}")
        
        # Prepare trade data with FRESH LTP
        trade_data = {
            'symbol': symbol,
            'action': action,
            'entry_price': fresh_ltp,  # ← FRESH PRICE!
            'target': result.get('target', 0),
            'stop_loss': result.get('stop_loss', 0),
            'quantity': 1,
            'confidence': result.get('confidence', 0)
        }
        
        print(f"🔍 DEBUG: Trade data prepared - Entry: ₹{trade_data['entry_price']:.2f}, Target: ₹{trade_data['target']:.2f}, SL: ₹{trade_data['stop_loss']:.2f}")
        
        # Add to paper trading
        try:
            print(f"🔍 DEBUG: Calling paper_trading_tab.add_trade with data: {trade_data}")
            order_id = self.paper_trading_tab.add_trade(trade_data)
            print(f"✅ DEBUG: Trade added successfully! Order ID: {order_id}")
        except Exception as e:
            print(f"❌ DEBUG: Error adding trade: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to add trade: {str(e)}"
            )
            return
        
        # Show confirmation
        QMessageBox.information(
            self,
            "Trade Executed",
            f"✅ {action} order placed successfully!\n\n"
            f"Symbol: {result.get('symbol', '')}\n"
            f"Entry: ₹{result.get('ltp', result.get('current_price', 0)):.2f}\n"
            f"Target: ₹{result.get('target', 0):.2f}\n"
            f"Stop Loss: ₹{result.get('stop_loss', 0):.2f}\n"
            f"Confidence: {result.get('confidence', 0)}%\n\n"
            f"Order ID: {order_id[-8:]}\n\n"
            f"Check the Paper Trading tab to monitor this trade."
        )
        
        self.parent.statusBar().showMessage(
            f"✅ {action} trade executed for {result.get('symbol', '')}", 
            5000
        )
    
    def closeEvent(self, event):
        """Clean up thread when tab is closed"""
        if self.analyzer_thread and self.analyzer_thread.isRunning():
            self.analyzer_thread.stop()
        event.accept()
