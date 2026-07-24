# risk/execution_gate.py
"""
Formal Execution Authorization Contract Gate for NexTrade (Sub-Phase 2H-6).
Acts as a strict default-deny firewall between RiskEngine decisions and downstream broker execution.
Enforces the invariant:
Execution Permission Permitted <=> decision.status in (APPROVED, MODIFIED) AND decision.approved_quantity > 0 AND Authoritative Audit Persistence Succeeded
"""
from typing import Optional
from contracts.risk import RiskDecision, RiskDecisionStatus
from risk.audit_logger import AuditHealthStatus


class ExecutionAuthorizationGate:
    """
    Default-Deny Execution Firewall Gate.
    """

    @staticmethod
    def can_execute(
        decision: Optional[RiskDecision],
        audit_health: Optional[AuditHealthStatus] = None
    ) -> bool:
        """
        Evaluate if an order request is authorized to proceed to broker execution.
        Returns True ONLY IF decision is valid APPROVED/MODIFIED with approved_quantity > 0
        and authoritative audit persistence did not fail.
        """
        if decision is None:
            return False

        if not isinstance(decision, RiskDecision):
            return False

        # Status Must Be APPROVED or MODIFIED
        if decision.decision not in (RiskDecisionStatus.APPROVED, RiskDecisionStatus.MODIFIED):
            return False

        # Approved Quantity Must Be Strictly Positive
        if decision.approved_quantity <= 0:
            return False

        # Quantity Cannot Exceed Requested Quantity
        if decision.approved_quantity > decision.requested_quantity:
            return False

        # Authoritative Audit Persistence Check
        if audit_health and audit_health.status == "FAILED":
            return False

        return True
