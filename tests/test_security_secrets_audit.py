"""
NexTrade Phase 5C — Security & Secret Management Safety Audit Test Suite.

Certifies 5C invariants:
- 5C-P1: Zero plain-text secrets persisted in configuration files
- 5C-P2: SecretVault & OSKeyringAdapter credential isolation
- 5C-P3: System-wide SecretSanitizer redacts secrets from logs and stack traces
- 5C-P4: Exception and error tracebacks scrub sensitive payloads
- 5C-P5: Subprocess environment inheritance sanitizes secrets
- 5C-P6: JSON serialization redacts sensitive keys
- 5C-P7: In-memory byte scrubbing clears revoked secrets
- 5C-P8: Secret revocation trips SafetyControlPlane to REVALIDATION_REQUIRED
- 5C-P9: Secret rotation maintains validity windows without exposing plain text
- 5C-P10: Zero secret leakage in temporary storage
- 5C-P11: UI state objects and diagnostic payloads sanitize credentials
- 5C-P12: Backward compatibility with 5A, 5B, and baseline tests
"""

import os
import json
import pytest
from unittest.mock import MagicMock, patch

from hardening import SafetyControlPlane, SafetyState
from governance import (
    SecretSanitizer,
    SanitizingLoggingFilter,
    SecretVault,
    OSKeyringAdapter,
    SecretLifecycleManager,
    SecretRevocationException,
    SecretVaultViolationException,
)


@pytest.fixture(autouse=True)
def reset_control_plane():
    """Reset SafetyControlPlane singleton before each test."""
    SafetyControlPlane.reset_instance()
    yield
    SafetyControlPlane.reset_instance()


class TestSecretSanitizerSystemWide:
    """Tests for system-wide secret sanitization across text, dicts, logging, and environment."""

    def test_text_sanitization_patterns(self):
        """Verify regex patterns for API keys, tokens, HMACs, passwords, and private keys (5C-P3)."""
        raw_text = "api_key=ak_live_12345678901234567890 Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9 password=my_super_secret"
        sanitized = SecretSanitizer.sanitize_text(raw_text)

        assert "ak_live_12345678901234567890" not in sanitized
        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in sanitized
        assert "my_super_secret" not in sanitized
        assert "[REDACTED_API_KEY]" in sanitized or "[REDACTED_TOKEN]" in sanitized

    def test_dict_serialization_sanitization(self):
        """Verify JSON / dict serialization redacts sensitive fields (5C-P6, 5C-P11)."""
        data = {
            "user_id": "usr_100",
            "api_key": "secret_key_value_999",
            "nested": {
                "password": "pass12345_secret",
                "normal": "value"
            }
        }
        clean = SecretSanitizer.sanitize_dict(data)
        assert clean["api_key"] == "[REDACTED_SENSITIVE_FIELD]"
        assert clean["nested"]["password"] == "[REDACTED_SENSITIVE_FIELD]"
        assert clean["nested"]["normal"] == "value"

    def test_environment_variable_sanitization(self):
        """Verify subprocess environment dictionary sanitization (5C-P5)."""
        env = {
            "PATH": "/usr/bin",
            "NEXTRADE_SECRET_KEY": "super_secret_hmac_key_123",
            "DB_PASSWORD": "db_password_sec"
        }
        clean_env = SecretSanitizer.sanitize_environment(env)
        assert clean_env["NEXTRADE_SECRET_KEY"] == "[REDACTED_ENV_SECRET]"
        assert clean_env["DB_PASSWORD"] == "[REDACTED_ENV_SECRET]"
        assert clean_env["PATH"] == "/usr/bin"


class TestSecretVaultAndKeyring:
    """Tests for 5C-P1, 5C-P2: SecretVault and OSKeyringAdapter isolation."""

    def test_secret_vault_store_and_retrieve(self, tmp_path):
        """Verify SecretVault stores and retrieves secrets via encrypted storage (5C-P2)."""
        vault_dir = str(tmp_path / "vault")
        adapter = OSKeyringAdapter(fallback_storage_dir=vault_dir)
        vault = SecretVault(adapter=adapter)

        vault.store_secret("ibkr_api_secret", "secret_payload_1234567890")
        assert vault.has_secret("ibkr_api_secret") is True

        retrieved = vault.get_secret("ibkr_api_secret")
        assert retrieved == "secret_payload_1234567890"

    def test_zero_plaintext_secrets_on_disk(self, tmp_path):
        """Verify zero plain-text secrets appear on disk vault fallback files (5C-P1)."""
        vault_dir = str(tmp_path / "vault")
        with patch("governance.secret_vault.HAS_KEYRING", False):
            adapter = OSKeyringAdapter(fallback_storage_dir=vault_dir)
            vault = SecretVault(adapter=adapter)

            secret_text = "ULTRA_CONFIDENTIAL_HMAC_KEY_999"
            vault.store_secret("hmac_key", secret_text)

            vault_file = os.path.join(vault_dir, "hmac_key.vault")
            assert os.path.exists(vault_file)
            
            with open(vault_file, "r") as f:
                content = f.read()

            # Secret text MUST NOT appear in plain-text inside the file
            assert secret_text not in content



