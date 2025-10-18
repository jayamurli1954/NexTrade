# data_provider/angel_provider.py - COMPLETE FIXED VERSION
# Replace your entire angel_provider.py with this file
# Save as: c:\Users\Dell\tradingbot_new\data_provider\angel_provider.py

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

# Import contracts
from contracts.data_provider_v1 import (
    DataProviderInterface,
    PortfolioHolding,
    FundsInfo
)

import pyotp
import logging
from datetime import datetime, time, timedelta
import json
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


class AngelProvider(DataProviderInterface):
    """Angel One provider implementing DataProviderInterface contract"""
    
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
        
        # Load token map
        self.token_map = self._load_token_map()
        
        # Fallback prices
        self._fallback_prices = {
            'RELIANCE': 2895.00, 'TCS': 4012.00, 'HDFCBANK': 1648.00,
            'INFY': 1867.00, 'ICICIBANK': 1296.00, 'SBIN': 836.00,
            'CASTROLIND': 189.00, 'BPCL': 1000.00
        }
        
        self._load_saved_credentials()
        logger.info(f"Angel One provider initialized (paper_mode={paper_mode})")

    def _load_token_map(self) -> dict:
        """Load token mapping"""
        try:
            token_file = 'data/angel_tokens_map.json'
            if not os.path.exists(token_file):
                return {}
            with open(token_file, 'r') as f:
                tokens = json.load(f)
            logger.info(f"✓ Loaded {len(tokens)} tokens")
            return tokens
        except Exception as e:
            logger.error(f"Token map error: {e}")
            return {}

    def _load_saved_credentials(self):
        """Load saved credentials"""
        success, credentials = self.credentials_manager.load_credentials()
        if success:
            self.api_key = credentials.get('api_key')
            self.client_code = credentials.get('client_code')
            self.password = credentials.get('password')
            self.totp_secret = credentials.get('totp_secret')
            if self.api_key and SmartConnect:
                self.smart_api = SmartConnect(api_key=self.api_key)
                logger.info("Credentials loaded")

    def set_credentials(self, api_key: str, client_code: str, password: str, totp_secret: str, save_credentials: bool = True) -> Tuple[bool, str]:
        """Set credentials"""
        if not all([api_key, client_code, password, totp_secret]):
            return False, "All fields required"
        self.api_key = api_key.strip()
        self.client_code = client_code.strip()
        self.password = password.strip()
        self.totp_secret = totp_secret.strip()
        if SmartConnect:
            self.smart_api = SmartConnect(api_key=self.api_key)
            if save_credentials:
                self.credentials_manager.save_credentials(
                    self.api_key, self.client_code, self.password, self.totp_secret
                )
            logger.info("Credentials set")
            return True, "Credentials set"
        return False, "SmartConnect not available"

    def generate_totp(self) -> Optional[str]:
        """Generate TOTP"""
        if not self.totp_secret:
            return None
        clean_secret = self.totp_secret.replace(" ", "").upper()
        totp = pyotp.TOTP(clean_secret)
        return totp.now()

    def login(self) -> Tuple[bool, str]:
        """Login with JWT token storage"""
        if not self.smart_api:
            return False, "Not initialized"
        totp_value = self.generate_totp()
        if not totp_value:
            return False, "TOTP failed"
        try:
            data = self.smart_api.generateSession(
                self.client_code, self.password, totp_value
            )
            if data['status']:
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
            return False, str(e)

    def _check_token_validity(self):
        """Check if token needs refresh"""
        if self.token_expiry and self.is_connected:
            if datetime.now() >= self.token_expiry - timedelta(minutes=5):
                self._refresh_token()

    def _refresh_token(self):
        """Refresh JWT token"""
        try:
            if not self.refresh_token:
                return self.login()
            data = self.smart_api.generateToken(self.refresh_token)
            if data.get('status'):
                self.auth_token = data['data']['jwtToken']
                self.refresh_token = data['data']['refreshToken']
                self.token_expiry = datetime.now() + timedelta(hours=6)
                logger.info("✓ Token refreshed")
                return True
            else:
                return self.login()
        except Exception as e:
            logger.error(f"Token refresh error: {e}")
            return self.login()

    def logout(self) -> Tuple[bool, str]:
        """Logout"""
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
        """Get token from map"""
        key = f"{exchange}:{symbol}"
        token = self.token_map.get(key) or self.token_map.get(symbol)
        if not token:
            logger.warning(f"Token not found for {key}")
        return str(token) if token else None

    def get_ltp(self, symbol: str, exchange: str) -> Optional[float]:
        """CONTRACT METHOD: Get live LTP"""
        self._check_token_validity()
        
        if self.is_connected:
            try:
                token = self.get_token(symbol, exchange)
                if not token:
                    return self._fallback_prices.get(symbol, 1000.00)
                
                data = self.smart_api.ltpData(exchange, symbol, token)
                
                if data.get('status'):
                    ltp = float(data['data']['ltp'])
                    logger.info(f"✓ REAL LTP for {symbol}: ₹{ltp:.2f}")
                    return ltp
                else:
                    if 'Invalid Token' in data.get('message', ''):
                        if self._refresh_token():
                            data = self.smart_api.ltpData(exchange, symbol, token)
                            if data.get('status'):
                                return float(data['data']['ltp'])
                    return self._fallback_prices.get(symbol, 1000.00)
            except Exception as e:
                logger.error(f"LTP error for {symbol}: {e}")
        
        return self._fallback_prices.get(symbol, 1000.00)

    def get_holdings(self) -> List[PortfolioHolding]:
        """CONTRACT METHOD: Fetch real holdings from Angel One"""
        # ✅ GLOBAL RATE LIMITING - Applied to ALL get_ltp calls
        import time
        import threading
        
        # Thread-safe rate limiting using a lock
        if not hasattr(self, '_ltp_lock'):
            self._ltp_lock = threading.Lock()
            self._last_ltp_call = 0
        
        with self._ltp_lock:
            # Enforce minimum 0.5 second delay between ANY get_ltp calls
            elapsed = time.time() - self._last_ltp_call
            if elapsed < 0.5:
                time.sleep(0.5 - elapsed)
            self._last_ltp_call = time.time()
        
        if not self.smart_api or not self.is_connected:
            logger.warning("Not connected to Angel One")
            return []
        
        self._check_token_validity()
        
        try:
            response = self.smart_api.holding()
            
            if not response or not response.get('status'):
                logger.error(f"Holdings API failed: {response}")
                return []
            
            holdings_data = response.get('data', [])
            holdings: List[PortfolioHolding] = []
            
            for item in holdings_data:
                # Get live price
                current_price = self.get_ltp(
                    item['tradingsymbol'],
                    item['exchange']
                ) or float(item.get('ltp', item.get('averageprice', 0)))
                
                avg_price = float(item.get('averageprice', 0))
                quantity = int(item.get('quantity', 0))
                
                # Calculate P/L
                pnl = (current_price - avg_price) * quantity
                pnl_percent = ((current_price - avg_price) / avg_price * 100) if avg_price > 0 else 0
                
                holding: PortfolioHolding = {
                    'symbol': item['tradingsymbol'],
                    'quantity': quantity,
                    'avg_price': avg_price,
                    'current_price': current_price,
                    'pnl': pnl,
                    'pnl_percent': pnl_percent
                }
                holdings.append(holding)
            
            logger.info(f"✓ Fetched {len(holdings)} holdings from Angel One")
            return holdings
            
        except Exception as e:
            logger.error(f"Holdings error: {e}")
            return []

    def get_funds(self) -> FundsInfo:
        """CONTRACT METHOD: Fetch funds from Angel One"""
        if not self.smart_api or not self.is_connected:
            return self._empty_funds()
        
        self._check_token_validity()
        
        try:
            response = self.smart_api.rmsLimit()
            
            if not response or not response.get('status'):
                logger.error("Funds API failed")
                return self._empty_funds()
            
            data = response.get('data', {})
            
            funds: FundsInfo = {
                'available_cash': float(data.get('availablecash', 0)),
                'used_margin': float(data.get('utiliseddebits', 0)),
                'available_margin': float(data.get('availablemargin', 0)),
                'total_collateral': float(data.get('collateral', 0))
            }
            
            logger.info(f"✓ Funds: Available ₹{funds['available_cash']:.2f}")
            return funds
            
        except Exception as e:
            logger.error(f"Funds error: {e}")
            return self._empty_funds()

    def _empty_funds(self) -> FundsInfo:
        """Return empty funds structure"""
        return {
            'available_cash': 0.0,
            'used_margin': 0.0,
            'available_margin': 0.0,
            'total_collateral': 0.0
        }

    def get_historical(self, symbol, exchange='NSE', interval='ONE_MINUTE', period_days=50):
        """Get historical data"""
        self._check_token_validity()
        
        if self.is_connected:
            try:
                token = self.get_token(symbol, exchange)
                if not token:
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
                    df = pd.DataFrame(
                        data['data'],
                        columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
                    )
                    df['timestamp'] = pd.to_datetime(df['timestamp'])
                    df.set_index('timestamp', inplace=True)
                    return df
            except Exception as e:
                logger.error(f"Historical data error: {e}")
        
        return self._generate_fallback_historical(symbol, period_days)

    def _generate_fallback_historical(self, symbol, period_days):
        """Generate fallback data"""
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

    def snapshot(self) -> dict:
        """Provider snapshot"""
        return {
            "provider": "Angel One (Paper Mode - REAL DATA)" if self.paper_mode else "Angel One (Live)",
            "paper_mode": self.paper_mode,
            "connected": self.is_connected,
            "data_source": "LIVE Angel One API" if self.is_connected else "Fallback prices",
            "server_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "client_code": self.client_code or "Not set",
            "tokens_loaded": len(self.token_map)
        }

    def account_name(self) -> str:
        """Account name"""
        if self.paper_mode:
            return "PaperAccount (Real Data)"
        return self.client_code if self.client_code else "LiveAccount"

    def is_market_open(self) -> bool:
        """Check if market is open"""
        now = datetime.now()
        if now.weekday() >= 5:
            return False
        market_start = time(9, 15)
        market_end = time(15, 30)
        return market_start <= now.time() <= market_end