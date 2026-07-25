# execution/shadow_runner.py
"""
Strategy & Gateway Shadow Mode Runner for NexTrade (Sub-Phase 4G).
Orchestrates the non-executing comparison pipeline:
ExecutionRequest -> ExecutionGateway -> LiveSafetyGate (S12 DENY) -> ShadowEngine -> ShadowStore -> Telemetry.
Zero external broker dispatches occur.
"""
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from contracts.execution import ExecutionRequest
from contracts.broker_translation import to_broker_order_request
from contracts.safety_contracts import SafetyEvaluationContext, ExecutionEnvironment
from contracts.shadow_contracts import ShadowExecutionRecord
from execution.safety_gate import LiveSafetyGate
from execution.shadow_engine import ShadowEngine
from storage.shadow_store import ShadowStore
from observability.metrics_registry import MetricsRegistry
from contracts.observability_contracts import MetricCategory


class ShadowRunner:
    """
    Non-executing comparison pipeline orchestrating shadow executions.
    """

    def __init__(
        self,
        safety_gate: Optional[LiveSafetyGate] = None,
        shadow_engine: Optional[ShadowEngine] = None,
        shadow_store: Optional[ShadowStore] = None,
        metrics_registry: Optional[MetricsRegistry] = None
    ):
        self.safety_gate = safety_gate or LiveSafetyGate()
        self.shadow_engine = shadow_engine or ShadowEngine()
        self.shadow_store = shadow_store or ShadowStore()
        self.metrics_registry = metrics_registry

    def process_shadow_execution(
        self,
        request: ExecutionRequest,
        market_tick_price: float,
        live_trading_enabled: bool = False
    ) -> ShadowExecutionRecord:
        """
        Processes an ExecutionRequest in Shadow Mode:
        1. Translates ExecutionRequest to BrokerOrderRequest.
        2. Evaluates LiveSafetyGate in ExecutionEnvironment.SHADOW (S12 evaluates to DENY).
        3. Matches shadow order against market_tick_price in ShadowEngine.
        4. Saves record to ShadowStore (SQLite + JSONL).
        5. Emits read-only shadow metrics.
        Returns ShadowExecutionRecord.
        """
        now = datetime.now(timezone.utc)
        broker_req = to_broker_order_request(request)

        # 2. Evaluate LiveSafetyGate under ExecutionEnvironment.SHADOW
        safety_context = SafetyEvaluationContext(
            live_trading_enabled=live_trading_enabled,
            environment=ExecutionEnvironment.SHADOW,
            timestamp=now
        )
        safety_res = self.safety_gate.authorize_dispatch(broker_req, safety_context)
        denial_reasons = safety_res.denial_reasons or ["SHADOW_ENVIRONMENT_NO_DISPATCH"]

        # 3. Match shadow order against market tick price
        record = self.shadow_engine.match_shadow_order(
            request=broker_req,
            market_tick_price=market_tick_price,
            safety_denial_reasons=denial_reasons,
            request_timestamp=request.timestamp
        )

        # 4. Save record to dual persistence store (SQLite + JSONL)
        saved = self.shadow_store.save_record(record)

        # 5. Emit shadow telemetry metrics (best-effort)
        if self.metrics_registry is not None:
            self.metrics_registry.increment_counter(
                "nextrade_shadow_orders_total",
                MetricCategory.GATEWAY,
                labels={"symbol": record.symbol, "status": record.status.value}
            )
            self.metrics_registry.set_gauge(
                "nextrade_shadow_last_slippage_bps",
                MetricCategory.GATEWAY,
                record.slippage_bps
            )
            if not saved:
                self.metrics_registry.increment_counter(
                    "nextrade_shadow_persistence_failures_total",
                    MetricCategory.SYSTEM_HEALTH
                )

        return record
