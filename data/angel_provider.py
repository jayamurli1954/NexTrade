# data_provider/angel_provider.py
"""
Angel One API Data Provider with Secure Credentials Management
Handles authentication, data fetching, and order management
"""
import pyotp
import logging
from datetime import datetime, time
import json
import os
from typing import Dict, List, Tuple, Optional, Any
import time as time_module

try:
    from SmartApi import SmartConnect
except ImportError:
    print("Warning: SmartApi not installed. Install with: pip install smartapi-python")
    SmartConnect = None

from config.credentials_manager import SecureCredentialsManager

logger = logging.getLogger("AngelProvider")


class AngelProvider:
    """Angel One API provider with secure credentials management"""
    
    def __init__(self):
        """Initialize Angel One provider"""
        self.smart_api = None
        self.credentials_manager = SecureCredentialsManager()
        
        # Current session data
        self.api_key = None
        self.client_code = None
        self.password = None
        self.totp_secret = None
        
        # Session tokens
        self.auth_token = None
        self.refresh_token = None
        self.feed_token = None
        
        # Connection state
        self.is_connected = False
        self.last_login_time = None
        
        # Rate limiting
        self.last_request_time = 0
        self.min_request_interval = 0.1  # 100ms between requests
        
        # Auto-load saved credentials
        self._load_saved_credentials()
        
        logger.info("Angel One provider initialized")

    def _load_saved_credentials(self):
        """Load saved credentials automatically on startup"""
        try:
            success, credentials = self.credentials_manager.load_credentials()
            if success:
                self.api_key = credentials.get('api_key')
                self.client_code = credentials.get('client_code')
                self.password = credentials.get('password')
                self.totp_secret = credentials.get('totp_secret')
                
                # Initialize SmartConnect if credentials loaded
                if self.api_key and SmartConnect:
                    self.smart_api = SmartConnect(api_key=self.api_key)
                    logger.info("Credentials loaded automatically - ready for login")
                else:
                    logger.warning("SmartConnect not available")
            else:
                logger.info("No saved credentials found")
                
        except Exception as e:
            logger.exception(f"Auto-load credentials error: {e}")

    def set_credentials(self, api_key: str, client_code: str, password: str, totp_secret: str, 
                       save_credentials: bool = True) -> Tuple[bool, str]:
        """Set and optionally save API credentials"""
        try:
            # Validate inputs
            if not all([api_key, client_code, password, totp_secret]):
                return False, "All credential fields are required"
            
            # Set current session credentials
            self.api_key = api_key.strip()
            self.client_code = client_code.strip()
            self.password = password.strip()
            self.totp_secret = totp_secret.strip()
            
            # Initialize SmartConnect
            if SmartConnect:
                self.smart_api = SmartConnect(api_key=self.api_key)
                
                # Save credentials if requested
                if save_credentials:
                    save_success, save_message = self.credentials_manager.save_credentials(
                        self.api_key, self.client_code, self.password, self.totp_secret
                    )
                    if not save_success:
                        logger.warning(f"Credentials not saved: {save_message}")
                
                logger.info("Credentials set successfully")
                return True, "Credentials configured successfully"
            else:
                return False, "SmartConnect library not available"
                
        except Exception as e:
            logger.exception(f"Set credentials error: {e}")
            return False, f"Failed to set credentials: {str(e)}"

    def has_saved_credentials(self) -> bool:
        """Check if credentials are saved"""
        return self.credentials_manager.has_saved_credentials()

    def delete_saved_credentials(self) -> Tuple[bool, str]:
        """Delete saved credentials"""
        return self.credentials_manager.delete_credentials()

    def generate_totp(self) -> Optional[str]:
        """Generate TOTP from secret key"""
        try:
            if not self.totp_secret:
                logger.error("TOTP secret not configured")
                return None
            
            # Clean the secret key (remove spaces, make uppercase)
            clean_secret = self.totp_secret.replace(" ", "").upper()
            
            # Generate TOTP
            totp = pyotp.TOTP(clean_secret)
            totp_value = totp.now()
            
            logger.info(f"TOTP generated successfully: {totp_value}")
            return totp_value
            
        except Exception as e:
            logger.exception(f"TOTP generation error: {e}")
            return None

    def login(self) -> Tuple[bool, str]:
        """Login to Angel One API with multiple fallback attempts"""
        try:
            logger.info("Attempting to login to Angel One API")
            
            # Check if credentials are available
            if not all([self.api_key, self.client_code, self.password, self.totp_secret]):
                # Try to load saved credentials
                success, credentials = self.credentials_manager.load_credentials()
                if success:
                    self.api_key = credentials.get('api_key')
                    self.client_code = credentials.get('client_code')
                    self.password = credentials.get('password')
                    self.totp_secret = credentials.get('totp_secret')
                    
                    if self.api_key and SmartConnect:
                        self.smart_api = SmartConnect(api_key=self.api_key)
                else:
                    return False, "No credentials available. Please configure credentials first."
            
            # Validate prerequisites
            if not self.smart_api:
                return False, "SmartConnect not initialized. Set credentials first."
            
            if not all([self.client_code, self.password, self.totp_secret]):
                return False, "Missing required credentials (client_code, password, or totp_secret)"
            
            # Generate TOTP
            totp_value = self.generate_totp()
            if not totp_value:
                return False, "Failed to generate TOTP"
            
            logger.info(f"Using Client Code: {self.client_code}")
            logger.info(f"Generated TOTP: {totp_value}")
            
            # Try multiple API parameter variations
            login_attempts = [
                # Attempt 1: Try with clientCode (capital C)
                {
                    'params': {
                        'clientCode': self.client_code,
                        'password': self.password,
                        'totp': totp_value
                    },
                    'description': 'clientCode parameter'
                },
                # Attempt 2: Try with clientcode (lowercase)
                {
                    'params': {
                        'clientcode': self.client_code,
                        'password': self.password,
                        'totp': totp_value
                    },
                    'description': 'clientcode parameter'
                },
                # Attempt 3: Try with userId
                {
                    'params': {
                        'userId': self.client_code,
                        'password': self.password,
                        'totp': totp_value
                    },
                    'description': 'userId parameter'
                },
                # Attempt 4: Try with username
                {
                    'params': {
                        'username': self.client_code,
                        'password': self.password,
                        'totp': totp_value
                    },
                    'description': 'username parameter'
                },
                # Attempt 5: Try with only password and totp
                {
                    'params': {
                        'password': self.password,
                        'totp': totp_value
                    },
                    'description': 'password and totp only'
                }
            ]
            
            last_error = None
            
            for i, attempt in enumerate(login_attempts, 1):
                try:
                    logger.info(f"Login attempt {i}: Trying with {attempt['description']}")
                    
                    # Make the API call
                    data = self.smart_api.generateSession(**attempt['params'])
                    
                    # Check response
                    if data and data.get('status'):
                        # Success - extract tokens
                        token_data = data.get('data', {})
                        self.auth_token = token_data.get('jwtToken')
                        self.refresh_token = token_data.get('refreshToken')
                        self.feed_token = token_data.get('feedToken')
                        
                        if self.auth_token:
                            self.is_connected = True
                            self.last_login_time = datetime.now()
                            
                            logger.info(f"Login successful on attempt {i}")
                            logger.info(f"Auth Token: {self.auth_token[:20]}...")
                            logger.info(f"Refresh Token: {self.refresh_token[:20] if self.refresh_token else 'None'}...")
                            logger.info(f"Feed Token: {self.feed_token[:20] if self.feed_token else 'None'}...")
                            
                            return True, f"Login successful using {attempt['description']}"
                        else:
                            logger.warning(f"Attempt {i}: No auth token in response")
                            last_error = "No authentication token received"
                    else:
                        error_msg = data.get('message', 'Unknown error') if data else 'No response received'
                        logger.warning(f"Attempt {i}: API returned error: {error_msg}")
                        last_error = error_msg
                        
                except TypeError as e:
                    logger.info(f"Attempt {i}: Parameter error - {str(e)}")
                    last_error = f"Parameter error: {str(e)}"
                    continue
                    
                except Exception as e:
                    logger.warning(f"Attempt {i}: Unexpected error - {str(e)}")
                    last_error = f"Unexpected error: {str(e)}"
                    continue
            
            # All attempts failed
            self.is_connected = False
            error_message = f"All login attempts failed. Last error: {last_error}"
            logger.error(error_message)
            
            # Provide helpful debugging info
            debug_info = (
                "\n\nDEBUGGING INFO:\n"
                f"• API Key: {'Set' if self.api_key else 'Not set'}\n"
                f"• Client Code: {'Set' if self.client_code else 'Not set'}\n"
                f"• Password: {'Set' if self.password else 'Not set'}\n"
                f"• TOTP Secret: {'Set' if self.totp_secret else 'Not set'}\n"
                f"• SmartConnect: {'Available' if SmartConnect else 'Not installed'}\n"
                f"• Generated TOTP: {totp_value}\n\n"
                "TROUBLESHOOTING:\n"
                "1. Verify credentials are correct in Angel One web/app\n"
                "2. Ensure TOTP secret is the correct base32 string\n"
                "3. Check if Angel One API service is operational\n"
                "4. Try logging in manually to Angel One web platform first"
            )
            
            return False, error_message + debug_info
            
        except Exception as e:
            self.is_connected = False
            logger.exception(f"Critical login error: {e}")
            return False, f"Critical login error: {str(e)}"

    def logout(self) -> Tuple[bool, str]:
        """Logout from Angel One API"""
        try:
            if self.smart_api and self.auth_token:
                try:
                    response = self.smart_api.terminateSession(self.client_code)
                    logger.info(f"Logout response: {response}")
                except Exception as e:
                    logger.warning(f"Logout API call failed: {e}")
            
            # Clear session data
            self.auth_token = None
            self.refresh_token = None
            self.feed_token = None
            self.is_connected = False
            self.last_login_time = None
            
            logger.info("Logged out successfully")
            return True, "Logged out successfully"
            
        except Exception as e:
            logger.exception(f"Logout error: {e}")
            return False, f"Logout error: {str(e)}"

    def check_connection(self) -> bool:
        """Check if connection is still valid"""
        try:
            if not self.is_connected or not self.auth_token:
                return False
            
            # Try a simple API call to verify connection
            if self.smart_api:
                try:
                    # Use a lightweight API call to test connection
                    profile = self.smart_api.getProfile(self.refresh_token)
                    if profile and profile.get('status'):
                        return True
                    else:
                        logger.warning("Connection check failed - invalid response")
                        self.is_connected = False
                        return False
                except Exception as e:
                    logger.warning(f"Connection check failed: {e}")
                    self.is_connected = False
                    return False
            
            return False
            
        except Exception as e:
            logger.exception(f"Connection check error: {e}")
            return False

    def get_connection_status(self) -> Dict[str, Any]:
        """Get detailed connection status"""
        return {
            "connected": self.is_connected,
            "has_saved_credentials": self.has_saved_credentials(),
            "api_key_set": bool(self.api_key),
            "credentials_set": bool(self.client_code and self.password and self.totp_secret),
            "auth_token": bool(self.auth_token),
            "last_login": self.last_login_time.isoformat() if self.last_login_time else None,
            "market_open": self.is_market_open(),
            "smart_api_available": SmartConnect is not None
        }

    def is_market_open(self) -> bool:
        """Check if market is currently open"""
        try:
            now = datetime.now()
            current_time = now.time()
            current_day = now.weekday()  # 0 = Monday, 6 = Sunday
            
            # Market is closed on weekends
            if current_day >= 5:  # Saturday or Sunday
                return False
            
            # Market hours: 9:15 AM to 3:30 PM
            market_start = time(9, 15)
            market_end = time(15, 30)
            
            return market_start <= current_time <= market_end
            
        except Exception as e:
            logger.exception(f"Market open check error: {e}")
            return False

    def __str__(self) -> str:
        """String representation"""
        status = "Connected" if self.is_connected else "Disconnected"
        saved_creds = "with saved credentials" if self.has_saved_credentials() else "no saved credentials"
        return f"AngelProvider({status}, {saved_creds})"