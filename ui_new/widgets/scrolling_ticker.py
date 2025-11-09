#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ==============================================================================
# FILE: scrolling_ticker.py
# LOCATION: c:\Users\Dell\tradingbot_new\ui_new\widgets\scrolling_ticker.py
#
# ==============================================================================

from PyQt5.QtWidgets import QWidget, QLabel
from PyQt5.QtCore import QTimer, Qt, QRect
from PyQt5.QtGui import QFont, QPainter

class ScrollingTicker(QWidget):
    """
    A scrolling ticker widget that displays stock prices.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(40)
        self.setContentsMargins(0, 0, 0, 0)
        
        self.text = ""
        self.offset = 0
        self.current_prices = {}
        self.previous_prices = {}
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.scroll)
        self.timer.start(30)  # Scroll speed
        
        self.font = QFont("Arial", 12, QFont.Bold) # Reduced font size to 12
        
    def set_text(self, text):
        # This method is no longer used directly for drawing, but can be kept for debugging
        self.text = text
        self.update()
        
    def scroll(self):
        self.offset += 1
        # The offset should loop based on the actual content width
        # This will be calculated dynamically in paintEvent
        self.update()
        
    def paintEvent(self, event):
        from PyQt5.QtGui import QColor

        painter = QPainter(self)
        painter.setFont(self.font)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)

        # Fill background with dark color for contrast
        painter.fillRect(self.rect(), QColor(30, 30, 40))  # Dark blue-gray background
        
        metrics = self.fontMetrics()
        text_height = metrics.height()
        y_pos = int((self.height() - text_height) / 2 + metrics.ascent())
        
        # Build the full ticker string and calculate its total width
        full_ticker_string_parts = []
        for symbol, current_price in self.current_prices.items():
            # Skip symbols with None or invalid prices
            if current_price is None or (isinstance(current_price, str) and current_price.lower() in ['none', 'n/a', '']):
                continue

            price_str = f"{current_price:.2f}" if isinstance(current_price, (int, float)) else str(current_price)

            # Determine color based on price trend (up/down)
            from PyQt5.QtGui import QColor
            symbol_color = QColor(255, 255, 255)  # Default white
            price_color = QColor(255, 255, 255)   # Default white

            if (symbol in self.previous_prices and
                isinstance(current_price, (int, float)) and
                isinstance(self.previous_prices[symbol], (int, float))):
                prev_price = self.previous_prices[symbol]
                if current_price > prev_price:
                    # Price went up - show green
                    symbol_color = QColor(0, 255, 100)  # Bright green
                    price_color = QColor(0, 255, 100)   # Bright green
                elif current_price < prev_price:
                    # Price went down - show red
                    symbol_color = QColor(255, 80, 80)  # Bright red
                    price_color = QColor(255, 80, 80)   # Bright red

            # Add symbol with extra spacing, price, and separator with spacing
            full_ticker_string_parts.append((f"{symbol}:  ", symbol_color))  # Symbol with 2 spaces after colon
            full_ticker_string_parts.append((f"{price_str}  ", price_color))  # Price with 2 spaces after
            full_ticker_string_parts.append(("|  ", QColor(150, 150, 150)))  # Separator with spacing
        
        if not full_ticker_string_parts:
            return # Nothing to draw
            
        # Calculate the total width of one full cycle of the ticker content
        total_content_width = 0
        for text_part, _ in full_ticker_string_parts:
            total_content_width += metrics.width(text_part)
        
        # Add some buffer space at the end of the content before it loops
        buffer_space = 100 # Pixels of empty space between repetitions
        total_content_width_with_buffer = total_content_width + buffer_space
        
        # Adjust offset to loop seamlessly
        if self.offset > total_content_width_with_buffer:
            self.offset = 0
            
        # Determine how many times to draw the content to fill the visible area and beyond
        # We need to draw from -total_content_width_with_buffer up to self.width() + total_content_width_with_buffer
        # to ensure seamless scrolling.
        
        start_drawing_x = -self.offset % total_content_width_with_buffer
        
        current_draw_x = start_drawing_x
        while current_draw_x < self.width() + total_content_width_with_buffer: # Draw enough to cover the visible area and beyond for seamless loop
            x_pos_in_block = current_draw_x
            for text_part, color in full_ticker_string_parts:
                painter.setPen(color)
                # Use integer positions to avoid sub-pixel rendering artifacts
                painter.drawText(int(x_pos_in_block), int(y_pos), text_part)
                x_pos_in_block += metrics.width(text_part)
            
            # Move to the start of the next full block repetition
            current_draw_x += total_content_width_with_buffer
            
    def update_prices(self, prices):
        """
        Update the ticker with new prices.
        `prices` should be a dictionary of {symbol: price}.
        """
        self.previous_prices = self.current_prices
        self.current_prices = prices
        self.update() # Trigger repaint

