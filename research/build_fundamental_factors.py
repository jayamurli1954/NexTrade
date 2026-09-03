"""
Build current + historical fundamental factor scores from local Screener store.

Usage:
  python -m research.build_fundamental_factors
  python -m research.build_fundamental_factors --no-historical
"""

from __future__ import annotations

import argparse
import logging
from typing import Any, Dict

from research.factor_score_store import FactorScoreStore, utc_now_iso
from research.fundamental_factor_engine import (
    compute_all_current,
    compute_all_historical,
    load_factor_config,
    scores_to_symbol_record,
)
from research.fundamentals_store import FundamentalsStore, default_fundamentals_dir

logger = logging.getLogger("BuildFundamentalFactors")


def build(*, include_historical: bool = True) -> Dict[str, Any]:
    root = default_fundamentals_dir()
    raw = FundamentalsStore(root)
    store = FactorScoreStore(root)
    cfg = load_factor_config()

    current = compute_all_current(raw, config=cfg)
    current_payload = {
        "built_at": utc_now_iso(),
        "config_version": cfg.get("version"),
        "symbol_count": len(current),
        "symbols": {sym: scores_to_symbol_record(fs) for sym, fs in sorted(current.items())},
    }
    store.save_current(current_payload)

    hist_years = []
    if include_historical:
        by_year = compute_all_historical(raw, config=cfg)
        for year, mapping in sorted(by_year.items()):
            hist_payload = {
                "fiscal_year": year,
                "built_at": utc_now_iso(),
                "config_version": cfg.get("version"),
                "symbol_count": len(mapping),
                "symbols": {sym: scores_to_symbol_record(fs) for sym, fs in sorted(mapping.items())},
            }
            store.save_historical_year(year, hist_payload)
            hist_years.append(year)

    scored = sum(1 for fs in current.values() if fs.overall_fundamental is not None)
    manifest = {
        "built_at": utc_now_iso(),
        "config_version": cfg.get("version"),
        "current_symbol_count": len(current),
        "current_scored_count": scored,
        "historical_years": hist_years,
        "note": "Research-only Fundamental Intelligence Layer FI-1. Not execution authority.",
    }
    store.save_manifest(manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Build fundamental factor scores (FI-1)")
    parser.add_argument("--no-historical", action="store_true", help="Skip historical year files")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)
    manifest = build(include_historical=not args.no_historical)
    print(
        f"Built current={manifest['current_scored_count']}/{manifest['current_symbol_count']} "
        f"historical_years={len(manifest['historical_years'])}"
    )


if __name__ == "__main__":
    main()