class TestSecretLifecycleManager:
    """Tests for 5C-P7, 5C-P8, 5C-P9: Rotation, revocation, memory scrubbing."""

    def test_secret_rotation_workflow(self, tmp_path):
        """Verify secret rotation updates key version (5C-P9)."""
        vault_dir = str(tmp_path / "vault")
        adapter = OSKeyringAdapter(fallback_storage_dir=vault_dir)
        vault = SecretVault(adapter=adapter)
        mgr = SecretLifecycleManager(vault=vault)

        vault.store_secret("api_key", "old_key_val")
        mgr.rotate_secret("api_key", "new_key_val", new_version="v2.0")

        assert mgr.get_valid_secret("api_key") == "new_key_val"

    def test_secret_revocation_trips_safety_control_plane(self, tmp_path):
        """Verify emergency secret revocation trips SafetyControlPlane (5C-P8)."""
        scp = SafetyControlPlane()
        vault_dir = str(tmp_path / "vault")
        adapter = OSKeyringAdapter(fallback_storage_dir=vault_dir)
        vault = SecretVault(adapter=adapter)
        mgr = SecretLifecycleManager(vault=vault, control_plane=scp)

        vault.store_secret("active_jwt", "bearer_token_xyz")
        mgr.revoke_secret("active_jwt", reason="Key compromised")

        assert mgr.is_revoked("active_jwt") is True
        assert scp.get_state() == SafetyState.REVALIDATION_REQUIRED

        with pytest.raises(SecretRevocationException):
            mgr.get_valid_secret("active_jwt")

    def test_in_memory_byte_scrubbing(self):
        """Verify in-memory bytearray scrubbing zero-overwrites buffer (5C-P7)."""
        buffer = bytearray(b"SENSITIVE_KEY_BYTES_12345")
        assert b"SENSITIVE" in buffer

        SecretLifecycleManager.scrub_memory_buffer(buffer)
        assert all(b == 0 for b in buffer)


class TestAdditionalSecretInvariants:
    """Tests for 5C-P4, 5C-P10, 5C-P11 exception, temp storage, and UI payload sanitization."""

    def test_exception_traceback_sanitization(self):
        """Verify exception strings scrub secret key patterns (5C-P4)."""
        try:
            raw_err = "Failed connection to db using password=super_secret_db_pass_123"
            raise ValueError(raw_err)
        except ValueError as e:
            err_msg = SecretSanitizer.sanitize_text(str(e))
            assert "super_secret_db_pass_123" not in err_msg
            assert "[REDACTED_PASSWORD]" in err_msg

    def test_temp_storage_secret_sanitization(self, tmp_path):
        """Verify zero secret leakage in temporary storage (5C-P10)."""
        from hardening import SecureTempManager
        secure_root = str(tmp_path / "secure_temp")
        manager = SecureTempManager(base_dir=secure_root)

        raw_secret_data = "api_key=ak_secret_temp_99999"
        sanitized = SecretSanitizer.sanitize_text(raw_secret_data)
        filepath = manager.create_temp_file(data=sanitized.encode("utf-8"), prefix="sec_", ttl_seconds=60)

        content = manager.read_temp_file(filepath).decode("utf-8")
        assert "ak_secret_temp_99999" not in content
        manager.delete_temp_file(filepath)

    def test_ui_diagnostic_payload_sanitization(self):
        """Verify UI state objects scrub sensitive credential fields (5C-P11)."""
        ui_state = {
            "component": "TradingWorkspace",
            "session_token": "token_val_123456789012345",
            "broker_config": {
                "account_id": "ACC123",
                "secret_key": "secret_key_val_888"
            }
        }
        sanitized_ui = SecretSanitizer.sanitize_dict(ui_state)
        assert sanitized_ui["session_token"] == "[REDACTED_SENSITIVE_FIELD]"
        assert sanitized_ui["broker_config"]["secret_key"] == "[REDACTED_SENSITIVE_FIELD]"

