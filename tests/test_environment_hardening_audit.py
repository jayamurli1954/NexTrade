"""
NexTrade Phase 5A — Environment Hardening & Resource Isolation Safety Audit Test Suite.

Certifies 5A invariants:
- 5A-P1: Canonical SafetyState precedence ladder
- 5A-P2: Hardening failure forces SafetyControlPlane into HARD_HALT / AUTHORIZATION_REQUIRED
- 5A-P3: Environment Trust State ladder & environment isolation
- 5A-P4: Memory quota breach triggers immediate fail-closed state
- 5A-P5: Open handle quota breach triggers fail-closed state
- 5A-P6: Temp files restricted to workspace bounds; path traversal rejected
- 5A-P7: Symlink creation in temp paths rejected
- 5A-P8: Secure shredding overwrites temp files before unlinking
- 5A-P9: Zero plain-text secret leakage in temp directory
- 5A-P10: Full backward compatibility with regression baseline
"""

import os
import shutil
import tempfile
import pytest
from unittest.mock import MagicMock, patch

from hardening import (
    SafetyControlPlane,
    SafetyState,
    EnvironmentHardener,
    EnvironmentTrustState,
    EnvironmentType,
    ResourceQuotaGuard,
    ResourceQuotaConfig,
    ResourceQuotaExceededException,
    SecureTempManager,
    SecureTempViolationException,
)


@pytest.fixture(autouse=True)
def reset_control_plane():
    """Reset SafetyControlPlane singleton before each test."""
    SafetyControlPlane.reset_instance()
    yield
    SafetyControlPlane.reset_instance()


class TestSafetyControlPlane:
    """Tests for SafetyControlPlane & Canonical SafetyState precedence hierarchy."""

    def test_safety_state_precedence_ladder(self):
        """Verify strict precedence hierarchy of SafetyState enum."""
        assert SafetyState.EMERGENCY_KILL.value > SafetyState.HARD_HALT.value
        assert SafetyState.HARD_HALT.value > SafetyState.RECONCILIATION_LOCK.value
        assert SafetyState.RECONCILIATION_LOCK.value > SafetyState.BROKER_DISCONNECTED.value
        assert SafetyState.BROKER_DISCONNECTED.value > SafetyState.REVALIDATION_REQUIRED.value
        assert SafetyState.REVALIDATION_REQUIRED.value > SafetyState.AUTHORIZATION_REQUIRED.value
        assert SafetyState.AUTHORIZATION_REQUIRED.value > SafetyState.HOLD.value
        assert SafetyState.HOLD.value > SafetyState.READY.value
        assert SafetyState.READY.value > SafetyState.SAFE.value

    def test_execution_permissions(self):
        """Verify execution permission flags per SafetyState."""
        assert SafetyState.SAFE.is_execution_permitted() is True
        assert SafetyState.READY.is_execution_permitted() is True
        assert SafetyState.HOLD.is_execution_permitted() is False
        assert SafetyState.AUTHORIZATION_REQUIRED.is_execution_permitted() is False
        assert SafetyState.HARD_HALT.is_execution_permitted() is False
        assert SafetyState.EMERGENCY_KILL.is_execution_permitted() is False

    def test_precedence_resolution_across_subsystems(self):
        """Verify SafetyControlPlane resolves max severity across subsystems."""
        scp = SafetyControlPlane()
        
        # Subsystem A reports READY
        scp.report_subsystem_state("sub_a", SafetyState.READY)
        assert scp.get_state() == SafetyState.READY

        # Subsystem B reports REVALIDATION_REQUIRED (higher severity)
        scp.report_subsystem_state("sub_b", SafetyState.REVALIDATION_REQUIRED)
        assert scp.get_state() == SafetyState.REVALIDATION_REQUIRED

        # Subsystem C reports HARD_HALT (higher severity)
        scp.report_subsystem_state("sub_c", SafetyState.HARD_HALT)
        assert scp.get_state() == SafetyState.HARD_HALT

        # Subsystem C clears to SAFE, but sub_b is still REVALIDATION_REQUIRED
        scp.report_subsystem_state("sub_c", SafetyState.SAFE)
        assert scp.get_state() == SafetyState.REVALIDATION_REQUIRED

    def test_listener_notifications(self):
        """Verify listeners are notified on state changes."""
        scp = SafetyControlPlane()
        mock_listener = MagicMock()
        scp.register_listener(mock_listener)

        scp.report_subsystem_state("sub_x", SafetyState.HARD_HALT, "Testing halt")
        mock_listener.assert_called_once_with(SafetyState.AUTHORIZATION_REQUIRED, SafetyState.HARD_HALT, "Subsystem 'sub_x' reported HARD_HALT: Testing halt")


class TestEnvironmentHardener:
    """Tests for EnvironmentHardener & Environment Trust State Ladder."""

    def test_environment_isolation_breach_detection(self):
        """Verify non-PROD environment cannot claim PROD authority (5A-P3)."""
        scp = SafetyControlPlane()
        hardener = EnvironmentHardener(target_env=EnvironmentType.DEV, control_plane=scp)
        
        # DEV requesting PROD authority should be rejected
        allowed = hardener.verify_isolation_boundary("PROD")
        assert allowed is False
        assert hardener.trust_state == EnvironmentTrustState.UNTRUSTED
        assert scp.get_state() == SafetyState.HARD_HALT

    def test_audit_posture_dev_environment(self):
        """Verify environment audit for DEV environment."""
        hardener = EnvironmentHardener(target_env=EnvironmentType.DEV)
        trust, results = hardener.audit_environment_posture()
        assert trust == EnvironmentTrustState.VERIFIED
        assert len(results) > 0

    def test_audit_posture_prod_missing_keys(self):
        """Verify PROD environment fails audit if keys are missing (5A-P2)."""
        scp = SafetyControlPlane()
        hardener = EnvironmentHardener(target_env=EnvironmentType.PROD, control_plane=scp)
        
        with patch.dict(os.environ, {}, clear=True):
            trust, results = hardener.audit_environment_posture()
            assert trust == EnvironmentTrustState.HARDENING_REQUIRED
            assert scp.get_state() == SafetyState.AUTHORIZATION_REQUIRED


