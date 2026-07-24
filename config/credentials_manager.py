# config/credentials_manager.py
"""
Backward-compatible wrapper around canonical OS Keyring credential manager
(enhancements.config.secure_credentials.SecureCredentialsManager)
"""
import logging
from typing import Tuple, Dict, Any

logger = logging.getLogger("CredentialsManager")

try:
    from enhancements.config.secure_credentials import SecureCredentialsManager as KeyringCredentialsManager
    _KEYRING_OK = True
except Exception as e:
    logger.warning(f"Keyring credential manager import error: {e}")
    KeyringCredentialsManager = None
    _KEYRING_OK = False


class SecureCredentialsManager:
    """
    Backward-compatible wrapper that delegates to enhancements.config.secure_credentials
    """
    def __init__(self, config_dir: str = "config"):
        self.config_dir = config_dir
        if _KEYRING_OK and KeyringCredentialsManager:
            self._keyring_mgr = KeyringCredentialsManager()
        else:
            self._keyring_mgr = None
            logger.warning("OS Keyring credential manager not available")

    def save_credentials(self, api_key: str, client_code: str, password: str, totp_secret: str = "") -> Tuple[bool, str]:
        if self._keyring_mgr:
            creds = {
                "api_key": api_key.strip(),
                "client_id": client_code.strip(),
                "password": password.strip(),
                "totp_token": (totp_secret or "").strip()
            }
            success = self._keyring_mgr.store_credentials("default", creds)
            if success:
                logger.info("Credentials saved securely to OS keyring")
                return True, "Saved to OS Keyring"
            else:
                return False, "Keyring save failed"
        return False, "Keyring unavailable"

    def load_credentials(self) -> Tuple[bool, Dict[str, Any]]:
        if self._keyring_mgr:
            creds = self._keyring_mgr.retrieve_credentials("default")
            if creds:
                # Map client_id -> client_code for backward compatibility
                if "client_id" in creds and "client_code" not in creds:
                    creds["client_code"] = creds["client_id"]
                logger.info("Credentials loaded securely from OS keyring")
                return True, creds
        return False, {}
