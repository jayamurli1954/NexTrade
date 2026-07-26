#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ==============================================================================
# FILE: dashboard_tab.py
# VERSION: 3.0.0 - Premium Financial Terminal UI & Paper Sandbox Dialog
# LOCATION: ui_new/tabs/dashboard_tab.py
# ==============================================================================

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QMessageBox, QDialog
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont
from ui_new.widgets.scrolling_ticker import ScrollingTicker


class ConnectionOptionsDialog(QDialog):
    """Custom dark themed dialog for selecting connection mode when credentials are missing or unconfigured"""
    
    def __init__(self, parent=None, error_msg=None):
        super().__init__(parent)
        self.setWindowTitle("NexTrade — Broker Connection Setup")
        self.setMinimumWidth(520)
        self.setStyleSheet("""
            QDialog {
                background-color: #1E2532;
                border: 1px solid #334155;
                border-radius: 12px;
            }
            QLabel {
                color: #F8FAFC;
            }
        """)
        self.selected_action = "cancel"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel("🔌 Broker Connection Setup")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #38BDF8;")
        layout.addWidget(title)

        detail_text = f"Angel One Response: {error_msg}\n\n" if error_msg else ""
        desc = QLabel(
            f"{detail_text}"
            "Live Angel One broker credentials may be unconfigured, incomplete, or require re-authentication.\n\n"
            "You can launch directly in Paper Trading Sandbox Mode to evaluate technical "
            "strategies and paper trades, or update your live credentials in Settings."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("font-size: 14px; color: #94A3B8; line-height: 1.6;")
        layout.addWidget(desc)


        # Action Buttons
        self.paper_btn = QPushButton("🚀 Connect Paper Trading Sandbox Mode")
        self.paper_btn.setMinimumHeight(48)
        self.paper_btn.setCursor(Qt.PointingHandCursor)
        self.paper_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #10B981, stop:1 #059669);
                color: #FFFFFF;
                border: none;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #059669;
            }
        """)
        self.paper_btn.clicked.connect(self.on_paper)
        layout.addWidget(self.paper_btn)

        self.settings_btn = QPushButton("⚙️ Configure Angel One API Credentials")
        self.settings_btn.setMinimumHeight(44)
        self.settings_btn.setCursor(Qt.PointingHandCursor)
        self.settings_btn.setStyleSheet("""
            QPushButton {
                background: #151A24;
                color: #E2E8F0;
                border: 1px solid #334155;
                border-radius: 8px;
                font-size: 13px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #2A3447;
                border: 1px solid #475569;
            }
        """)
        self.settings_btn.clicked.connect(self.on_settings)
        layout.addWidget(self.settings_btn)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setCursor(Qt.PointingHandCursor)
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #64748B;
                border: none;
                font-size: 12px;
            }
            QPushButton:hover {
                color: #94A3B8;
            }
        """)
        self.cancel_btn.clicked.connect(self.reject)
        layout.addWidget(self.cancel_btn)

    def on_paper(self):
        self.selected_action = "paper"
        self.accept()

    def on_settings(self):
        self.selected_action = "settings"
        self.accept()


