from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QLineEdit, QSpinBox, QCheckBox, QPushButton, QGridLayout, QGroupBox
from PyQt5.QtCore import Qt

class SettingsTab(QWidget):
    """Settings - loads from config via Connection Manager"""
    
    def __init__(self, parent, conn_mgr):
        super().__init__(parent)
        self.parent = parent
        self.conn_mgr = conn_mgr
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        
        header = QLabel("⚙️ Application & API Settings")
        header.setStyleSheet("font-size: 22px; font-weight: bold; color: #38BDF8; padding: 6px;")
        layout.addWidget(header)
        
        # Get config from connection manager
        config = self.conn_mgr.config
        
        # Trading settings
        trading = QGroupBox("📊 Trading Engine Settings")
        trading.setStyleSheet("font-size: 16px; font-weight: bold; color: #38BDF8; border: 1px solid #334155; border-radius: 10px; padding: 15px; background-color: #151A24;")
        t_layout = QGridLayout()
        t_layout.setSpacing(12)
        
        t_layout.addWidget(QLabel("Initial Capital (₹):"), 0, 0)
        self.capital_input = QLineEdit(str(config.get('initial_capital', 100000)))
        t_layout.addWidget(self.capital_input, 0, 1)
        
        t_layout.addWidget(QLabel("Risk Per Trade (%):"), 1, 0)
        self.risk_input = QSpinBox()
        self.risk_input.setRange(1, 10)
        self.risk_input.setValue(int(config.get('risk_per_trade', 2)))
        t_layout.addWidget(self.risk_input, 1, 1)
        
        self.auto_checkbox = QCheckBox("Enable Auto-Trading Engine")
        self.auto_checkbox.setChecked(config.get('auto_trading', False))
        t_layout.addWidget(self.auto_checkbox, 2, 0, 1, 2)
        
        trading.setLayout(t_layout)
        layout.addWidget(trading)
        
        # API settings
        api = QGroupBox("🔌 Angel One Broker Credentials & TOTP Setup")
        api.setStyleSheet("font-size: 16px; font-weight: bold; color: #38BDF8; border: 1px solid #334155; border-radius: 10px; padding: 15px; background-color: #151A24;")
        a_layout = QGridLayout()
        a_layout.setSpacing(12)
        
        # API Key
        a_layout.addWidget(QLabel("API Key:"), 0, 0)
        self.api_key_input = QLineEdit(config.get('api_key', ''))
        self.api_key_input.setEchoMode(QLineEdit.Password)
        self.api_key_input.setPlaceholderText("Enter your Angel One SmartAPI key")
        a_layout.addWidget(self.api_key_input, 0, 1)
        
        # Client ID
        a_layout.addWidget(QLabel("Client ID:"), 1, 0)
        self.client_id_input = QLineEdit(config.get('client_id', ''))
        self.client_id_input.setPlaceholderText("e.g. M586478")
        a_layout.addWidget(self.client_id_input, 1, 1)
        
        # Password / PIN
        a_layout.addWidget(QLabel("Password / PIN:"), 2, 0)
        self.password_input = QLineEdit(config.get('password', ''))
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setPlaceholderText("Enter your Angel One account PIN/Password")
        a_layout.addWidget(self.password_input, 2, 1)
        
        # TOTP Secret Key
        a_layout.addWidget(QLabel("TOTP Secret Key:"), 3, 0)
        self.totp_input = QLineEdit(config.get('totp_token', ''))
        self.totp_input.setEchoMode(QLineEdit.Password)
        self.totp_input.setPlaceholderText("Enter 16-character base32 TOTP secret key (e.g. IHB5UTV7XWWI4DPZ5XOGUNZXUE)")
        a_layout.addWidget(self.totp_input, 3, 1)
        
        # News API Key (Optional)
        a_layout.addWidget(QLabel("News API Key (Optional):"), 4, 0)
        self.news_api_key_input = QLineEdit(config.get('NEWSAPI_KEY', ''))
        self.news_api_key_input.setEchoMode(QLineEdit.Password)
        self.news_api_key_input.setPlaceholderText("Optional: For sentiment analysis")
        a_layout.addWidget(self.news_api_key_input, 4, 1)
        
        api.setLayout(a_layout)
        layout.addWidget(api)
        
        # Save button
        save = QPushButton("💾 Save Configuration")
        save.setMinimumHeight(48)
        save.clicked.connect(self.save_settings)
        layout.addWidget(save)
        
        layout.addStretch()
    
    def save_settings(self):
        """Save settings via connection manager"""
        try:
            initial_cap = float(self.capital_input.text())
        except ValueError:
            initial_cap = 100000.0

        new_config = {
            'initial_capital': initial_cap,
            'risk_per_trade': self.risk_input.value(),
            'auto_trading': self.auto_checkbox.isChecked(),
            'api_key': self.api_key_input.text().strip(),
            'client_id': self.client_id_input.text().strip(),
            'password': self.password_input.text().strip(),
            'totp_token': self.totp_input.text().strip(),
            'NEWSAPI_KEY': self.news_api_key_input.text().strip()
        }
        
        if self.conn_mgr.update_config(new_config):
            self.parent.statusBar().showMessage("✅ Credentials & TOTP key saved to config.json!", 5000)
        else:
            self.parent.statusBar().showMessage("⚠️ Error saving configuration", 5000)
