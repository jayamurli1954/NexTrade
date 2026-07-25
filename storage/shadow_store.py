# storage/shadow_store.py
"""
Dual Persistence Store for NexTrade Shadow Mode (Sub-Phase 4G).
Saves ShadowExecutionRecord items into a SQLite database (primary authoritative store)
and appends to a JSONL log file (diagnostic audit trail). Failure-isolated.
"""
import os
import json
import sqlite3
import threading
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from contracts.shadow_contracts import ShadowExecutionRecord, ShadowOrderStatus


class ShadowStore:
    """
    Thread-safe, failure-isolated dual persistence manager (SQLite + JSONL).
    """

    def __init__(
        self,
        db_path: str = "storage/shadow_execution.db",
        jsonl_path: str = "logs/shadow_execution.jsonl"
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
                    CREATE TABLE IF NOT EXISTS shadow_records (
                        shadow_id TEXT PRIMARY KEY,
                        execution_request_id TEXT NOT NULL,
                        symbol TEXT NOT NULL,
                        side TEXT NOT NULL,
                        quantity REAL NOT NULL,
                        limit_price REAL NOT NULL,
                        simulated_fill_price REAL NOT NULL,
                        market_tick_price REAL NOT NULL,
                        slippage_bps REAL NOT NULL,
                        timing_delta_ms REAL NOT NULL,
                        status TEXT NOT NULL,
                        safety_gate_denial_reasons TEXT NOT NULL,
                        timestamp TEXT NOT NULL
                    )
                """)
                conn.commit()
        except Exception:
            pass  # Failure-isolated initialization

    def save_record(self, record: ShadowExecutionRecord) -> bool:
        """
        Saves a ShadowExecutionRecord to both SQLite DB and JSONL log.
        Returns True if successful; False if persistence failed (failure-isolated).
        """
        success = True
        with self._lock:
            # 1. SQLite Persistence
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    reasons_str = json.dumps(record.safety_gate_denial_reasons)
                    cursor.execute("""
                        INSERT OR REPLACE INTO shadow_records (
                            shadow_id, execution_request_id, symbol, side, quantity,
                            limit_price, simulated_fill_price, market_tick_price,
                            slippage_bps, timing_delta_ms, status, safety_gate_denial_reasons, timestamp
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        record.shadow_id,
                        record.execution_request_id,
                        record.symbol,
                        record.side,
                        record.quantity,
                        record.limit_price,
                        record.simulated_fill_price,
                        record.market_tick_price,
                        record.slippage_bps,
                        record.timing_delta_ms,
                        record.status.value if hasattr(record.status, "value") else str(record.status),
                        reasons_str,
                        record.timestamp.isoformat()
                    ))
                    conn.commit()
            except Exception:
                success = False

            # 2. JSONL Append-Only Diagnostic Log
            try:
                log_data = {
                    "shadow_id": record.shadow_id,
                    "execution_request_id": record.execution_request_id,
                    "symbol": record.symbol,
                    "side": record.side,
                    "quantity": record.quantity,
                    "limit_price": record.limit_price,
                    "simulated_fill_price": record.simulated_fill_price,
                    "market_tick_price": record.market_tick_price,
                    "slippage_bps": record.slippage_bps,
                    "timing_delta_ms": record.timing_delta_ms,
                    "status": record.status.value if hasattr(record.status, "value") else str(record.status),
                    "safety_gate_denial_reasons": record.safety_gate_denial_reasons,
                    "timestamp": record.timestamp.isoformat()
                }
                with open(self.jsonl_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(log_data) + "\n")
            except Exception:
                success = False

        return success

    def get_records(self) -> List[ShadowExecutionRecord]:
        """Returns all records stored in the SQLite database."""
        records: List[ShadowExecutionRecord] = []
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT shadow_id, execution_request_id, symbol, side, quantity, limit_price, simulated_fill_price, market_tick_price, slippage_bps, timing_delta_ms, status, safety_gate_denial_reasons, timestamp FROM shadow_records ORDER BY timestamp ASC")
                rows = cursor.fetchall()
                for row in rows:
                    reasons = json.loads(row[11]) if row[11] else []
                    ts = datetime.fromisoformat(row[12])
                    records.append(
                        ShadowExecutionRecord(
                            shadow_id=row[0],
                            execution_request_id=row[1],
                            symbol=row[2],
                            side=row[3],
                            quantity=row[4],
                            limit_price=row[5],
                            simulated_fill_price=row[6],
                            market_tick_price=row[7],
                            slippage_bps=row[8],
                            timing_delta_ms=row[9],
                            status=ShadowOrderStatus(row[10]),
                            safety_gate_denial_reasons=reasons,
                            timestamp=ts
                        )
                    )
        except Exception:
            pass
        return records

    def clear(self) -> None:
        """Clears SQLite database records and JSONL log file."""
        with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM shadow_records")
                    conn.commit()
            except Exception:
                pass

            try:
                if os.path.exists(self.jsonl_path):
                    os.remove(self.jsonl_path)
            except Exception:
                pass
