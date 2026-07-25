# tests/test_broker_isolation.py
"""
Automated Architectural Isolation Test for NexTrade (Sub-Phase 4B).
Enforces absolute physical isolation between NexTrade Core Subsystems (core, execution, risk, protection, contracts)
and concrete external broker SDKs (e.g., ibapi, ib_insync, alpaca_trade_api, ccxt).
"""
import ast
import os
import pytest

FORBIDDEN_BROKER_SDKS = {
    "ibapi",
    "ib_insync",
    "alpaca",
    "alpaca_trade_api",
    "ccxt",
    "InteractiveBrokers",
}

CORE_DIRS_TO_SCAN = [
    "core",
    "execution",
    "risk",
    "protection",
    "contracts",
]


def test_no_broker_sdk_imports_in_core_subsystems():
    """
    Scans all .py files in core directories and asserts 0 imports of external broker SDKs.
    """
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    violations = []

    for core_dir in CORE_DIRS_TO_SCAN:
        dir_path = os.path.join(repo_root, core_dir)
        if not os.path.exists(dir_path):
            continue

        for root, _, files in os.walk(dir_path):
            for file in files:
                if file.endswith(".py"):
                    file_path = os.path.join(root, file)
                    rel_path = os.path.relpath(file_path, repo_root)

                    with open(file_path, "r", encoding="utf-8") as f:
                        try:
                            tree = ast.parse(f.read(), filename=file_path)
                        except SyntaxError:
                            continue

                    for node in ast.walk(tree):
                        if isinstance(node, ast.Import):
                            for alias in node.names:
                                top_package = alias.name.split(".")[0]
                                if top_package in FORBIDDEN_BROKER_SDKS:
                                    violations.append((rel_path, node.lineno, alias.name))
                        elif isinstance(node, ast.ImportFrom):
                            if node.module:
                                top_package = node.module.split(".")[0]
                                if top_package in FORBIDDEN_BROKER_SDKS:
                                    violations.append((rel_path, node.lineno, node.module))

    assert len(violations) == 0, (
        f"ARCHITECTURAL VIOLATION: Core subsystem files import external broker SDKs:\n"
        + "\n".join([f"  - {path}:{line} imports '{mod}'" for path, line, mod in violations])
    )
