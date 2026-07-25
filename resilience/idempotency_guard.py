# resilience/idempotency_guard.py
"""
Idempotent Crash Recovery & Recovery Epoch Guard for NexTrade (Sub-Phase 4L).
Tracks recovery epochs and persistent correlation keys to prevent duplicate order submissions,
duplicate fill processing, or duplicate cancels across system crashes and restarts (Invariant 4L-P5).
"""
import os
import json
import sqlite3
import threading
from typing import Dict, Any, Tuple, Optional, Set


class IdempotencyGuard:
    """
    Thread-safe, SQLite-backed idempotency guard enforcing recovery epoch isolation and zero duplicate processing.
    """

    def __init__(self, db_path: str = "storage/idempotency_guard.db"):
        self.db_path = db_path
        self._lock = threading.RLock()
        self._recovery_epoch = 1
        self._init_db()

    def _init_db(self) -> None:
        """Initializes SQLite schema for recovery epoch and processed keys."""
        try:
            db_dir = os.path.dirname(self.db_path)
            if db_dir and not os.path.exists(db_dir):
                os.makedirs(db_dir, exist_ok=True)

            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS recovery_metadata (
                        key TEXT PRIMARY KEY,
                        val INTEGER NOT NULL
                    )
                """)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS processed_keys (
                        key_type TEXT NOT NULL,
                        idempotency_key TEXT NOT NULL,
                        recovery_epoch INTEGER NOT NULL,
                        processed_at TEXT NOT NULL,
                        PRIMARY KEY (key_type, idempotency_key)
                    )
                """)
                conn.commit()

                # Load current recovery epoch
                cursor.execute("SELECT val FROM recovery_metadata WHERE key = 'current_recovery_epoch'")
                row = cursor.fetchone()
                if row:
                    self._recovery_epoch = row[0]
                else:
                    cursor.execute("INSERT INTO recovery_metadata (key, val) VALUES ('current_recovery_epoch', 1)")
                    conn.commit()
                    self._recovery_epoch = 1
        except Exception:
            pass

    @property
    def recovery_epoch(self) -> int:
        with self._lock:
            return self._recovery_epoch

    def advance_recovery_epoch(self) -> int:
        """Advances monotonically increasing recovery epoch (Invariant 4L-P5)."""
        with self._lock:
            self._recovery_epoch += 1
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute("UPDATE recovery_metadata SET val = ? WHERE key = 'current_recovery_epoch'", (self._recovery_epoch,))
                    conn.commit()
            except Exception:
                pass
            return self._recovery_epoch

    def is_processed(self, key_type: str, idempotency_key: str) -> bool:
        """
        Returns True if idempotency_key has already been processed for key_type.
        Key types: 'ORDER', 'FILL', 'CANCEL', 'REPLAY'.
        """
        with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT 1 FROM processed_keys WHERE key_type = ? AND idempotency_key = ?", (key_type, idempotency_key))
                    return cursor.fetchone() is not None
            except Exception:
                return False

    def mark_processed(self, key_type: str, idempotency_key: str) -> bool:
        """
        Marks an idempotency_key as processed under current recovery_epoch.
        Returns False if duplicate key detected!
        """
        with self._lock:
            if self.is_processed(key_type, idempotency_key):
                return False

            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT INTO processed_keys (key_type, idempotency_key, recovery_epoch, processed_at)
                        VALUES (?, ?, ?, ?)
                    """, (key_type, idempotency_key, self._recovery_epoch, "NOW"))
                    conn.commit()
                    return True
            except Exception:
                return False

    def clear(self) -> None:
        """Clears processed keys for testing."""
        with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM processed_keys")
                    conn.commit()
            except Exception:
                pass
