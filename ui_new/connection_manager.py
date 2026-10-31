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
import random
import threading
from pathlib import Path

# OIE-001: redact JWT / PrivateKey from SmartAPI logzero dumps
try:
    from trading_app.angel_log_redaction import install_angel_secret_redaction, redact_secrets
    install_angel_secret_redaction()
except Exception:
    def redact_secrets(text):  # type: ignore
        return text

# Historical candle cache + rate-limit protection (OIE-001)
_HIST_CACHE_LOCK = threading.Lock()
_HIST_CACHE = {}
_HIST_CACHE_TTL_SEC = 120.0
# Daily bars change once per session — keep long enough for a full watchlist scan/rescan
_HIST_CACHE_TTL_ONE_DAY_SEC = 6 * 3600.0

# Angel scrip master is ~30MB — 10s timeouts always fall through to stale fallbacks (AB4046).
_SCRIP_MASTER_URLS = (
    "https://margincalculator.angelone.in/OpenAPI_File/files/OpenAPIScripMaster.json",
    "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json",
)
_SCRIP_MASTER_TIMEOUT_SEC = 90
_SCRIP_MASTER_RETRIES = 2
_SCRIP_TOKEN_CACHE_PATH = Path(__file__).resolve().parents[1] / "storage" / "angel_scrip_token_map.json"
_SCRIP_TOKEN_CACHE_TTL_SEC = 24 * 3600

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
        self.last_tick_ts = 0.0  # any symbol — transport/data health
        self._ws_owner_pid = os.getpid()
        self._ws_owner_lock_path = _workspace_path("storage", "angel_ws_owner.lock")
        self._broker_auth_error = False  # OIE-001: stop reconnect storm on auth failure
        
        # WebSocket credentials
        self.auth_token = None
        self.feed_token = None
        self.client_code = None
        self.api_key = None
        self._angel_creds_from_env = False
        self.last_connection_error = None

        # WS reconnect — OIE-001 schedule: 0,1,2,5,10,30,60+ with jitter
        self._ws_reconnect_pending = False
        self._ws_reconnect_last = 0.0
        self._ws_reconnect_attempts = 0
        self._ws_reconnect_max_attempts = 12
        self._ws_reconnect_delays = (0.0, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0)
        self._ws_reconnect_min_interval_sec = 1.0
        self._ws_reconnect_exhausted_logged = False
        self._subscribe_skip_log_ts = 0.0
        self._ws_dead_reason = None
        self._ws_start_lock = threading.Lock()
        # Identity of the active SmartWebSocketV2 — ignore callbacks from disposed sockets
        self._ws_active_id = 0
        self._ws_instance_id = 0
        self._connect_lock = threading.Lock()
        self._ws_starting = False
        
        # Initialize (but DON'T load tokens yet for fast startup!)
        self.load_config()
        self.load_stock_list()
        # Token loading moved to ensure_tokens_loaded() - called on demand
    
    def load_config(self):
        """Load API credentials from config.json, then overlay Angel keys from .env if present."""
        config_files = [
            _workspace_path("config.json"),
            "config.json",
            "config.py",
        ]

        self.config = {
            'api_key': '', 'client_id': '', 'password': '', 'totp_token': '',
            'initial_capital': 100000, 'risk_per_trade': 2, 'auto_trading': False
        }
        loaded_from = None
        for config_file in config_files:
            if os.path.exists(config_file):
                try:
                    if config_file.endswith('.json'):
                        with open(config_file, 'r', encoding='utf-8') as f:
                            raw = json.load(f) or {}
                        if isinstance(raw, dict):
                            self.config.update(raw)
                            loaded_from = config_file
                            _safe_print(f"[OK] Loaded config from {config_file}")
                            break
                except Exception as e:
                    _safe_print(f"[WARN] Could not load {config_file}: {e}")

        if not loaded_from:
            _safe_print("[WARN] No config file found, using defaults")

        # .env overrides (dashboard previously ignored .env entirely — only config.json was used)
        env_overlay = self._load_angel_env_overlay()
        self._angel_creds_from_env = bool(env_overlay.get("api_key"))
        if env_overlay:
            self.config.update(env_overlay)
            _safe_print(
                "[OK] Applied Angel credentials from .env "
                f"({', '.join(sorted(env_overlay.keys()))})"
            )

    def _load_angel_env_overlay(self) -> dict:
        """Read ANGEL_* from process env and/or project .env into config.json field names."""
        env_path = _workspace_path(".env")
        file_vars = {}
        if os.path.isfile(env_path):
            try:
                try:
                    from dotenv import dotenv_values
                    file_vars = {k: v for k, v in (dotenv_values(env_path) or {}).items() if v}
                except Exception:
                    for line in open(env_path, encoding="utf-8", errors="ignore"):
                        s = line.strip()
                        if not s or s.startswith("#") or "=" not in s:
                            continue
                        k, v = s.split("=", 1)
                        k, v = k.strip(), v.strip().strip('"').strip("'")
                        if k and v:
                            file_vars[k] = v
            except Exception as e:
                _safe_print(f"[WARN] Could not read .env: {e}")

        def _get(name: str) -> str:
            return str(os.environ.get(name) or file_vars.get(name) or "").strip()

        mapping = {
            "api_key": _get("ANGEL_API_KEY"),
            "client_id": _get("ANGEL_CLIENT_ID"),
            "password": _get("ANGEL_PASSWORD"),
            "totp_token": _get("ANGEL_TOTP_SECRET") or _get("ANGEL_TOTP_TOKEN"),
        }
        return {k: v for k, v in mapping.items() if v}
    def load_stock_list(self):
        """Load stock list from watchlist.json (workspace-relative first)."""
        watchlist_paths = [_workspace_path("watchlist.json"), "watchlist.json"]
        for watchlist_path in watchlist_paths:
            if os.path.exists(watchlist_path):
                try:
                    with open(watchlist_path, 'r', encoding='utf-8') as f:
                        self.stock_list = json.load(f)
                        self.stock_list = sorted({s.upper() for s in self.stock_list if str(s).strip()})
                    _safe_print(f"[OK] Loaded {len(self.stock_list)} stocks from {watchlist_path}")
                    return
                except Exception as e:
                    _safe_print(f"[WARN] Could not load {watchlist_path}: {e}")
        
        # Fallback to stock_list.txt
        for stock_path in (_workspace_path("stock_list.txt"), "stock_list.txt"):
            if os.path.exists(stock_path):
                try:
                    with open(stock_path, 'r', encoding='utf-8') as f:
                        self.stock_list = sorted({line.strip().upper() for line in f if line.strip()})
                    _safe_print(f"[OK] Loaded {len(self.stock_list)} stocks from {stock_path}")
                    return
                except Exception as e:
                    _safe_print(f"[WARN] Could not load {stock_path}: {e}")
        
        # Default stocks
        _safe_print("[WARN] No watchlist file found, using defaults")
        self.stock_list = ["HDFCBANK", "ICICIBANK", "INFY", "RELIANCE", "TCS"]
    
    def save_stock_list(self):
        """Save stock list to watchlist.json"""
        try:
            path = _workspace_path("watchlist.json")
            ordered = sorted({str(s).upper().strip() for s in self.stock_list if str(s).strip()})
            self.stock_list = ordered
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(ordered, f, indent=2)
                f.write("\n")
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
    
    @staticmethod
    def _parse_scrip_master_items(data):
        """Build EXCH:SYMBOL -> token map from Angel OpenAPIScripMaster rows."""
        token_map = {}
        exchanges = ("NSE", "NFO", "BSE")
        for item in data or []:
            exch_seg = item.get("exch_seg")
            if exch_seg not in exchanges:
                continue
            symbol = item.get("symbol", "") or ""
            name = (item.get("name", "") or "").upper()
            token = item.get("token", "")
            if not symbol or not token:
                continue
            if exch_seg == "NSE" and symbol.endswith("-EQ"):
                clean_symbol = symbol[:-3].upper()
            else:
                clean_symbol = symbol.upper()
            key = f"{exch_seg}:{clean_symbol}"
            token_map[key] = str(token)
            # Prefer equity name keys when present (e.g. LODHA) — same token.
            if exch_seg == "NSE" and name and name != clean_symbol and symbol.endswith("-EQ"):
                token_map[f"{exch_seg}:{name}"] = str(token)
        return token_map

    def _load_token_map_from_disk(self, *, allow_stale: bool = False):
        """Return (token_map, age_sec) from local cache, or (None, None)."""
        path = _SCRIP_TOKEN_CACHE_PATH
        if not path.is_file():
            return None, None
        try:
            age = time.time() - path.stat().st_mtime
            if (not allow_stale) and age > _SCRIP_TOKEN_CACHE_TTL_SEC:
                return None, age
            with path.open("r", encoding="utf-8") as fh:
                payload = json.load(fh)
            tokens = payload.get("tokens") if isinstance(payload, dict) else None
            if not isinstance(tokens, dict) or not tokens:
                return None, age
            return {str(k): str(v) for k, v in tokens.items()}, age
        except Exception as e:
            _safe_print(f"[WARN] Could not read scrip token cache: {e}")
            return None, None

    def _save_token_map_to_disk(self, token_map):
        """Persist parsed token map so timeouts do not strand us on wrong hardcoded tokens."""
        try:
            path = _SCRIP_TOKEN_CACHE_PATH
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "saved_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "source": "OpenAPIScripMaster",
                "count": len(token_map),
                "tokens": token_map,
            }
            tmp = path.with_suffix(".tmp")
            with tmp.open("w", encoding="utf-8") as fh:
                json.dump(payload, fh)
            tmp.replace(path)
            _safe_print(f"[OK] Cached {len(token_map)} scrip tokens -> {path.name}")
        except Exception as e:
            _safe_print(f"[WARN] Could not write scrip token cache: {e}")

    def _download_scrip_master(self):
        """Download Angel scrip master with alternate hosts and retries."""
        import requests

        last_err = None
        for url in _SCRIP_MASTER_URLS:
            for attempt in range(1, _SCRIP_MASTER_RETRIES + 1):
                try:
                    _safe_print(
                        f"[...] Downloading Angel scrip master "
                        f"(attempt {attempt}/{_SCRIP_MASTER_RETRIES}, timeout={_SCRIP_MASTER_TIMEOUT_SEC}s)..."
                    )
                    response = requests.get(url, timeout=_SCRIP_MASTER_TIMEOUT_SEC)
                    if response.status_code == 200:
                        data = response.json()
                        if isinstance(data, list) and data:
                            return data
                        last_err = f"empty/invalid JSON from {url}"
                    else:
                        last_err = f"HTTP {response.status_code} from {url}"
                except Exception as e:
                    last_err = str(e)
                    _safe_print(f"[WARN] Scrip master download failed: {e}")
        if last_err:
            raise RuntimeError(last_err)
        raise RuntimeError("scrip master download failed")

    def load_symbol_tokens(self):
        """Load symbol tokens from Angel master, disk cache, or hardcoded fallback."""
        # Fast path: fresh local cache (avoids 30MB download every boot).
        cached, age = self._load_token_map_from_disk(allow_stale=False)
        if cached:
            self.token_map = cached
            _safe_print(
                f"[OK] Loaded {len(self.token_map)} symbol tokens from disk cache "
                f"(age {int(age or 0)}s)"
            )
            return True

        try:
            data = self._download_scrip_master()
            parsed = self._parse_scrip_master_items(data)
            if not parsed:
                raise RuntimeError("parsed token map empty")
            self.token_map = parsed
            self._save_token_map_to_disk(parsed)
            for key in ("NSE:NIFTY", "NSE:BANKNIFTY", "BSE:SENSEX", "NSE:INDIAVIX", "NSE:LODHA"):
                if key in self.token_map:
                    _safe_print(f"[DEBUG] Loaded token for {key}: {self.token_map[key]}")
            _safe_print(f"[OK] Loaded {len(self.token_map)} symbol tokens from Angel One")
            return True
        except Exception as e:
            _safe_print(f"[WARN] Error loading symbol tokens: {e}")

        stale, age = self._load_token_map_from_disk(allow_stale=True)
        if stale:
            self.token_map = stale
            _safe_print(
                f"[OK] Using stale scrip token cache ({len(self.token_map)} tokens, "
                f"age {int(age or 0)}s) — better than hardcoded fallback"
            )
            return True

        _safe_print("[WARN] Could not download symbol master, using hardcoded fallback")
        self._load_fallback_tokens()
        return False

    def _load_fallback_tokens(self):
        """Fallback token map for major stocks (last resort; prefer live/disk scrip master)."""
        self.token_map = {
            'NSE:ABB': '5', 'NSE:ADANIENT': '25', 'NSE:ADANIGREEN': '15083',
            'NSE:ADANIPORTS': '15083', 'NSE:ADANIPOWER': '4', 'NSE:AMBUJACEM': '1270',
            'NSE:APOLLOHOSP': '157', 'NSE:ASIANPAINT': '236', 'NSE:DMART': '14299',
            'NSE:AXISBANK': '5900', 'NSE:BAJAJ-AUTO': '16669', 'NSE:BAJFINANCE': '317',
            'NSE:BAJAJFINSV': '16675', 'NSE:BAJAJHLDNG': '16675', 'NSE:BANKBARODA': '4668',
            'NSE:BEL': '383', 'NSE:BHARTIARTL': '10604', 'NSE:BHEL': '438',
            'NSE:BOSCHLTD': '558', 'NSE:BPCL': '526', 'NSE:BRITANNIA': '547',
            'NSE:CANBK': '10794', 'NSE:CHOLAFIN': '685', 'NSE:CIPLA': '694',
            'NSE:COALINDIA': '20374', 'NSE:DABUR': '772', 'NSE:DIVISLAB': '10940',
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
            'NSE:LICI': '19209', 'NSE:M&M': '2031', 'NSE:LODHA': '3220',
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

        # Serialize login — concurrent connect_broker (bridge + /api/holdings) was
        # replacing smart_api mid-session → AG8003 Token missing + WS dispose thrash.
        with self._connect_lock:
            if self.is_connected and self.smart_api and self.auth_token and self.feed_token:
                # Do NOT call start_websocket if a socket is already opening — that
                # dispose+restart race is what produced dual "WebSocket started" lines.
                if not self.websocket_connected and self.websocket is None and not self._ws_starting:
                    self.start_websocket()
                return True
            return self._connect_broker_locked()

    def _connect_broker_locked(self):
        """Angel login + WS start. Caller must hold _connect_lock."""
        try:
            # Ensure tokens are loaded before connecting
            self.ensure_tokens_loaded()
            
            _safe_print(f"[DEBUG] Token for BSE:SENSEX: {self.token_map.get('BSE:SENSEX')}")
            _safe_print(f"[DEBUG] Token for NSE:INDIAVIX: {self.token_map.get('NSE:INDIAVIX')}")
            
            # Get credentials — .env (if present) already merged into self.config and wins.
            self.api_key = self.config.get('api_key', '')
            self.client_code = self.config.get('client_id', '')
            password = self.config.get('password', '')
            totp_secret = self.config.get('totp_token', '')
            cred_source = "env" if getattr(self, "_angel_creds_from_env", False) else "config.json"

            # Encrypted storage only fills gaps — never overrides an explicit .env API key.
            if (not password or not totp_secret or not self.api_key) and not getattr(
                self, "_angel_creds_from_env", False
            ):
                try:
                    from config.credentials_manager import SecureCredentialsManager
                    cred_mgr = SecureCredentialsManager()
                    success, creds = cred_mgr.load_credentials()

                    if success and creds:
                        _safe_print("[OK] Loaded credentials from encrypted storage")
                        self.api_key = creds.get('api_key', self.api_key) or self.api_key
                        self.client_code = creds.get('client_code', self.client_code) or self.client_code
                        password = creds.get('password', password) or password
                        totp_secret = creds.get('totp_secret', totp_secret) or totp_secret
                        cred_source = "encrypted"
                    else:
                        _safe_print("[WARN] Could not load encrypted credentials")
                except Exception as e:
                    _safe_print(f"[WARN] Encrypted credentials unavailable: {e}")

            if not all([self.api_key, self.client_code, password]):
                _safe_print("[WARN] Missing credentials (need API Key, Client Code, and Password)")
                return False

            key = str(self.api_key or "")
            _safe_print(
                f"[OK] Angel credential source={cred_source} "
                f"api_key_len={len(key)} api_key_prefix={(key[:2] + '***') if key else 'NONE'}"
            )
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
                self.last_connection_error = redact_secrets(str(error_msg))
                self._broker_auth_error = True
                _safe_print(f"[WARN] Failed to authenticate: {redact_secrets(str(error_msg))}")
                _safe_print("[WARN] BROKER_AUTH_ERROR — operator intervention required (no auto reconnect storm)")
                return False

            self.last_connection_error = None
            self._broker_auth_error = False

            
            # Store tokens
            self.auth_token = data['data']['jwtToken']
            self.feed_token = self.smart_api.getfeedToken()
            # Ensure REST Authorization header is present (SmartAPI AG8003 guard)
            try:
                jwt = self.auth_token
                if isinstance(jwt, str) and jwt.startswith("Bearer "):
                    jwt = jwt[len("Bearer "):]
                if jwt and not getattr(self.smart_api, "access_token", None):
                    self.smart_api.setAccessToken(jwt)
            except Exception:
                pass
            self.is_connected = True
            
            _safe_print("[OK] Connected to Angel One broker")
            _safe_print("[OK] Feed Token: [REDACTED_FEED_TOKEN]")

            # Login can succeed while REST LTP/holdings still fail (AG8004 / IP whitelist).
            self._probe_angel_rest_after_login()
            
            # Start WebSocket in separate thread (single-process owner)
            self._ws_reconnect_attempts = 0
            self._ws_reconnect_exhausted_logged = False
            if self._claim_ws_ownership():
                self.start_websocket()
            else:
                _safe_print(
                    "[WARN] Another NexTrade process owns Angel WebSocket — "
                    "this process will use REST reference only"
                )
            
            return True
            
        except ImportError as e:
            _safe_print(f"[WARN] SmartApi library not installed: {e}")
            return False
        except Exception as e:
            msg = redact_secrets(str(e))
            low = msg.lower()
            if any(k in low for k in ("invalid", "auth", "token", "credential", "login", "totp", "password")):
                self._broker_auth_error = True
                self.last_connection_error = msg
                _safe_print(f"[WARN] BROKER_AUTH_ERROR: {msg}")
            else:
                _safe_print(f"[WARN] Connection error: {msg}")
            return False

    def _probe_angel_rest_after_login(self) -> None:
        """One REST LTP call after login to surface AG8004 / IP issues immediately."""
        try:
            token = self.token_map.get("NSE:NIFTY") or self.token_map.get("NIFTY") or "99926000"
            resp = self.smart_api.ltpData("NSE", "NIFTY", str(token))
            ok = bool(resp) and (
                resp.get("status") is True
                or resp.get("success") is True
                or (isinstance(resp.get("data"), dict) and resp.get("data"))
            )
            if ok:
                _safe_print("[OK] Angel REST LTP probe succeeded (API key + session usable)")
                return
            msg = str((resp or {}).get("message") or (resp or {}).get("errorcode") or resp or "unknown")
            _safe_print(f"[WARN] Angel REST LTP probe failed: {redact_secrets(msg)}")
        except Exception as e:
            msg = redact_secrets(str(e))
            _safe_print(f"[WARN] Angel REST LTP probe failed: {msg}")
            low = msg.lower()
            if "invalid api key" in low or "ag8004" in low:
                _safe_print(
                    "[WARN] AG8004 checklist: (1) use Trading app key (NexTrade_v2), "
                    "not Market Feeds; (2) whitelist THIS machine's public IP on that app; "
                    "(3) restart dashboard after portal IP save; "
                    "(4) confirm startup log shows Applied Angel credentials from .env"
                )
            return
        low = msg.lower()
        if "invalid api key" in low or "ag8004" in low:
            _safe_print(
                "[WARN] AG8004 checklist: (1) use Trading app key (NexTrade_v2), "
                "not Market Feeds; (2) whitelist THIS machine's public IP on that app; "
                "(3) restart dashboard after portal IP save; "
                "(4) confirm startup log shows Applied Angel credentials from .env"
            )
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

    def _ws_socket_alive(self) -> bool:
        """True if flag is up and underlying websocket-client sock is not known-closed.

        NOTE: Do NOT use SmartAPI SmartWebSocketV2.DISCONNECT_FLAG here.
        That library sets DISCONNECT_FLAG=True in __init__ and never clears it,
        so treating it as 'dead' false-positives every fresh connection and
        immediately tears down subscribe (the 08:51 log pattern).
        """
        if not self.websocket_connected or not self.websocket:
            return False
        if getattr(self, "is_paper_sandbox", False):
            return True
        wsapp = getattr(self.websocket, "wsapp", None)
        if wsapp is None:
            # Mid-open wiring race — trust flag until sock proves closed
            return True
        sock = getattr(wsapp, "sock", None)
        if sock is None:
            return True
        try:
            connected = getattr(sock, "connected", None)
            if connected is False:
                return False
        except Exception:
            return False
        return True

    def _is_current_websocket(self, ws_obj=None) -> bool:
        """True if callbacks belong to the currently active SmartWebSocketV2 instance."""
        current = self.websocket
        if current is None:
            return False
        if ws_obj is not None and ws_obj is not current:
            # Only reject when caller passed the SmartWebSocketV2 instance itself
            if hasattr(ws_obj, "feed_token") and hasattr(ws_obj, "close_connection"):
                return False
        return int(getattr(current, "_nextrade_ws_id", -1)) == int(self._ws_active_id)

    def _dispose_websocket(self) -> None:
        """Close and drop any existing SmartWebSocketV2 so we never stack sockets."""
        ws = self.websocket
        self.websocket = None
        self.websocket_connected = False
        self._ws_starting = False
        # Invalidate callbacks from the disposed instance (SmartAPI still fires on_error/on_close)
        self._ws_active_id = int(self._ws_active_id) + 1
        if not ws:
            return
        # Detach callbacks so a dying socket cannot mark the next connection dead
        try:
            ws.on_open = lambda *_a, **_k: None
            ws.on_data = lambda *_a, **_k: None
            ws.on_error = lambda *_a, **_k: None
            ws.on_close = lambda *_a, **_k: None
        except Exception:
            pass
        try:
            ws.close_connection()
        except Exception:
            pass

    def _ws_error_text(self, wsapp, error) -> str:
        """Normalize SmartAPI on_error args (often two strings, not a wsapp object)."""
        parts = []
        for part in (wsapp, error):
            if part is None:
                continue
            if hasattr(part, "sock") or hasattr(part, "run_forever"):
                continue
            text = str(part).strip()
            if text:
                parts.append(text)
        return " | ".join(parts) if parts else str(error or wsapp or "websocket error")

    def _mark_websocket_dead(self, reason: str = "") -> None:
        """Flip WS flag off immediately; log once per close; schedule capped reconnect."""
        was_connected = self.websocket_connected
        self.websocket_connected = False
        if reason:
            self._ws_dead_reason = reason
        if was_connected:
            _safe_print(f"[WARN] Angel WebSocket marked dead: {reason or 'socket closed'}")
        self._schedule_ws_reconnect()

    def _claim_ws_ownership(self) -> bool:
        """
        OIE-001: only one OS process may own the Angel broker WebSocket.
        Stale locks from dead PIDs are taken over.
        """
        path = self._ws_owner_lock_path
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        raw = (f.read() or "").strip()
                    other_pid = int(raw.split()[0]) if raw else 0
                except Exception:
                    other_pid = 0
                if other_pid and other_pid != os.getpid():
                    alive = False
                    try:
                        os.kill(other_pid, 0)
                        alive = True
                    except PermissionError:
                        alive = True  # process exists; we lack rights to signal
                    except OSError:
                        alive = False
                    if alive:
                        return False
            with open(path, "w", encoding="utf-8") as f:
                f.write(f"{os.getpid()}\n")
            self._ws_owner_pid = os.getpid()
            return True
        except Exception as exc:
            _safe_print(f"[WARN] WS ownership lock failed ({exc}) — allowing WS in this process")
            return True

    def _owns_broker_ws(self) -> bool:
        try:
            if not os.path.exists(self._ws_owner_lock_path):
                return True
            with open(self._ws_owner_lock_path, "r", encoding="utf-8") as f:
                raw = (f.read() or "").strip()
            return int(raw.split()[0]) == os.getpid()
        except Exception:
            return True

    def _ws_reconnect_delay(self, attempt: int) -> float:
        delays = getattr(self, "_ws_reconnect_delays", None) or (0.0, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0)
        idx = min(int(attempt), len(delays) - 1)
        base = float(delays[idx])
        jitter = random.uniform(0.0, min(1.5, base * 0.25 + 0.05))
        return base + jitter

    def _is_auth_failure_text(self, text: str) -> bool:
        low = str(text or "").lower()
        return any(
            k in low
            for k in (
                "invalid token",
                "jwt",
                "unauthorized",
                "authentication",
                "auth failed",
                "login failed",
                "invalid session",
                "session expired",
                "ag8003",
                "token expired",
            )
        )

    def _schedule_ws_reconnect(self) -> None:
        """Delayed reconnect with OIE-001 backoff+jitter; stop on BROKER_AUTH_ERROR."""
        if getattr(self, "is_paper_sandbox", False):
            return
        if getattr(self, "_broker_auth_error", False):
            if not self._ws_reconnect_exhausted_logged:
                self._ws_reconnect_exhausted_logged = True
                _safe_print(
                    "[WARN] Angel WebSocket reconnect halted — BROKER_AUTH_ERROR "
                    "(fix credentials / TOTP, then restart dashboard)"
                )
            return
        if not self.is_connected:
            return
        if not self._owns_broker_ws():
            return
        if self._ws_reconnect_pending:
            return
        if self._ws_socket_alive():
            return
        if int(self._ws_reconnect_attempts) >= int(self._ws_reconnect_max_attempts):
            if not self._ws_reconnect_exhausted_logged:
                self._ws_reconnect_exhausted_logged = True
                _safe_print(
                    f"[WARN] Angel WebSocket reconnect exhausted "
                    f"({self._ws_reconnect_max_attempts} attempts) — "
                    "holding REST reference only; restart dashboard to retry WS"
                )
            return
        now = time.time()
        if (now - float(self._ws_reconnect_last or 0.0)) < float(self._ws_reconnect_min_interval_sec):
            return

        attempt = int(self._ws_reconnect_attempts)
        delay = self._ws_reconnect_delay(attempt)
        self._ws_reconnect_pending = True

        def _do_reconnect():
            try:
                time.sleep(delay)
                if getattr(self, "_broker_auth_error", False):
                    return
                if self._ws_socket_alive():
                    return
                if not self.is_connected or not self._owns_broker_ws():
                    return
                self._ws_reconnect_attempts = attempt + 1
                self._ws_reconnect_last = time.time()
                _safe_print(
                    f"[...] Angel WebSocket reconnect "
                    f"{self._ws_reconnect_attempts}/{self._ws_reconnect_max_attempts} "
                    f"(waited {delay:.1f}s)..."
                )
                self._dispose_websocket()
                self.start_websocket()
            finally:
                self._ws_reconnect_pending = False

        threading.Thread(target=_do_reconnect, daemon=True, name="AngelWSReconnect").start()

    def start_websocket(self):
        """Start WebSocket in separate thread - PREVENTS UI FREEZING!"""
        if getattr(self, "_broker_auth_error", False):
            _safe_print("[WARN] Skipping WebSocket start — BROKER_AUTH_ERROR")
            return False
        if not all([self.auth_token, self.feed_token, self.api_key, self.client_code]):
            _safe_print("[WARN] Missing WebSocket credentials")
            return False
        
        if not SMARTAPI_AVAILABLE:
            _safe_print("[WARN] SmartApi library not available for WebSocket")
            return False

        if not self._claim_ws_ownership():
            _safe_print("[WARN] Skipping WebSocket — another process owns Angel WS")
            return False

        with self._ws_start_lock:
            # Already live or mid-handshake — do not dispose a healthy/opening socket
            if self.websocket_connected and self._ws_socket_alive():
                return True
            if self._ws_starting and self.websocket is not None:
                return True
            # Never leave a prior SmartWebSocketV2 running alongside a new one
            self._dispose_websocket()
            try:
                # max_retry_attempt=0: we own reconnect (avoids dual SmartAPI+app reconnect)
                self.websocket = SmartWebSocketV2(
                    auth_token=self.auth_token,
                    api_key=self.api_key,
                    client_code=self.client_code,
                    feed_token=self.feed_token,
                    max_retry_attempt=0,
                )
                # SmartAPI leaves DISCONNECT_FLAG=True forever after __init__; clear for sanity
                try:
                    self.websocket.DISCONNECT_FLAG = False
                except Exception:
                    pass
                self._ws_instance_id = int(self._ws_instance_id) + 1
                self._ws_active_id = self._ws_instance_id
                self.websocket._nextrade_ws_id = self._ws_active_id
                self._ws_starting = True

                self.websocket.on_open = self._on_ws_open
                self.websocket.on_data = self._on_ws_data
                self.websocket.on_error = self._on_ws_error
                self.websocket.on_close = self._on_ws_close

                ws_thread = threading.Thread(target=self.websocket.connect, daemon=True)
                ws_thread.start()

                _safe_print("[OK] WebSocket started in background thread")
                return True

            except Exception as e:
                self.websocket = None
                self.websocket_connected = False
                self._ws_starting = False
                _safe_print(f"[WARN] WebSocket startup error: {e}")
                return False
    
    def _on_ws_open(self, wsapp):
        """WebSocket opened - subscribe to stocks"""
        if not self._is_current_websocket():
            return
        _safe_print("[OK] WebSocket connected")
        self.websocket_connected = True
        self._ws_starting = False
        self._ws_dead_reason = None
        self._ws_reconnect_attempts = 0
        self._ws_reconnect_exhausted_logged = False
        try:
            # Ensure library flag matches live socket (it starts True in SmartAPI __init__)
            if self.websocket is not None:
                self.websocket.DISCONNECT_FLAG = False
        except Exception:
            pass
        
        # Subscribe to watchlist + index symbols (indices often need explicit subscribe)
        watchlist_with_exchange = [(symbol, "NSE") for symbol in self.stock_list]
        index_pairs = [("NIFTY", "NSE"), ("BANKNIFTY", "NSE"), ("INDIAVIX", "NSE"), ("SENSEX", "BSE")]
        self.subscribe_symbols(watchlist_with_exchange + index_pairs)
    
    def _on_ws_data(self, wsapp, message):
        """WebSocket data received - update LTP cache (runs in background thread)"""
        if not self._is_current_websocket():
            return
        try:
            # Message is already parsed by SmartWebSocketV2
            if isinstance(message, dict):
                token = str(message.get('token', ''))
                ltp = message.get('last_traded_price', 0)
                
                if token and ltp:
                    symbol = self.token_to_symbol_map.get(token) # Use reverse map
                    if symbol:
                        now = time.time()
                        # Update LTP cache (thread-safe) + global last-tick for data health
                        # Prices are paise (*100). QUOTE/SNAP modes also send closed_price.
                        ltp_val = float(ltp) / 100.0
                        closed_raw = message.get('closed_price', 0) or 0
                        close_val = float(closed_raw) / 100.0 if float(closed_raw) > 0 else 0.0
                        change_pct = (
                            ((ltp_val - close_val) / close_val) * 100.0
                            if close_val > 0 and ltp_val > 0
                            else 0.0
                        )
                        vol_raw = message.get('volume_trade_for_the_day', 0) or 0
                        with self.ltp_lock:
                            prev = self.ltp_data.get(symbol) or {}
                            # Keep last known close if this tick is LTP-only (mode 1)
                            if close_val <= 0:
                                close_val = float(prev.get('closed_price') or 0)
                                if close_val > 0 and ltp_val > 0:
                                    change_pct = ((ltp_val - close_val) / close_val) * 100.0
                            self.ltp_data[symbol] = {
                                'ltp': ltp_val,
                                'closed_price': close_val,
                                'change_pct': round(change_pct, 4),
                                'volume': int(vol_raw) if vol_raw else int(prev.get('volume') or 0),
                                'timestamp': now,
                                'token': token,
                                'received_ts': now,
                            }
                            self.last_tick_ts = now
        except Exception as e:
            _safe_print(f"[WARN] Error in _on_ws_data: {e}")
    
    def _on_ws_error(self, wsapp, error):
        """WebSocket error — always clear connected flag (incl. SmartAPI max-retry)."""
        if not self._is_current_websocket():
            return
        self._ws_starting = False
        err = redact_secrets(self._ws_error_text(wsapp, error))
        _safe_print(f"[WARN] WebSocket error: {err}")
        if self._is_auth_failure_text(err):
            self._broker_auth_error = True
            self.last_connection_error = err
            _safe_print("[WARN] BROKER_AUTH_ERROR detected on WebSocket — reconnect halted")
        self._mark_websocket_dead(err)
    
    def _on_ws_close(self, wsapp):
        """WebSocket closed — clear flag immediately; log once; schedule capped reconnect."""
        if not self._is_current_websocket():
            return
        self._ws_starting = False
        was_connected = self.websocket_connected
        self.websocket_connected = False
        if was_connected:
            _safe_print("[INFO] WebSocket disconnected")
        self._schedule_ws_reconnect()
    
    def subscribe_symbols(self, symbols_with_exchange):
        """
        Subscribe to symbols on WebSocket.
        Early-returns without calling SmartAPI when socket is down (no spam).
        """
        if not self.websocket or not self._ws_socket_alive():
            if self.websocket_connected:
                self._mark_websocket_dead("subscribe skipped - underlying socket not alive")
            else:
                now = time.time()
                if (now - float(self._subscribe_skip_log_ts or 0.0)) > 60.0:
                    self._subscribe_skip_log_ts = now
                    reason = self._ws_dead_reason or "not connected"
                    _safe_print(f"[WARN] WebSocket not connected, skipping subscribe ({reason})")
                self._schedule_ws_reconnect()
            return False
        
        self.ensure_tokens_loaded()

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

            if token:
                # Special handling for indices - NSE indices use NFO exchange type for WebSocket
                symbol_upper = symbol.upper()
                if symbol_upper in ["NIFTY", "BANKNIFTY", "NIFTY50", "FINNIFTY", "MIDCPNIFTY", "INDIAVIX"]:
                    exchange_type = 2  # NFO for NSE indices
                elif exchange_upper == "NSE":
                    exchange_type = 1
                elif exchange_upper == "NFO":
                    exchange_type = 2
                elif exchange_upper == "BSE":
                    exchange_type = 4  # BSE indices use BSE exchange type
                else:
                    continue # Skip unsupported exchanges

                if exchange_type not in tokens_by_exchange:
                    tokens_by_exchange[exchange_type] = []
                tokens_by_exchange[exchange_type].append(token)

        if not tokens_by_exchange:
            return False
            
        correlation_id = "quote_subscription"
        # Mode 2 = QUOTE (LTP + OHLC + closed_price + volume). Mode 1 = LTP only → change% stuck at 0.
        mode = 2  # QUOTE_MODE
        any_ok = False

        for exchange_type, tokens in tokens_by_exchange.items():
            # Angel WS accepts large lists poorly in one shot — subscribe in chunks.
            chunk_size = 40
            for i in range(0, len(tokens), chunk_size):
                chunk = tokens[i : i + chunk_size]
                token_data = [{"exchangeType": exchange_type, "tokens": chunk}]
                try:
                    self.websocket.subscribe(correlation_id, mode, token_data)
                    any_ok = True
                except Exception as e:
                    err = str(e)
                    low = err.lower()
                    if "already closed" in low or "socket is already closed" in low or "connection closed" in low:
                        self._mark_websocket_dead(err)
                        return False
                    _safe_print(f"[WARN] Subscription error for exchange type {exchange_type}: {e}")

        return any_ok

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
        """Get Last Traded Price from WebSocket cache. Returns None when no live tick (OIE-001)."""
        symbol_upper = symbol.upper()

        with self.ltp_lock:
            if symbol_upper in self.ltp_data:
                data = self.ltp_data[symbol_upper]
                if time.time() - data['timestamp'] < 30:
                    return data['ltp']

        # Fail closed — do not invent prices from hard-coded bases / simulated candles.
        return None

    
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
        """Get broker holdings from Angel One (never mix with demo data)."""
        if not self.smart_api or not self.is_connected:
            return []

        if getattr(self, "is_paper_sandbox", False):
            return []

        try:
            resp = self.smart_api.holding()
            if resp and resp.get('status'):
                return resp.get('data', [])
            msg = (resp or {}).get('message', 'Holdings API returned failure')
            _safe_print(f"[WARN] Holdings API failed: {msg}")
            return []
        except Exception as e:
            _safe_print(f"[WARN] Error fetching holdings: {e}")
            return []
    
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

            cache_key = (exchange, symbol.upper(), interval, int(period_days))
            now = time.time()
            ttl = (
                _HIST_CACHE_TTL_ONE_DAY_SEC
                if str(interval or "").upper() in ("ONE_DAY", "DAY", "1D", "D")
                else _HIST_CACHE_TTL_SEC
            )
            with _HIST_CACHE_LOCK:
                hit = _HIST_CACHE.get(cache_key)
                if hit and (now - float(hit.get("fetched_at") or 0.0)) < ttl:
                    df_hit = hit.get("df")
                    return df_hit.copy(deep=True) if isinstance(df_hit, pd.DataFrame) else pd.DataFrame()
            
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
            
            def _call_candles():
                return self.smart_api.getCandleData(historic_param)

            try:
                from trading_app.angel_rest_limiter import angel_rest_call
            except Exception:
                angel_rest_call = None  # type: ignore

            if angel_rest_call:
                response = angel_rest_call(
                    f"historical:getCandleData:{exchange}:{symbol.upper()}:{interval}",
                    _call_candles,
                )
            else:
                response = _call_candles()
            
            if not response or not response.get('status'):
                error_msg = response.get('message', 'Unknown error') if response else 'No response'
                _safe_print(f"⚠️  Failed to fetch historical data for {symbol}: {error_msg}")
                try:
                    from trading_app.angel_rest_limiter import _looks_rate_limited, trip_rest_cooldown
                    if _looks_rate_limited(error_msg):
                        trip_rest_cooldown(45.0, str(error_msg)[:120])
                except Exception:
                    pass
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
            
            with _HIST_CACHE_LOCK:
                _HIST_CACHE[cache_key] = {"fetched_at": now, "df": df}
            return df
            
        except Exception as e:
            _safe_print(f"⚠️  Error fetching historical data for {symbol}: {e}")
            # Fail-closed: do not substitute simulated candles when broker is connected.
            return pd.DataFrame()

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
        """Get connection status for UI display (transport + tick freshness)."""
        is_paper = getattr(self, 'is_paper_sandbox', False)
        if self.is_connected:
            status_text = '[OK] Paper Sandbox Connected' if is_paper else '[OK] Live Broker Connected'
        else:
            status_text = '[OFF] Broker Disconnected'

        last_tick = float(getattr(self, "last_tick_ts", 0.0) or 0.0)
        tick_age = (time.time() - last_tick) if last_tick > 0 else None
        tick_fresh = tick_age is not None and tick_age <= 15.0
        # Transport vs data health (OIE-001)
        ws_transport = bool(self.websocket_connected and self._ws_socket_alive())
            
        return {
            'broker_connected': self.is_connected,
            'websocket_connected': ws_transport,
            'websocket_streaming': bool(ws_transport and tick_fresh),
            'last_tick_ts': last_tick or None,
            'last_tick_age_sec': round(tick_age, 2) if tick_age is not None else None,
            'broker_auth_error': bool(getattr(self, "_broker_auth_error", False)),
            'ws_owner_pid': getattr(self, "_ws_owner_pid", os.getpid()),
            'owns_broker_ws': self._owns_broker_ws(),
            'analyzer_connected': self.analyzer is not None,
            'is_paper_sandbox': is_paper,
            'status_text': status_text,
            'last_connection_error': getattr(self, "last_connection_error", None),
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
        self._dispose_websocket() if hasattr(self, "_dispose_websocket") else None
        if self.websocket:
            try:
                self.websocket.close_connection()
            except Exception:
                pass
            self.websocket = None
        
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