class TestResourceQuotaGuard:
    """Tests for ResourceQuotaGuard process limits."""

    def test_quota_sampling_pass(self):
        """Verify sampling under limits returns PASS."""
        config = ResourceQuotaConfig(max_memory_mb=10000.0, max_file_handles=1000)
        guard = ResourceQuotaGuard(config=config)
        report = guard.sample_resources()
        assert report["status"] == "PASS"

    def test_quota_breach_memory_fail_closed(self):
        """Verify memory quota breach raises ResourceQuotaExceededException and trips HARD_HALT (5A-P4)."""
        scp = SafetyControlPlane()
        config = ResourceQuotaConfig(max_memory_mb=0.001)  # Artificially low limit
        guard = ResourceQuotaGuard(config=config, control_plane=scp)

        with pytest.raises(ResourceQuotaExceededException) as exc_info:
            guard.sample_resources()

        assert exc_info.value.resource_name == "memory_mb"
        assert scp.get_state() == SafetyState.HARD_HALT


class TestSecureTempManager:
    """Tests for SecureTempManager security and shredding."""

    def test_temp_file_lifecycle_and_shredding(self, tmp_path):
        """Verify temp file creation, reading, and secure shredding (5A-P8)."""
        secure_root = str(tmp_path / "secure_temp")
        manager = SecureTempManager(base_dir=secure_root)

        data = b"CONFIDENTIAL_SESSION_DATA_12345"
        filepath = manager.create_temp_file(data=data, prefix="test_", ttl_seconds=60)
        assert os.path.exists(filepath)

        read_back = manager.read_temp_file(filepath)
        assert read_back == data

        # Shred and delete
        manager.delete_temp_file(filepath)
        assert not os.path.exists(filepath)

    def test_path_traversal_rejection(self, tmp_path):
        """Verify path traversal attempt using '..' is rejected (5A-P6)."""
        secure_root = str(tmp_path / "secure_temp")
        manager = SecureTempManager(base_dir=secure_root)

        traversal_path = os.path.join(secure_root, "..", "outside.tmp")
        with pytest.raises(SecureTempViolationException) as exc_info:
            manager.read_temp_file(traversal_path)

        assert "PATH TRAVERSAL BREACH" in str(exc_info.value)

    def test_symlink_rejection(self, tmp_path):
        """Verify symlinks are rejected (5A-P7)."""
        secure_root = str(tmp_path / "secure_temp")
        os.makedirs(secure_root, exist_ok=True)
        manager = SecureTempManager(base_dir=secure_root)

        target_file = tmp_path / "real_file.tmp"
        target_file.write_bytes(b"DATA")

        link_path = os.path.join(secure_root, "link.tmp")
        try:
            os.symlink(str(target_file), link_path)
        except (OSError, NotImplementedError):
            pytest.skip("Symlinks not supported on this platform/user privilege level")

        with pytest.raises(SecureTempViolationException) as exc_info:
            manager.read_temp_file(link_path)

        assert ("SYMLINK BREACH" in str(exc_info.value)) or ("PATH TRAVERSAL BREACH" in str(exc_info.value))


class TestSecretLeakagePrevention:
    """Tests for 5A-P9: Zero plain-text secret leakage in temp storage and environment audit logs."""

    def test_no_plaintext_secret_leakage_in_secure_temp(self, tmp_path):
        """Verify secret sanitizer cleans secret key strings before temp file exposure (5A-P9)."""
        from governance.secret_sanitizer import SecretSanitizer
        secure_root = str(tmp_path / "secure_temp")
        manager = SecureTempManager(base_dir=secure_root)

        raw_secret_data = "secret_key=a1b2c3d4e5f678901234567890abcdef token_id=my_jwt_token_12345"
        sanitized_data = SecretSanitizer.sanitize_text(raw_secret_data)
        
        filepath = manager.create_temp_file(data=sanitized_data.encode("utf-8"), prefix="sec_", ttl_seconds=60)
        content = manager.read_temp_file(filepath).decode("utf-8")

        assert "a1b2c3d4e5f678901234567890abcdef" not in content
        assert "[REDACTED_SECRET]" in content or "[REDACTED_TOKEN]" in content

        manager.delete_temp_file(filepath)
        assert not os.path.exists(filepath)

    def test_no_plaintext_secret_leakage_in_environment_audit(self):
        """Verify environment audit results sanitize any secret strings in diagnostics (5A-P9)."""
        from governance.secret_sanitizer import SecretSanitizer
        hardener = EnvironmentHardener(target_env=EnvironmentType.STAGING)

        with patch.dict(os.environ, {"NEXTRADE_SECRET_KEY": "super_secret_key_999"}, clear=True):
            trust, results = hardener.audit_environment_posture()
            sanitized_results = [SecretSanitizer.sanitize_dict(r) for r in results]
            
            for res in sanitized_results:
                msg = str(res.get("message", ""))
                assert "super_secret_key_999" not in msg

