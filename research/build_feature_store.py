"""
Build Feature Store (Sprint B1).

Usage:
  python -m research.build_feature_store --fundamentals-only
  python -m research.build_feature_store --with-technicals
  python -m research.build_feature_store --with-technicals --max-symbols 5
"""

from __future__ import annotations

import argparse
import json
import logging

from research.feature_registry import bootstrap_registry
from research.feature_store import FeatureStore
from research.factor_score_store import FactorScoreStore

logger = logging.getLogger("BuildFeatureStore")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build SanMitra Feature Store (B1)")
    parser.add_argument("--fundamentals-only", action="store_true", help="B1b PIT fundamentals only")
    parser.add_argument("--with-technicals", action="store_true", help="B1c daily tech + PIT fund + VIX")
    parser.add_argument("--max-symbols", type=int, default=0, help="Limit symbols (debug)")
    parser.add_argument("--symbols", type=str, default="", help="Comma-separated symbols to (re)build")
    parser.add_argument("--sleep", type=float, default=0.35, help="Sleep between yfinance calls")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)

    if not args.fundamentals_only and not args.with_technicals:
        args.with_technicals = True

    store = FeatureStore()
    reg = bootstrap_registry(store.registry_path)
    logger.info("Registry saved: %s (%s features)", reg.path, len(reg.entries))

    factors = FactorScoreStore()
    symbol_list = [s.strip().upper() for s in args.symbols.split(",") if s.strip()] or None
    if args.fundamentals_only and not args.with_technicals:
        manifest = store.backfill_fundamentals_pit(factor_store=factors)
    else:
        manifest = store.backfill_technicals_and_fundamentals(
            symbols=symbol_list,
            factor_store=factors,
            sleep_s=args.sleep,
            max_symbols=args.max_symbols or None,
        )
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
