"""
NexTrade Tamper-Evident Logger Subsystem (Phase 6B).

Provides append-only, SHA-256 hash-chained log entry durability for production audit trails.
Each log record maintains a cryptographic link to the preceding record hash.
"""

import os
import json
import hashlib
import time
from typing import Dict, Any, List, Tuple


class TamperEvidentLogger:
    """Tamper-evident audit logger using SHA-256 cryptographic hash chaining."""

    GENESIS_HASH = "0000000000000000000000000000000000000000000000000000000000000000"

    def __init__(self, log_filepath: str):
        self.log_filepath = os.path.abspath(log_filepath)
        os.makedirs(os.path.dirname(self.log_filepath), exist_ok=True)
        self.last_hash = self._calculate_current_chain_tail()

    def _calculate_current_chain_tail(self) -> str:
        """Read existing log file to determine the hash of the last entry."""
        if not os.path.exists(self.log_filepath) or os.path.getsize(self.log_filepath) == 0:
            return self.GENESIS_HASH

        last_hash = self.GENESIS_HASH
        try:
            with open(self.log_filepath, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        record = json.loads(line)
                        if "entry_hash" in record:
                            last_hash = record["entry_hash"]
        except Exception:
            return self.GENESIS_HASH
        return last_hash

    @staticmethod
    def compute_entry_hash(prev_hash: str, index: int, timestamp: float, payload: Dict[str, Any]) -> str:
        """Compute canonical SHA-256 hash of a log record."""
        canonical_str = f"{prev_hash}|{index}|{timestamp:.6f}|{json.dumps(payload, sort_keys=True)}"
        return hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()

    def append_audit_event(self, event_type: str, details: Dict[str, Any]) -> Dict[str, Any]:
        """Append a tamper-evident audit log record."""
        existing_records = self.read_all_records()
        index = len(existing_records) + 1
        timestamp = time.time()
        prev_hash = self.last_hash

        payload = {
            "event_type": event_type,
            "details": details,
        }

        entry_hash = self.compute_entry_hash(prev_hash, index, timestamp, payload)

        record = {
            "index": index,
            "timestamp": timestamp,
            "prev_hash": prev_hash,
            "payload": payload,
            "entry_hash": entry_hash,
        }

        # Write to log file in append-only mode
        with open(self.log_filepath, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

        self.last_hash = entry_hash
        return record

    def read_all_records(self) -> List[Dict[str, Any]]:
        """Read all log records from file."""
        records = []
        if not os.path.exists(self.log_filepath):
            return records

        with open(self.log_filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        return records

    def verify_integrity(self) -> Tuple[bool, str, int]:
        """
        Verify cryptographic hash chain integrity of the log file.
        Returns (is_valid, reason_or_status, broken_index).
        """
        records = self.read_all_records()
        if not records:
            return True, "LOG_EMPTY", 0

        expected_prev_hash = self.GENESIS_HASH

        for i, rec in enumerate(records):
            idx = rec.get("index", i + 1)
            timestamp = rec.get("timestamp", 0.0)
            prev_hash = rec.get("prev_hash", "")
            payload = rec.get("payload", {})
            entry_hash = rec.get("entry_hash", "")

            # 1. Verify prev_hash link
            if prev_hash != expected_prev_hash:
                return False, f"HASH_CHAIN_DISCONTINUITY at index {idx}: expected prev {expected_prev_hash[:8]}, got {prev_hash[:8]}", idx

            # 2. Re-compute entry hash
            computed_hash = self.compute_entry_hash(prev_hash, idx, timestamp, payload)
            if computed_hash != entry_hash:
                return False, f"TAMPERING_DETECTED at index {idx}: payload modified", idx

            expected_prev_hash = entry_hash

        return True, "HASH_CHAIN_INTACT", len(records)
