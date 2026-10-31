"""CLI: run Validation Phase evidence pack (VAL-A … VAL-H).

Usage:
  python -m research.run_validation_phase
  python -m research.run_validation_phase --tracks VAL-A,VAL-H
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from research.validation_phase import run_validation_phase

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("RunValidationPhase")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="NexTrade Validation Phase (evidence only)")
    ap.add_argument("--tracks", default=None, help="Comma-separated tracks e.g. VAL-A,VAL-B")
    args = ap.parse_args(argv)
    tracks = [t.strip() for t in args.tracks.split(",")] if args.tracks else None
    report = run_validation_phase(tracks=tracks)
    logger.info(
        "Validation Phase %s pass=%s partial=%s fail=%s",
        report["overall"],
        report["pass_count"],
        report["partial_count"],
        report["fail_count"],
    )
    print(json.dumps(report, indent=2))
    return 0 if report["overall"] in ("PASS", "PARTIAL") else 1


if __name__ == "__main__":
    sys.exit(main())
