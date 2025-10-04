# data_provider/angel_provider.py - FIXED: JWT Token + Token Map Issues
import pyotp
import logging
from datetime import datetime, time, timedelta
import json
import os
from typing import Dict, List, Tuple, Optional, Any
import time as time_module
import pandas as pd
import numpy as np

try:
    from SmartApi import SmartConnect
except ImportError:
    logging.warning("SmartApi not installed. Install with: pip install smartapi-python")
    SmartConnect = None

from config.credentials_manager import SecureCredentialsManager

logger = logging.getLogger("AngelProvider")


class AngelProvider:
    def __init__(self, paper_mode: bool = True):
        self.smart_api = None
        self.credentials_manager = SecureCredentialsManager()
        self.paper_mode = paper_mode
        self.api_key = None
        self.client_code = None
        self.password = None
        self.totp_secret = None
        self.auth_token = None
        self.refresh_token = None
        self.feed_token = None
        self.is_connected = False
        self.last_login_time = None
        self.last_request_time = 0
        self.min_request_interval = 0.1
        self.token_expiry = None
        
        # Load token map at initialization
        self.token_map = self._load_token_map()
        
        # Fallback prices only when API is unavailable
        self._fallback_prices = {
            'RELIANCE': 2895.00, 'TCS': 4012.00, 'HDFCBANK': 1648.00,
            'INFY': 1867.00, 'ICICIBANK': 1296.00, 'SBIN': 836.00,
            'CASTROLIND': 189.00, 'BPCL': 1000.00, 'NIFTY': 25235.00, 'SENSEX': 82456.00
        }
        
        self._load_saved_credentials()
        logger.info(f"Angel One provider initialized (paper_mode={paper_mode})")

    def _load_token_map(self) -> dict:
        """Load token mapping from file at initialization"""
        try:
            token_file = 'data/angel_tokens_map.json'
            if not os.path.exists(token_file):
                logger.warning(f"Token file not found: {token_file}")
                return {}
            
            with open(token_file, 'r') as f:
                tokens = json.load(f)
            
            logger.info(f"✓ Loaded {len(tokens)} tokens from {token_file}")
            return tokens
        except Exception as e:
            logger.error(f"Error loading token map: {e}")
            return {}

    def _load_saved_credentials(self):
        success, credentials = self.credentials_manager.load_credentials()
        if success:
            self.api_key = credentials.get('api_key')
            self.client_code = credentials.get('client_code')
            self.password = credentials.get('password')
            self.totp_secret = credentials.get('totp_secret')
            if self.api_key and SmartConnect:
                self.smart_api = SmartConnect(api_key=self.api_key)
                logger.info("Credentials loaded - ready for login")
            else:
                logger.warning("SmartConnect not available")

    def set_credentials(self, api_key: str, client_code: str, password: str, totp_secret: str, save_credentials: bool = True) -> Tuple[bool, str]:
        if not all([api_key, client_code, password, totp_secret]):
            return False, "All fields required"
        self.api_key = api_key.strip()
        self.client_code = client_code.strip()
        self.password = password.strip()
        self.totp_secret = totp_secret.strip()
        if SmartConnect:
            self.smart_api = SmartConnect(api_key=self.api_key)
            if save_credentials:
                self.credentials_manager.save_credentials(self.api_key, self.client_code, self.password, self.totp_secret)
            logger.info("Credentials set")
            return True, "Credentials set"
        return False, "SmartConnect not available"

    def generate_totp(self) -> Optional[str]:
        if not self.totp_secret:
            return None
        clean_secret = self.totp_secret.replace(" ", "").upper()
        totp = pyotp.TOTP(clean_secret)
        return totp.now()

    def login(self) -> Tuple[bool, str]:
        """FIXED: Proper JWT token storage and session management"""
        if not self.smart_api:
            return False, "Not initialized"
        totp_value = self.generate_totp()
        if not totp_value:
            return False, "TOTP failed"
        try:
            data = self.smart_api.generateSession(self.client_code, self.password, totp_value)
            if data['status']:
                # CRITICAL FIX: Store JWT token properly
                self.auth_token = data['data']['jwtToken']
                self.refresh_token = data['data']['refreshToken']
                self.feed_token = self.smart_api.getfeedToken()
                self.is_connected = True
                self.last_login_time = datetime.now()
                self.token_expiry = datetime.now() + timedelta(hours=6)
                
                logger.info("✓ Successfully logged in to Angel One - JWT token stored")
                logger.info("✓ Now fetching REAL market data")
                return True, "Logged in"
            return False, data.get('message', 'Login failed')
        except Exception as e:
            logger.error(f"Login error: {e}")
            return False, f"Login error: {str(e)}"

    def _check_token_validity(self):
        """Check if token needs refresh"""
        if self.token_expiry and self.is_connected:
            # Refresh 5 minutes before expiry
            if datetime.now() >= self.token_expiry - timedelta(minutes=5):
                logger.info("Token nearing expiry, refreshing...")
                self._refresh_token()

    def _refresh_token(self):
        """Refresh JWT token"""
        try:
            if not self.refresh_token:
                logger.warning("No refresh token, re-logging...")
                return self.login()
            
            data = self.smart_api.generateToken(self.refresh_token)
            if data.get('status'):
                self.auth_token = data['data']['jwtToken']
                self.refresh_token = data['data']['refreshToken']
                self.token_expiry = datetime.now() + timedelta(hours=6)
                logger.info("✓ Token refreshed successfully")
                return True
            else:
                logger.error(f"Token refresh failed: {data.get('message')}")
                return self.login()  # Re-login if refresh fails
        except Exception as e:
            logger.error(f"Token refresh error: {e}")
            return self.login()

    def logout(self) -> Tuple[bool, str]:
        if self.smart_api and self.auth_token:
            try:
                self.smart_api.terminateSession(self.client_code)
            except Exception as e:
                logger.error(f"Logout error: {e}")
        self.is_connected = False
        self.auth_token = None
        self.refresh_token = None
        return True, "Logged out"

    def get_token(self, symbol, exchange='NSE'):
        """FIXED: Get token from pre-loaded map"""
        key = f"{exchange}:{symbol}"
        token = self.token_map.get(key)
        
        if not token:
            # Try without exchange prefix
            token = self.token_map.get(symbol)
        
        if token:
            return str(token)
        else:
            logger.warning(f"Token not found for {key}")
            return None

    def get_ltp(self, symbol, exchange='NSE'):
        """
        FIXED: Get REAL Last Traded Price with proper token validation
        """
        # Check token validity before making API call
        self._check_token_validity()
        
        if self.is_connected:
            try:
                token = self.get_token(symbol, exchange)
                if not token:
                    logger.warning(f"Token not found for {symbol}, using fallback")
                    return self._fallback_prices.get(symbol, 1000.00)
                
                # FIXED: Fetch REAL LTP with proper error handling
                data = self.smart_api.ltpData(exchange, symbol, token)
                
                if data.get('status'):
                    ltp = float(data['data']['ltp'])
                    logger.info(f"✓ REAL LTP for {symbol}: ₹{ltp:.2f}")
                    return ltp
                else:
                    error_msg = data.get('message', 'Unknown error')
                    logger.error(f"LTP API error for {symbol}: {error_msg}")
                    
                    # If invalid token error, try to refresh
                    if 'Invalid Token' in error_msg or 'AG8001' in error_msg:
                        logger.warning("Invalid token detected, refreshing...")
                        if self._refresh_token():
                            # Retry after refresh
                            data = self.smart_api.ltpData(exchange, symbol, token)
                            if data.get('status'):
                                ltp = float(data['data']['ltp'])
                                logger.info(f"✓ REAL LTP for {symbol} (after refresh): ₹{ltp:.2f}")
                                return ltp
                    
                    # Fallback if still failing
                    fallback_price = self._fallback_prices.get(symbol, 1000.00)
                    logger.warning(f"Using fallback price for {symbol}: ₹{fallback_price:.2f}")
                    return fallback_price
                    
            except Exception as e:
                logger.error(f"Error getting LTP for {symbol}: {e}")
        
        # Fallback only when not connected
        fallback_price = self._fallback_prices.get(symbol, 1000.00)
        logger.warning(f"API unavailable - Using fallback price for {symbol}: ₹{fallback_price:.2f}")
        return fallback_price

    def get_historical(self, symbol, exchange='NSE', interval='ONE_MINUTE', period_days=50):
        """Get historical data - REAL data if connected, fallback if not"""
        self._check_token_validity()
        
        if self.is_connected:
            try:
                token = self.get_token(symbol, exchange)
                if not token:
                    logger.warning(f"Token not found for {symbol}, using fallback data")
                    return self._generate_fallback_historical(symbol, period_days)
                
                fromdate = (datetime.now() - timedelta(days=period_days)).strftime('%Y-%m-%d %H:%M')
                todate = datetime.now().strftime('%Y-%m-%d %H:%M')
                params = {
                    'exchange': exchange,
                    'symboltoken': token,
                    'interval': interval,
                    'fromdate': fromdate,
                    'todate': todate
                }
                data = self.smart_api.getCandleData(params)
                if data.get('status'):
                    df = pd.DataFrame(data['data'], columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                    df['timestamp'] = pd.to_datetime(df['timestamp'])
                    df.set_index('timestamp', inplace=True)
                    logger.info(f"✓ Fetched REAL historical data for {symbol}")
                    return df
                logger.warning(f"Failed to get historical data: {data.get('message')}")
            except Exception as e:
                logger.error(f"Error getting historical data: {e}")
        
        # Fallback only when API unavailable
        logger.warning(f"Using fallback historical data for {symbol}")
        return self._generate_fallback_historical(symbol, period_days)

    def _generate_fallback_historical(self, symbol, period_days):
        """Generate fallback data only when API is unavailable"""
        base_price = self._fallback_prices.get(symbol, 1000.00)
        dates = pd.date_range(end=datetime.now(), periods=period_days * 375, freq='1min')
        returns = np.random.randn(len(dates)) * 0.001
        price_series = base_price * (1 + returns).cumprod()
        
        df = pd.DataFrame({
            'timestamp': dates,
            'open': price_series,
            'high': price_series * 1.001,
            'low': price_series * 0.999,
            'close': price_series,
            'volume': np.random.uniform(10000, 100000, len(dates))
        })
        df.set_index('timestamp', inplace=True)
        return df

    def get_holdings(self):
        """Fetch holdings from broker"""
        if self.paper_mode or not self.is_connected:
            return {'holdings': [], 'total_value': 0}
        
        self._check_token_validity()
        try:
            data = self.smart_api.holding()
            if data.get('status'):
                holdings = data['data']
                total_value = sum([float(h.get('pnl', 0)) for h in holdings])
                return {
                    'holdings': holdings,
                    'total_value': round(total_value, 2)
                }
            logger.error(f"Failed to get holdings: {data.get('message')}")
            return {'holdings': [], 'total_value': 0}
        except Exception as e:
            logger.error(f"Error getting holdings: {e}")
            return {'holdings': [], 'total_value': 0}

    def get_funds(self):
        """Fetch available funds from broker"""
        if self.paper_mode or not self.is_connected:
            return 0.0
        
        self._check_token_validity()
        try:
            data = self.smart_api.rmsLimit()
            if data.get('status'):
                funds = data['data']
                available_cash = float(funds.get('availablecash', 0))
                return round(available_cash, 2)
            logger.error(f"Failed to get funds: {data.get('message')}")
            return 0.0
        except Exception as e:
            logger.error(f"Error getting funds: {e}")
            return 0.0

    def snapshot(self) -> dict:
        return {
            "provider": "Angel One (Paper Mode - REAL DATA)" if self.paper_mode else "Angel One (Live)",
            "paper_mode": self.paper_mode,
            "connected": self.is_connected,
            "data_source": "LIVE Angel One API" if self.is_connected else "Fallback prices",
            "server_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "client_code": self.client_code if self.client_code else "Not set",
            "tokens_loaded": len(self.token_map)
        }

    def account_name(self) -> str:
        if self.paper_mode:
            return "PaperAccount (Real Data)"
        return self.client_code if self.client_code else "LiveAccount"

    def is_market_open(self) -> bool:
        now = datetime.now()
        if now.weekday() >= 5:
            return False
        market_start = time(9, 15)
        market_end = time(15, 30)
        return market_start <= now.time() <= market_end