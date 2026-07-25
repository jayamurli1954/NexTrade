# storage/readiness_audit_store.py
"""
Dual Persistence Store for Readiness Audit Certificates (Sub-Phase 4I).
Saves ReadinessAuditCertificates into SQLite database (primary authoritative store)
and appends to a JSONL log file (diagnostic audit trail). Failure-isolated.
"""
import os
import json
import sqlite3
import threading
from datetime import datetime, timezone
from typing import List, Optional

from contracts.audit_contracts import ReadinessAuditCertificate, ReadinessAuditStatus


class ReadinessAuditStore:
    """
    Thread-safe, failure-isolated dual persistence manager for Readiness Audit Certificates.
    """

    def __init__(
        self,
        db_path: str = "storage/readiness_audit.db",
        jsonl_path: str = "logs/readiness_audit.jsonl"
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
                    CREATE TABLE IF NOT EXISTS readiness_certificates (
                        audit_id TEXT PRIMARY KEY,
                        promotion_certificate_id TEXT NOT NULL,
                        verified_evidence_hash TEXT NOT NULL,
                        audit_status TEXT NOT NULL,
                        audit_hash TEXT NOT NULL,
                        audit_reasons TEXT NOT NULL,
                        audited_at TEXT NOT NULL
                    )
                """)
                conn.commit()
        except Exception:
            pass

    def save_certificate(self, record: ReadinessAuditCertificate) -> bool:
        """
        Saves a ReadinessAuditCertificate to both SQLite DB and JSONL log file.
        Returns True if successful; False if persistence failed.
        """
        success = True
        with self._lock:
            # 1. SQLite Persistence
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT OR REPLACE INTO readiness_certificates (
                            audit_id, promotion_certificate_id, verified_evidence_hash,
                            audit_status, audit_hash, audit_reasons, audited_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        record.audit_id,
                        record.promotion_certificate_id,
                        record.verified_evidence_hash,
                        record.audit_status.value if hasattr(record.audit_status, "value") else str(record.audit_status),
                        record.audit_hash,
                        json.dumps(record.audit_reasons),
                        record.audited_at.isoformat()
                    ))
                    conn.commit()
            except Exception:
                success = False

            # 2. JSONL Diagnostic Append-Only Log
            try:
                log_data = {
                    "audit_id": record.audit_id,
                    "promotion_certificate_id": record.promotion_certificate_id,
                    "verified_evidence_hash": record.verified_evidence_hash,
                    "audit_status": record.audit_status.value if hasattr(record.audit_status, "value") else str(record.audit_status),
                    "audit_hash": record.audit_hash,
                    "audit_reasons": record.audit_reasons,
                    "audited_at": record.audited_at.isoformat()
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
                    cursor.execute("DELETE FROM readiness_certificates")
                    conn.commit()
            except Exception:
                pass

            try:
                if os.path.exists(self.jsonl_path):
                    os.remove(self.jsonl_path)
            except Exception:
                pass
