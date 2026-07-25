# storage/promotion_store.py
"""
Dual Persistence Store for Promotion Decision Certificates (Sub-Phase 4H).
Saves PromotionDecisionRecords into SQLite database (primary authoritative store)
and appends to a JSONL log file (diagnostic audit trail). Failure-isolated.
"""
import os
import json
import sqlite3
import threading
from datetime import datetime, timezone
from typing import List, Optional

from contracts.promotion_contracts import PromotionDecisionRecord, PromotionDecisionStatus


class PromotionStore:
    """
    Thread-safe, failure-isolated dual persistence manager for Promotion Decision Certificates.
    """

    def __init__(
        self,
        db_path: str = "storage/promotion_decision.db",
        jsonl_path: str = "logs/promotion_decision.jsonl"
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
                    CREATE TABLE IF NOT EXISTS promotion_certificates (
                        decision_id TEXT PRIMARY KEY,
                        snapshot_id TEXT NOT NULL,
                        evidence_snapshot_hash TEXT NOT NULL,
                        decision TEXT NOT NULL,
                        decision_reasons TEXT NOT NULL,
                        approved_at TEXT NOT NULL
                    )
                """)
                conn.commit()
        except Exception:
            pass

    def save_certificate(self, record: PromotionDecisionRecord) -> bool:
        """
        Saves a PromotionDecisionRecord to both SQLite DB and JSONL log file.
        Returns True if successful; False if persistence failed.
        """
        success = True
        with self._lock:
            # 1. SQLite Persistence
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT OR REPLACE INTO promotion_certificates (
                            decision_id, snapshot_id, evidence_snapshot_hash,
                            decision, decision_reasons, approved_at
                        ) VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        record.decision_id,
                        record.evidence_snapshot.snapshot_id,
                        record.evidence_snapshot.evidence_snapshot_hash,
                        record.decision.value if hasattr(record.decision, "value") else str(record.decision),
                        json.dumps(record.decision_reasons),
                        record.approved_at.isoformat()
                    ))
                    conn.commit()
            except Exception:
                success = False

            # 2. JSONL Diagnostic Append-Only Log
            try:
                log_data = {
                    "decision_id": record.decision_id,
                    "snapshot_id": record.evidence_snapshot.snapshot_id,
                    "evidence_snapshot_hash": record.evidence_snapshot.evidence_snapshot_hash,
                    "shadow_dataset_hash": record.evidence_snapshot.shadow_dataset_hash,
                    "decision": record.decision.value if hasattr(record.decision, "value") else str(record.decision),
                    "decision_reasons": record.decision_reasons,
                    "approved_at": record.approved_at.isoformat()
                }
                with open(self.jsonl_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(log_data) + "\n")
            except Exception:
                success = False

        return success

    def clear(self) -> None:
        """Clears stored certificates."""
        with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM promotion_certificates")
                    conn.commit()
            except Exception:
                pass

            try:
                if os.path.exists(self.jsonl_path):
                    os.remove(self.jsonl_path)
            except Exception:
                pass
