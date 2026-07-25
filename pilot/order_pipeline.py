# pilot/order_pipeline.py
"""
Human Approval Order Pipeline for NexTrade (Sub-Phase 4K).
Enforces explicit per-order human approvals for Stage 1 pilot orders (Invariant 4K-P4),
binding operator IDs, order request IDs, approved quantities, and config hashes.
"""
import uuid
import hashlib
import json
from datetime import datetime, timezone
from typing import Tuple, Optional, Any, Dict

from contracts.broker_domain import BrokerOrderRequest
from contracts.pilot_contracts import HumanOrderApproval, PilotSessionConfig, PilotStage


class PilotOrderPipeline:
    """
    Pipeline validator enforcing human sign-off per order in Stage 1 pilot sessions.
    """

    @staticmethod
    def _compute_sha256(data: Any) -> str:
        """Computes deterministic SHA-256 hash."""
        json_str = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(json_str.encode("utf-8")).hexdigest()

    def create_human_approval(
        self,
        operator_id: str,
        request: BrokerOrderRequest,
        config: PilotSessionConfig
    ) -> HumanOrderApproval:
        """
        Creates an immutable HumanOrderApproval record binding order request parameters.
        """
        now = datetime.now(timezone.utc)
        approval_id = f"APP-{uuid.uuid4().hex[:12].upper()}"

        limit_price = request.limit_price or 100.0
        approved_notional = request.quantity * limit_price

        payload = {
            "approval_id": approval_id,
            "operator_id": operator_id,
            "order_request_id": request.nextrade_execution_id,
            "symbol": request.symbol,
            "side": request.side.value if hasattr(request.side, "value") else str(request.side),
            "approved_quantity": request.quantity,
            "approved_notional": approved_notional,
            "config_hash": config.config_hash
        }
        signature = self._compute_sha256(payload)

        return HumanOrderApproval(
            approval_id=approval_id,
            operator_id=operator_id,
            order_request_id=request.nextrade_execution_id,
            symbol=request.symbol,
            side=request.side.value if hasattr(request.side, "value") else str(request.side),
            approved_quantity=request.quantity,
            approved_notional=approved_notional,
            config_hash=config.config_hash,
            approved_at=now,
            signature=signature
        )

    def validate_human_approval(
        self,
        approval: Optional[HumanOrderApproval],
        request: BrokerOrderRequest,
        config: PilotSessionConfig
    ) -> Tuple[bool, str]:
        """
        Validates HumanOrderApproval against BrokerOrderRequest and PilotSessionConfig.
        """
        if config.pilot_stage == PilotStage.STAGE_1_TINY_PILOT:
            if approval is None:
                return False, "PIPELINE_DENIED: Stage 1 requires explicit HumanOrderApproval for every order"

            if approval.order_request_id != request.nextrade_execution_id:
                return False, "PIPELINE_DENIED: HumanOrderApproval order_request_id mismatch"

            if approval.symbol != request.symbol:
                return False, "PIPELINE_DENIED: Approved symbol mismatch"

            if approval.approved_quantity != request.quantity:
                return False, "PIPELINE_DENIED: Approved quantity mismatch (tampering detected)"

            # Verify cryptographic signature
            limit_price = request.limit_price or 100.0
            approved_notional = request.quantity * limit_price
            payload = {
                "approval_id": approval.approval_id,
                "operator_id": approval.operator_id,
                "order_request_id": request.nextrade_execution_id,
                "symbol": request.symbol,
                "side": request.side.value if hasattr(request.side, "value") else str(request.side),
                "approved_quantity": request.quantity,
                "approved_notional": approved_notional,
                "config_hash": config.config_hash
            }
            expected_sig = self._compute_sha256(payload)
            if approval.signature != expected_sig:
                return False, "PIPELINE_DENIED: HumanOrderApproval signature mismatch"

        return True, "PIPELINE_APPROVED: Human approval validated"
