from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QFrame, QMessageBox
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor

class HoldingsTab(QWidget):
    """Holdings tab - fetches REAL data from Angel One broker via Connection Manager"""
    
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
        layout.setSpacing(16)
        
        # Mode Notice Banner
        self.mode_notice = QLabel()
        self.mode_notice.setAlignment(Qt.AlignCenter)
        self.mode_notice.setWordWrap(True)
        self.mode_notice.setStyleSheet("""
            font-size: 14px;
            font-weight: 600;
            padding: 12px;
            border-radius: 8px;
        """)
        layout.addWidget(self.mode_notice)
        
        # Header
        header = QHBoxLayout()
        h = QLabel("💼 Broker Holdings & Portfolio")
        h.setStyleSheet("font-size: 22px; font-weight: bold; color: #38BDF8;")
        header.addWidget(h)
        header.addStretch()
        
        # Connect Live Broker button
        self.connect_live_btn = QPushButton("🔑 Connect Live Angel One")
        self.connect_live_btn.setStyleSheet("""
            QPushButton {
                font-size: 14px;
                font-weight: bold;
                padding: 10px 20px;
                background-color: #1E2532;
                border: 1px solid #38BDF8;
                color: #38BDF8;
                border-radius: 8px;
            }
            QPushButton:hover {
                background-color: #2A3447;
                color: #FFFFFF;
            }
        """)
        self.connect_live_btn.clicked.connect(self.connect_live_broker)
        header.addWidget(self.connect_live_btn)
        
        refresh_btn = QPushButton("🔄 Refresh Holdings")
        refresh_btn.setStyleSheet("""
            QPushButton {
                font-size: 14px;
                font-weight: bold;
                padding: 10px 20px;
                border-radius: 8px;
            }
        """)
        refresh_btn.clicked.connect(self.refresh)
        header.addWidget(refresh_btn)
        layout.addLayout(header)
        
        # Funds cards
        funds = QHBoxLayout()
        funds.setSpacing(16)
        self.cash_card = self.create_fund_card("💰 Available Cash", "₹0.00", "#4F46E5")
        self.margin_card = self.create_fund_card("📊 Utilised Margin", "₹0.00", "#3B82F6")
        self.value_card = self.create_fund_card("💼 Portfolio Value", "₹0.00", "#10B981")
        funds.addWidget(self.cash_card)
        funds.addWidget(self.margin_card)
        funds.addWidget(self.value_card)
        layout.addLayout(funds)
        
        # Table
        self.table = QTableWidget()
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #151A24;
                border: 1px solid #1E293B;
                border-radius: 8px;
                font-size: 14px;
                color: #F8FAFC;
            }
            QHeaderView::section {
                font-weight: bold;
                font-size: 14px;
                padding: 12px;
                background-color: #1E2532;
                color: #38BDF8;
                border: none;
                border-bottom: 2px solid #38BDF8;
            }
            QTableWidget::item {
                padding: 10px;
            }
        """)
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(["Symbol", "Qty", "Avg Price", "LTP", "P&L", "Day %", "Total Value"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.table)

    def create_fund_card(self, title, value, accent_color="#4F46E5"):
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background-color: #1E2532;
                border: 1px solid #2D3748;
                border-left: 5px solid {accent_color};
                border-radius: 10px;
                padding: 16px;
                min-height: 90px;
            }}
        """)
        layout = QVBoxLayout(card)
        layout.setSpacing(6)
        
        t = QLabel(title)
        t.setStyleSheet("font-size: 14px; font-weight: bold; color: #94A3B8;")
        t.setAlignment(Qt.AlignLeft)
        
        v = QLabel(value)
        v.setStyleSheet("font-size: 26px; font-weight: 800; color: #FFFFFF;")
        v.setAlignment(Qt.AlignLeft)
        v.setObjectName(f"value_{title.split()[-1]}")
        
        layout.addWidget(t)
        layout.addWidget(v)
        return card

    def connect_live_broker(self):
        """Prompt to configure live broker or switch tabs"""
        if hasattr(self.parent, 'tabs'):
            for i in range(self.parent.tabs.count()):
                if "Settings" in self.parent.tabs.tabText(i):
                    self.parent.tabs.setCurrentIndex(i)
                    QMessageBox.information(
                        self,
                        'Angel One Live Credentials Required',
                        'Please enter your Angel One API Key, Client Code, Password, and TOTP Secret below.\n\n'
                        'Once configured, click "Connect" on the Dashboard to fetch your live broker holdings.'
                    )
                    break

    def refresh(self):
        """Fetch holdings from broker via connection manager"""
        status = self.conn_mgr.get_connection_status()
        is_paper = status.get('is_paper_sandbox', False)
        is_connected = status.get('broker_connected', False)
        
        if is_paper or not is_connected:
            self.mode_notice.setText(
                "ℹ️ Currently in Paper Trading Sandbox Mode. "
                "To sync live portfolio holdings directly from your Angel One account, "
                "connect with your live Angel One API credentials."
            )
            self.mode_notice.setStyleSheet("""
                background-color: #1E1B4B;
                border: 1px solid #6366F1;
                color: #A5B4FC;
                font-size: 14px;
                font-weight: 600;
                padding: 12px;
                border-radius: 8px;
            """)
            self.connect_live_btn.show()
        else:
            self.mode_notice.setText("🟢 Connected to Angel One Live Broker — Portfolio Synced")
            self.mode_notice.setStyleSheet("""
                background-color: #064E3B;
                border: 1px solid #10B981;
                color: #34D399;
                font-size: 14px;
                font-weight: 600;
                padding: 12px;
                border-radius: 8px;
            """)
            self.connect_live_btn.hide()
            
        holdings = self.conn_mgr.get_holdings()
        self.display_holdings(holdings)
        
        funds = self.conn_mgr.get_funds()
        self.update_fund_card(self.cash_card, f"₹{funds['cash']:,.2f}")
        self.update_fund_card(self.margin_card, f"₹{funds['margin']:,.2f}")
        
        total_value = sum(float(h.get('quantity', 0)) * float(h.get('ltp', 0)) for h in holdings)
        self.update_fund_card(self.value_card, f"₹{total_value:,.2f}")
    
    def update_fund_card(self, card, value):
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
                items[4].setForeground(QColor(52, 211, 153)) # Emerald green
            elif pnl < 0:
                items[4].setForeground(QColor(248, 113, 113)) # Ruby red
            
            for col, item in enumerate(items):
                item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row, col, item)
