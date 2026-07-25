# storage/pilot_store.py
"""
Dual Persistence Store for Controlled Live Pilot Evidence Packages (Sub-Phase 4K).
Saves PilotSessionRecords into SQLite database (primary authoritative store)
and appends to a JSONL log file (diagnostic audit trail). Failure-isolated.
"""
import os
import json
import sqlite3
import threading
from datetime import datetime, timezone
from typing import List, Optional

from contracts.pilot_contracts import PilotSessionRecord, PilotStage


class PilotStore:
    """
    Thread-safe, failure-isolated dual persistence manager for Controlled Live Pilot Evidence Packages.
    """

    def __init__(
        self,
        db_path: str = "storage/pilot_operations.db",
        jsonl_path: str = "logs/pilot_operations.jsonl"
    ):
        self.db_path = db_path
        self.jsonl_path = jsonl_path
        self._lock = threading.RLock()
        self._init_db()

    def _init_db(self) -> None:
        """Initializes SQLite table schema if not present."""
        try:
            db_dir = os.path.dirname(self.db_path)
            if db_dir and not os.path.exists(db_dir):
                os.makedirs(db_dir, exist_ok=True)

            log_dir = os.path.dirname(self.jsonl_path)
            if log_dir and not os.path.exists(log_dir):
                os.makedirs(log_dir, exist_ok=True)

            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS pilot_sessions (
                        session_id TEXT PRIMARY KEY,
                        pilot_stage TEXT NOT NULL,
                        preflight_certificate_id TEXT NOT NULL,
                        total_orders INTEGER NOT NULL,
                        filled_orders INTEGER NOT NULL,
                        total_volume REAL NOT NULL,
                        total_pnl REAL NOT NULL,
                        average_slippage_bps REAL NOT NULL,
                        reconciliation_clean INTEGER NOT NULL,
                        pilot_evidence_hash TEXT NOT NULL,
                        closed_at TEXT NOT NULL
                    )
                """)
                conn.commit()
        except Exception:
            pass

    def save_session_record(self, record: PilotSessionRecord) -> bool:
        """
        Saves a PilotSessionRecord to both SQLite DB and JSONL log file.
        Returns True if successful; False if persistence failed.
        """
        success = True
        with self._lock:
            # 1. SQLite Persistence
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT OR REPLACE INTO pilot_sessions (
                            session_id, pilot_stage, preflight_certificate_id,
                            total_orders, filled_orders, total_volume, total_pnl,
                            average_slippage_bps, reconciliation_clean, pilot_evidence_hash, closed_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        record.session_id,
                        record.pilot_stage.value if hasattr(record.pilot_stage, "value") else str(record.pilot_stage),
                        record.preflight_certificate_id,
                        record.total_orders,
                        record.filled_orders,
                        record.total_volume,
                        record.total_pnl,
                        record.average_slippage_bps,
                        1 if record.reconciliation_clean else 0,
                        record.pilot_evidence_hash,
                        record.closed_at.isoformat()
                    ))
                    conn.commit()
            except Exception:
                success = False

            # 2. JSONL Diagnostic Append-Only Log
            try:
                log_data = {
                    "session_id": record.session_id,
                    "pilot_stage": record.pilot_stage.value if hasattr(record.pilot_stage, "value") else str(record.pilot_stage),
                    "preflight_certificate_id": record.preflight_certificate_id,
                    "total_orders": record.total_orders,
                    "filled_orders": record.filled_orders,
                    "total_volume": record.total_volume,
                    "total_pnl": record.total_pnl,
                    "average_slippage_bps": record.average_slippage_bps,
                    "reconciliation_clean": record.reconciliation_clean,
                    "pilot_evidence_hash": record.pilot_evidence_hash,
                    "closed_at": record.closed_at.isoformat()
                }
                with open(self.jsonl_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(log_data) + "\n")
            except Exception:
                success = False

        return success

    def clear(self) -> None:
        """Clears stored session records."""
        with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM pilot_sessions")
                    conn.commit()
            except Exception:
                pass

            try:
                if os.path.exists(self.jsonl_path):
                    os.remove(self.jsonl_path)
            except Exception:
                pass
