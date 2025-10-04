# config/credentials_manager.py
import os
import json
import logging
from typing import Tuple, Dict, Any

logger = logging.getLogger("CredentialsManager")

try:
    from cryptography.fernet import Fernet
    _CRYPTO_OK = True
except ImportError:
    Fernet = None
    _CRYPTO_OK = False
    logger.warning("cryptography not installed - using plain JSON fallback")


def _user_appdata_dir() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if base:
        return os.path.join(base, "AngelTradingBot", "credentials")
    home = os.path.expanduser("~")
    return os.path.join(home, ".local", "share", "AngelTradingBot", "credentials")


def _ensure_dir(p: str) -> None:
    os.makedirs(p, exist_ok=True)


def _atomic_write_bytes(path: str, data: bytes) -> None:
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


class SecureCredentialsManager:
    def __init__(self, config_dir: str = "config"):
        self.project_config_dir = config_dir
        _ensure_dir(self.project_config_dir)
        self.appdata_dir = _user_appdata_dir()
        _ensure_dir(self.appdata_dir)
        self._key_file = os.path.join(self.appdata_dir, "key.key")
        self._cred_file = os.path.join(self.appdata_dir, "encrypted_credentials.dat")
        self.pointer_file = os.path.join(self.project_config_dir, "credentials_path.txt")
        try:
            with open(self.pointer_file, "w", encoding="utf-8") as f:
                f.write(self._cred_file)
        except Exception:
            pass
        self._fernet = None
        if _CRYPTO_OK:
            try:
                if not os.path.exists(self._key_file):
                    key = Fernet.generate_key()
                    _atomic_write_bytes(self._key_file, key)
                    logger.info("New encryption key generated")
                with open(self._key_file, "rb") as kf:
                    key = kf.read()
                self._fernet = Fernet(key)
            except Exception as e:
                logger.warning(f"Encryption disabled: {e}")
                self._fernet = None
        logger.info("Credentials manager initialized")

    def save_credentials(self, api_key: str, client_code: str, password: str, totp_secret: str = "") -> Tuple[bool, str]:
        payload = {
            "api_key": api_key.strip(),
            "client_code": client_code.strip(),
            "password": password.strip(),
            "totp_secret": (totp_secret or "").strip(),
        }
        try:
            raw = json.dumps(payload).encode("utf-8")
            if self._fernet:
                data = self._fernet.encrypt(raw)
            else:
                data = raw
            _atomic_write_bytes(self._cred_file, data)
            logger.info("Credentials saved")
            return True, "Saved"
        except Exception as e:
            logger.error(f"Save error: {e}")
            return False, f"Failed: {e}"

    def load_credentials(self) -> Tuple[bool, Dict[str, Any]]:
        if not os.path.exists(self._cred_file):
            return False, {}
        try:
            with open(self._cred_file, "rb") as f:
                data = f.read()
            if self._fernet:
                try:
                    raw = self._fernet.decrypt(data)
                except Exception:
                    raw = data  # Fallback if old plain
            else:
                raw = data
            payload = json.loads(raw.decode("utf-8"))
            logger.info("Credentials loaded")
            return True, payload
        except Exception as e:
            logger.error(f"Load error: {e}")
            return False, {}

