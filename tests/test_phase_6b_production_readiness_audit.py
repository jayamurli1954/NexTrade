"""
NexTrade Phase 6B — Production Deployment Readiness & Infrastructure Hardening Test Suite.

Verifies all 15 production readiness invariants (6B-P1 through 6B-P15).
"""

import os
import pytest
from hardening import SafetyControlPlane, SafetyState
from hardening.production_readiness_checker import ProductionReadinessChecker
from hardening.environment_hardener import EnvironmentHardener, EnvironmentType
from governance.secret_vault import SecretVault
from observability.tamper_evident_logger import TamperEvidentLogger


@pytest.fixture(autouse=True)
def reset_control_plane():
    """Reset SafetyControlPlane before each test."""
    SafetyControlPlane.reset_instance()
    yield
    SafetyControlPlane.reset_instance()


class TestPhase6BProductionReadinessAudit:
    """Test suite certifying 6B-P1 through 6B-P15 invariants."""

    def test_6b_p1_environment_isolation(self):
        """Verify 6B-P1 production environment isolation."""
        checker = ProductionReadinessChecker()
        res = checker.verify_6b_p1_environment_isolation()
        assert res["status"] == "PASS"
        assert res["invariant_id"] == "6B-P1"

    def test_6b_p2_os_filesystem_security(self):
        """Verify 6B-P2 OS privileges and filesystem security."""
        checker = ProductionReadinessChecker()
        res = checker.verify_6b_p2_os_filesystem_security()
        assert res["status"] == "PASS"
        assert res["invariant_id"] == "6B-P2"

    def test_6b_p3_secret_vaulting_and_qualified_memory(self):
        """Verify 6B-P3 SecretVault initialisation and qualified bytearray zeroing."""
        checker = ProductionReadinessChecker()
        res = checker.verify_6b_p3_secret_vaulting()
        assert res["status"] == "PASS"
        assert res["qualification"]["zero_disk_plaintext_verified"] is True
        assert res["qualification"]["bytearray_buffer_scrubbing_supported"] is True

        # Verify bytearray zeroing directly
        buf = bytearray(b"secret_bytes_123")
        assert SecretVault.zero_bytearray_buffer(buf) is True
        assert all(b == 0 for b in buf)

    def test_6b_p4_subprocess_env_scrubbing_process_boundary(self):
        """Verify 6B-P4 environment scrubbing at actual process boundary."""
        is_scrubbed = EnvironmentHardener.verify_subprocess_environment_scrubbing()
        assert is_scrubbed is True

    def test_6b_p5_database_wal_mode_and_backup(self):
        """Verify 6B-P5 SQLite WAL mode and pre-flight snapshot backup."""
        checker = ProductionReadinessChecker()
        res = checker.verify_6b_p5_database_wal_and_backup()
        assert res["status"] == "PASS"
        assert res["journal_mode"] == "WAL"
        assert res["backup_created"] is True

    def test_6b_p6_tamper_evident_logging_hash_chain(self):
        """Verify 6B-P6 SHA-256 tamper-evident log hash chaining."""
        checker = ProductionReadinessChecker()
        res = checker.verify_6b_p6_tamper_evident_logging()
        assert res["status"] == "PASS"
        assert res["integrity_verified"] is True

    def test_6b_p7_tls_pinning_readiness(self):
        """Verify 6B-P7 TLS certificate pinning configuration readiness."""
        checker = ProductionReadinessChecker()
        res = checker.verify_6b_p7_tls_pinning_readiness()
        assert res["status"] == "PASS"
        assert res["active_pin_present"] is True
        assert res["backup_pin_present"] is True

    def test_6b_p8_alert_broadcaster(self):
        """Verify 6B-P8 telemetry alert engine broadcaster."""
        checker = ProductionReadinessChecker()
        res = checker.verify_6b_p8_alert_broadcaster()
        assert res["status"] == "PASS"

    def test_6b_p9_kill_switch_precedence(self):
        """Verify 6B-P9 4-tier emergency kill-switch precedence ladder."""
        checker = ProductionReadinessChecker()
        res = checker.verify_6b_p9_kill_switch_precedence()
        assert res["status"] == "PASS"
        assert res["final_state"] == "EMERGENCY_KILL"

    def test_6b_p10_process_supervision_pid_locks(self):
        """Verify 6B-P10 process supervision and PID lock management."""
        checker = ProductionReadinessChecker()
        res = checker.verify_6b_p10_process_supervision_and_recovery()
        assert res["status"] == "PASS"
        assert res["pid_lock_active"] is True

    def test_6b_p11_config_immutability(self):
        """Verify 6B-P11 configuration schema hash immutability."""
        checker = ProductionReadinessChecker()
        res = checker.verify_6b_p11_config_immutability()
        assert res["status"] == "PASS"
        assert len(res["config_hash"]) == 64

    def test_6b_p12_deployment_rollback_snapshots(self):
        """Verify 6B-P12 deployment rollback and snapshot availability."""
        checker = ProductionReadinessChecker()
        res = checker.verify_6b_p12_deployment_rollback()
        assert res["status"] == "PASS"
        assert res["snapshots_available"] > 0

    def test_6b_p13_disaster_recovery_pipeline(self):
        """Verify 6B-P13 disaster recovery pipeline readiness."""
        checker = ProductionReadinessChecker()
        res = checker.verify_6b_p13_disaster_recovery()
        assert res["status"] == "PASS"

    def test_6b_p14_operational_runbook(self):
        """Verify 6B-P14 operational runbook pre-flight execution."""
        checker = ProductionReadinessChecker()
        res = checker.verify_6b_p14_operational_runbook()
        assert res["status"] == "PASS"

    def test_6b_p15_production_manifest_generation(self):
        """Verify 6B-P15 complete production readiness manifest generation."""
        checker = ProductionReadinessChecker()
        all_passed, manifest = checker.execute_full_6b_readiness_audit()
        assert all_passed is True
        assert manifest["invariants_total"] == 15
        assert manifest["invariants_passed"] == 15
        assert manifest["signing_status"] == "CERTIFICATION_SIGNING_PENDING"
        assert len(manifest["manifest_sha256"]) == 64
