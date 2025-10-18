#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ==============================================================================
# FILE: positions_tab.py
# VERSION: 2.0.0 - Live positions monitoring
# ==============================================================================

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor

class PositionsTab(QWidget):
    """Live Positions - Real-time position tracking"""
    
    def __init__(self, parent, conn_mgr):
        super().__init__(parent)
        self.parent = parent
        self.conn_mgr = conn_mgr
        
        self.init_ui()
        
        # Auto-refresh every 5 seconds
        self.timer = QTimer()
        self.timer.timeout.connect(self.refresh_positions)
        self.timer.start(5000)
        
        self.refresh_positions()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        
        # Header
        header = QHBoxLayout()
        
        title = QLabel("🟢 Live Positions")
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: #333;")
        header.addWidget(title)
        
        header.addStretch()
        
        # Refresh button
        refresh_btn = QPushButton("🔄 Refresh")
        refresh_btn.setStyleSheet("""
            background: #2196F3; 
            color: white; 
            font-size: 16px; 
            font-weight: bold; 
            padding: 10px 25px; 
            border-radius: 8px;
        """)
        refresh_btn.clicked.connect(self.refresh_positions)
        refresh_btn.setCursor(Qt.PointingHandCursor)
        header.addWidget(refresh_btn)
        
        layout.addLayout(header)
        
        # Positions table
        self.table = QTableWidget()
        self.table.setStyleSheet("""
            QTableWidget { 
                background: white; 
                border: 2px solid #ddd; 
                border-radius: 5px; 
                font-size: 15px;
            }
            QHeaderView::section { 
                background: #4CAF50; 
                color: white; 
                font-weight: bold; 
                font-size: 16px; 
                padding: 10px; 
            }
            QTableWidget::item { 
                padding: 10px;
            }
        """)
        
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "Symbol", "Qty", "Avg Price", "LTP", "P&L", "Day Change", "Type", "Action"
        ])
        
        header_view = self.table.horizontalHeader()
        header_view.setSectionResizeMode(QHeaderView.Stretch)
        
        self.table.setVerticalScrollMode(QTableWidget.ScrollPerPixel)
        self.table.setMinimumHeight(400)
        
        layout.addWidget(self.table)
        
        # Info
        self.info_label = QLabel("Auto-refreshing every 5 seconds")
        self.info_label.setStyleSheet("""
            font-size: 14px; 
            color: #666; 
            padding: 10px;
            background: #f9f9f9;
            border-radius: 5px;
        """)
        self.info_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.info_label)
    
    def refresh_positions(self):
        """Refresh positions from broker"""
        self.parent.statusBar().showMessage("🔄 Fetching positions...", 2000)
        
        positions = self.conn_mgr.get_positions()
        
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(positions) if positions else 1)
        
        if not positions:
            no_data = QTableWidgetItem("No open positions")
            no_data.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(0, 0, no_data)
            self.table.setSpan(0, 0, 1, 8)
            return
        
        for row, pos in enumerate(positions):
            symbol = pos.get('tradingsymbol', 'N/A')
            qty = pos.get('netqty', 0)
            avg_price = pos.get('averageprice', 0)
            ltp = pos.get('ltp', avg_price)
            pnl = pos.get('pnl', 0)
            day_change = pos.get('daychange', 0)
            product_type = pos.get('producttype', 'N/A')
            
            items = [
                QTableWidgetItem(symbol),
                QTableWidgetItem(str(qty)),
                QTableWidgetItem(f"₹{avg_price:.2f}"),
                QTableWidgetItem(f"₹{ltp:.2f}"),
                QTableWidgetItem(f"₹{pnl:.2f}"),
                QTableWidgetItem(f"{day_change:.2f}%"),
                QTableWidgetItem(product_type)
            ]
            
            # Color P&L
            if pnl > 0:
                items[4].setForeground(QColor(0, 150, 0))
            elif pnl < 0:
                items[4].setForeground(QColor(200, 0, 0))
            
            # Center align
            for col, item in enumerate(items):
                item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row, col, item)
            
            # Exit button
            exit_btn = QPushButton("❌ Exit")
            exit_btn.setStyleSheet("""
                background: #f44336; 
                color: white; 
                font-size: 12px; 
                padding: 5px 10px; 
                border-radius: 4px;
            """)
            exit_btn.setCursor(Qt.PointingHandCursor)
            self.table.setCellWidget(row, 7, exit_btn)
        
        self.table.setSortingEnabled(True)
        self.parent.statusBar().showMessage(f"✅ Loaded {len(positions)} positions", 2000)