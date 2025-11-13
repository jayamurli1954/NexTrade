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
    A modern, sleek collapsible card showing major indices and stocks.
    Refreshes every 30 seconds with beautiful UI.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.is_collapsed = False
        self.current_prices = {}
        self.previous_prices = {}

        self.init_ui()

    def init_ui(self):
        """Initialize the modern UI"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Main card container with shadow effect
        self.card_container = QWidget()
        self.card_container.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #1e3c72, stop:1 #2a5298);
                border-radius: 12px;
                border: 1px solid rgba(255, 255, 255, 0.1);
            }
        """)

        card_layout = QVBoxLayout(self.card_container)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)

        # Title bar (clickable to collapse/expand)
        self.title_bar = QWidget()
        self.title_bar.setStyleSheet("""
            QWidget {
                background: transparent;
                border-radius: 12px 12px 0 0;
                padding: 15px;
            }
        """)
        self.title_bar.setCursor(QCursor(Qt.PointingHandCursor))
        self.title_bar.mousePressEvent = self.toggle_collapse

        title_layout = QHBoxLayout(self.title_bar)
        title_layout.setContentsMargins(20, 10, 20, 10)

        # Icon + Title
        icon_label = QLabel("📊")
        icon_label.setStyleSheet("font-size: 20px;")
        title_layout.addWidget(icon_label)

        title_label = QLabel("Market Overview")
        title_label.setStyleSheet("""
            font-size: 18px;
            font-weight: bold;
            color: white;
            margin-left: 5px;
        """)
        title_layout.addWidget(title_label)

        title_layout.addStretch()

        # Last updated label
        self.last_updated_label = QLabel("Last updated: Never")
        self.last_updated_label.setStyleSheet("""
            font-size: 11px;
            color: rgba(255, 255, 255, 0.7);
            background: rgba(255, 255, 255, 0.1);
            padding: 5px 12px;
            border-radius: 12px;
        """)
        title_layout.addWidget(self.last_updated_label)

        # Collapse/Expand button
        self.collapse_btn = QPushButton("▼")
        self.collapse_btn.setFixedSize(30, 30)
        self.collapse_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.15);
                border: none;
                color: white;
                font-size: 14px;
                font-weight: bold;
                border-radius: 15px;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.25);
            }
        """)
        self.collapse_btn.clicked.connect(self.toggle_collapse)
        title_layout.addWidget(self.collapse_btn)

        card_layout.addWidget(self.title_bar)

        # Separator line
        separator_top = QFrame()
        separator_top.setFrameShape(QFrame.HLine)
        separator_top.setStyleSheet("""
            background: rgba(255, 255, 255, 0.1);
            max-height: 1px;
            border: none;
        """)
        card_layout.addWidget(separator_top)

        # Content area (collapsible)
        self.content_widget = QWidget()
        self.content_widget.setStyleSheet("""
            QWidget {
                background: transparent;
                padding: 20px;
            }
        """)

        content_layout = QVBoxLayout(self.content_widget)
        content_layout.setSpacing(20)

        # Major Indices Section
        indices_header = QHBoxLayout()
        indices_icon = QLabel("📈")
        indices_icon.setStyleSheet("font-size: 16px;")
        indices_header.addWidget(indices_icon)

        indices_label = QLabel("Major Indices")
        indices_label.setStyleSheet("""
            font-size: 15px;
            font-weight: bold;
            color: #ffffff;
            letter-spacing: 0.5px;
        """)
        indices_header.addWidget(indices_label)
        indices_header.addStretch()
        content_layout.addLayout(indices_header)

        # Indices cards container
        indices_container = QHBoxLayout()
        indices_container.setSpacing(15)

        self.indices_labels = {}
        indices = ["NIFTY", "BANKNIFTY", "SENSEX", "INDIAVIX"]

        for index in indices:
            # Create individual card for each index
            index_card = QWidget()
            index_card.setStyleSheet("""
                QWidget {
                    background: rgba(255, 255, 255, 0.1);
                    border-radius: 10px;
                    padding: 15px;
                    border: 1px solid rgba(255, 255, 255, 0.15);
                }
            """)

            index_layout = QVBoxLayout(index_card)
            index_layout.setSpacing(8)

            # Symbol name
            symbol_label = QLabel(index)
            symbol_label.setStyleSheet("""
                font-size: 13px;
                font-weight: 600;
                color: rgba(255, 255, 255, 0.8);
                letter-spacing: 0.3px;
            """)
            symbol_label.setAlignment(Qt.AlignCenter)
            index_layout.addWidget(symbol_label)

            # Price
            price_label = QLabel("--")
            price_label.setAlignment(Qt.AlignCenter)
            price_label.setStyleSheet("""
                font-size: 18px;
                font-weight: bold;
                color: #ffffff;
            """)
            index_layout.addWidget(price_label)

            # Change percentage
            change_label = QLabel("--")
            change_label.setAlignment(Qt.AlignCenter)
            change_label.setStyleSheet("""
                font-size: 12px;
                font-weight: 600;
                color: #95a5a6;
                padding: 4px 8px;
                border-radius: 6px;
                background: rgba(0, 0, 0, 0.2);
            """)
            index_layout.addWidget(change_label)

            indices_container.addWidget(index_card)

            self.indices_labels[index] = {
                'card': index_card,
                'symbol': symbol_label,
                'price': price_label,
                'change': change_label
            }

        content_layout.addLayout(indices_container)

        # Separator
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setStyleSheet("""
            background: rgba(255, 255, 255, 0.1);
            max-height: 1px;
            border: none;
            margin: 10px 0;
        """)
        content_layout.addWidget(separator)

        # Major Stocks Section
        stocks_header = QHBoxLayout()
        stocks_icon = QLabel("💼")
        stocks_icon.setStyleSheet("font-size: 16px;")
        stocks_header.addWidget(stocks_icon)

        stocks_label = QLabel("Major Stocks")
        stocks_label.setStyleSheet("""
            font-size: 15px;
            font-weight: bold;
            color: #ffffff;
            letter-spacing: 0.5px;
        """)
        stocks_header.addWidget(stocks_label)
        stocks_header.addStretch()
        content_layout.addLayout(stocks_header)

        # Stocks grid
        self.stocks_grid = QGridLayout()
        self.stocks_grid.setSpacing(12)
        self.stocks_grid.setContentsMargins(0, 0, 0, 0)

        self.stocks_labels = {}
        stocks = ["RELIANCE", "HDFCBANK", "BHARTIARTL", "TCS",
                  "INFY", "ICICIBANK", "SBIN", "LT",
                  "WIPRO", "TITAN"]

        for i, stock in enumerate(stocks):
            # Create mini card for each stock
            stock_item = QWidget()
            stock_item.setStyleSheet("""
                QWidget {
                    background: rgba(255, 255, 255, 0.08);
                    border-radius: 8px;
                    padding: 12px 15px;
                    border: 1px solid rgba(255, 255, 255, 0.1);
                }
            """)

            stock_layout = QHBoxLayout(stock_item)
            stock_layout.setContentsMargins(0, 0, 0, 0)
            stock_layout.setSpacing(10)

            # Symbol
            symbol_label = QLabel(stock)
            symbol_label.setStyleSheet("""
                font-size: 13px;
                font-weight: 600;
                color: #ffffff;
                min-width: 90px;
            """)
            stock_layout.addWidget(symbol_label)

            stock_layout.addStretch()

            # Price
            price_label = QLabel("--")
            price_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            price_label.setStyleSheet("""
                font-size: 14px;
                font-weight: bold;
                color: #ffffff;
                min-width: 80px;
            """)
            stock_layout.addWidget(price_label)

            # Change
            change_label = QLabel("--")
            change_label.setAlignment(Qt.AlignCenter)
            change_label.setStyleSheet("""
                font-size: 11px;
                font-weight: 600;
                color: #95a5a6;
                padding: 3px 8px;
                border-radius: 5px;
                background: rgba(0, 0, 0, 0.2);
                min-width: 65px;
            """)
            stock_layout.addWidget(change_label)

            row = i // 2
            col = i % 2

            self.stocks_grid.addWidget(stock_item, row, col)

            self.stocks_labels[stock] = {
                'item': stock_item,
                'symbol': symbol_label,
                'price': price_label,
                'change': change_label
            }

        content_layout.addLayout(self.stocks_grid)

        card_layout.addWidget(self.content_widget)

        main_layout.addWidget(self.card_container)

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
                            color = "#00ff88"  # Bright green
                            bg_color = "rgba(0, 255, 136, 0.15)"
                            sign = "+"
                        elif change < 0:
                            color = "#ff4757"  # Bright red
                            bg_color = "rgba(255, 71, 87, 0.15)"
                            sign = ""
                        else:
                            color = "#95a5a6"  # Gray
                            bg_color = "rgba(0, 0, 0, 0.2)"
                            sign = ""

                        change_text = f"{sign}{change_pct:.2f}%"
                        self.indices_labels[symbol]['change'].setText(change_text)
                        self.indices_labels[symbol]['change'].setStyleSheet(f"""
                            font-size: 12px;
                            color: {color};
                            font-weight: 600;
                            padding: 4px 8px;
                            border-radius: 6px;
                            background: {bg_color};
                        """)
                        self.indices_labels[symbol]['price'].setStyleSheet(f"""
                            font-size: 18px;
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
                            color = "#00ff88"  # Bright green
                            bg_color = "rgba(0, 255, 136, 0.15)"
                            sign = "+"
                        elif change < 0:
                            color = "#ff4757"  # Bright red
                            bg_color = "rgba(255, 71, 87, 0.15)"
                            sign = ""
                        else:
                            color = "#95a5a6"  # Gray
                            bg_color = "rgba(0, 0, 0, 0.2)"
                            sign = ""

                        change_text = f"{sign}{change_pct:.2f}%"
                        self.stocks_labels[symbol]['change'].setText(change_text)
                        self.stocks_labels[symbol]['change'].setStyleSheet(f"""
                            font-size: 11px;
                            color: {color};
                            font-weight: 600;
                            padding: 3px 8px;
                            border-radius: 5px;
                            background: {bg_color};
                        """)
                        self.stocks_labels[symbol]['price'].setStyleSheet(f"""
                            font-size: 14px;
                            font-weight: bold;
                            color: {color};
                        """)

        # Update last updated time
        current_time = datetime.now().strftime("%I:%M:%S %p")
        self.last_updated_label.setText(f"Updated: {current_time}")