class DashboardTab(QWidget):
    """Dashboard - Overview of trading bot status"""
    
    def __init__(self, parent, conn_mgr, trade_logger=None):
        super().__init__(parent)
        self.parent = parent
        self.conn_mgr = conn_mgr
        self.trade_logger = trade_logger
        
        self.init_ui()
        
        # Refresh dashboard every 10 seconds
        self.timer = QTimer()
        self.timer.timeout.connect(self.refresh_dashboard)
        self.timer.start(10000)

        # Timer for the ticker
        self.ticker_timer = QTimer()
        self.ticker_timer.timeout.connect(self.update_ticker)
        self.ticker_timer.start(2000) # Update every 2 seconds

        self.ticker_symbols = [
            ("NIFTY", "NSE"),
            ("BANKNIFTY", "NSE"),
            ("SENSEX", "BSE"),
            ("INDIAVIX", "NSE"),
            ("RELIANCE", "NSE"),
            ("HDFCBANK", "NSE"),
            ("BHARTIARTL", "NSE"),
            ("TCS", "NSE"),
            ("INFY", "NSE"),
            ("ICICIBANK", "NSE"),
            ("SBIN", "NSE"),
            ("LT", "NSE"),
            ("WIPRO", "NSE"),
            ("TITAN", "NSE"),
        ]
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(20)

        # Scrolling Ticker
        self.ticker = ScrollingTicker(self)
        self.ticker.setFixedHeight(40)
        self.ticker.setObjectName("scrollingTicker")
        self.ticker.setStyleSheet("#scrollingTicker { border-bottom: 1px solid #1E293B; }")
        layout.addWidget(self.ticker)
        self.ticker.hide() # Initially hidden
        
        # Top bar with connection status and connect button
        top_bar = QHBoxLayout()
        top_bar.setSpacing(15)
        
        # Connection status banner
        self.connection_banner = QLabel()
        self.connection_banner.setAlignment(Qt.AlignCenter)
        self.connection_banner.setMinimumHeight(60)
        self.connection_banner.setStyleSheet("""
            font-size: 16px;
            font-weight: bold;
            padding: 15px;
            border-radius: 10px;
        """)
        top_bar.addWidget(self.connection_banner, 3)  # Takes 3/4 of space
        
        # Connect/Disconnect button
        self.connect_btn = QPushButton("🔌 Connect")
        self.connect_btn.setMinimumHeight(60)
        self.connect_btn.setStyleSheet("""
            QPushButton {
                font-size: 16px;
                font-weight: bold;
                padding: 15px 30px;
                border-radius: 10px;
            }
        """)
        self.connect_btn.setCursor(Qt.PointingHandCursor)
        self.connect_btn.clicked.connect(self.toggle_connection)
        top_bar.addWidget(self.connect_btn, 1)  # Takes 1/4 of space
        
        layout.addLayout(top_bar)
        
        # Stats cards container
        stats_container = QHBoxLayout()
        stats_container.setSpacing(20)
        
        # Card 1: Capital
        self.capital_card = self.create_stat_card(
            "💰 Capital",
            "₹100,000.00",
            "#4F46E5"
        )
        stats_container.addWidget(self.capital_card)
        
        # Card 2: Profit
        self.profit_card = self.create_stat_card(
            "📈 Profit",
            "₹0.00",
            "#10B981"
        )
        stats_container.addWidget(self.profit_card)
        
        # Card 3: Trades
        self.trades_card = self.create_stat_card(
            "💹 Trades",
            "0",
            "#3B82F6"
        )
        stats_container.addWidget(self.trades_card)
        
        # Card 4: Win Rate
        self.winrate_card = self.create_stat_card(
            "🎯 Win Rate",
            "0.0%",
            "#8B5CF6"
        )
        stats_container.addWidget(self.winrate_card)
        
        layout.addLayout(stats_container)
        
        # System status section
        status_section = QVBoxLayout()
        status_section.setSpacing(10)
        
        status_title = QLabel("📊 System Control Panel")
        status_title.setStyleSheet("font-size: 18px; font-weight: bold; color: #38BDF8;")
        status_section.addWidget(status_title)
        
        self.status_list = QLabel()
        self.status_list.setStyleSheet("""
            font-size: 14px;
            padding: 18px;
            background-color: #151A24;
            border: 1px solid #1E293B;
            border-radius: 10px;
            line-height: 1.6;
            color: #E2E8F0;
        """)
        status_section.addWidget(self.status_list)
        
        layout.addLayout(status_section)
        
        # Action buttons
        button_layout = QHBoxLayout()
        button_layout.setSpacing(15)
        
        # Start button
        self.start_btn = QPushButton("▶ Start Trading Engine")
        self.start_btn.setMinimumHeight(50)
        self.start_btn.setCursor(Qt.PointingHandCursor)
        self.start_btn.clicked.connect(self.start_trading)
        button_layout.addWidget(self.start_btn)
        
        # Pause button
        self.pause_btn = QPushButton("⏸ Pause Engine")
        self.pause_btn.setMinimumHeight(50)
        self.pause_btn.setObjectName("secondaryBtn")
        self.pause_btn.setCursor(Qt.PointingHandCursor)
        self.pause_btn.clicked.connect(self.pause_trading)
        button_layout.addWidget(self.pause_btn)
        
        # Refresh button
        refresh_btn = QPushButton("🔄 Refresh Status")
        refresh_btn.setMinimumHeight(50)
        refresh_btn.setObjectName("secondaryBtn")
        refresh_btn.setCursor(Qt.PointingHandCursor)
        refresh_btn.clicked.connect(self.refresh_dashboard)
        button_layout.addWidget(refresh_btn)
        
        layout.addLayout(button_layout)

        # Top Gainers and Losers Section
        gainers_losers_section = QVBoxLayout()
        gainers_losers_section.setSpacing(10)

        section_title = QLabel("📊 Top Gainers & Losers")
        section_title.setStyleSheet("font-size: 18px; font-weight: bold; color: #38BDF8; margin-top: 10px;")
        gainers_losers_section.addWidget(section_title)

        # Container for gainers and losers cards
        gainers_losers_container = QHBoxLayout()
        gainers_losers_container.setSpacing(20)

        # Top Gainers Card
        self.gainers_card = self.create_gainers_losers_card("🚀 Top Gainers", "#10B981")
        gainers_losers_container.addWidget(self.gainers_card)

        # Top Losers Card
        self.losers_card = self.create_gainers_losers_card("📉 Top Losers", "#EF4444")
        gainers_losers_container.addWidget(self.losers_card)

        gainers_losers_section.addLayout(gainers_losers_container)
        layout.addLayout(gainers_losers_section)

        layout.addStretch()

        # Initial refresh
        self.refresh_dashboard()

    def create_stat_card(self, title, value, accent_color="#4F46E5"):
        """Create a modern financial stat card"""
        card = QWidget()
        card.setStyleSheet(f"""
            QWidget {{
                background-color: #1E2532;
                border: 1px solid #2D3748;
                border-left: 5px solid {accent_color};
                border-radius: 12px;
                padding: 16px;
            }}
        """)
        
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(8)
        
        # Title
        title_label = QLabel(title)
        title_label.setAlignment(Qt.AlignLeft)
        title_label.setStyleSheet("font-size: 14px; font-weight: 600; color: #94A3B8;")
        card_layout.addWidget(title_label)
        
        # Value
        value_label = QLabel(value)
        value_label.setAlignment(Qt.AlignLeft)
        value_label.setStyleSheet("font-size: 26px; font-weight: bold; color: #F8FAFC;")
        card_layout.addWidget(value_label)
        
        # Store reference to value label for updates
        card.value_label = value_label

        return card

    def create_gainers_losers_card(self, title, accent_color):
        """Create a card for displaying top gainers or losers"""
        card = QWidget()
        card.setStyleSheet(f"""
            QWidget {{
                background-color: #151A24;
                border: 1px solid #1E293B;
                border-top: 3px solid {accent_color};
                border-radius: 12px;
                padding: 16px;
            }}
        """)

        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(10)

        # Title
        title_label = QLabel(title)
        title_label.setAlignment(Qt.AlignLeft)
        title_label.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {accent_color};")
        card_layout.addWidget(title_label)

        # Content label for the list
        content_label = QLabel("Waiting for market data...")
        content_label.setAlignment(Qt.AlignLeft)
        content_label.setStyleSheet("""
            font-size: 13px;
            font-weight: 500;
            color: #CBD5E1;
            padding: 8px;
            line-height: 1.6;
        """)
        content_label.setWordWrap(True)
        card_layout.addWidget(content_label)

        # Store reference to content label for updates
        card.content_label = content_label

        return card

    def update_ticker(self):
        if not self.conn_mgr.get_connection_status()['broker_connected']:
            return

        ltp_data = self.conn_mgr.get_ltp_batch(self.ticker_symbols)

        prices = {}
        for item in self.ticker_symbols:
            symbol = item[0]
            price = ltp_data.get(symbol)
            if price is not None:
                prices[symbol] = price
            else:
                prices[symbol] = "N/A"

        self.ticker.update_prices(prices)
        self.update_gainers_losers()

    def update_gainers_losers(self):
        """Calculate and update top gainers and losers"""
        if not self.conn_mgr.get_connection_status()['broker_connected']:
            self.gainers_card.content_label.setText("Broker disconnected")
            self.losers_card.content_label.setText("Broker disconnected")
            return

        current_prices = self.ticker.current_prices
        previous_prices = self.ticker.previous_prices

        if not current_prices or not previous_prices:
            self.gainers_card.content_label.setText("Waiting for streaming data...")
            self.losers_card.content_label.setText("Waiting for streaming data...")
            return

        changes = []
        for symbol in current_prices:
            if symbol in previous_prices:
                current = current_prices[symbol]
                previous = previous_prices[symbol]

                if (current is None or previous is None or
                    current == "N/A" or previous == "N/A" or
                    not isinstance(current, (int, float)) or
                    not isinstance(previous, (int, float)) or
                    previous == 0):
                    continue

                pct_change = ((current - previous) / previous) * 100
                changes.append({
                    'symbol': symbol,
                    'current': current,
                    'previous': previous,
                    'change': pct_change
                })

        if not changes:
            self.gainers_card.content_label.setText("No price movements recorded")
            self.losers_card.content_label.setText("No price movements recorded")
            return

        changes.sort(key=lambda x: x['change'], reverse=True)

        top_gainers = changes[:5]
        top_losers = changes[-5:]
        top_losers.reverse()

        gainers_text = ""
        for i, item in enumerate(top_gainers, 1):
            gainers_text += f"{i}. {item['symbol']}: ₹{item['current']:.2f} "
            gainers_text += f"(+{item['change']:.2f}%)\n"

        losers_text = ""
        for i, item in enumerate(top_losers, 1):
            losers_text += f"{i}. {item['symbol']}: ₹{item['current']:.2f} "
            losers_text += f"({item['change']:.2f}%)\n"

        self.gainers_card.content_label.setText(gainers_text.strip() or "No gainers")
        self.losers_card.content_label.setText(losers_text.strip() or "No losers")

    def toggle_connection(self):
        """Toggle broker connection with intelligent Paper Sandbox option"""
        status = self.conn_mgr.get_connection_status()
        
        if status['broker_connected']:
            reply = QMessageBox.question(
                self,
                'Confirm Disconnect',
                'Are you sure you want to disconnect from the broker session?\n\n'
                'This will halt active market data streaming.',
                QMessageBox.Yes | QMessageBox.No
            )
            
            if reply == QMessageBox.Yes:
                self.conn_mgr.close()
                self.refresh_dashboard()
                self.parent.statusBar().showMessage("🔴 Disconnected from broker", 5000)
        else:
            self.parent.statusBar().showMessage("🔄 Connecting to broker...", 3000)
            
            # Try live connection first
            success = self.conn_mgr.connect_broker()
            
            if success:
                self.refresh_dashboard()
                self.parent.statusBar().showMessage("✅ Connected to Angel One broker successfully!", 5000)
                self.conn_mgr.subscribe_initial_symbols(self.ticker_symbols)
            else:
                # Open modern dark setup dialog with Paper Sandbox option
                err = getattr(self.conn_mgr, 'last_connection_error', None)
                dialog = ConnectionOptionsDialog(self, err)

                if dialog.exec_() == QDialog.Accepted:
                    if dialog.selected_action == "paper":
                        self.conn_mgr.connect_paper_sandbox()
                        self.refresh_dashboard()
                        self.parent.statusBar().showMessage("🟢 Connected to Paper Trading Sandbox Mode!", 5000)
                        self.conn_mgr.subscribe_initial_symbols(self.ticker_symbols)
                    elif dialog.selected_action == "settings":
                        if hasattr(self.parent, 'tabs'):
                            for i in range(self.parent.tabs.count()):
                                if "Settings" in self.parent.tabs.tabText(i):
                                    self.parent.tabs.setCurrentIndex(i)
                                    break
                else:
                    self.parent.statusBar().showMessage("❌ Connection cancelled", 3000)

    def start_trading(self):
        """Start trading bot"""
        if not self.conn_mgr.get_connection_status()['broker_connected']:
            QMessageBox.warning(
                self,
                'Not Connected',
                'Please connect to the broker or launch Paper Sandbox before starting the trading engine.'
            )
            return
            
        self.conn_mgr.config['auto_trading'] = True
        self.refresh_dashboard()
        self.parent.statusBar().showMessage("▶ Trading engine started", 5000)

    def pause_trading(self):
        """Pause trading bot"""
        self.conn_mgr.config['auto_trading'] = False
        self.refresh_dashboard()
        self.parent.statusBar().showMessage("⏸ Trading engine paused", 5000)

    def refresh_dashboard(self):
        """Refresh dashboard status and cards"""
        status = self.conn_mgr.get_connection_status()
        
        if status['broker_connected']:
            is_paper = status.get('is_paper_sandbox', False)
            if is_paper:
                self.connection_banner.setText("🟢 Broker: Connected (Paper Trading Sandbox)")
                self.connection_banner.setStyleSheet("""
                    background: #1E1B4B;
                    border: 1px solid #6366F1;
                    color: #818CF8;
                    font-size: 16px;
                    font-weight: bold;
                    padding: 14px;
                    border-radius: 10px;
                """)
            else:
                self.connection_banner.setText("🟢 Broker: Connected (Angel One Live)")
                self.connection_banner.setStyleSheet("""
                    background: #064E3B;
                    border: 1px solid #10B981;
                    color: #34D399;
                    font-size: 16px;
                    font-weight: bold;
                    padding: 14px;
                    border-radius: 10px;
                """)
            
            self.connect_btn.setText("🔌 Disconnect")
            self.ticker.show()
        else:
            self.connection_banner.setText("🔴 Broker: Disconnected")
            self.connection_banner.setStyleSheet("""
                background: #451A03;
                border: 1px solid #F59E0B;
                color: #FBBF24;
                font-size: 16px;
                font-weight: bold;
                padding: 14px;
                border-radius: 10px;
            """)
            
            self.connect_btn.setText("🔌 Connect")
            self.ticker.hide()
        
        capital = self.conn_mgr.config.get('initial_capital', 100000)
        
        if self.trade_logger and hasattr(self.trade_logger, 'trades'):
            trades = self.trade_logger.trades
            trades_count = len(trades)
            
            if trades_count > 0:
                total_profit = sum(t.get('profit', 0) for t in trades if t.get('profit'))
                winning_trades = sum(1 for t in trades if t.get('profit', 0) > 0)
                win_rate = (winning_trades / trades_count * 100) if trades_count > 0 else 0
                
                self.capital_card.value_label.setText(f"₹{capital + total_profit:,.2f}")
                self.profit_card.value_label.setText(f"₹{total_profit:,.2f}")
                self.trades_card.value_label.setText(str(trades_count))
                self.winrate_card.value_label.setText(f"{win_rate:.1f}%")
            else:
                self.capital_card.value_label.setText(f"₹{capital:,.2f}")
                self.profit_card.value_label.setText("₹0.00")
                self.trades_card.value_label.setText("0")
                self.winrate_card.value_label.setText("0.0%")
        else:
            self.capital_card.value_label.setText(f"₹{capital:,.2f}")
            self.profit_card.value_label.setText("₹0.00")
            self.trades_card.value_label.setText("0")
            self.winrate_card.value_label.setText("0.0%")
        
        stock_count = len(self.conn_mgr.get_stock_list())
        engine_mode = "Paper Trading Sandbox" if status.get('is_paper_sandbox', False) else ("Live Broker" if status['broker_connected'] else "Offline")
        auto_status = "ACTIVE" if self.conn_mgr.config.get('auto_trading', False) else "PAUSED"
        
        status_text = f"""⚡ Subsystem Mode: {engine_mode}
💰 Available Capital: ₹{capital:,.2f}
🤖 Auto Trading Engine: {auto_status}
📊 Actively Monitoring {stock_count} Instruments"""
        
        self.status_list.setText(status_text)