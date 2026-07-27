#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ==============================================================================
# FILE NAME: connection_manager.py
# SAVE LOCATION: c:\Users\Dell\tradingbot_new\ui_new\connection_manager.py
# VERSION: 4.1.0 - Fast Startup with Lazy Token Loading
# LAST UPDATED: 2025-10-13
# 
# CHANGELOG:
#   v4.1.0 (2025-10-13) - Lazy token loading for instant startup
#   v4.0.0 (2025-10-13) - WebSocket V2 implementation (FIXES FREEZING!)
#
# PURPOSE: Single source of truth for Angel One API with WebSocket streaming
# ==============================================================================

import os
import json
import time
import threading
from pathlib import Path

# Angel One SmartAPI
try:
    from SmartApi import SmartConnect
    from SmartApi.smartWebSocketV2 import SmartWebSocketV2
    SMARTAPI_AVAILABLE = True
except Exception:
    SMARTAPI_AVAILABLE = False
    print("[INFO] SmartApi library optional or dependencies missing (websocket-client).")

# TOTP for authentication
try:
    import pyotp
    PYOTP_AVAILABLE = True
except ImportError:
    PYOTP_AVAILABLE = False
    print("[INFO] pyotp optional (install pyotp for automatic TOTP generation).")


def _safe_print(text):
    """Windows cp1252-safe console output (emojis crash default print)."""
    safe_text = str(text).encode("ascii", errors="replace").decode("ascii")
    try:
        print(safe_text)
    except Exception:
        pass


_WORKSPACE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _workspace_path(*parts: str) -> str:
    return os.path.join(_WORKSPACE_DIR, *parts)


