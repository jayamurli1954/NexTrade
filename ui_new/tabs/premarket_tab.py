from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                             QTextEdit, QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QColor
from analyzer.enhanced_analyzer import EnhancedAnalyzer
from datetime import datetime, time as dt_time


class PreMarketThread(QThread):
    """Background thread for pre-market analysis"""
    progress_update = pyqtSignal(str)  # Progress message
    analysis_complete = pyqtSignal(dict)  # Results
    analysis_error = pyqtSignal(str)  # Error message

    def __init__(self, analyzer, watchlist):
        super().__init__()
        self.analyzer = analyzer
        self.watchlist = watchlist
        self.is_running = True

    def run(self):
        """Run pre-market analysis in background with real-time progress"""
        try:
            total = len(self.watchlist)
            self.progress_update.emit(f"🔍 Starting pre-market analysis of {total} stocks...")

            # Analyze stocks one by one with progress updates
            results = []
            signals_found = 0

            for idx, symbol in enumerate(self.watchlist, 1):
                if not self.is_running:
                    return

                try:
                    signal = self.analyzer.analyze_symbol(symbol, exchange="NSE")
                    if signal:
                        results.append(signal)
                        signals_found += 1

                    percentage = int((idx / total) * 100)
                    self.progress_update.emit(
                        f"🔍 Analyzing... {idx}/{total} ({percentage}%) | Found: {signals_found} signals"
                    )

                except Exception as e:
                    print(f"⚠️ Error analyzing {symbol}: {e}")

                if idx < total:
                    import time
                    time.sleep(0.25)

            if not self.is_running:
                return

            # Sort by confidence
            results.sort(key=lambda x: x['confidence'], reverse=True)

            # Package results
            result_data = {
                'timestamp': datetime.now().isoformat(),
                'total_analyzed': total,
                'signals_found': len(results),
                'signals': results[:10]  # Top 10
            }

            self.analysis_complete.emit(result_data)

        except Exception as e:
            self.analysis_error.emit(str(e))

    def stop(self):
        self.is_running = False
        self.quit()
        self.wait()


