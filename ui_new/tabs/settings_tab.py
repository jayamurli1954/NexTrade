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
        
        header = QLabel("⚙️ Settings")
        header.setStyleSheet("font-size: 24px; font-weight: bold; padding: 10px;")
        layout.addWidget(header)
        
        # Get config from connection manager
        config = self.conn_mgr.config
        
        # Trading settings
        trading = QGroupBox("📊 Trading Settings")
        trading.setStyleSheet("font-size: 18px; font-weight: bold; border: 2px solid #ccc; border-radius: 10px; padding: 15px;")
        t_layout = QGridLayout()
        
        t_layout.addWidget(QLabel("Initial Capital:"), 0, 0)
        self.capital_input = QLineEdit(str(config.get('initial_capital', 100000)))
        self.capital_input.setStyleSheet("font-size: 16px; padding: 8px;")
        t_layout.addWidget(self.capital_input, 0, 1)
        
        t_layout.addWidget(QLabel("Risk Per Trade (%):"), 1, 0)
        self.risk_input = QSpinBox()
        self.risk_input.setRange(1, 10)
        self.risk_input.setValue(int(config.get('risk_per_trade', 2)))
        self.risk_input.setStyleSheet("font-size: 16px; padding: 8px;")
        t_layout.addWidget(self.risk_input, 1, 1)
        
        self.auto_checkbox = QCheckBox("Enable Auto-Trading")
        self.auto_checkbox.setChecked(config.get('auto_trading', False))
        self.auto_checkbox.setStyleSheet("font-size: 16px;")
        t_layout.addWidget(self.auto_checkbox, 2, 0, 1, 2)
        
        trading.setLayout(t_layout)
        layout.addWidget(trading)
        
        # API settings
        api = QGroupBox("🔌 API Configuration")
        api.setStyleSheet("font-size: 18px; font-weight: bold; border: 2px solid #ccc; border-radius: 10px; padding: 15px;")
        a_layout = QGridLayout()
        
        a_layout.addWidget(QLabel("API Key:"), 0, 0)
        self.api_key_input = QLineEdit(config.get('api_key', ''))
        self.api_key_input.setEchoMode(QLineEdit.Password)
        self.api_key_input.setStyleSheet("font-size: 16px; padding: 8px;")
        a_layout.addWidget(self.api_key_input, 0, 1)
        
        a_layout.addWidget(QLabel("Client ID:"), 1, 0)
        self.client_id_input = QLineEdit(config.get('client_id', ''))
        self.client_id_input.setStyleSheet("font-size: 16px; padding: 8px;")
        a_layout.addWidget(self.client_id_input, 1, 1)
        
        api.setLayout(a_layout)
        layout.addWidget(api)
        
        # Save button
        save = QPushButton("💾 Save Settings")
        save.setStyleSheet("background: #4CAF50; color: white; font-size: 19px; font-weight: bold; padding: 12px; border-radius: 8px;")
        save.setMinimumHeight(50)
        save.clicked.connect(self.save_settings)
        layout.addWidget(save)
        
        layout.addStretch()
    
    def save_settings(self):
        """Save settings via connection manager"""
        new_config = {
            'initial_capital': float(self.capital_input.text()),
            'risk_per_trade': self.risk_input.value(),
            'auto_trading': self.auto_checkbox.isChecked(),
            'api_key': self.api_key_input.text(),
            'client_id': self.client_id_input.text()
        }
        
        if self.conn_mgr.update_config(new_config):
            self.parent.statusBar().showMessage("✅ Settings saved!", 3000)
        else:
            self.parent.statusBar().showMessage("⚠️ Error saving settings", 3000)
