# execution/shadow_evaluator.py
"""
Shadow Evaluator & Comparison Report Generator for NexTrade (Sub-Phase 4G).
Aggregates stored ShadowExecutionRecords into statistical ShadowComparisonReports
to provide empirical fill rate, slippage, and safety metrics for 4H promotion review.
"""
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from contracts.shadow_contracts import (
    ShadowExecutionRecord,
    ShadowOrderStatus,
    ShadowComparisonReport,
)
from storage.shadow_store import ShadowStore


class ShadowEvaluator:
    """
    Evaluates shadow mode performance metrics and constructs statistical comparison reports.
    """

    def __init__(self, shadow_store: Optional[ShadowStore] = None):
        self.shadow_store = shadow_store or ShadowStore()

    def generate_comparison_report(self) -> ShadowComparisonReport:
        """
        Queries ShadowStore records and computes statistical comparison metrics.
        """
        records = self.shadow_store.get_records()
        now = datetime.now(timezone.utc)
        report_id = f"REP-SHD-{uuid.uuid4().hex[:12].upper()}"

        if not records:
            return ShadowComparisonReport(
                report_id=report_id,
                total_shadow_orders=0,
                simulated_fill_count=0,
                missed_fill_count=0,
                simulated_fill_rate=0.0,
                average_slippage_bps=0.0,
                max_slippage_bps=0.0,
                average_timing_delta_ms=0.0,
                safety_gate_denials_count=0,
                timestamp=now
            )

        total_orders = len(records)
        filled_records = [r for r in records if r.status == ShadowOrderStatus.SHADOW_FILLED]
        missed_records = [r for r in records if r.status == ShadowOrderStatus.SHADOW_MISSED]
        denied_records = [r for r in records if r.safety_gate_denial_reasons]

        simulated_fill_count = len(filled_records)
        missed_fill_count = len(missed_records)
        simulated_fill_rate = (simulated_fill_count / total_orders) * 100.0 if total_orders > 0 else 0.0

        slippage_values = [r.slippage_bps for r in filled_records]
        avg_slippage = (sum(slippage_values) / len(slippage_values)) if slippage_values else 0.0
        max_slippage = max(slippage_values) if slippage_values else 0.0

        timing_deltas = [r.timing_delta_ms for r in records]
        avg_timing_delta = (sum(timing_deltas) / len(timing_deltas)) if timing_deltas else 0.0

        return ShadowComparisonReport(
            report_id=report_id,
            total_shadow_orders=total_orders,
            simulated_fill_count=simulated_fill_count,
            missed_fill_count=missed_fill_count,
            simulated_fill_rate=round(simulated_fill_rate, 2),
            average_slippage_bps=round(avg_slippage, 2),
            max_slippage_bps=round(max_slippage, 2),
            average_timing_delta_ms=round(avg_timing_delta, 2),
            safety_gate_denials_count=len(denied_records),
            timestamp=now
        )
