from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QTextEdit

class PreMarketTab(QWidget):
    """Pre-Market - connects to Angel One pre-market API"""
    
    def __init__(self, parent, conn_mgr):
        super().__init__(parent)
        self.parent = parent
        self.conn_mgr = conn_mgr
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        header = QLabel("🌅 Pre-Market Analyzer")
        header.setStyleSheet("font-size: 24px; font-weight: bold; padding: 10px;")
        layout.addWidget(header)
        
        text = QTextEdit()
        text.setReadOnly(True)
        text.setStyleSheet("border: 1px solid #ddd; border-radius: 5px; padding: 12px; font-size: 16px;")
        text.append("🌅 Pre-Market Analysis (9:00 AM - 9:15 AM)")
        text.append("")
        text.append("📈 Gap Up Stocks: Analyzing...")
        text.append("📉 Gap Down Stocks: Analyzing...")
        text.append("⏰ Pre-market data available from 9:00 AM")
        text.append("")
        
        status = self.conn_mgr.get_connection_status()
        if status['broker_connected']:
            text.append("✅ Connected to Angel One for pre-market data")
        else:
            text.append("⚠️ Connect to broker for pre-market analysis")
        
        layout.addWidget(text)
        
        scan = QPushButton("🔍 Scan Pre-Market")
        scan.setStyleSheet("font-size: 19px; font-weight: bold; padding: 12px; border-radius: 8px;")
        scan.setMinimumHeight(50)
        layout.addWidget(scan)
