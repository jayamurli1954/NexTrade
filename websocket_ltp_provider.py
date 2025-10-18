#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
WebSocket LTP Provider for Angel One
File: websocket_ltp_provider.py

This replaces REST API get_ltp calls with WebSocket streaming.
NO MORE RATE LIMITS!
"""

import threading
import time
import json
from typing import Dict, Optional, List, Callable
from datetime import datetime
from SmartApi.smartWebSocketV2 import SmartWebSocketV2
from logzero import logger


class WebSocketLTPProvider:
    """
    Real-time LTP provider using Angel One WebSocket
    
    Features:
    - Automatic reconnection
    - Thread-safe price storage
    - Subscribe/unsubscribe on demand
    - Callback support for price updates
    - No rate limits!
    """
    
    def __init__(self, auth_token: str, api_key: str, client_code: str, feed_token: str):
        """Initialize WebSocket LTP provider"""
        self.auth_token = auth_token
        self.api_key = api_key
        self.client_code = client_code
        self.feed_token = feed_token
        
        # Thread-safe price storage
        self._prices: Dict[str, float] = {}
        self._price_lock = threading.Lock()
        
        # Token to symbol mapping
        self._token_to_symbol: Dict[str, str] = {}
        self._symbol_to_token: Dict[str, str] = {}
        
        # Subscribed tokens
        self._subscribed_tokens: set = set()
        
        # WebSocket instance
        self.ws = None
        self._ws_thread = None
        self._is_connected = False
        self._should_run = True
        
        # Callbacks
        self._price_callbacks: List[Callable] = []
        
        # Connection retry settings
        self._max_retries = 5
        self._retry_delay = 5  # seconds
        
        logger.info("WebSocketLTPProvider initialized")
    
    def add_price_callback(self, callback: Callable):
        """Add a callback function that will be called on price updates"""
        self._price_callbacks.append(callback)
    
    def _on_data(self, ws, message):
        """Handle incoming WebSocket data"""
        try:
            # Parse the message
            data = json.loads(message) if isinstance(message, str) else message
            
            # Extract LTP from the message
            # Angel One WebSocket sends data in this format
            if isinstance(data, dict) and 'last_traded_price' in data:
                token = str(data.get('token', ''))
                ltp = float(data['last_traded_price']) / 100  # Angel One sends price * 100
                
                if token in self._token_to_symbol:
                    symbol = self._token_to_symbol[token]
                    
                    # Store the price
                    with self._price_lock:
                        self._prices[symbol] = ltp
                    
                    # Call callbacks
                    for callback in self._price_callbacks:
                        try:
                            callback(symbol, ltp)
                        except Exception as e:
                            logger.error(f"Error in price callback: {e}")
                    
                    logger.debug(f"WebSocket: {symbol} = ₹{ltp:.2f}")
            
        except Exception as e:
            logger.error(f"Error parsing WebSocket message: {e}")
    
    def _on_open(self, ws):
        """Handle WebSocket connection open"""
        logger.info("✅ WebSocket connected!")
        self._is_connected = True
        
        # Re-subscribe to all tokens if this is a reconnection
        if self._subscribed_tokens:
            logger.info(f"Re-subscribing to {len(self._subscribed_tokens)} tokens...")
            self._subscribe_tokens(list(self._subscribed_tokens))
    
    def _on_error(self, ws, error):
        """Handle WebSocket errors"""
        logger.error(f"WebSocket error: {error}")
        self._is_connected = False
    
    def _on_close(self, ws):
        """Handle WebSocket closure"""
        logger.warning("WebSocket connection closed")
        self._is_connected = False
        
        # Attempt reconnection
        if self._should_run:
            logger.info("Attempting to reconnect in 5 seconds...")
            time.sleep(5)
            self._connect_websocket()
    
    def _connect_websocket(self):
        """Establish WebSocket connection"""
        try:
            # Create WebSocket instance
            self.ws = SmartWebSocketV2(
                self.auth_token,
                self.api_key,
                self.client_code,
                self.feed_token
            )
            
            # Assign callbacks
            self.ws.on_data = self._on_data
            self.ws.on_open = self._on_open
            self.ws.on_error = self._on_error
            self.ws.on_close = self._on_close
            
            # Connect in a separate thread
            self._ws_thread = threading.Thread(target=self.ws.connect, daemon=True)
            self._ws_thread.start()
            
            logger.info("WebSocket connection initiated...")
            
            # Wait for connection
            timeout = 10
            start = time.time()
            while not self._is_connected and (time.time() - start) < timeout:
                time.sleep(0.1)
            
            if self._is_connected:
                logger.info("✅ WebSocket connected successfully!")
                return True
            else:
                logger.error("❌ WebSocket connection timeout")
                return False
                
        except Exception as e:
            logger.error(f"Error connecting WebSocket: {e}")
            return False
    
    def _subscribe_tokens(self, tokens: List[str]):
        """Subscribe to a list of tokens"""
        if not self._is_connected or not self.ws:
            logger.warning("Cannot subscribe: WebSocket not connected")
            return False
        
        try:
            # Prepare subscription data
            token_list = [{
                "exchangeType": 1,  # NSE
                "tokens": tokens
            }]
            
            # Subscribe (mode 1 = LTP only)
            correlation_id = f"sub_{int(time.time())}"
            self.ws.subscribe(correlation_id, 1, token_list)
            
            logger.info(f"✅ Subscribed to {len(tokens)} tokens")
            return True
            
        except Exception as e:
            logger.error(f"Error subscribing to tokens: {e}")
            return False
    
    def start(self):
        """Start the WebSocket connection"""
        logger.info("Starting WebSocket LTP Provider...")
        self._should_run = True
        return self._connect_websocket()
    
    def stop(self):
        """Stop the WebSocket connection"""
        logger.info("Stopping WebSocket LTP Provider...")
        self._should_run = False
        
        if self.ws:
            try:
                self.ws.close_connection()
            except:
                pass
        
        self._is_connected = False
    
    def subscribe_symbols(self, symbols: List[str], token_map: Dict[str, str]):
        """
        Subscribe to a list of symbols
        
        Args:
            symbols: List of symbol names (e.g., ['TCS', 'INFY'])
            token_map: Dict mapping symbols to tokens (e.g., {'TCS': '11536'})
        """
        tokens_to_subscribe = []
        
        for symbol in symbols:
            if symbol in token_map:
                token = token_map[symbol]
                
                # Update mappings
                self._token_to_symbol[token] = symbol
                self._symbol_to_token[symbol] = token
                
                if token not in self._subscribed_tokens:
                    tokens_to_subscribe.append(token)
                    self._subscribed_tokens.add(token)
        
        if tokens_to_subscribe:
            logger.info(f"Subscribing to {len(tokens_to_subscribe)} new symbols...")
            return self._subscribe_tokens(tokens_to_subscribe)
        
        return True
    
    def get_ltp(self, symbol: str) -> Optional[float]:
        """
        Get the latest traded price for a symbol
        
        This is a DROP-IN REPLACEMENT for the REST API get_ltp()
        Returns cached price from WebSocket stream (no API call!)
        """
        with self._price_lock:
            return self._prices.get(symbol)
    
    def get_all_prices(self) -> Dict[str, float]:
        """Get all cached prices"""
        with self._price_lock:
            return self._prices.copy()
    
    def is_connected(self) -> bool:
        """Check if WebSocket is connected"""
        return self._is_connected
    
    def get_subscribed_count(self) -> int:
        """Get number of subscribed symbols"""
        return len(self._subscribed_tokens)


# Singleton instance
_ws_provider_instance = None


def get_websocket_provider(auth_token=None, api_key=None, client_code=None, feed_token=None):
    """Get or create the WebSocket provider singleton"""
    global _ws_provider_instance
    
    if _ws_provider_instance is None:
        if not all([auth_token, api_key, client_code, feed_token]):
            raise ValueError("First call requires all authentication parameters")
        
        _ws_provider_instance = WebSocketLTPProvider(
            auth_token, api_key, client_code, feed_token
        )
        _ws_provider_instance.start()
    
    return _ws_provider_instance