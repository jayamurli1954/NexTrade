"""
NexTrade Phase 5A / 6B — Environment Hardener & Trust State Ladder.

Manages EnvironmentTrustState (UNTRUSTED -> HARDENING_REQUIRED -> HARDENED -> VERIFIED -> CERTIFIED)
and enforces environment isolation across DEV, TEST, SANDBOX, PAPER, STAGING, and PROD.
Adds 6B subprocess boundary environment variable scrubbing verification.
"""

from enum import Enum, IntEnum
import os
import sys
import subprocess
import logging
from typing import Dict, List, Optional, Tuple, Any

from .safety_control_plane import SafetyControlPlane, SafetyState

logger = logging.getLogger("EnvironmentHardener")


class EnvironmentTrustState(IntEnum):
    """
    Environment Trust State Ladder.
    Only CERTIFIED trust state is eligible for production readiness gates.
    """
    UNTRUSTED = 0
    HARDENING_REQUIRED = 1
    HARDENED = 2
    VERIFIED = 3
    CERTIFIED = 4


class EnvironmentType(str, Enum):
    """Supported NexTrade operational environments."""
    DEV = "DEV"
    TEST = "TEST"
    SANDBOX = "SANDBOX"
    PAPER = "PAPER"
    STAGING = "STAGING"
    PROD = "PROD"


class EnvironmentHardeningViolationException(Exception):
    """Raised when environment hardening checks fail critical security checks."""
    pass


