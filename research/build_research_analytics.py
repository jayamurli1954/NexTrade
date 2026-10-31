"""
Build Research Analytics artifacts (Sprint B2).

Usage:
  python -m research.build_research_analytics
"""

from __future__ import annotations

import argparse
import json
import logging

from research.analytics import ResearchAnalyticsEngine

logger = logging.getLogger("BuildResearchAnalytics")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build RAE-1…4 + RAE-7 analytics")
    parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    engine = ResearchAnalyticsEngine()
    manifest = engine.build_all()
    logger.info(
        "Analytics built: universe=%s history_rows=%s feature_rows=%s",
        manifest.get("current_universe"),
        manifest.get("history_rows"),
        manifest.get("feature_panel_rows"),
    )
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
