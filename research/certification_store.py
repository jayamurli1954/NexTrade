"""
Persist Strategy Certification packages (research domain JSONL/JSON).

Does not promote strategies into the live StrategyRegistry.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from contracts.strategy_research import StrategyCertificationRecord

logger = logging.getLogger("CertificationStore")

_WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEFAULT_DIR = os.path.join(_WORKSPACE, "storage", "research")
_DEFAULT_PATH = os.path.join(_DEFAULT_DIR, "strategy_certifications.jsonl")


class CertificationStore:
    def __init__(self, path: Optional[str] = None):
        self.path = path or _DEFAULT_PATH
        self._lock = threading.Lock()
        os.makedirs(os.path.dirname(self.path), exist_ok=True)

    def save(self, record: StrategyCertificationRecord) -> str:
        row = {
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "record": self._record_to_dict(record),
        }
        line = json.dumps(row, sort_keys=True)
        with self._lock:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        logger.info("Saved certification %s → %s", record.certification_id, self.path)
        return record.certification_id

    def list_records(self, strategy_id: Optional[str] = None) -> List[Dict[str, Any]]:
        if not os.path.exists(self.path):
            return []
        out: List[Dict[str, Any]] = []
        with self._lock:
            with open(self.path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    rec = row.get("record") or {}
                    if strategy_id and rec.get("strategy_id") != strategy_id:
                        continue
                    out.append(row)
        return out

    def latest_for(self, strategy_id: str, version: str) -> Optional[Dict[str, Any]]:
        matches = [
            r
            for r in self.list_records(strategy_id)
            if (r.get("record") or {}).get("strategy_version") == version
        ]
        return matches[-1] if matches else None

    @staticmethod
    def _record_to_dict(record: StrategyCertificationRecord) -> Dict[str, Any]:
        d = asdict(record)
        d["research_source"] = record.research_source.value
        return d