class ConnectionManager:

    """
    Connection Manager with WebSocket V2 for Real-Time Market Data
    Fast startup with lazy token loading
    """
    
    def __init__(self):
        # API instances
        self.smart_api = None
        self.websocket = None
        self.analyzer = None
        
        # Configuration
        self.config = {}
        self.stock_list = []
        
        # Connection status
        self.is_connected = False
        self.websocket_connected = False
        
        # Token mapping: NSE:SYMBOL -> token
        self.token_map = {}
        self.token_to_symbol_map = {} # NEW: Reverse map for faster lookup
        self.tokens_loaded = False  # NEW: Track if tokens are loaded
        
        # Real-time LTP data from WebSocket
        self.ltp_data = {}
        self.ltp_lock = threading.Lock()
        
        # WebSocket credentials
        self.auth_token = None
        self.feed_token = None
        self.client_code = None
        self.api_key = None
        
        # Initialize (but DON'T load tokens yet for fast startup!)
        self.load_config()
        self.load_stock_list()
        # Token loading moved to ensure_tokens_loaded() - called on demand
    
    def load_config(self):
        """Load API credentials from config.json (workspace-relative first)."""
        config_files = [
            _workspace_path("config.json"),
            "config.json",
            "config.py",
            ".env",
        ]
        
        for config_file in config_files:
            if os.path.exists(config_file):
                try:
                    if config_file.endswith('.json'):
                        with open(config_file, 'r', encoding='utf-8') as f:
                            self.config = json.load(f)
                        _safe_print(f"[OK] Loaded config from {config_file}")
                        return
                except Exception as e:
                    _safe_print(f"[WARN] Could not load {config_file}: {e}")
        
        # Default config
        self.config = {
            'api_key': '', 'client_id': '', 'password': '', 'totp_token': '',
            'initial_capital': 100000, 'risk_per_trade': 2, 'auto_trading': False
        }
        _safe_print("[WARN] No config file found, using defaults")


    
    def load_stock_list(self):
        """Load stock list from watchlist.json (workspace-relative first)."""
        watchlist_paths = [_workspace_path("watchlist.json"), "watchlist.json"]
        for watchlist_path in watchlist_paths:
            if os.path.exists(watchlist_path):
                try:
                    with open(watchlist_path, 'r', encoding='utf-8') as f:
                        self.stock_list = json.load(f)
                        self.stock_list = [s.upper() for s in self.stock_list]
                    _safe_print(f"[OK] Loaded {len(self.stock_list)} stocks from {watchlist_path}")
                    return
                except Exception as e:
                    _safe_print(f"[WARN] Could not load {watchlist_path}: {e}")
        
        # Fallback to stock_list.txt
        for stock_path in (_workspace_path("stock_list.txt"), "stock_list.txt"):
            if os.path.exists(stock_path):
                try:
                    with open(stock_path, 'r', encoding='utf-8') as f:
                        self.stock_list = [line.strip().upper() for line in f if line.strip()]
                    _safe_print(f"[OK] Loaded {len(self.stock_list)} stocks from {stock_path}")
                    return
                except Exception as e:
                    _safe_print(f"[WARN] Could not load {stock_path}: {e}")
        
        # Default stocks
        _safe_print("[WARN] No watchlist file found, using defaults")
        self.stock_list = ["INFY", "TCS", "RELIANCE", "HDFCBANK", "ICICIBANK"]
    
    def save_stock_list(self):
        """Save stock list to watchlist.json"""
        try:
            path = _workspace_path("watchlist.json")
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(self.stock_list, f, indent=2)
            _safe_print(f"[OK] Saved {len(self.stock_list)} stocks to {path}")
            return True
        except Exception as e:
            _safe_print(f"[WARN] Could not save watchlist: {e}")
            return False

    
    def add_stock(self, symbol):
        """Add a stock to watchlist and subscribe to WebSocket"""
        symbol = symbol.upper().strip()
        if symbol and symbol not in self.stock_list:
            self.stock_list.append(symbol)
            self.save_stock_list()
            
            # Subscribe to WebSocket if connected
            if self.websocket_connected:
                self.subscribe_symbols([symbol])
            
            return True
        return False
    
    def remove_stock(self, symbol):
        """Remove a stock from watchlist"""
        symbol = symbol.upper().strip()
        if symbol in self.stock_list:
            self.stock_list.remove(symbol)
            self.save_stock_list()
            return True
        return False
    
    def ensure_tokens_loaded(self):
        """Load tokens only when needed (lazy loading for fast startup)"""
        if not self.tokens_loaded:
            _safe_print("[...] Loading symbol tokens (first time only)...")
            self.load_symbol_tokens()

            # Manually add index tokens if not found by load_symbol_tokens
            # These indices need exact tokens for WebSocket subscription
            # Using correct Angel One index tokens
            index_tokens = {
                "NSE:NIFTY": "99926000",      # Nifty 50 index (Correct)
                "NSE:BANKNIFTY": "99926009",  # Bank Nifty index (Correct)
                "BSE:SENSEX": "99919000",     # Sensex index (Correct)
                "NSE:INDIAVIX": "99926017"    # India VIX (Correct)
            }

            # Force update with correct tokens (override any wrong fallback values)
            for key, token in index_tokens.items():
                self.token_map[key] = token
                _safe_print(f"[OK] Added/Updated {key} token: {token}")

            # Build reverse map
            self.token_to_symbol_map = {token: key.split(':')[1] for key, token in self.token_map.items()}

            self.tokens_loaded = True
    
    def load_symbol_tokens(self):
        """Load symbol tokens from Angel One master file for multiple exchanges."""
        try:
            import requests
            
            url = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                # Supported exchanges
                exchanges = ["NSE", "NFO", "BSE"]
                
                for item in data:
                    exch_seg = item.get('exch_seg')
                    if exch_seg in exchanges:
                        symbol = item.get('symbol', '')
                        token = item.get('token', '')
                        
                        if symbol and token:
                            # Handle -EQ suffix for NSE
                            if exch_seg == 'NSE' and symbol.endswith('-EQ'):
                                clean_symbol = symbol.replace('-EQ', '').upper()
                            else:
                                clean_symbol = symbol.upper()
                            
                            key = f"{exch_seg}:{clean_symbol}"
                            self.token_map[key] = token
                            if clean_symbol in ["SENSEX", "INDIAVIX", "NIFTY", "BANKNIFTY"]: # Added indices for debug
                                _safe_print(f"[DEBUG] Loaded token for {key}: {token}")
                
                _safe_print(f"[OK] Loaded {len(self.token_map)} symbol tokens from Angel One")
                return True
            else:
                _safe_print("[WARN] Could not download symbol master, using fallback")
                self._load_fallback_tokens()
                return False
                
        except Exception as e:
            _safe_print(f"[WARN] Error loading symbol tokens: {e}")
            self._load_fallback_tokens()
            return False
    
    def _load_fallback_tokens(self):
        """Fallback token map for major stocks"""
        self.token_map = {
            'NSE:ABB': '5', 'NSE:ADANIENT': '25', 'NSE:ADANIGREEN': '15083',
            'NSE:ADANIPORTS': '15083', 'NSE:ADANIPOWER': '4', 'NSE:AMBUJACEM': '1270',
            'NSE:APOLLOHOSP': '157', 'NSE:ASIANPAINT': '236', 'NSE:DMART': '14299',
            'NSE:AXISBANK': '5900', 'NSE:BAJAJ-AUTO': '16669', 'NSE:BAJFINANCE': '317',
            'NSE:BAJAJFINSV': '16675', 'NSE:BAJAJHLDNG': '16675', 'NSE:BANKBARODA': '4668',
            'NSE:BEL': '383', 'NSE:BHARTIARTL': '10604', 'NSE:BHEL': '438',
            'NSE:BOSCHLTD': '558', 'NSE:BPCL': '526', 'NSE:BRITANNIA': '547',
            'NSE:CANBK': '10794', 'NSE:CHOLAFIN': '685', 'NSE:CIPLA': '694',
            'NSE:COALINDIA': '20374', 'NSE:DABUR': '768', 'NSE:DIVISLAB': '10940',
            'NSE:DLF': '3771', 'NSE:DRREDDY': '881', 'NSE:EICHERMOT': '910',
            'NSE:GAIL': '4717', 'NSE:GODREJCP': '10099', 'NSE:GRASIM': '1232',
            'NSE:HAVELLS': '9819', 'NSE:HCLTECH': '7229', 'NSE:HDFCBANK': '1333',
            'NSE:HDFCLIFE': '467', 'NSE:HEROMOTOCO': '1348', 'NSE:HINDALCO': '1363',
            'NSE:HAL': '2303', 'NSE:HINDUNILVR': '1394', 'NSE:ICICIBANK': '4963',
            'NSE:ICICIGI': '21770', 'NSE:ICICIPRULI': '18652', 'NSE:INDUSINDBK': '5258',
            'NSE:NAUKRI': '13751', 'NSE:INFY': '1594', 'NSE:INDIGO': '11195',
            'NSE:IOC': '1624', 'NSE:IRCTC': '13611', 'NSE:IRFC': '17534',
            'NSE:ITC': '1660', 'NSE:JINDALSTEL': '6733', 'NSE:JSWENERGY': '6733',
            'NSE:JSWSTEEL': '11723', 'NSE:KOTAKBANK': '1922', 'NSE:LT': '11483',
            'NSE:LICI': '19209', 'NSE:M&M': '2031', 'NSE:LODHA': '25197',
            'NSE:MARUTI': '10999', 'NSE:NESTLEIND': '17963', 'NSE:NHPC': '4162',
            'NSE:NTPC': '11630', 'NSE:ONGC': '2475', 'NSE:PIDILITIND': '2664',
            'NSE:PNB': '10666', 'NSE:PFC': '14299', 'NSE:POWERGRID': '14977',
            'NSE:RECLTD': '15355', 'NSE:RELIANCE': '2885', 'NSE:MOTHERSON': '4204',
            'NSE:SBIN': '3045', 'NSE:SBILIFE': '21808', 'NSE:SHREECEM': '3103',
            'NSE:SIEMENS': '3150', 'NSE:SUNPHARMA': '3351', 'NSE:TATACONSUM': '3432',
            'NSE:TATAMOTORS': '3456', 'NSE:TATAPOWER': '3426', 'NSE:TATASTEEL': '3499',
            'NSE:TCS': '11536', 'NSE:TECHM': '13538', 'NSE:TITAN': '3506',
            'NSE:TORNTPHARM': '3518', 'NSE:TRENT': '1964', 'NSE:TVSMOTOR': '8479',
            'NSE:ULTRACEMCO': '11532', 'NSE:UNIONBANK': '5423', 'NSE:VBL': '13540',
            'NSE:VEDL': '3063', 'NSE:WIPRO': '3787', 'NSE:ATGL': '25152',
            # Correct index tokens for Angel One
            'BSE:SENSEX': '99919000',
            'NSE:INDIAVIX': '99926017',  # Fixed: was INDIA_VIX
            'NSE:NIFTY': '99926000',     # Fixed: correct token
            'NSE:BANKNIFTY': '99926009'  # Fixed: correct token
        }
        _safe_print(f"[OK] Loaded {len(self.token_map)} fallback tokens")
        for key, token in self.token_map.items():
            if key.split(':')[1] in ["SENSEX", "INDIAVIX", "NIFTY", "BANKNIFTY"]:
                _safe_print(f"[DEBUG] Fallback token for {key}: {token}")
    def connect_paper_sandbox(self):
        """Connect in Paper Trading Sandbox mode without requiring live Angel One credentials"""
        self.ensure_tokens_loaded()
        self.is_connected = True
        self.is_paper_sandbox = True
        self.websocket_connected = True
        _safe_print("🟢 Connected to Paper Trading Sandbox Mode")
        return True

    def connect_broker(self, smart_api_instance=None):
        """Connect to Angel One broker and start WebSocket"""
        self.is_paper_sandbox = False

        if smart_api_instance:
            self.smart_api = smart_api_instance
            self.is_connected = True
            _safe_print("[OK] Broker API connected")
            return True
        
        if not SMARTAPI_AVAILABLE:
            _safe_print("[WARN] SmartApi library not available")
            return False
        
        try:
            # Ensure tokens are loaded before connecting
            self.ensure_tokens_loaded()
            
            _safe_print(f"[DEBUG] Token for BSE:SENSEX: {self.token_map.get('BSE:SENSEX')}")
            _safe_print(f"[DEBUG] Token for NSE:INDIAVIX: {self.token_map.get('NSE:INDIAVIX')}")
            
            # Get credentials - try encrypted storage first, then config.json
            self.api_key = self.config.get('api_key', '')
            self.client_code = self.config.get('client_id', '')
            password = self.config.get('password', '')
            totp_secret = self.config.get('totp_token', '')

            # If password/totp missing, try loading from encrypted storage
            if not password or not totp_secret:
                try:
                    from config.credentials_manager import SecureCredentialsManager
                    cred_mgr = SecureCredentialsManager()
                    success, creds = cred_mgr.load_credentials()

                    if success and creds:
                        _safe_print("[OK] Loaded credentials from encrypted storage")
                        # Use encrypted credentials (override config.json)
                        self.api_key = creds.get('api_key', self.api_key)
                        self.client_code = creds.get('client_code', self.client_code)
                        password = creds.get('password', password)
                        totp_secret = creds.get('totp_secret', totp_secret)
                    else:
                        _safe_print("[WARN] Could not load encrypted credentials")
                except Exception as e:
                    _safe_print(f"[WARN] Encrypted credentials unavailable: {e}")

            if not all([self.api_key, self.client_code, password]):
                _safe_print("[WARN] Missing credentials (need API Key, Client Code, and Password)")
                return False
            
            # Create SmartConnect instance
            self.smart_api = SmartConnect(api_key=self.api_key)
            
            # Generate TOTP
            if PYOTP_AVAILABLE and totp_secret:
                totp = pyotp.TOTP(totp_secret).now()
                _safe_print("[OK] Generated TOTP for Angel session")
            else:
                totp = totp_secret
                _safe_print("[WARN] Using static TOTP (install pyotp for auto-generation)")
            
            # Generate session
            data = self.smart_api.generateSession(self.client_code, password, totp)
            
            if not data or not data.get('status'):
                error_msg = data.get('message', 'Unknown authentication error') if data else 'No response from Angel One server'
                self.last_connection_error = error_msg
                _safe_print(f"[WARN] Failed to authenticate: {error_msg}")
                return False

            self.last_connection_error = None

            
            # Store tokens
            self.auth_token = data['data']['jwtToken']
            self.feed_token = self.smart_api.getfeedToken()
            self.is_connected = True
            
            _safe_print("[OK] Connected to Angel One broker")
            _safe_print(f"[OK] Feed Token: {self.feed_token[:20] if self.feed_token else 'N/A'}...")
            
            # Start WebSocket in separate thread
            self.start_websocket()
            
            return True
            
        except ImportError as e:
            _safe_print(f"[WARN] SmartApi library not installed: {e}")
            return False
        except Exception as e:
            _safe_print(f"[WARN] Connection error: {e}")
            return False
    
    def subscribe_initial_symbols(self, symbols_with_exchange):
        """
        Subscribe to a list of symbols (e.g., ticker symbols) after WebSocket is connected.
        This is called from the UI after successful broker connection.
        `symbols_with_exchange` should be a list of tuples: [(symbol, exchange), (symbol, exchange, token), ...]
        """
        if self.websocket_connected:
            # Prepare symbols for subscription, prioritizing provided tokens
            symbols_to_subscribe = []
            for item in symbols_with_exchange:
                if len(item) == 3: # (symbol, exchange, token)
                    symbol, exchange, token = item
                    symbols_to_subscribe.append((symbol, exchange, token))
                else: # (symbol, exchange)
                    symbol, exchange = item
                    symbols_to_subscribe.append((symbol, exchange))
            
            self.subscribe_symbols(symbols_to_subscribe)
        else:
            _safe_print("⚠️  WebSocket not connected yet, cannot subscribe initial symbols.")

    def start_websocket(self):
        """Start WebSocket in separate thread - PREVENTS UI FREEZING!"""
        if not all([self.auth_token, self.feed_token, self.api_key, self.client_code]):
            _safe_print("[WARN] Missing WebSocket credentials")
            return False
        
        if not SMARTAPI_AVAILABLE:
            _safe_print("[WARN] SmartApi library not available for WebSocket")
            return False
        
        try:
            # Create WebSocket instance
            self.websocket = SmartWebSocketV2(
                auth_token=self.auth_token,
                api_key=self.api_key,
                client_code=self.client_code,
                feed_token=self.feed_token
            )
            
            # Set callbacks
            self.websocket.on_open = self._on_ws_open
            self.websocket.on_data = self._on_ws_data
            self.websocket.on_error = self._on_ws_error
            self.websocket.on_close = self._on_ws_close
            
            # CRITICAL: Start WebSocket in separate thread (prevents freezing!)
            ws_thread = threading.Thread(target=self.websocket.connect, daemon=True)
            ws_thread.start()
            
            _safe_print("[OK] WebSocket started in background thread")
            return True
            
        except Exception as e:
            _safe_print(f"[WARN] WebSocket startup error: {e}")
            return False
    
    def _on_ws_open(self, wsapp):
        """WebSocket opened - subscribe to stocks"""
        _safe_print("[OK] WebSocket connected")
        self.websocket_connected = True
        
        # Subscribe to watchlist + index symbols (indices often need explicit subscribe)
        watchlist_with_exchange = [(symbol, "NSE") for symbol in self.stock_list]
        index_pairs = [("NIFTY", "NSE"), ("BANKNIFTY", "NSE"), ("INDIAVIX", "NSE"), ("SENSEX", "BSE")]
        self.subscribe_symbols(watchlist_with_exchange + index_pairs)
    
    def _on_ws_data(self, wsapp, message):
        """WebSocket data received - update LTP cache (runs in background thread)"""
        try:
            # print(f"ℹ️  [DEBUG] WebSocket data received: {message}") # This can be very noisy
            # Message is already parsed by SmartWebSocketV2
            if isinstance(message, dict):
                token = str(message.get('token', ''))
                ltp = message.get('last_traded_price', 0)
                
                if token and ltp:
                    symbol = self.token_to_symbol_map.get(token) # Use reverse map
                    if symbol:
                        if symbol in ["NIFTY", "BANKNIFTY", "SENSEX", "INDIAVIX"]: # NEW DEBUG PRINT
                            _safe_print(f"ℹ️  [DEBUG] WebSocket data for {symbol}: {ltp / 100.0}")
                        
                        # Update LTP cache (thread-safe)
                        with self.ltp_lock:
                            self.ltp_data[symbol] = {
                                'ltp': ltp / 100.0,  # Angel One sends price * 100
                                'timestamp': time.time(),
                                'token': token
                            }
                        # print(f"ℹ️  [DEBUG] Updated LTP for {symbol}: {self.ltp_data[symbol]['ltp']}")
        except Exception as e:
            _safe_print(f"⚠️  [DEBUG] Error in _on_ws_data: {e}")
    
    def _on_ws_error(self, wsapp, error):
        """WebSocket error"""
        _safe_print(f"⚠️  WebSocket error: {error}")
    
    def _on_ws_close(self, wsapp):
        """WebSocket closed"""
        _safe_print("🔌 WebSocket disconnected")
        self.websocket_connected = False
    
    def subscribe_symbols(self, symbols_with_exchange):
        """
        Subscribe to symbols on WebSocket.
        `symbols_with_exchange` should be a list of tuples: [(symbol, exchange), ...]
        """
        if not self.websocket or not self.websocket_connected:
            _safe_print("⚠️  [DEBUG] WebSocket not connected, cannot subscribe")
            return False
        
        self.ensure_tokens_loaded()
        
        _safe_print(f"ℹ️  [DEBUG] Attempting to subscribe to: {symbols_with_exchange}")

        # Group tokens by exchange type
        tokens_by_exchange = {}
        
        for item in symbols_with_exchange:
            if len(item) == 3: # (symbol, exchange, token)
                symbol, exchange, token = item
                exchange_upper = exchange.upper()
                key = f"{exchange_upper}:{symbol.upper()}"
                self.token_map[key] = token # Add to token_map for consistency
            else: # (symbol, exchange)
                symbol, exchange = item
                exchange_upper = exchange.upper()
                key = f"{exchange_upper}:{symbol.upper()}"
                token = self.token_map.get(key)
            
            _safe_print(f"ℹ️  [DEBUG] Symbol: {symbol}, Exchange: {exchange}, Key: {key}, Token: {token}")

            if token:
                # Special handling for indices - NSE indices use NFO exchange type for WebSocket
                symbol_upper = symbol.upper()
                if symbol_upper in ["NIFTY", "BANKNIFTY", "NIFTY50", "FINNIFTY", "MIDCPNIFTY", "INDIAVIX"]:
                    exchange_type = 2  # NFO for NSE indices
                    _safe_print(f"ℹ️  [DEBUG] Using NFO exchange type (2) for NSE index {symbol_upper}")
                elif exchange_upper == "NSE":
                    exchange_type = 1
                elif exchange_upper == "NFO":
                    exchange_type = 2
                elif exchange_upper == "BSE":
                    exchange_type = 4  # BSE indices use BSE exchange type
                else:
                    _safe_print(f"⚠️  [DEBUG] Unsupported exchange: {exchange_upper}")
                    continue # Skip unsupported exchanges

                if exchange_type not in tokens_by_exchange:
                    tokens_by_exchange[exchange_type] = []
                tokens_by_exchange[exchange_type].append(token)

        if not tokens_by_exchange:
            _safe_print("⚠️  [DEBUG] No valid tokens found for subscription")
            return False
            
        correlation_id = "ltp_subscription"
        mode = 1  # LTP_MODE

        for exchange_type, tokens in tokens_by_exchange.items():
            token_data = [{"exchangeType": exchange_type, "tokens": tokens}]
            _safe_print(f"ℹ️  [DEBUG] Subscribing with token_data: {token_data}") # NEW DEBUG PRINT
            try:
                _safe_print(f"ℹ️  [DEBUG] Subscribing to exchange {exchange_type} with tokens: {tokens}")
                self.websocket.subscribe(correlation_id, mode, token_data)
                _safe_print(f"✅ Subscribed to {len(tokens)} symbols on exchange type {exchange_type}")
            except Exception as e:
                _safe_print(f"⚠️  [DEBUG] Subscription error for exchange type {exchange_type}: {e}")

        return True

    def connect_analyzer(self, analyzer_instance=None):
        """Connect analyzer module"""
        if analyzer_instance:
            self.analyzer = analyzer_instance
            _safe_print("✅ Analyzer connected")
            return True
        else:
            try:
                from analyzer import StockAnalyzer
                self.analyzer = StockAnalyzer()
                _safe_print("✅ Analyzer module loaded")
                return True
            except ImportError:
                _safe_print("⚠️  Analyzer module not found")
                return False
    
    def get_ltp(self, symbol, exchange="NSE"):
        """Get Last Traded Price from WebSocket cache or simulated fallback"""
        symbol_upper = symbol.upper()
        
        # Get from WebSocket cache (thread-safe)
        with self.ltp_lock:
            if symbol_upper in self.ltp_data:
                data = self.ltp_data[symbol_upper]
                if time.time() - data['timestamp'] < 30:
                    return data['ltp']
        
        # Fallback to simulated LTP in Paper Sandbox mode or offline
        try:
            df = self._generate_simulated_historical(symbol_upper, period_days=1)
            if not df.empty and 'close' in df:
                return float(df['close'].iloc[-1])
        except Exception:
            pass

        base_prices = {
            'RELIANCE': 2500.0, 'TCS': 3600.0, 'INFY': 1500.0, 'HDFCBANK': 1600.0,
            'ICICIBANK': 1000.0, 'SBIN': 600.0, 'BHARTIARTL': 1200.0, 'LT': 3400.0
        }
        return base_prices.get(symbol_upper, 1000.0)

    
    def get_ltp_batch(self, symbols_with_exchange):
        """
        Get LTP for multiple symbols from WebSocket cache.
        `symbols_with_exchange` should be a list of tuples: [(symbol, exchange), (symbol, exchange, token), ...]
        """
        results = {}
        
        with self.ltp_lock:
            for item in symbols_with_exchange:
                if len(item) == 3: # (symbol, exchange, token)
                    symbol, exchange, token = item
                    symbol_upper = symbol.upper()
                    # If token is provided, we can directly use it to find the symbol in ltp_data
                    # This assumes ltp_data keys are just symbols, not EXCH:SYMBOL
                    # We need to ensure _on_ws_data populates ltp_data with just the symbol
                    # For now, we'll rely on the symbol_upper as the key
                    if symbol_upper in self.ltp_data:
                        results[symbol] = self.ltp_data[symbol_upper]['ltp']
                    else:
                        results[symbol] = None
                else: # (symbol, exchange)
                    symbol, exchange = item
                    symbol_upper = symbol.upper()
                    if symbol_upper in self.ltp_data:
                        results[symbol] = self.ltp_data[symbol_upper]['ltp']
                    else:
                        results[symbol] = None

        _safe_print(f"ℹ️  [DEBUG] get_ltp_batch results: {results}")
        return results
    
    def get_holdings(self):
        """Get broker holdings"""
        if not self.smart_api or not self.is_connected:
            return self._get_demo_holdings()
        
        try:
            resp = self.smart_api.holding()
            if resp and resp.get('status'):
                return resp.get('data', [])
            else:
                return self._get_demo_holdings()
        except Exception as e:
            _safe_print(f"⚠️  Error fetching holdings: {e}")
            return self._get_demo_holdings()
    
    def get_positions(self):
        """Get active positions"""
        if not self.smart_api or not self.is_connected:
            return []
        
        try:
            resp = self.smart_api.position()
            if resp and resp.get('status'):
                return resp.get('data', [])
            else:
                return []
        except Exception as e:
            _safe_print(f"⚠️  Error fetching positions: {e}")
            return []
    
    def get_funds(self):
        """Get available funds"""
        if not self.smart_api or not self.is_connected:
            return {'cash': 0, 'margin': 0}
        
        try:
            resp = self.smart_api.rmsLimit()
            if resp and resp.get('status'):
                data = resp.get('data', {})
                return {
                    'cash': float(data.get('availablecash', 0)),
                    'margin': float(data.get('utiliseddebitmoney', 0))
                }
            else:
                return {'cash': 0, 'margin': 0}
        except Exception as e:
            _safe_print(f"⚠️  Error fetching funds: {e}")
            return {'cash': 0, 'margin': 0}
    def get_historical(self, symbol, exchange="NSE", interval="ONE_MINUTE", period_days=5):
        """
        Get historical candle data for technical analysis
        
        Args:
            symbol: Stock symbol (e.g., 'RELIANCE')
            exchange: Exchange name (default: 'NSE')
            interval: Candle interval - ONE_MINUTE, THREE_MINUTE, FIVE_MINUTE, 
                     TEN_MINUTE, FIFTEEN_MINUTE, THIRTY_MINUTE, ONE_HOUR, ONE_DAY
            period_days: Number of days of history to fetch (default: 5)
        
        Returns:
            pandas.DataFrame with columns: timestamp, open, high, low, close, volume
        """
        import pandas as pd
        from datetime import datetime, timedelta
        
        if not self.smart_api or not self.is_connected:
            return self._generate_simulated_historical(symbol, period_days)

        
        try:
            # Ensure tokens are loaded
            self.ensure_tokens_loaded()
            
            # Get token for symbol
            key = f"{exchange}:{symbol.upper()}"
            token = self.token_map.get(key)
            
            if not token:
                _safe_print(f"⚠️  Token not found for {key}")
                return pd.DataFrame()
            
            # Calculate date range
            to_date = datetime.now()
            from_date = to_date - timedelta(days=period_days)
            
            # Format dates for Angel One API
            from_date_str = from_date.strftime("%Y-%m-%d %H:%M")
            to_date_str = to_date.strftime("%Y-%m-%d %H:%M")
            
            # Fetch historical data from Angel One
            historic_param = {
                "exchange": exchange,
                "symboltoken": token,
                "interval": interval,
                "fromdate": from_date_str,
                "todate": to_date_str
            }
            
            response = self.smart_api.getCandleData(historic_param)
            
            if not response or not response.get('status'):
                error_msg = response.get('message', 'Unknown error') if response else 'No response'
                _safe_print(f"⚠️  Failed to fetch historical data for {symbol}: {error_msg}")
                return pd.DataFrame()
            
            # Parse candle data
            candles = response.get('data', [])
            
            if not candles:
                _safe_print(f"⚠️  No historical data returned for {symbol}")
                return pd.DataFrame()
            
            # Convert to DataFrame
            df = pd.DataFrame(candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            
            # Convert timestamp to datetime
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            
            # Convert price columns to float
            for col in ['open', 'high', 'low', 'close']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            
            df['volume'] = pd.to_numeric(df['volume'], errors='coerce')
            
            return df
            
        except Exception as e:
            _safe_print(f"⚠️  Error fetching historical data for {symbol}: {e}")
            return self._generate_simulated_historical(symbol, period_days)

    def _generate_simulated_historical(self, symbol, period_days=5):
        """Generate realistic simulated OHLCV candle data for technical analysis in Paper Sandbox mode"""
        import pandas as pd
        import numpy as np
        from datetime import datetime, timedelta

        seed = sum(ord(c) for c in symbol)
        np.random.seed(seed)

        base_prices = {
            'RELIANCE': 2500.0, 'TCS': 3600.0, 'INFY': 1500.0, 'HDFCBANK': 1600.0,
            'ICICIBANK': 1000.0, 'SBIN': 600.0, 'BHARTIARTL': 1200.0, 'LT': 3400.0,
            'NIFTY': 22000.0, 'BANKNIFTY': 48000.0, 'SENSEX': 72000.0, 'TITAN': 3200.0
        }
        base_price = base_prices.get(symbol.upper(), 1000.0)

        num_candles = max(50, period_days * 5)
        now = datetime.now()
        timestamps = [now - timedelta(hours=i) for i in range(num_candles, 0, -1)]

        returns = np.random.normal(0.0005, 0.012, num_candles)
        price_series = base_price * np.cumprod(1 + returns)

        opens = price_series * (1 + np.random.normal(0, 0.002, num_candles))
        closes = price_series
        highs = np.maximum(opens, closes) * (1 + np.abs(np.random.normal(0, 0.005, num_candles)))
        lows = np.minimum(opens, closes) * (1 - np.abs(np.random.normal(0, 0.005, num_candles)))
        volumes = np.random.randint(50000, 500000, num_candles)

        df = pd.DataFrame({
            'timestamp': timestamps,
            'open': opens,
            'high': highs,
            'low': lows,
            'close': closes,
            'volume': volumes
        })
        return df

    def get_stock_list(self):

        """Get list of stocks to monitor"""
        return self.stock_list.copy()
    
    def _get_demo_holdings(self):
        """Return demo holdings when not connected"""
        return [
            {
                'tradingsymbol': 'INFY',
                'quantity': 10,
                'averageprice': 1500,
                'ltp': 1520,
                'pnl': 200,
                'daychange': 1.33
            },
            {
                'tradingsymbol': 'TCS',
                'quantity': 5,
                'averageprice': 3650,
                'ltp': 3680,
                'pnl': 150,
                'daychange': 0.82
            }
        ]
    
    def get_connection_status(self):
        """Get connection status for UI display"""
        is_paper = getattr(self, 'is_paper_sandbox', False)
        if self.is_connected:
            status_text = '[OK] Paper Sandbox Connected' if is_paper else '[OK] Live Broker Connected'
        else:
            status_text = '[OFF] Broker Disconnected'
            
        return {
            'broker_connected': self.is_connected,
            'websocket_connected': self.websocket_connected,
            'analyzer_connected': self.analyzer is not None,
            'is_paper_sandbox': is_paper,
            'status_text': status_text,
        }

    
    def update_config(self, new_config):
        """Update configuration"""
        self.config.update(new_config)
        
        config_file = "config.json"
        try:
            with open(config_file, 'w') as f:
                json.dump(self.config, f, indent=4)
            _safe_print(f"✅ Config saved to {config_file}")
            return True
        except Exception as e:
            _safe_print(f"⚠️  Could not save config: {e}")
            return False
    
    def close(self):
        """Clean shutdown"""
        if self.websocket:
            try:
                self.websocket.close_connection()
            except:
                pass
        
        self.websocket_connected = False
        self.is_connected = False
        _safe_print("✅ Connection closed cleanly")

# Global singleton instance
_connection_manager = None

def get_connection_manager():
    """Get global connection manager instance"""
    global _connection_manager
    if _connection_manager is None:
        _connection_manager = ConnectionManager()
    return _connection_manager