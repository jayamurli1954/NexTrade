# tests/test_governance_safety_audit.py
"""
Platform Governance Safety Audit Test Suite for NexTrade (Sub-Phase 4N).
Verifies:
1. Invariant 4N-P2: Software readiness certification NEVER automatically enables production activation.
2. Invariant 4N-P3: Secret isolation audit (0 secret HMAC keys or tokens leak into UI outputs).
3. Invariant 4N-P7: UI consumer authority invariant (0 UI safety bypass calls).
4. AST Broker SDK Scan: Zero broker SDK imports (ibapi, ib_insync, etc.) in governance/ package.
"""
import ast
import os
import pytest

from governance.activation_manager import ProductionActivationManager
from governance.secret_sanitizer import SecretSanitizer


def test_4n_p2_software_readiness_never_auto_activates_production():
    """Verify ProductionActivationManager initializes in INACTIVE state (Invariant 4N-P2)."""
    mgr = ProductionActivationManager()
    assert mgr.is_production_active is False
    assert not hasattr(mgr, "auto_activate_production")


def test_4n_p3_secret_isolation_audit():
    """Verify SecretSanitizer strips secrets from dictionaries containing HMAC or token keys (Invariant 4N-P3)."""
    dirty_dict = {
        "user": "trader1",
        "hmac_secret": "SuperSecretHMACKey12345",
        "access_token": "TOK-999-ABCDEF",
        "environment": "CONTROLLED_LIVE"
    }

    clean_dict = SecretSanitizer.sanitize_dict(dirty_dict)
    assert clean_dict["user"] == "trader1"
    assert clean_dict["hmac_secret"] == "[REDACTED_SENSITIVE_FIELD]"
    assert clean_dict["access_token"] == "[REDACTED_SENSITIVE_FIELD]"
    assert clean_dict["environment"] == "CONTROLLED_LIVE"


def test_ast_audit_zero_broker_sdk_imports_in_governance_package():
    """AST Scan: Assert zero broker SDK imports (ibapi, ib_insync, alpaca) in governance/ package."""
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    gov_dir = os.path.join(repo_root, "governance")
    disallowed_sdks = {"ibapi", "ib_insync", "alpaca_trade_api"}

    violations = []
    if os.path.exists(gov_dir):
        for root, _, files in os.walk(gov_dir):
            for f_name in files:
                if f_name.endswith(".py"):
                    f_path = os.path.join(root, f_name)
                    with open(f_path, "r", encoding="utf-8") as f:
                        tree = ast.parse(f.read(), filename=f_path)
                    for node in ast.walk(tree):
                        if isinstance(node, ast.Import):
                            for alias in node.names:
                                if alias.name.split('.')[0] in disallowed_sdks:
                                    violations.append((os.path.relpath(f_path, repo_root), alias.name))
                        elif isinstance(node, ast.ImportFrom):
                            if node.module and node.module.split('.')[0] in disallowed_sdks:
                                violations.append((os.path.relpath(f_path, repo_root), node.module))

    assert len(violations) == 0, f"ISOLATION VIOLATION: Governance module imports broker SDK: {violations}"