class PreMarketTab(QWidget):
    """Pre-Market Analysis with real-time progress tracking"""

    def __init__(self, parent, conn_mgr):
        super().__init__(parent)
        self.parent = parent
        self.conn_mgr = conn_mgr
        self.analyzer = EnhancedAnalyzer(data_provider=self.conn_mgr)
        self.analysis_thread = None
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        # Header
        header = QHBoxLayout()
        title = QLabel("🌅 Pre-Market Analyzer")
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: #333;")
        header.addWidget(title)

        header.addStretch()

        # Scan button
        self.scan_btn = QPushButton("🔍 Scan Pre-Market")
        self.scan_btn.setStyleSheet("""
            font-size: 16px;
            font-weight: bold;
            padding: 10px 25px;
            border-radius: 8px;
        """)
        self.scan_btn.clicked.connect(self.scan_premarket)
        self.scan_btn.setCursor(Qt.PointingHandCursor)
        header.addWidget(self.scan_btn)

        layout.addLayout(header)

        # Progress label
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
                font-size: 14px;
                gridline-color: #e0e0e0;
            }
            QHeaderView::section {
                font-weight: bold;
                font-size: 15px;
                padding: 10px;
                border: none;
            }
        """)

        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "Rank", "Symbol", "LTP", "Signal", "Confidence", "Target / SL"
        ])

        header_view = self.table.horizontalHeader()
        header_view.setSectionResizeMode(QHeaderView.Stretch)
        header_view.setSectionResizeMode(0, QHeaderView.Fixed)
        self.table.setColumnWidth(0, 60)

        self.table.setMinimumHeight(400)
        layout.addWidget(self.table)

        # Status label
        self.status_label = QLabel("Click 'Scan Pre-Market' to analyze stocks")
        self.status_label.setStyleSheet("""
            font-size: 14px;
            color: #666;
            padding: 10px;
            background: #f9f9f9;
            border-radius: 5px;
        """)
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)

    def scan_premarket(self):
        """Start pre-market analysis"""
        # Check if already scanning
        if self.analysis_thread and self.analysis_thread.isRunning():
            QMessageBox.warning(self, "Scan in Progress", "Please wait for the current scan to complete.")
            return

        # Check connection
        status = self.conn_mgr.get_connection_status()
        if not status['broker_connected']:
            QMessageBox.warning(
                self,
                "Not Connected",
                "⚠️ Please connect to broker first!\n\nGo to Dashboard and click 'Connect to Broker'"
            )
            return

        # Update UI
        self.status_label.setText("🔍 Preparing pre-market scan...")
        self.progress_label.setText("🔍 Initializing...")
        self.scan_btn.setEnabled(False)

        # Get watchlist
        watchlist = self.conn_mgr.get_stock_list()

        # Create and start thread
        self.analysis_thread = PreMarketThread(self.analyzer, watchlist)
        self.analysis_thread.progress_update.connect(self.on_progress_update)
        self.analysis_thread.analysis_complete.connect(self.on_analysis_complete)
        self.analysis_thread.analysis_error.connect(self.on_analysis_error)
        self.analysis_thread.start()

        self.parent.statusBar().showMessage("🔍 Pre-market analysis running...", 2000)

    def on_progress_update(self, message):
        """Handle progress updates"""
        self.progress_label.setText(message)

    def on_analysis_complete(self, result_data):
        """Handle analysis completion"""
        signals = result_data['signals']
        total_analyzed = result_data['total_analyzed']
        signals_found = result_data['signals_found']

        # Display results
        self.display_results(signals)

        # Update status
        self.progress_label.setText(f"✅ Analysis complete! Found {signals_found} signals")
        self.status_label.setText(
            f"✅ Analyzed {total_analyzed} stocks | Found {signals_found} signals | Showing top {len(signals)}"
        )

        # Re-enable button
        self.scan_btn.setEnabled(True)
        self.parent.statusBar().showMessage(f"✅ Pre-market scan complete: {signals_found} signals", 5000)

    def on_analysis_error(self, error_msg):
        """Handle analysis errors"""
        self.progress_label.setText(f"❌ Error: {error_msg}")
        self.status_label.setText("❌ Analysis failed. Please try again.")
        self.scan_btn.setEnabled(True)
        QMessageBox.critical(self, "Analysis Error", f"An error occurred:\n\n{error_msg}")

    def display_results(self, signals):
        """Display analysis results"""
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(signals))

        if not signals:
            self.table.setRowCount(1)
            no_data = QTableWidgetItem("No signals found")
            no_data.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(0, 0, no_data)
            self.table.setSpan(0, 0, 1, 6)
            return

        for row, signal in enumerate(signals):
            # Rank
            rank_item = QTableWidgetItem(f"#{row + 1}")
            rank_item.setTextAlignment(Qt.AlignCenter)
            rank_item.setBackground(QColor(240, 240, 240))
            self.table.setItem(row, 0, rank_item)

            # Symbol
            symbol_item = QTableWidgetItem(signal.get('symbol', ''))
            symbol_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 1, symbol_item)

            # LTP
            ltp = signal.get('ltp', signal.get('current_price', 0))
            ltp_item = QTableWidgetItem(f"₹{ltp:.2f}")
            ltp_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 2, ltp_item)

            # Signal
            signal_type = signal.get('signal', signal.get('action', 'HOLD'))
            signal_item = QTableWidgetItem(signal_type)
            signal_item.setTextAlignment(Qt.AlignCenter)
            if signal_type == 'BUY':
                signal_item.setForeground(QColor(0, 150, 0))
                signal_item.setBackground(QColor(230, 255, 230))
            else:
                signal_item.setForeground(QColor(200, 0, 0))
                signal_item.setBackground(QColor(255, 230, 230))
            self.table.setItem(row, 3, signal_item)

            # Confidence
            conf = signal.get('confidence', 0)
            conf_item = QTableWidgetItem(f"{conf}%")
            conf_item.setTextAlignment(Qt.AlignCenter)
            if conf >= 80:
                conf_item.setForeground(QColor(0, 150, 0))
            elif conf >= 70:
                conf_item.setForeground(QColor(255, 140, 0))
            self.table.setItem(row, 4, conf_item)

            # Target / SL
            target_sl_item = QTableWidgetItem(
                f"T: ₹{signal.get('target', 0):.2f}\nSL: ₹{signal.get('stop_loss', 0):.2f}"
            )
            target_sl_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 5, target_sl_item)

        self.table.setSortingEnabled(True)
