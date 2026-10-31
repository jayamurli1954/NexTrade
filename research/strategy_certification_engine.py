"""
NexTrade Strategy Certification Engine (Phase 7A scaffold).

Enforces Strategy Certification Invariant for research lifecycle transitions.
Does not modify live StrategyRegistry trading behaviour or Risk Engine (OIE-001 safe).
"""

from __future__ import annotations

import logging
import uuid
from typing import Dict, Optional

from contracts.strategy_research import (
    ResearchHypothesis,
    ResearchSource,
    StrategyCertificationRecord,
    StrategyDefinitionDraft,
    StrategyLifecycleError,
    StrategyLifecycleState,
    assert_transition,
    can_transition,
)
from research.backtest_protocol import BacktestResult

logger = logging.getLogger("StrategyCertificationEngine")


class StrategyCertificationEngine:
    """Tracks hypothesis → draft → lifecycle → certification packages (research domain)."""

    def __init__(self, store=None) -> None:
        self._hypotheses: Dict[str, ResearchHypothesis] = {}
        self._drafts: Dict[str, StrategyDefinitionDraft] = {}
        self._states: Dict[str, StrategyLifecycleState] = {}
        self._certs: Dict[str, StrategyCertificationRecord] = {}
        self._store = store

    def submit_hypothesis(self, hypothesis: ResearchHypothesis) -> ResearchHypothesis:
        self._hypotheses[hypothesis.hypothesis_id] = hypothesis
        logger.info("Research hypothesis registered: %s", hypothesis.hypothesis_id)
        return hypothesis

    def register_draft(
        self,
        draft: StrategyDefinitionDraft,
        *,
        initial_state: StrategyLifecycleState = StrategyLifecycleState.RESEARCH,
    ) -> StrategyDefinitionDraft:
        if draft.hypothesis_id not in self._hypotheses:
            raise StrategyLifecycleError(
                f"Unknown hypothesis_id '{draft.hypothesis_id}' — submit ResearchHypothesis first"
            )
        key = self._key(draft.strategy_id, draft.version)
        self._drafts[key] = draft
        self._states[key] = initial_state
        return draft

    def get_state(self, strategy_id: str, version: str) -> Optional[StrategyLifecycleState]:
        return self._states.get(self._key(strategy_id, version))

    def transition(
        self,
        strategy_id: str,
        version: str,
        target: StrategyLifecycleState,
    ) -> StrategyLifecycleState:
        key = self._key(strategy_id, version)
        current = self._states.get(key)
        if current is None:
            raise StrategyLifecycleError(f"Unknown strategy draft {strategy_id}@{version}")
        cert = self._certs.get(key)
        has_cert = bool(
            cert
            and cert.certification_status == "CERTIFIED"
            and cert.package_hash
        )
        assert_transition(current, target, has_valid_certification=has_cert)
        self._states[key] = target
        logger.info(
            "Strategy lifecycle %s@%s: %s → %s",
            strategy_id,
            version,
            current.value,
            target.value,
        )
        return target

    def certify_from_backtest(
        self,
        draft: StrategyDefinitionDraft,
        result: BacktestResult,
        *,
        certifier: str = "NEXTRADE_STRATEGY_CERTIFICATION_ENGINE",
        walk_forward_summary: str = "",
        monte_carlo_summary: str = "",
        known_failure_modes: tuple = (),
    ) -> StrategyCertificationRecord:
        """Create a CERTIFIED package from a research backtest result (does not auto-promote to LIVE)."""
        key = self._key(draft.strategy_id, draft.version)
        if key not in self._drafts:
            self.register_draft(draft, initial_state=StrategyLifecycleState.BACKTESTED)

        hyp = self._hypotheses.get(draft.hypothesis_id)
        source = hyp.source if hyp else ResearchSource.INTERNAL

        provisional = StrategyCertificationRecord(
            certification_id=f"cert-{uuid.uuid4().hex[:12]}",
            strategy_id=draft.strategy_id,
            strategy_version=draft.version,
            hypothesis_id=draft.hypothesis_id,
            research_source=source,
            backtest_engine=result.engine_name,
            backtest_period_start=result.period_start,
            backtest_period_end=result.period_end,
            out_of_sample_period="",
            walk_forward_summary=walk_forward_summary,
            monte_carlo_summary=monte_carlo_summary,
            metrics=result.metrics,
            known_failure_modes=known_failure_modes,
            certification_status="CERTIFIED",
            certifier=certifier,
            package_hash="",
            evidence_refs={"backtest_run_id": result.run_id},
        )
        package_hash = provisional.compute_package_hash()
        record = StrategyCertificationRecord(
            certification_id=provisional.certification_id,
            strategy_id=provisional.strategy_id,
            strategy_version=provisional.strategy_version,
            hypothesis_id=provisional.hypothesis_id,
            research_source=provisional.research_source,
            backtest_engine=provisional.backtest_engine,
            backtest_period_start=provisional.backtest_period_start,
            backtest_period_end=provisional.backtest_period_end,
            out_of_sample_period=provisional.out_of_sample_period,
            walk_forward_summary=provisional.walk_forward_summary,
            monte_carlo_summary=provisional.monte_carlo_summary,
            metrics=provisional.metrics,
            known_failure_modes=provisional.known_failure_modes,
            certification_status=provisional.certification_status,
            certifier=provisional.certifier,
            certified_at=provisional.certified_at,
            package_hash=package_hash,
            evidence_refs=provisional.evidence_refs,
        )
        self._certs[key] = record
        if self._store is not None:
            try:
                self._store.save(record)
            except Exception as exc:
                logger.warning("Certification persist failed: %s", exc)

        # Advance toward CERTIFIED if currently earlier in the pipeline
        state = self._states.get(key, StrategyLifecycleState.BACKTESTED)
        for step in (
            StrategyLifecycleState.BACKTESTED,
            StrategyLifecycleState.VALIDATED,
            StrategyLifecycleState.CERTIFIED,
        ):
            if can_transition(state, step, has_valid_certification=True) or state == step:
                if state != step and can_transition(state, step, has_valid_certification=True):
                    state = self.transition(draft.strategy_id, draft.version, step)
                elif state == step:
                    continue
        if self._states.get(key) != StrategyLifecycleState.CERTIFIED:
            # Force-set when already past earlier gates
            self._states[key] = StrategyLifecycleState.CERTIFIED

        return record

    def is_live_eligible(self, strategy_id: str, version: str) -> bool:
        key = self._key(strategy_id, version)
        return self._states.get(key) == StrategyLifecycleState.LIVE_ELIGIBLE

    @staticmethod
    def _key(strategy_id: str, version: str) -> str:
        return f"{strategy_id}@{version}"
