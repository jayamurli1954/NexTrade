#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ==============================================================================
# SAVE THIS FILE AS: core/websocket/price_provider.py
# NOTE: This requires SmartAPI library
# Install: pip install smartapi-python
# ==============================================================================
"""
WebSocket Price Provider for Angel One

Real-time price streaming with NO rate limits!
"""

import threading
import time
import json
from typing import Dict, Optional, List, Callable
from datetime import datetime
from logzero import logger

try:
    from SmartApi.smartWebSocketV2 import SmartWebSocketV2
except ImportError:
    logger.warning("SmartAPI not installed. Run: pip install smartapi-python")
    SmartWebSocketV2 = None


class WebSocketPriceProvider:
    """
    Real-time price provider using Angel One WebSocket
    
    Features:
    - Real-time LTP updates (no API calls!)
    - Automatic reconnection
    - Thread-safe price storage
    - Subscribe/unsubscribe on demand
    - NO RATE LIMITS!
    """
    
    def __init__(self, auth_token: str, api_key: str, client_code: str, feed_token: str):
        """
        Initialize WebSocket price provider
        
        Args:
            auth_token: JWT token from login
            api_key: Your API key
            client_code: Your client ID
            feed_token: Feed token from login
        """
        
        if SmartWebSocketV2 is None:
            raise ImportError("SmartAPI library not installed. Run: pip install smartapi-python")
        
        self.auth_token = auth_token
        self.api_key = api_key
        self.client_code = client_code
        self.feed_token = feed_token
        
        # Thread-safe price storage
        self._prices: Dict[str, Dict] = {}
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
        
        # Callbacks for price updates
        self._price_callbacks: List[Callable] = []
        
        # Reconnection settings
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 10
        self._reconnect_delay = 5  # seconds
        
        logger.info("WebSocket Price Provider initialized")
    
    def add_price_callback(self, callback: Callable):
        """
        Add a callback function that will be called on price updates
        
        Args:
            callback: Function with signature callback(symbol, price_data)
        """
        self._price_callbacks.append(callback)
    
    def _on_data(self, ws, message):
        """Handle incoming WebSocket data"""
        try:
            # Parse message
            if isinstance(message, str):
                data = json.loads(message)
            else:
                data = message
            
            # Extract price information
            # Angel One WebSocket format
            if isinstance(data, dict):
                token = str(data.get('token', ''))
                
                if token in self._token_to_symbol:
                    symbol = self._token_to_symbol[token]
                    
                    # Angel One sends price * 100, so divide by 100
                    ltp = data.get('last_traded_price', 0) / 100.0
                    
                    price_data = {
                        'ltp': ltp,
                        'timestamp': datetime.now(),
                        'volume': data.get('volume_trade_for_the_day', 0),
                        'open': data.get('open_price_of_the_day', 0) / 100.0,
                        'high': data.get('high_price_of_the_day', 0) / 100.0,
                        'low': data.get('low_price_of_the_day', 0) / 100.0,
                        'close': data.get('closed_price', 0) / 100.0,
                    }
                    
                    # Store price
                    with self._price_lock:
                        self._prices[symbol] = price_data
                    
                    # Call callbacks
                    for callback in self._price_callbacks:
                        try:
                            callback(symbol, price_data)
                        except Exception as e:
                            logger.error(f"Error in price callback: {e}")
                    
                    logger.debug(f"WebSocket: {symbol} = Rs.{ltp:.2f}")
            
        except Exception as e:
            logger.error(f"Error parsing WebSocket message: {e}")
    
    def _on_open(self, ws):
        """Handle WebSocket connection open"""
        logger.info("WebSocket connected!")
        self._is_connected = True
        self._reconnect_attempts = 0
        
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
        
        # Attempt reconnection if we should still be running
        if self._should_run and self._reconnect_attempts < self._max_reconnect_attempts:
            self._reconnect_attempts += 1
            delay = self._reconnect_delay * self._reconnect_attempts
            
            logger.info(f"Reconnecting in {delay} seconds (attempt {self._reconnect_attempts}/{self._max_reconnect_attempts})...")
            time.sleep(delay)
            
            self._connect_websocket()
    
    def _connect_websocket(self):
        """Establish WebSocket connection"""
        try:
            logger.info("Connecting to Angel One WebSocket...")
            
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
            
            # Wait for connection
            timeout = 10
            start = time.time()
            while not self._is_connected and (time.time() - start) < timeout:
                time.sleep(0.1)
            
            if self._is_connected:
                logger.info("WebSocket connected successfully!")
                return True
            else:
                logger.error("WebSocket connection timeout")
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
            # Mode 1 = LTP only (fastest, least data)
            token_list = [{
                "exchangeType": 1,  # NSE
                "tokens": tokens
            }]
            
            # Subscribe
            correlation_id = f"sub_{int(time.time())}"
            self.ws.subscribe(correlation_id, 1, token_list)
            
            logger.info(f"Subscribed to {len(tokens)} tokens")
            return True
            
        except Exception as e:
            logger.error(f"Error subscribing to tokens: {e}")
            return False
    
    def start(self):
        """Start the WebSocket connection"""
        logger.info("Starting WebSocket Price Provider...")
        self._should_run = True
        return self._connect_websocket()
    
    def stop(self):
        """Stop the WebSocket connection"""
        logger.info("Stopping WebSocket Price Provider...")
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
        
        This is a DROP-IN REPLACEMENT for REST API get_ltp()
        Returns cached price from WebSocket stream (no API call!)
        
        Args:
            symbol: Stock symbol
            
        Returns:
            Latest price or None if not available
        """
        with self._price_lock:
            price_data = self._prices.get(symbol)
            if price_data:
                return price_data['ltp']
        return None
    
    def get_price_data(self, symbol: str) -> Optional[Dict]:
        """
        Get complete price data for a symbol
        
        Args:
            symbol: Stock symbol
            
        Returns:
            Dict with ltp, open, high, low, close, volume, timestamp
        """
        with self._price_lock:
            return self._prices.get(symbol)
    
    def get_all_prices(self) -> Dict[str, Dict]:
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
    """
    Get or create the WebSocket provider singleton
    
    Args:
        auth_token: JWT token (required on first call)
        api_key: API key (required on first call)
        client_code: Client ID (required on first call)
        feed_token: Feed token (required on first call)
    
    Returns:
        WebSocketPriceProvider instance
    """
    global _ws_provider_instance
    
    if _ws_provider_instance is None:
        if not all([auth_token, api_key, client_code, feed_token]):
            raise ValueError("First call requires all authentication parameters")
        
        _ws_provider_instance = WebSocketPriceProvider(
            auth_token, api_key, client_code, feed_token
        )
        _ws_provider_instance.start()
    
    return _ws_provider_instance


if __name__ == "__main__":
    print("WebSocket Price Provider")
    print()
    print("This module requires authentication tokens from Angel One.")
    print("It will be integrated with your existing bot.")
    print()
    print("Features:")
    print("  - Real-time price streaming")
    print("  - NO rate limits")
    print("  - Automatic reconnection")
    print("  - Thread-safe")
    print()