# storage/staging_store.py
"""
Dual Persistence Store for Controlled Live Staging Order Lineages (Sub-Phase 4J).
Saves StagingOrderLineage items into SQLite database (primary authoritative store)
and appends to a JSONL log file (diagnostic audit trail). Failure-isolated.
"""
import os
import json
import sqlite3
import threading
from datetime import datetime, timezone
from typing import List, Optional

from contracts.staging_contracts import StagingOrderLineage


class StagingStore:
    """
    Thread-safe, failure-isolated dual persistence manager for Controlled Live Staging order lineages.
    """

    def __init__(
        self,
        db_path: str = "storage/controlled_live_staging.db",
        jsonl_path: str = "logs/controlled_live_staging.jsonl"
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
                    CREATE TABLE IF NOT EXISTS staging_lineages (
                        staging_id TEXT PRIMARY KEY,
                        correlation_id TEXT NOT NULL,
                        execution_request_id TEXT NOT NULL,
                        authorization_token_id TEXT NOT NULL,
                        config_hash TEXT NOT NULL,
                        staging_gate_result TEXT NOT NULL,
                        circuit_breaker_state TEXT NOT NULL,
                        broker_status TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    )
                """)
                conn.commit()
        except Exception:
            pass

    def save_lineage(self, record: StagingOrderLineage) -> bool:
        """
        Saves a StagingOrderLineage to both SQLite DB and JSONL log file.
        Returns True if successful; False if persistence failed.
        """
        success = True
        with self._lock:
            # 1. SQLite Persistence
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    created_at = record.timestamps.get("request_time", datetime.now(timezone.utc)).isoformat()
                    cursor.execute("""
                        INSERT OR REPLACE INTO staging_lineages (
                            staging_id, correlation_id, execution_request_id,
                            authorization_token_id, config_hash, staging_gate_result,
                            circuit_breaker_state, broker_status, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        record.staging_id,
                        record.correlation_id,
                        record.execution_request_id,
                        record.authorization_token_id,
                        record.config_hash,
                        record.staging_gate_result,
                        record.circuit_breaker_state,
                        record.broker_status,
                        created_at
                    ))
                    conn.commit()
            except Exception:
                success = False

            # 2. JSONL Diagnostic Append-Only Log
            try:
                log_data = {
                    "staging_id": record.staging_id,
                    "correlation_id": record.correlation_id,
                    "execution_request_id": record.execution_request_id,
                    "authorization_token_id": record.authorization_token_id,
                    "config_hash": record.config_hash,
                    "staging_gate_result": record.staging_gate_result,
                    "circuit_breaker_state": record.circuit_breaker_state,
                    "broker_status": record.broker_status,
                    "created_at": record.timestamps.get("request_time", datetime.now(timezone.utc)).isoformat()
                }
                with open(self.jsonl_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(log_data) + "\n")
            except Exception:
                success = False

        return success

    def clear(self) -> None:
        """Clears stored lineages."""
        with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM staging_lineages")
                    conn.commit()
            except Exception:
                pass

            try:
                if os.path.exists(self.jsonl_path):
                    os.remove(self.jsonl_path)
            except Exception:
                pass
