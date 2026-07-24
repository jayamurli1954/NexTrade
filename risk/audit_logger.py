# risk/audit_logger.py
"""
Canonical Write-Only Tamper-Evident Risk Audit Trail Engine for NexTrade.
Provides append-only persistence in JSONL (authoritative) and CSV (reporting projection),
SHA-256 cryptographic hash chaining, sequence monotonicity, atomic fsync disk flushes,
integrity verifier, and health monitoring.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import os
import csv
import uuid
import threading
from typing import Optional, Dict, Any, List, Tuple
from types import MappingProxyType

from contracts.risk import RiskDecision, RiskDecisionStatus, OrderIntent

GENESIS_HASH = "GENESIS_0000000000000000000000000000000000000000000000000000000000000000"


@dataclass(frozen=True)
class AuditEvent:
    """
    Immutable canonical audit event payload.
    """
    sequence_number: int
    audit_event_id: str
    decision_id: str
    signal_id: Optional[str]
    strategy_id: Optional[str]
    symbol: str
    exchange: str
    order_intent: OrderIntent
    decision_status: RiskDecisionStatus
    requested_quantity: int
    position_sized_quantity: int
    portfolio_approved_quantity: int
    kill_switch_authorized_quantity: int
    approved_quantity: int
    primary_reason: Optional[str]
    limiting_phase: Optional[str]
    timestamp: str
    previous_hash: str
    event_hash: str

    def to_canonical_payload(self) -> Dict[str, Any]:
        """Return canonical dictionary payload excluding event_hash for deterministic hashing."""
        return {
            "sequence_number": self.sequence_number,
            "audit_event_id": self.audit_event_id,
            "decision_id": self.decision_id,
            "signal_id": self.signal_id,
            "strategy_id": self.strategy_id,
            "symbol": self.symbol,
            "exchange": self.exchange,
            "order_intent": self.order_intent.value if isinstance(self.order_intent, Enum) else str(self.order_intent),
            "decision_status": self.decision_status.value if isinstance(self.decision_status, Enum) else str(self.decision_status),
            "requested_quantity": self.requested_quantity,
            "position_sized_quantity": self.position_sized_quantity,
            "portfolio_approved_quantity": self.portfolio_approved_quantity,
            "kill_switch_authorized_quantity": self.kill_switch_authorized_quantity,
            "approved_quantity": self.approved_quantity,
            "primary_reason": self.primary_reason,
            "limiting_phase": self.limiting_phase,
            "timestamp": self.timestamp,
            "previous_hash": self.previous_hash,
        }

    def compute_hash(self) -> str:
        """Compute SHA-256 hash from canonical payload and previous_hash."""
        canonical_str = json.dumps(
            self.to_canonical_payload(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False
        )
        data_to_hash = (canonical_str + self.previous_hash).encode("utf-8")
        return hashlib.sha256(data_to_hash).hexdigest()


@dataclass(frozen=True)
class AuditIntegrityResult:
    """
    Output of audit log integrity verification.
    """
    is_valid: bool
    total_records_checked: int
    first_invalid_sequence: Optional[int] = None
    first_invalid_event_id: Optional[str] = None
    error_reason: Optional[str] = None


@dataclass(frozen=True)
class AuditHealthStatus:
    """
    Logger operational health status.
    """
    status: str                                        # HEALTHY, DEGRADED, FAILED
    total_records: int
    last_sequence_number: int
    current_hash: str
    write_failures: int
    last_error: Optional[str] = None


from enum import Enum


class RiskAuditLogger:
    """
    Write-only, thread-safe, tamper-evident Risk Audit Logger with atomic disk flushes.
    """

    def __init__(
        self,
        jsonl_path: str = "logs/audit/risk_decisions.jsonl",
        csv_path: str = "logs/audit/risk_decisions.csv"
    ):
        self.jsonl_path = jsonl_path
        self.csv_path = csv_path
        self._lock = threading.RLock()
        self._write_failures = 0
        self._last_error: Optional[str] = None
        self._sequence_number = 0
        self._previous_hash = GENESIS_HASH
        self._is_degraded = False

        self._init_and_recover_state()

    def log_decision(
        self,
        decision: RiskDecision,
        symbol: str = "UNKNOWN",
        exchange: str = "NSE",
        strategy_id: Optional[str] = None
    ) -> AuditEvent:
        """
        Atomically append RiskDecision to JSONL (authoritative) and CSV (projection) storage.
        """
        with self._lock:
            self._sequence_number += 1
            audit_event_id = f"AE-{uuid.uuid4().hex[:12]}"
            ts_str = decision.timestamp.isoformat() if hasattr(decision.timestamp, "isoformat") else str(decision.timestamp)

            # Get metric fields if available
            metrics = decision.metrics if hasattr(decision, "metrics") and decision.metrics else {}
            pos_qty = metrics.get("q_2b", decision.approved_quantity)
            port_qty = metrics.get("q_2c", decision.approved_quantity)
            kill_qty = metrics.get("q_2d", decision.approved_quantity)
            lim_phase = getattr(decision, "limiting_phase", None)

            # Unfinalized event payload for hash calculation
            raw_event = AuditEvent(
                sequence_number=self._sequence_number,
                audit_event_id=audit_event_id,
                decision_id=decision.decision_id,
                signal_id=decision.signal_id,
                strategy_id=strategy_id,
                symbol=symbol,
                exchange=exchange,
                order_intent=decision.order_intent,
                decision_status=decision.decision,
                requested_quantity=decision.requested_quantity,
                position_sized_quantity=pos_qty,
                portfolio_approved_quantity=port_qty,
                kill_switch_authorized_quantity=kill_qty,
                approved_quantity=decision.approved_quantity,
                primary_reason=decision.modification_reason,
                limiting_phase=lim_phase,
                timestamp=ts_str,
                previous_hash=self._previous_hash,
                event_hash=""
            )

            event_hash = raw_event.compute_hash()

            event = AuditEvent(
                sequence_number=raw_event.sequence_number,
                audit_event_id=raw_event.audit_event_id,
                decision_id=raw_event.decision_id,
                signal_id=raw_event.signal_id,
                strategy_id=raw_event.strategy_id,
                symbol=raw_event.symbol,
                exchange=raw_event.exchange,
                order_intent=raw_event.order_intent,
                decision_status=raw_event.decision_status,
                requested_quantity=raw_event.requested_quantity,
                position_sized_quantity=raw_event.position_sized_quantity,
                portfolio_approved_quantity=raw_event.portfolio_approved_quantity,
                kill_switch_authorized_quantity=raw_event.kill_switch_authorized_quantity,
                approved_quantity=raw_event.approved_quantity,
                primary_reason=raw_event.primary_reason,
                limiting_phase=raw_event.limiting_phase,
                timestamp=raw_event.timestamp,
                previous_hash=raw_event.previous_hash,
                event_hash=event_hash
            )

            # Step 1: Write Authoritative JSONL Record
            try:
                self._append_jsonl(event)
                self._previous_hash = event_hash
            except Exception as e:
                self._write_failures += 1
                self._last_error = f"JSONL write failure: {str(e)}"
                raise RuntimeError(f"Authoritative audit write failed: {str(e)}") from e

            # Step 2: Best-effort CSV Projection Write
            try:
                self._append_csv(event)
            except Exception as e:
                self._write_failures += 1
                self._is_degraded = True
                self._last_error = f"CSV projection write failure: {str(e)}"

            return event

    def verify_integrity(self) -> AuditIntegrityResult:
        """
        Verify sequence monotonicity, hash chain continuity, and payload integrity.
        """
        with self._lock:
            if not os.path.exists(self.jsonl_path):
                return AuditIntegrityResult(is_valid=True, total_records_checked=0)

            records_checked = 0
            expected_seq = 1
            expected_prev_hash = GENESIS_HASH

            try:
                with open(self.jsonl_path, "r", encoding="utf-8") as f:
                    for line_num, line in enumerate(f, 1):
                        line_str = line.strip()
                        if not line_str:
                            continue

                        try:
                            d = json.loads(line_str)
                        except json.JSONDecodeError as err:
                            return AuditIntegrityResult(
                                is_valid=False,
                                total_records_checked=records_checked,
                                first_invalid_sequence=expected_seq,
                                error_reason=f"Corrupt JSON format on line {line_num}: {str(err)}"
                            )

                        seq = d.get("sequence_number")
                        event_id = d.get("audit_event_id")
                        prev_hash = d.get("previous_hash")
                        event_hash = d.get("event_hash")

                        # 1. Sequence monotonicity check
                        if seq != expected_seq:
                            return AuditIntegrityResult(
                                is_valid=False,
                                total_records_checked=records_checked,
                                first_invalid_sequence=seq,
                                first_invalid_event_id=event_id,
                                error_reason=f"Sequence discontinuity: expected {expected_seq}, got {seq}"
                            )

                        # 2. Previous hash continuity check
                        if prev_hash != expected_prev_hash:
                            return AuditIntegrityResult(
                                is_valid=False,
                                total_records_checked=records_checked,
                                first_invalid_sequence=seq,
                                first_invalid_event_id=event_id,
                                error_reason=f"Previous hash mismatch at sequence {seq}: expected {expected_prev_hash}, got {prev_hash}"
                            )

                        # 3. Recompute and verify event hash
                        rec_payload = {
                            "sequence_number": d.get("sequence_number"),
                            "audit_event_id": d.get("audit_event_id"),
                            "decision_id": d.get("decision_id"),
                            "signal_id": d.get("signal_id"),
                            "strategy_id": d.get("strategy_id"),
                            "symbol": d.get("symbol"),
                            "exchange": d.get("exchange"),
                            "order_intent": d.get("order_intent"),
                            "decision_status": d.get("decision_status"),
                            "requested_quantity": d.get("requested_quantity"),
                            "position_sized_quantity": d.get("position_sized_quantity"),
                            "portfolio_approved_quantity": d.get("portfolio_approved_quantity"),
                            "kill_switch_authorized_quantity": d.get("kill_switch_authorized_quantity"),
                            "approved_quantity": d.get("approved_quantity"),
                            "primary_reason": d.get("primary_reason"),
                            "limiting_phase": d.get("limiting_phase"),
                            "timestamp": d.get("timestamp"),
                            "previous_hash": d.get("previous_hash"),
                        }
                        canonical_str = json.dumps(rec_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
                        calc_hash = hashlib.sha256((canonical_str + prev_hash).encode("utf-8")).hexdigest()

                        if calc_hash != event_hash:
                            return AuditIntegrityResult(
                                is_valid=False,
                                total_records_checked=records_checked,
                                first_invalid_sequence=seq,
                                first_invalid_event_id=event_id,
                                error_reason=f"Hash chain tampering detected at sequence {seq}: calculated {calc_hash}, stored {event_hash}"
                            )

                        records_checked += 1
                        expected_seq += 1
                        expected_prev_hash = event_hash

                return AuditIntegrityResult(is_valid=True, total_records_checked=records_checked)

            except Exception as e:
                return AuditIntegrityResult(
                    is_valid=False,
                    total_records_checked=records_checked,
                    error_reason=f"Integrity check exception: {str(e)}"
                )

    def health(self) -> AuditHealthStatus:
        """
        Get current operational health status.
        """
        with self._lock:
            if self._write_failures > 0 and self._is_degraded:
                status_str = "DEGRADED"
            elif self._write_failures > 0:
                status_str = "FAILED"
            else:
                status_str = "HEALTHY"

            return AuditHealthStatus(
                status=status_str,
                total_records=self._sequence_number,
                last_sequence_number=self._sequence_number,
                current_hash=self._previous_hash,
                write_failures=self._write_failures,
                last_error=self._last_error
            )

    # ----------------------------------------------------------------------
    # Internal Storage Methods
    # ----------------------------------------------------------------------
    def _append_jsonl(self, event: AuditEvent) -> None:
        """Append record to JSONL file with flush + fsync."""
        os.makedirs(os.path.dirname(os.path.abspath(self.jsonl_path)), exist_ok=True)
        data = event.to_canonical_payload()
        data["event_hash"] = event.event_hash

        with open(self.jsonl_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(data, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())

    def _append_csv(self, event: AuditEvent) -> None:
        """Append record projection to CSV file with flush + fsync."""
        os.makedirs(os.path.dirname(os.path.abspath(self.csv_path)), exist_ok=True)
        file_exists = os.path.exists(self.csv_path) and os.path.getsize(self.csv_path) > 0

        fieldnames = [
            "sequence_number", "audit_event_id", "decision_id", "signal_id", "strategy_id",
            "symbol", "exchange", "order_intent", "decision_status", "requested_quantity",
            "position_sized_quantity", "portfolio_approved_quantity", "kill_switch_authorized_quantity",
            "approved_quantity", "primary_reason", "limiting_phase", "timestamp", "event_hash"
        ]

        with open(self.csv_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if not file_exists:
                writer.writeheader()

            writer.writerow({
                "sequence_number": event.sequence_number,
                "audit_event_id": event.audit_event_id,
                "decision_id": event.decision_id,
                "signal_id": event.signal_id or "",
                "strategy_id": event.strategy_id or "",
                "symbol": event.symbol,
                "exchange": event.exchange,
                "order_intent": event.order_intent.value if isinstance(event.order_intent, Enum) else str(event.order_intent),
                "decision_status": event.decision_status.value if isinstance(event.decision_status, Enum) else str(event.decision_status),
                "requested_quantity": event.requested_quantity,
                "position_sized_quantity": event.position_sized_quantity,
                "portfolio_approved_quantity": event.portfolio_approved_quantity,
                "kill_switch_authorized_quantity": event.kill_switch_authorized_quantity,
                "approved_quantity": event.approved_quantity,
                "primary_reason": event.primary_reason or "",
                "limiting_phase": event.limiting_phase or "",
                "timestamp": event.timestamp,
                "event_hash": event.event_hash
            })
            f.flush()
            os.fsync(f.fileno())

    def _init_and_recover_state(self) -> None:
        """Scan existing JSONL log file to recover sequence_number and previous_hash."""
        if not os.path.exists(self.jsonl_path):
            return

        last_seq = 0
        last_hash = GENESIS_HASH

        try:
            with open(self.jsonl_path, "r", encoding="utf-8") as f:
                for line in f:
                    line_str = line.strip()
                    if not line_str:
                        continue
                    try:
                        d = json.loads(line_str)
                        if "sequence_number" in d and "event_hash" in d:
                            last_seq = int(d["sequence_number"])
                            last_hash = str(d["event_hash"])
                    except json.JSONDecodeError:
                        self._is_degraded = True
                        self._last_error = "Incomplete or corrupt final line in JSONL audit log"
                        break

            self._sequence_number = last_seq
            self._previous_hash = last_hash

        except Exception as e:
            self._is_degraded = True
            self._last_error = f"Recovery failure: {str(e)}"
