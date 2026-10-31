"""CLI: run DVE-1 full validation pack.

Usage:
  python -m research.run_data_validation
"""

from __future__ import annotations

import json
import logging
import sys

from research.data_validation import run_full_validation

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("RunDataValidation")


def main() -> int:
    result = run_full_validation()
    logger.info(
        "Validation %s errors=%s issues=%s path=%s",
        "PASS" if result["ok"] else "FAIL",
        result["error_count"],
        result["issue_count"],
        result["validation_path"],
    )
    print(json.dumps({"ok": result["ok"], "release_readiness": result["release_readiness"]}, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
