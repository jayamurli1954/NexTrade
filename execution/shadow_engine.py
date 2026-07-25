# execution/shadow_engine.py
"""
Shadow Execution Engine & Deterministic Market Matcher for NexTrade (Sub-Phase 4G).
Matches non-executing shadow order requests against real-time market data ticks,
calculates deterministic simulated fill prices, slippage (bps), and timing deltas.
"""
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

from contracts.broker_domain import BrokerOrderRequest, BrokerOrderSide
from contracts.shadow_contracts import ShadowExecutionRecord, ShadowOrderStatus


class ShadowEngine:
    """
    Deterministic tick matcher computing simulated fills and slippage for shadow orders.
    """

    def __init__(self, fixed_slippage_bps: float = 2.0):
        self.fixed_slippage_bps = fixed_slippage_bps

    def match_shadow_order(
        self,
        request: BrokerOrderRequest,
        market_tick_price: float,
        safety_denial_reasons: Optional[List[str]] = None,
        request_timestamp: Optional[datetime] = None
    ) -> ShadowExecutionRecord:
        """
        Deterministically matches a shadow order against a market tick price.
        Returns a ShadowExecutionRecord.
        """
        now = datetime.now(timezone.utc)
        req_time = request_timestamp or now
        timing_delta_ms = (now - req_time).total_seconds() * 1000.0

        limit_price = request.limit_price or market_tick_price
        is_buy = (request.side == BrokerOrderSide.BUY)

        # Deterministic Matching Rule:
        # BUY fills if market_tick_price <= limit_price
        # SELL fills if market_tick_price >= limit_price
        fills_buy = is_buy and (market_tick_price <= limit_price)
        fills_sell = (not is_buy) and (market_tick_price >= limit_price)

        if fills_buy or fills_sell:
            status = ShadowOrderStatus.SHADOW_FILLED
            # Apply deterministic slippage model
            slippage_factor = (1.0 + (self.fixed_slippage_bps / 10000.0)) if is_buy else (1.0 - (self.fixed_slippage_bps / 10000.0))
            simulated_fill_price = round(market_tick_price * slippage_factor, 4)
            slippage_bps = self.fixed_slippage_bps
        else:
            status = ShadowOrderStatus.SHADOW_MISSED
            simulated_fill_price = 0.0
            slippage_bps = 0.0

        shadow_id = f"SHD-{uuid.uuid4().hex[:12].upper()}"

        return ShadowExecutionRecord(
            shadow_id=shadow_id,
            execution_request_id=request.nextrade_execution_id,
            symbol=request.symbol,
            side=request.side.value if hasattr(request.side, "value") else str(request.side),
            quantity=request.quantity,
            limit_price=limit_price,
            simulated_fill_price=simulated_fill_price,
            market_tick_price=market_tick_price,
            slippage_bps=slippage_bps,
            timing_delta_ms=timing_delta_ms,
            status=status,
            safety_gate_denial_reasons=safety_denial_reasons or ["SHADOW_ENVIRONMENT_NO_DISPATCH"],
            timestamp=now
        )
