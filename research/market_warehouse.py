"""
Market Data Warehouse facade (MDW-7 skeleton).

Research-only access to index / options / (future) OI, PCR, futures, calendar.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd

from research.arass.options_store import OptionsStore, default_store_dir


def default_warehouse_dir(root: Optional[Path] = None) -> Path:
    base = root or Path(__file__).resolve().parents[1]
    return base / "research" / "data" / "market_warehouse"


@dataclass
class WarehouseProvenance:
    source: str
    path: Optional[str] = None
    rows: Optional[int] = None
    note: str = "research_only"


class MarketWarehouse:
    def __init__(self, root: Optional[Path] = None):
        self.root = Path(root) if root else default_warehouse_dir()
        for sub in ("index", "options", "futures", "oi", "derived", "calendar", "manifests"):
            (self.root / sub).mkdir(parents=True, exist_ok=True)
        self._options: Optional[OptionsStore] = None

    def options_path(self) -> Path:
        # Prefer warehouse copy; fall back to legacy options dir
        wh = self.root / "options" / "nifty_options_daily.csv"
        if wh.exists():
            return wh
        return default_store_dir() / "nifty_options_daily.csv"

    def load_options(self, path: Optional[Path] = None) -> OptionsStore:
        p = Path(path) if path else self.options_path()
        self._options = OptionsStore.load(p)
        return self._options

    def options_store(self) -> OptionsStore:
        if self._options is None:
            return self.load_options()
        return self._options

    def write_manifest(self, name: str, payload: Dict[str, Any]) -> Path:
        path = self.root / "manifests" / f"{name}.json"
        payload = dict(payload)
        payload.setdefault("updated_at", datetime.now(timezone.utc).isoformat())
        payload.setdefault("note", "Research-only Market Data Warehouse. Not execution authority.")
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path

    def options_summary(self) -> Dict[str, Any]:
        store = self.options_store()
        df = store.df
        return {
            "path": str(store.path),
            "rows": int(len(df)),
            "date_min": str(df["date"].min().date()) if len(df) else None,
            "date_max": str(df["date"].max().date()) if len(df) else None,
            "symbols": sorted(df["symbol"].unique().tolist()) if len(df) else [],
        }
