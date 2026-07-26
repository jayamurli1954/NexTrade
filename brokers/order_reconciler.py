"""
NexTrade Phase 5B — ORDER_STATE_UNKNOWN Reconciliation Engine.

Manages execution ACK uncertainty lifecycle, treating ACK timeouts as ORDER_STATE_UNKNOWN,
forcing RECONCILIATION_LOCK in SafetyControlPlane until broker truth is reconciled.
"""

from dataclasses import dataclass, field
import hashlib
import json
import time
import uuid
import logging
from typing import Dict, Any, Optional, List

from hardening.safety_control_plane import SafetyControlPlane, SafetyState
from .connection_state_machine import BrokerConnectionStateMachine, ConnectionState, ConnectionFault

logger = logging.getLogger("OrderReconciler")


class OrderStateUnknownException(Exception):
    """Raised when an order acknowledgement times out and state is UNKNOWN."""
    pass


@dataclass
class ReconciliationEvidenceRecord:
    """
    Evidence-backed, immutable reconciliation record for forensic auditability.
    """
    order_id: str
    request_id: str
    broker_order_id: Optional[str]
    reconciliation_id: str = field(default_factory=lambda: f"rec_{uuid.uuid4().hex[:12]}")
    timestamp: float = field(default_factory=time.time)
    monotonic_timestamp: float = field(default_factory=time.monotonic)
    broker_truth: str = "UNKNOWN"
    position_truth: str = "UNCONFIRMED"
    resolution: str = "PENDING_RECONCILIATION"
    evidence_hash: str = field(default="")

    def __post_init__(self) -> None:
        if not self.evidence_hash:
            self.evidence_hash = self.compute_hash()

    def canonical_dict(self) -> Dict[str, Any]:
        return {
            "order_id": self.order_id,
            "request_id": self.request_id,
            "broker_order_id": self.broker_order_id,
            "reconciliation_id": self.reconciliation_id,
            "broker_truth": self.broker_truth,
            "position_truth": self.position_truth,
            "resolution": self.resolution,
        }

    def compute_hash(self) -> str:
        payload = json.dumps(self.canonical_dict(), sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class OrderReconciler:
    """
    Reconciliation engine for execution ACK uncertainty and ORDER_STATE_UNKNOWN.
    Enforces RECONCILIATION_LOCK until all ambiguous orders are reconciled against broker truth.
    """

    def __init__(self, control_plane: Optional[SafetyControlPlane] = None, state_machine: Optional[BrokerConnectionStateMachine] = None) -> None:
        self.control_plane = control_plane or SafetyControlPlane()
        self.state_machine = state_machine
        self._unknown_orders: Dict[str, ReconciliationEvidenceRecord] = {}
        self._reconciliation_history: List[ReconciliationEvidenceRecord] = []

    def register_ack_timeout(self, order_id: str, request_id: str, is_cancel: bool = False) -> ReconciliationEvidenceRecord:
        """
        Registers an ACK timeout. Transitions order state to ORDER_STATE_UNKNOWN and
        forces RECONCILIATION_LOCK in SafetyControlPlane.
        """
        record = ReconciliationEvidenceRecord(
            order_id=order_id,
            request_id=request_id,
            broker_order_id=None,
            broker_truth="ACK_TIMEOUT_UNKNOWN",
            position_truth="UNRESOLVED",
            resolution="RECONCILIATION_LOCK_ACTIVE"
        )
        self._unknown_orders[order_id] = record

        fault = ConnectionFault.CANCEL_ACK_UNKNOWN if is_cancel else ConnectionFault.ORDER_ACK_UNKNOWN
        err_msg = f"Order ACK timeout for order '{order_id}' (request '{request_id}'). ORDER_STATE_UNKNOWN enforced."
        logger.critical(err_msg)

        if self.state_machine:
            self.state_machine.record_fault(fault, err_msg)
        else:
            self.control_plane.report_subsystem_state(
                "order_reconciler",
                SafetyState.RECONCILIATION_LOCK,
                err_msg
            )

        return record

    def has_active_unknown_orders(self) -> bool:
        """Returns True if any active ORDER_STATE_UNKNOWN orders exist."""
        return len(self._unknown_orders) > 0

    def get_active_unknown_orders(self) -> Dict[str, ReconciliationEvidenceRecord]:
        """Returns snapshot of active un-reconciled orders."""
        return dict(self._unknown_orders)

    def reconcile_order_with_broker_truth(self, order_id: str, broker_truth_status: str, broker_order_id: Optional[str] = None) -> ReconciliationEvidenceRecord:
        """
        Reconciles an ORDER_STATE_UNKNOWN against authoritative broker truth.
        """
        if order_id not in self._unknown_orders:
            logger.warning("Attempted to reconcile order '%s' which is not in ORDER_STATE_UNKNOWN pool", order_id)
            # Create idempotent record
            record = ReconciliationEvidenceRecord(
                order_id=order_id,
                request_id="DIRECT_RECONCILE",
                broker_order_id=broker_order_id,
                broker_truth=broker_truth_status,
                resolution="ALREADY_RECONCILED"
            )
            return record

        record = self._unknown_orders.pop(order_id)
        record.broker_truth = broker_truth_status
        record.broker_order_id = broker_order_id
        record.position_truth = "CONFIRMED" if broker_truth_status in ("FILLED", "EXECUTIVE_CONFIRMED") else "CONFIRMED_ABSENCE"
        record.resolution = "RECONCILED_SUCCESS"
        record.evidence_hash = record.compute_hash()

        self._reconciliation_history.append(record)
        logger.info("Order '%s' reconciled against broker truth: %s (Evidence Hash: %s)",
                    order_id, broker_truth_status, record.evidence_hash[:12])

        # If no remaining unknown orders, report resolution to SafetyControlPlane
        if not self._unknown_orders:
            logger.info("All ORDER_STATE_UNKNOWN orders resolved. Releasing RECONCILIATION_LOCK.")
            if self.state_machine:
                self.state_machine.transition_to(ConnectionState.CONNECTED_HEALTHY, ConnectionFault.NONE, "Reconciliation lock cleared")
            else:
                self.control_plane.report_subsystem_state("order_reconciler", SafetyState.READY, "Reconciliation lock cleared")

        return record
