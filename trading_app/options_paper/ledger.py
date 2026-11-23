"""Own ledger for the options paper lane: JSONL event log, live state snapshot, daily summary CSV."""

from __future__ import annotations

import csv
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Optional

DEFAULT_DIR = Path(__file__).resolve().parents[2] / "logs" / "options_paper"


class PaperLedger:
    def __init__(self, strategy_id: str, day: date, root: Path = DEFAULT_DIR):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.strategy_id = strategy_id
        self.day = day
        stem = f"{day.isoformat()}_{strategy_id}"
        self.events_path = self.root / f"{stem}_events.jsonl"
        self.state_path = self.root / f"{stem}_state.json"
        self.summary_path = self.root / "summary.csv"

    def event(self, kind: str, **data: Any) -> Dict[str, Any]:
        rec = {"ts": datetime.now().isoformat(timespec="seconds"), "strategy": self.strategy_id, "kind": kind, **data}
        with self.events_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, default=str) + "\n")
        return rec

    def save_state(self, state: Dict[str, Any]) -> None:
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=1, default=str), encoding="utf-8")
        tmp.replace(self.state_path)

    def load_state(self) -> Optional[Dict[str, Any]]:
        if not self.state_path.exists():
            return None
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def write_summary(self, row: Dict[str, Any]) -> None:
        new = not self.summary_path.exists()
        fields = ["date", "strategy", "symbol", "expiry", "atm", "entry_credit", "exit_reason",
                  "gross_points", "charges", "net_pnl", "model_entry_credit", "fill_vs_model_points", "legs"]
        with self.summary_path.open("a", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
            if new:
                w.writeheader()
            w.writerow({**row, "date": self.day.isoformat(), "strategy": self.strategy_id})
