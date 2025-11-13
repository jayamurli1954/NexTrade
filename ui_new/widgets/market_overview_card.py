#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ==============================================================================
# FILE: market_overview_card.py
# LOCATION: ui_new/widgets/market_overview_card.py
# ==============================================================================

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                              QPushButton, QGridLayout, QFrame)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont, QCursor

class MarketOverviewCard(QWidget):
    """
    A static collapsible card showing major indices and stocks.
    Refreshes every 30 seconds.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.is_collapsed = False
        self.current_prices = {}
        self.previous_prices = {}

        self.init_ui()

    def init_ui(self):
        """Initialize the UI"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Title bar (clickable to collapse/expand)
        self.title_bar = QWidget()
        self.title_bar.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #2c3e50, stop:1 #34495e);
                border-radius: 8px 8px 0 0;
                padding: 12px;
            }
        """)
        self.title_bar.setCursor(QCursor(Qt.PointingHandCursor))
        self.title_bar.mousePressEvent = self.toggle_collapse

        title_layout = QHBoxLayout(self.title_bar)
        title_layout.setContentsMargins(15, 5, 15, 5)

        # Title
        title_label = QLabel("📊 Market Overview")
        title_label.setStyleSheet("""
            font-size: 16px;
            font-weight: bold;
            color: white;
        """)
        title_layout.addWidget(title_label)

        title_layout.addStretch()

        # Last updated label
        self.last_updated_label = QLabel("Last updated: Never")
        self.last_updated_label.setStyleSheet("""
            font-size: 11px;
            color: #bdc3c7;
        """)
        title_layout.addWidget(self.last_updated_label)

        # Collapse/Expand button
        self.collapse_btn = QPushButton("▼")
        self.collapse_btn.setFixedSize(25, 25)
        self.collapse_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                color: white;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.1);
                border-radius: 4px;
            }
        """)
        self.collapse_btn.clicked.connect(self.toggle_collapse)
        title_layout.addWidget(self.collapse_btn)

        main_layout.addWidget(self.title_bar)

        # Content area (collapsible)
        self.content_widget = QWidget()
        self.content_widget.setStyleSheet("""
            QWidget {
                background: #34495e;
                border-radius: 0 0 8px 8px;
                padding: 15px;
            }
        """)

        content_layout = QVBoxLayout(self.content_widget)
        content_layout.setSpacing(15)

        # Major Indices Section
        indices_label = QLabel("📈 Major Indices")
        indices_label.setStyleSheet("""
            font-size: 14px;
            font-weight: bold;
            color: #ecf0f1;
            margin-bottom: 5px;
        """)
        content_layout.addWidget(indices_label)

        # Indices grid
        self.indices_grid = QGridLayout()
        self.indices_grid.setSpacing(10)
        self.indices_grid.setContentsMargins(0, 0, 0, 0)

        self.indices_labels = {}
        indices = ["NIFTY", "BANKNIFTY", "SENSEX", "INDIAVIX"]

        for i, index in enumerate(indices):
            # Symbol label
            symbol_label = QLabel(index)
            symbol_label.setStyleSheet("""
                font-size: 13px;
                font-weight: bold;
                color: #bdc3c7;
            """)

            # Price label
            price_label = QLabel("--")
            price_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            price_label.setStyleSheet("""
                font-size: 14px;
                font-weight: bold;
                color: white;
            """)

            # Change label
            change_label = QLabel("--")
            change_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            change_label.setStyleSheet("""
                font-size: 12px;
                color: #95a5a6;
            """)

            row = i // 2
            col = (i % 2) * 3

            self.indices_grid.addWidget(symbol_label, row, col)
            self.indices_grid.addWidget(price_label, row, col + 1)
            self.indices_grid.addWidget(change_label, row, col + 2)

            self.indices_labels[index] = {
                'symbol': symbol_label,
                'price': price_label,
                'change': change_label
            }

        content_layout.addLayout(self.indices_grid)

        # Separator
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setStyleSheet("background: #7f8c8d; max-height: 1px;")
        content_layout.addWidget(separator)

        # Major Stocks Section
        stocks_label = QLabel("💼 Major Stocks")
        stocks_label.setStyleSheet("""
            font-size: 14px;
            font-weight: bold;
            color: #ecf0f1;
            margin-bottom: 5px;
        """)
        content_layout.addWidget(stocks_label)

        # Stocks grid
        self.stocks_grid = QGridLayout()
        self.stocks_grid.setSpacing(10)
        self.stocks_grid.setContentsMargins(0, 0, 0, 0)

        self.stocks_labels = {}
        stocks = ["RELIANCE", "HDFCBANK", "BHARTIARTL", "TCS",
                  "INFY", "ICICIBANK", "SBIN", "LT",
                  "WIPRO", "TITAN"]

        for i, stock in enumerate(stocks):
            # Symbol label
            symbol_label = QLabel(stock)
            symbol_label.setStyleSheet("""
                font-size: 12px;
                font-weight: bold;
                color: #bdc3c7;
            """)

            # Price label
            price_label = QLabel("--")
            price_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            price_label.setStyleSheet("""
                font-size: 13px;
                font-weight: bold;
                color: white;
            """)

            # Change label
            change_label = QLabel("--")
            change_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            change_label.setStyleSheet("""
                font-size: 11px;
                color: #95a5a6;
            """)

            row = i // 2
            col = (i % 2) * 3

            self.stocks_grid.addWidget(symbol_label, row, col)
            self.stocks_grid.addWidget(price_label, row, col + 1)
            self.stocks_grid.addWidget(change_label, row, col + 2)

            self.stocks_labels[stock] = {
                'symbol': symbol_label,
                'price': price_label,
                'change': change_label
            }

        content_layout.addLayout(self.stocks_grid)

        main_layout.addWidget(self.content_widget)

    def toggle_collapse(self, event=None):
        """Toggle collapse/expand state"""
        self.is_collapsed = not self.is_collapsed

        if self.is_collapsed:
            self.content_widget.hide()
            self.collapse_btn.setText("▶")
        else:
            self.content_widget.show()
            self.collapse_btn.setText("▼")

    def update_prices(self, prices):
        """
        Update the card with new prices.
        `prices` should be a dictionary of {symbol: price}.
        """
        from datetime import datetime

        self.previous_prices = self.current_prices.copy()
        self.current_prices = prices.copy()

        # Update indices
        for symbol in self.indices_labels:
            if symbol in prices:
                price = prices[symbol]

                if price is None or (isinstance(price, str) and price.lower() in ['none', 'n/a', '']):
                    self.indices_labels[symbol]['price'].setText("--")
                    self.indices_labels[symbol]['change'].setText("--")
                    continue

                # Update price
                price_str = f"₹{price:,.2f}" if isinstance(price, (int, float)) else str(price)
                self.indices_labels[symbol]['price'].setText(price_str)

                # Calculate and display change
                if symbol in self.previous_prices:
                    prev_price = self.previous_prices[symbol]
                    if isinstance(price, (int, float)) and isinstance(prev_price, (int, float)) and prev_price != 0:
                        change = price - prev_price
                        change_pct = (change / prev_price) * 100

                        if change > 0:
                            color = "#2ecc71"  # Green
                            sign = "+"
                        elif change < 0:
                            color = "#e74c3c"  # Red
                            sign = ""
                        else:
                            color = "#95a5a6"  # Gray
                            sign = ""

                        change_text = f"{sign}{change_pct:.2f}%"
                        self.indices_labels[symbol]['change'].setText(change_text)
                        self.indices_labels[symbol]['change'].setStyleSheet(f"""
                            font-size: 12px;
                            color: {color};
                            font-weight: bold;
                        """)
                        self.indices_labels[symbol]['price'].setStyleSheet(f"""
                            font-size: 14px;
                            font-weight: bold;
                            color: {color};
                        """)

        # Update stocks
        for symbol in self.stocks_labels:
            if symbol in prices:
                price = prices[symbol]

                if price is None or (isinstance(price, str) and price.lower() in ['none', 'n/a', '']):
                    self.stocks_labels[symbol]['price'].setText("--")
                    self.stocks_labels[symbol]['change'].setText("--")
                    continue

                # Update price
                price_str = f"₹{price:,.2f}" if isinstance(price, (int, float)) else str(price)
                self.stocks_labels[symbol]['price'].setText(price_str)

                # Calculate and display change
                if symbol in self.previous_prices:
                    prev_price = self.previous_prices[symbol]
                    if isinstance(price, (int, float)) and isinstance(prev_price, (int, float)) and prev_price != 0:
                        change = price - prev_price
                        change_pct = (change / prev_price) * 100

                        if change > 0:
                            color = "#2ecc71"  # Green
                            sign = "+"
                        elif change < 0:
                            color = "#e74c3c"  # Red
                            sign = ""
                        else:
                            color = "#95a5a6"  # Gray
                            sign = ""

                        change_text = f"{sign}{change_pct:.2f}%"
                        self.stocks_labels[symbol]['change'].setText(change_text)
                        self.stocks_labels[symbol]['change'].setStyleSheet(f"""
                            font-size: 11px;
                            color: {color};
                            font-weight: bold;
                        """)
                        self.stocks_labels[symbol]['price'].setStyleSheet(f"""
                            font-size: 13px;
                            font-weight: bold;
                            color: {color};
                        """)

        # Update last updated time
        current_time = datetime.now().strftime("%I:%M:%S %p")
        self.last_updated_label.setText(f"Last updated: {current_time}")
