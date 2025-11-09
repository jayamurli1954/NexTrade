"""
Secure Credentials Manager
CRITICAL SECURITY ENHANCEMENT

Replaces plain-text JSON credential storage with OS keyring encryption.

Installation:
    pip install keyring cryptography

Usage:
    from enhancements.config.secure_credentials import SecureCredentialsManager

    mgr = SecureCredentialsManager()

    # Store credentials
    mgr.store_credentials("myuser", {
        "api_key": "xxx",
        "client_id": "yyy",
        "password": "zzz",
        "totp_secret": "aaa"
    })

    # Retrieve credentials
    creds = mgr.retrieve_credentials("myuser")
"""

import json
import keyring
from cryptography.fernet import Fernet
from typing import Dict, Optional
import logging

logger = logging.getLogger("SecureCredentials")


class SecureCredentialsManager:
    """
    Secure credential storage using OS keyring + Fernet encryption

    Features:
    - Uses OS-native credential storage (Keychain/Credential Manager/Secret Service)
    - Encrypts credentials before storing
    - Never stores credentials in plain text files
    - Automatic cleanup on deletion
    """

    SERVICE_NAME = "NexTrade_SecureBot"

    def __init__(self):
        logger.info("Initialized secure credentials manager")

    def store_credentials(self, user_id: str, credentials: Dict[str, str]) -> bool:
        """
        Store encrypted credentials in OS keyring

        Args:
            user_id: Unique identifier for this credential set
            credentials: Dict containing api_key, client_id, password, totp_secret

        Returns:
            bool: True if successful
        """
        try:
            # Generate encryption key
            key = Fernet.generate_key()
            cipher = Fernet(key)

            # Encrypt credentials
            credentials_json = json.dumps(credentials)
            encrypted_creds = cipher.encrypt(credentials_json.encode())

            # Store encrypted credentials in keyring
            keyring.set_password(
                self.SERVICE_NAME,
                f"{user_id}_credentials",
                encrypted_creds.decode()
            )

            # Store encryption key separately
            keyring.set_password(
                self.SERVICE_NAME,
                f"{user_id}_key",
                key.decode()
            )

            logger.info(f"✅ Credentials stored securely for user: {user_id}")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to store credentials: {e}")
            return False

    def retrieve_credentials(self, user_id: str) -> Optional[Dict[str, str]]:
        """
        Retrieve and decrypt credentials from OS keyring

        Args:
            user_id: Unique identifier for credential set

        Returns:
            Dict containing credentials or None if not found
        """
        try:
            # Retrieve encrypted credentials
            encrypted_creds = keyring.get_password(
                self.SERVICE_NAME,
                f"{user_id}_credentials"
            )

            # Retrieve encryption key
            key = keyring.get_password(
                self.SERVICE_NAME,
                f"{user_id}_key"
            )

            if not encrypted_creds or not key:
                logger.warning(f"No credentials found for user: {user_id}")
                return None

            # Decrypt credentials
            cipher = Fernet(key.encode())
            decrypted_creds = cipher.decrypt(encrypted_creds.encode())

            credentials = json.loads(decrypted_creds.decode())

            logger.info(f"✅ Credentials retrieved for user: {user_id}")
            return credentials

        except Exception as e:
            logger.error(f"❌ Failed to retrieve credentials: {e}")
            return None

    def delete_credentials(self, user_id: str) -> bool:
        """
        Delete credentials from keyring

        Args:
            user_id: Unique identifier for credential set

        Returns:
            bool: True if successful
        """
        try:
            keyring.delete_password(
                self.SERVICE_NAME,
                f"{user_id}_credentials"
            )
            keyring.delete_password(
                self.SERVICE_NAME,
                f"{user_id}_key"
            )

            logger.info(f"✅ Credentials deleted for user: {user_id}")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to delete credentials: {e}")
            return False

    def credential_exists(self, user_id: str) -> bool:
        """
        Check if credentials exist for user

        Args:
            user_id: Unique identifier for credential set

        Returns:
            bool: True if credentials exist
        """
        try:
            creds = keyring.get_password(
                self.SERVICE_NAME,
                f"{user_id}_credentials"
            )
            return creds is not None
        except:
            return False


# Migration script from old config.json to secure storage
def migrate_from_config_json(config_path: str = "config.json", user_id: str = "default"):
    """
    Migrate credentials from config.json to secure storage

    Usage:
        python -c "from enhancements.config.secure_credentials import migrate_from_config_json; migrate_from_config_json()"
    """
    import os

    if not os.path.exists(config_path):
        print(f"❌ {config_path} not found")
        return False

    try:
        with open(config_path, 'r') as f:
            config = json.load(f)

        # Extract credentials
        credentials = {
            'api_key': config.get('api_key', ''),
            'client_id': config.get('client_id', ''),
            'password': config.get('password', ''),
            'totp_token': config.get('totp_token', '')
        }

        # Store securely
        mgr = SecureCredentialsManager()
        if mgr.store_credentials(user_id, credentials):
            print(f"✅ Credentials migrated successfully!")
            print(f"⚠️  IMPORTANT: Delete {config_path} manually after verifying login works")
            return True
        else:
            print("❌ Migration failed")
            return False

    except Exception as e:
        print(f"❌ Migration error: {e}")
        return False


if __name__ == "__main__":
    # Example usage
    print("=== Secure Credentials Manager Demo ===\n")

    mgr = SecureCredentialsManager()

    # Store test credentials
    test_creds = {
        "api_key": "test_api_key_123",
        "client_id": "C12345",
        "password": "secure_password",
        "totp_secret": "SECRET123456"
    }

    print("1. Storing credentials...")
    success = mgr.store_credentials("demo_user", test_creds)
    print(f"   Result: {'✅ Success' if success else '❌ Failed'}\n")

    # Retrieve credentials
    print("2. Retrieving credentials...")
    retrieved = mgr.retrieve_credentials("demo_user")
    if retrieved:
        print(f"   ✅ Retrieved: api_key={retrieved['api_key'][:10]}...\n")
    else:
        print("   ❌ Failed to retrieve\n")

    # Check existence
    print("3. Checking if credentials exist...")
    exists = mgr.credential_exists("demo_user")
    print(f"   Result: {'✅ Exists' if exists else '❌ Not found'}\n")

    # Delete credentials
    print("4. Deleting credentials...")
    deleted = mgr.delete_credentials("demo_user")
    print(f"   Result: {'✅ Deleted' if deleted else '❌ Failed'}\n")

    # Verify deletion
    print("5. Verifying deletion...")
    exists_after = mgr.credential_exists("demo_user")
    print(f"   Result: {'✅ Confirmed deleted' if not exists_after else '❌ Still exists'}\n")
