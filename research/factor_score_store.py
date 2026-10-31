"""
Persist current + historical fundamental factor scores.

Layout:
  research/data/fundamentals/current/factor_scores.json
  research/data/fundamentals/historical/YYYY.json
  research/data/fundamentals/manifests/factor_build_manifest.json
"""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from research.fundamentals_store import default_fundamentals_dir


def _json_default(obj: Any) -> Any:
    if is_dataclass(obj) and not isinstance(obj, type):
        return asdict(obj)
    raise TypeError(f"Not serializable: {type(obj)}")


class FactorScoreStore:
    def __init__(self, root: Optional[Path] = None):
        self.root = Path(root) if root else default_fundamentals_dir()
        self.current_dir = self.root / "current"
        self.historical_dir = self.root / "historical"
        self.manifests_dir = self.root / "manifests"
        for d in (self.current_dir, self.historical_dir, self.manifests_dir):
            d.mkdir(parents=True, exist_ok=True)

    def current_path(self) -> Path:
        return self.current_dir / "factor_scores.json"

    def current_table_path(self) -> Path:
        return self.current_dir / "factor_scores_table.csv"

    def historical_path(self, year: int) -> Path:
        return self.historical_dir / f"{int(year)}.json"

    def manifest_path(self) -> Path:
        return self.manifests_dir / "factor_build_manifest.json"

    def save_current(self, payload: Dict[str, Any]) -> Path:
        path = self.current_path()
        path.write_text(json.dumps(payload, indent=2, default=_json_default), encoding="utf-8")
        self._write_table(payload)
        return path

    def save_historical_year(self, year: int, payload: Dict[str, Any]) -> Path:
        path = self.historical_path(year)
        path.write_text(json.dumps(payload, indent=2, default=_json_default), encoding="utf-8")
        return path

    def save_manifest(self, manifest: Dict[str, Any]) -> Path:
        path = self.manifest_path()
        path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return path

    def load_current(self) -> Optional[Dict[str, Any]]:
        path = self.current_path()
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def load_current_symbol(self, symbol: str) -> Optional[Dict[str, Any]]:
        data = self.load_current()
        if not data:
            return None
        return (data.get("symbols") or {}).get(symbol.upper())

    def load_as_of(self, symbol: str, fiscal_year: int) -> Optional[Dict[str, Any]]:
        path = self.historical_path(fiscal_year)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return (data.get("symbols") or {}).get(symbol.upper())

    def list_historical_years(self) -> List[int]:
        years: List[int] = []
        for path in sorted(self.historical_dir.glob("*.json")):
            try:
                years.append(int(path.stem))
            except ValueError:
                continue
        return years

    def _write_table(self, payload: Dict[str, Any]) -> None:
        rows: List[Dict[str, Any]] = []
        for sym, rec in sorted((payload.get("symbols") or {}).items()):
            scores = rec.get("scores") or {}
            rows.append(
                {
                    "symbol": sym,
                    "quality": scores.get("quality"),
                    "growth": scores.get("growth"),
                    "value": scores.get("value"),
                    "financial_health": scores.get("financial_health"),
                    "consistency": scores.get("consistency"),
                    "overall_fundamental": scores.get("overall_fundamental"),
                    "fiscal_year": rec.get("fiscal_year"),
                }
            )
        path = self.current_table_path()
        if not rows:
            path.write_text("", encoding="utf-8")
            return
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
