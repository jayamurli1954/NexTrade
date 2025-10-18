from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QFrame
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor

class HoldingsTab(QWidget):
    """Holdings tab - fetches REAL data from broker via Connection Manager"""
    
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
        
        # Header
        header = QHBoxLayout()
        h = QLabel("💼 Broker Holdings")
        h.setStyleSheet("font-size: 24px; font-weight: bold;")
        header.addWidget(h)
        header.addStretch()
        
        refresh_btn = QPushButton("🔄 Refresh")
        refresh_btn.setStyleSheet("background: #4CAF50; color: white; font-size: 16px; font-weight: bold; padding: 10px 20px; border-radius: 8px;")
        refresh_btn.clicked.connect(self.refresh)
        header.addWidget(refresh_btn)
        layout.addLayout(header)
        
        # Funds cards
        funds = QHBoxLayout()
        self.cash_card = self.create_fund_card("Cash", "₹0", "#4CAF50")
        self.margin_card = self.create_fund_card("Margin", "₹0", "#2196F3")
        self.value_card = self.create_fund_card("Holdings", "₹0", "#9C27B0")
        funds.addWidget(self.cash_card)
        funds.addWidget(self.margin_card)
        funds.addWidget(self.value_card)
        layout.addLayout(funds)
        
        # Table
        self.table = QTableWidget()
        self.table.setStyleSheet("""
            QTableWidget { background: white; border: 2px solid #ddd; border-radius: 5px; font-size: 15px; }
            QHeaderView::section { background: #4CAF50; color: white; font-weight: bold; font-size: 16px; padding: 10px; border: none; }
            QTableWidget::item { padding: 10px; }
        """)
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(["Symbol", "Qty", "Avg", "LTP", "P&L", "Day%", "Value"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.table)
    
    def create_fund_card(self, title, value, color):
        card = QFrame()
        card.setStyleSheet(f"background: {color}; border-radius: 10px; padding: 15px; min-height: 100px;")
        layout = QVBoxLayout(card)
        
        t = QLabel(title)
        t.setStyleSheet("color: white; font-size: 18px; font-weight: bold;")
        t.setAlignment(Qt.AlignCenter)
        
        v = QLabel(value)
        v.setStyleSheet("color: white; font-size: 28px; font-weight: bold;")
        v.setAlignment(Qt.AlignCenter)
        v.setObjectName(f"value_{title}")
        
        layout.addWidget(t)
        layout.addWidget(v)
        return card
    
    def refresh(self):
        """Fetch REAL holdings from broker via connection manager"""
        # Get holdings from connection manager (handles demo/real data)
        holdings = self.conn_mgr.get_holdings()
        self.display_holdings(holdings)
        
        # Update funds
        funds = self.conn_mgr.get_funds()
        self.update_fund_card(self.cash_card, f"₹{funds['cash']:,.2f}")
        self.update_fund_card(self.margin_card, f"₹{funds['margin']:,.2f}")
        
        # Calculate total holdings value
        total_value = sum(float(h.get('quantity', 0)) * float(h.get('ltp', 0)) for h in holdings)
        self.update_fund_card(self.value_card, f"₹{total_value:,.2f}")
    
    def update_fund_card(self, card, value):
        """Update fund card value"""
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
                items[4].setForeground(QColor(0, 150, 0))
            elif pnl < 0:
                items[4].setForeground(QColor(200, 0, 0))
            
            for col, item in enumerate(items):
                item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row, col, item)