class EnvironmentHardener:
    """
    Enforces environment security posture, environment type isolation, and
    maintains the EnvironmentTrustState ladder.
    """

    SENSITIVE_ENV_PATTERNS = ("SECRET", "TOKEN", "PASSWORD", "KEY", "CREDENTIAL", "AUTH", "PRIVATE")

    def __init__(self, target_env: Optional[EnvironmentType] = None, control_plane: Optional[SafetyControlPlane] = None) -> None:
        self.control_plane = control_plane or SafetyControlPlane()
        self._detected_env = self._detect_environment(target_env)
        self._trust_state = EnvironmentTrustState.UNTRUSTED
        self._audit_results: List[Dict[str, Any]] = []

    def _detect_environment(self, override_env: Optional[EnvironmentType] = None) -> EnvironmentType:
        if override_env:
            return override_env
        env_str = os.environ.get("NEXTRADE_ENV", "DEV").upper()
        try:
            return EnvironmentType(env_str)
        except ValueError:
            logger.warning("Unrecognized NEXTRADE_ENV '%s', defaulting to DEV", env_str)
            return EnvironmentType.DEV

    @property
    def current_environment(self) -> EnvironmentType:
        return self._detected_env

    @property
    def trust_state(self) -> EnvironmentTrustState:
        return self._trust_state

    def verify_isolation_boundary(self, requested_authority: str) -> bool:
        """
        Verify that non-PROD environments cannot request PROD execution authority.
        """
        if requested_authority.upper() == "PROD" and self._detected_env != EnvironmentType.PROD:
            logger.critical("ISOLATION BREACH: Environment %s attempted to claim PROD authority!", self._detected_env.value)
            self._trust_state = EnvironmentTrustState.UNTRUSTED
            self.control_plane.report_subsystem_state(
                "environment_hardener",
                SafetyState.HARD_HALT,
                f"Isolation breach: {self._detected_env.value} requested PROD authority"
            )
            return False
        return True

    @classmethod
    def scrub_process_environment(cls, base_env: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """
        Scrub sensitive environment variables from dictionary prior to spawning child processes.
        """
        source = dict(base_env or os.environ)
        clean_env = {}
        for k, v in source.items():
            k_upper = k.upper()
            if any(pat in k_upper for pat in cls.SENSITIVE_ENV_PATTERNS):
                if k_upper not in ("NEXTRADE_ENV", "PATH", "PYTHONPATH"):
                    continue
            clean_env[k] = v
        return clean_env

    @classmethod
    def verify_subprocess_environment_scrubbing(cls, test_secret_val: str = "SUPER_SECRET_KEY_999") -> bool:
        """
        Verify environment scrubbing at actual process boundary (Phase 6B-P4).
        Spawns a python child process passing scrubbed env and verifies zero secret inheritance.
        """
        # Temporarily inject secret into current process env
        test_key = "NEXTRADE_TEST_SECRET_API_KEY"
        os.environ[test_key] = test_secret_val

        try:
            clean_env = cls.scrub_process_environment()
            cmd = [sys.executable, "-c", f"import os; print(os.environ.get('{test_key}', 'ABSENT'))"]
            res = subprocess.run(cmd, env=clean_env, capture_output=True, text=True, timeout=5)
            output = res.stdout.strip()
            is_scrubbed = (output == "ABSENT") and (test_secret_val not in output)
            return is_scrubbed
        finally:
            os.environ.pop(test_key, None)

    def audit_environment_posture(self) -> Tuple[EnvironmentTrustState, List[Dict[str, Any]]]:
        """
        Runs comprehensive security posture audit:
        1. Checks environment variable sanitization & subprocess boundary scrubbing
        2. Validates debug flags in staging/prod
        3. Validates path permissions
        4. Evaluates isolation boundaries
        """
        self._audit_results = []
        passed_all = True

        # Check 1: PROD / STAGING must not have debug mode enabled
        debug_flag = os.environ.get("NEXTRADE_DEBUG", "0").lower() in ("1", "true", "yes")
        if self._detected_env in (EnvironmentType.STAGING, EnvironmentType.PROD) and debug_flag:
            self._audit_results.append({
                "check": "debug_flag_disabled",
                "status": "FAIL",
                "message": f"Debug mode enabled in {self._detected_env.value} environment"
            })
            passed_all = False
        else:
            self._audit_results.append({
                "check": "debug_flag_disabled",
                "status": "PASS",
                "message": "Debug flag compliant"
            })

        # Check 2: Secret key presence check for STAGING / PROD
        if self._detected_env in (EnvironmentType.STAGING, EnvironmentType.PROD):
            if "NEXTRADE_SECRET_KEY" not in os.environ and "NEXTRADE_KMS_KEY_ID" not in os.environ:
                self._audit_results.append({
                    "check": "production_key_configured",
                    "status": "FAIL",
                    "message": "Missing production KMS/Secret key in environment"
                })
                passed_all = False
            else:
                self._audit_results.append({
                    "check": "production_key_configured",
                    "status": "PASS",
                    "message": "Production secret/KMS key configured"
                })

        # Check 3: Subprocess environment boundary scrubbing check (6B-P4)
        scrubbing_pass = self.verify_subprocess_environment_scrubbing()
        if not scrubbing_pass:
            self._audit_results.append({
                "check": "subprocess_env_scrubbing",
                "status": "FAIL",
                "message": "Subprocess environment boundary scrubbing failed"
            })
            passed_all = False
        else:
            self._audit_results.append({
                "check": "subprocess_env_scrubbing",
                "status": "PASS",
                "message": "Subprocess environment boundary scrubbing verified"
            })

        # Check 4: Check Python optimization / sandbox execution mode
        sys_path_writable = os.access(sys.prefix, os.W_OK) if hasattr(sys, 'prefix') else False
        if self._detected_env == EnvironmentType.PROD and sys_path_writable:
            logger.warning("PROD environment runtime directory is writable by current process")
            self._audit_results.append({
                "check": "runtime_write_protection",
                "status": "WARN",
                "message": "Runtime directory is writable"
            })

        # Transition trust state
        if not passed_all:
            self._trust_state = EnvironmentTrustState.HARDENING_REQUIRED
            self.control_plane.report_subsystem_state(
                "environment_hardener",
                SafetyState.AUTHORIZATION_REQUIRED,
                f"Environment hardening check failed for {self._detected_env.value}"
            )
        else:
            if self._detected_env in (EnvironmentType.STAGING, EnvironmentType.PROD):
                self._trust_state = EnvironmentTrustState.CERTIFIED
            else:
                self._trust_state = EnvironmentTrustState.VERIFIED
            
            self.control_plane.report_subsystem_state(
                "environment_hardener",
                SafetyState.READY,
                f"Environment {self._detected_env.value} hardened and verified ({self._trust_state.name})"
            )

        return self._trust_state, self._audit_results

    def enforce_hardening(self) -> None:
        """
        Enforce hardening policy. Raises EnvironmentHardeningViolationException if trust state is UNTRUSTED.
        """
        trust, results = self.audit_environment_posture()
        if trust in (EnvironmentTrustState.UNTRUSTED, EnvironmentTrustState.HARDENING_REQUIRED):
            failed = [r['message'] for r in results if r['status'] == 'FAIL']
            err_msg = f"Environment hardening failed for {self._detected_env.value}: {', '.join(failed)}"
            logger.error(err_msg)
            raise EnvironmentHardeningViolationException(err_msg)
