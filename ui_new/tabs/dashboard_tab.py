#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ==============================================================================
# FILE: dashboard_tab.py
# VERSION: 2.2.1 - Complete with toggle_connection method
# LOCATION: c:\Users\Dell\tradingbot_new\ui_new\tabs\dashboard_tab.py
# ==============================================================================

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QMessageBox
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont

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
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        
        # Top bar with connection status and connect button
        top_bar = QHBoxLayout()
        top_bar.setSpacing(15)
        
        # Connection status banner
        self.connection_banner = QLabel()
        self.connection_banner.setAlignment(Qt.AlignCenter)
        self.connection_banner.setMinimumHeight(60)
        self.connection_banner.setStyleSheet("""
            font-size: 18px;
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
                background: #4CAF50;
                color: white;
                font-size: 18px;
                font-weight: bold;
                padding: 15px 30px;
                border-radius: 10px;
                border: none;
            }
            QPushButton:hover {
                background: #45a049;
            }
            QPushButton:pressed {
                background: #3d8b40;
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
            "#4CAF50"
        )
        stats_container.addWidget(self.capital_card)
        
        # Card 2: Profit
        self.profit_card = self.create_stat_card(
            "📈 Profit",
            "₹0.00",
            "#2196F3"
        )
        stats_container.addWidget(self.profit_card)
        
        # Card 3: Trades
        self.trades_card = self.create_stat_card(
            "💹 Trades",
            "0",
            "#FF9800"
        )
        stats_container.addWidget(self.trades_card)
        
        # Card 4: Win Rate
        self.winrate_card = self.create_stat_card(
            "🎯 Win Rate",
            "0.0%",
            "#9C27B0"
        )
        stats_container.addWidget(self.winrate_card)
        
        layout.addLayout(stats_container)
        
        # System status section
        status_section = QVBoxLayout()
        status_section.setSpacing(10)
        
        status_title = QLabel("📊 System Status")
        status_title.setStyleSheet("font-size: 20px; font-weight: bold; color: #333;")
        status_section.addWidget(status_title)
        
        self.status_list = QLabel()
        self.status_list.setStyleSheet("""
            font-size: 16px;
            padding: 15px;
            background: white;
            border: 2px solid #ddd;
            border-radius: 8px;
            line-height: 1.8;
        """)
        status_section.addWidget(self.status_list)
        
        layout.addLayout(status_section)
        
        # Action buttons
        button_layout = QHBoxLayout()
        button_layout.setSpacing(15)
        
        # Start button
        self.start_btn = QPushButton("▶ Start")
        self.start_btn.setStyleSheet("""
            QPushButton {
                background: #4CAF50;
                color: white;
                font-size: 18px;
                font-weight: bold;
                padding: 15px 40px;
                border-radius: 10px;
                border: none;
            }
            QPushButton:hover {
                background: #45a049;
            }
            QPushButton:pressed {
                background: #3d8b40;
            }
        """)
        self.start_btn.setCursor(Qt.PointingHandCursor)
        self.start_btn.clicked.connect(self.start_trading)
        button_layout.addWidget(self.start_btn)
        
        # Pause button
        self.pause_btn = QPushButton("⏸ Pause")
        self.pause_btn.setStyleSheet("""
            QPushButton {
                background: #FF9800;
                color: white;
                font-size: 18px;
                font-weight: bold;
                padding: 15px 40px;
                border-radius: 10px;
                border: none;
            }
            QPushButton:hover {
                background: #f57c00;
            }
            QPushButton:pressed {
                background: #e65100;
            }
        """)
        self.pause_btn.setCursor(Qt.PointingHandCursor)
        self.pause_btn.clicked.connect(self.pause_trading)
        button_layout.addWidget(self.pause_btn)
        
        # Refresh button
        refresh_btn = QPushButton("🔄 Refresh")
        refresh_btn.setStyleSheet("""
            QPushButton {
                background: #2196F3;
                color: white;
                font-size: 18px;
                font-weight: bold;
                padding: 15px 40px;
                border-radius: 10px;
                border: none;
            }
            QPushButton:hover {
                background: #1976D2;
            }
            QPushButton:pressed {
                background: #1565C0;
            }
        """)
        refresh_btn.setCursor(Qt.PointingHandCursor)
        refresh_btn.clicked.connect(self.refresh_dashboard)
        button_layout.addWidget(refresh_btn)
        
        layout.addLayout(button_layout)
        
        layout.addStretch()
        
        # Initial refresh
        self.refresh_dashboard()
    
    def create_stat_card(self, title, value, color):
        """Create a statistics card"""
        card = QWidget()
        card.setStyleSheet(f"""
            QWidget {{
                background: {color};
                border-radius: 15px;
                padding: 20px;
            }}
        """)
        
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(10)
        
        # Title
        title_label = QLabel(title)
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("color: white; font-size: 18px; font-weight: bold;")
        card_layout.addWidget(title_label)
        
        # Value
        value_label = QLabel(value)
        value_label.setAlignment(Qt.AlignCenter)
        value_label.setStyleSheet("color: white; font-size: 32px; font-weight: bold;")
        card_layout.addWidget(value_label)
        
        # Store reference to value label for updates
        card.value_label = value_label
        
        return card
    
    def toggle_connection(self):
        """Toggle broker connection"""
        status = self.conn_mgr.get_connection_status()
        
        if status['broker_connected']:
            # Disconnect
            reply = QMessageBox.question(
                self,
                'Confirm Disconnect',
                'Are you sure you want to disconnect from the broker?\n\n'
                'This will stop all WebSocket streaming.',
                QMessageBox.Yes | QMessageBox.No
            )
            
            if reply == QMessageBox.Yes:
                self.conn_mgr.close()
                self.refresh_dashboard()
                self.parent.statusBar().showMessage("🔴 Disconnected from broker", 5000)
        else:
            # Connect
            self.parent.statusBar().showMessage("🔄 Connecting to broker...", 3000)
            
            success = self.conn_mgr.connect_broker()
            
            if success:
                self.refresh_dashboard()
                self.parent.statusBar().showMessage("✅ Connected to broker successfully!", 5000)
            else:
                QMessageBox.critical(
                    self,
                    'Connection Failed',
                    'Failed to connect to Angel One broker.\n\n'
                    'Please check:\n'
                    '- API credentials in config.json\n'
                    '- Internet connection\n'
                    '- TOTP token is valid'
                )
                self.parent.statusBar().showMessage("❌ Connection failed", 5000)
    
    def refresh_dashboard(self):
        """Refresh dashboard data"""
        # Get connection status
        status = self.conn_mgr.get_connection_status()
        
        # Update connection banner and button
        if status['broker_connected']:
            self.connection_banner.setText("🟢 Broker: Connected")
            self.connection_banner.setStyleSheet("""
                background: #4CAF50;
                color: white;
                font-size: 18px;
                font-weight: bold;
                padding: 15px;
                border-radius: 10px;
            """)
            
            # Update button to Disconnect
            self.connect_btn.setText("🔌 Disconnect")
            self.connect_btn.setStyleSheet("""
                QPushButton {
                    background: #f44336;
                    color: white;
                    font-size: 18px;
                    font-weight: bold;
                    padding: 15px 30px;
                    border-radius: 10px;
                    border: none;
                }
                QPushButton:hover {
                    background: #da190b;
                }
                QPushButton:pressed {
                    background: #c1170a;
                }
            """)
        else:
            self.connection_banner.setText("🔴 Broker: Disconnected")
            self.connection_banner.setStyleSheet("""
                background: #f44336;
                color: white;
                font-size: 18px;
                font-weight: bold;
                padding: 15px;
                border-radius: 10px;
            """)
            
            # Update button to Connect
            self.connect_btn.setText("🔌 Connect")
            self.connect_btn.setStyleSheet("""
                QPushButton {
                    background: #4CAF50;
                    color: white;
                    font-size: 18px;
                    font-weight: bold;
                    padding: 15px 30px;
                    border-radius: 10px;
                    border: none;
                }
                QPushButton:hover {
                    background: #45a049;
                }
                QPushButton:pressed {
                    background: #3d8b40;
                }
            """)
        
        # Update capital
        capital = self.conn_mgr.config.get('initial_capital', 100000)
        
        # Calculate stats from trade_logger if available
        if self.trade_logger and hasattr(self.trade_logger, 'trades'):
            trades = self.trade_logger.trades
            trades_count = len(trades)
            
            if trades_count > 0:
                # Calculate profit
                total_profit = sum(t.get('profit', 0) for t in trades if t.get('profit'))
                
                # Calculate win rate
                winning_trades = sum(1 for t in trades if t.get('profit', 0) > 0)
                win_rate = (winning_trades / trades_count * 100) if trades_count > 0 else 0
                
                # Update cards
                self.capital_card.value_label.setText(f"₹{capital + total_profit:,.2f}")
                self.profit_card.value_label.setText(f"₹{total_profit:,.2f}")
                self.trades_card.value_label.setText(str(trades_count))
                self.winrate_card.value_label.setText(f"{win_rate:.1f}%")
            else:
                # No trades yet
                self.capital_card.value_label.setText(f"₹{capital:,.2f}")
                self.profit_card.value_label.setText("₹0.00")
                self.trades_card.value_label.setText("0")
                self.winrate_card.value_label.setText("0.0%")
        else:
            # Default values
            self.capital_card.value_label.setText(f"₹{capital:,.2f}")
            self.profit_card.value_label.setText("₹0.00")
            self.trades_card.value_label.setText("0")
            self.winrate_card.value_label.setText("0.0%")
        
        # Update system status
        stock_count = len(self.conn_mgr.get_stock_list())
        
        status_text = f"""✅ System started
💰 Capital: ₹{capital:,.2f}
📊 Monitoring {stock_count} stocks"""
        
        if status.get('websocket_connected', False):
            status_text += "\n🔌 WebSocket: Connected"
        else:
            status_text += "\n⚠️  WebSocket: Disconnected"
        
        # Show refreshed capital
        refreshed_capital = capital
        if self.trade_logger and hasattr(self.trade_logger, 'trades') and len(self.trade_logger.trades) > 0:
            total_profit = sum(t.get('profit', 0) for t in self.trade_logger.trades if t.get('profit'))
            refreshed_capital = capital + total_profit
        
        status_text += f"\n💵 Refreshed! Capital: ₹{refreshed_capital:,.2f}"
        
        self.status_list.setText(status_text)
        
        # Show status message
        self.parent.statusBar().showMessage("✅ Dashboard refreshed", 2000)
    
    def start_trading(self):
        """Start trading"""
        status = self.conn_mgr.get_connection_status()
        
        if not status['broker_connected']:
            QMessageBox.warning(
                self,
                'Not Connected',
                'Please connect to broker first!'
            )
            return
        
        self.parent.statusBar().showMessage("▶ Trading started", 3000)
    
    def pause_trading(self):
        """Pause trading"""
        self.parent.statusBar().showMessage("⏸ Trading paused", 3000)