"""
NexTrade Strategy Research Domain Contracts
(Awesome Systematic Trading borrow — Phase 7A scaffold).

Defines Research Hypothesis, lifecycle states, and Strategy Certification records.
Does NOT change live strategy scoring, risk limits, or execution gates (OIE-001 safe).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class StrategyLifecycleState(str, Enum):
    RESEARCH = "RESEARCH"
    CANDIDATE = "CANDIDATE"
    BACKTESTED = "BACKTESTED"
    VALIDATED = "VALIDATED"
    CERTIFIED = "CERTIFIED"
    SHADOW = "SHADOW"
    PAPER = "PAPER"
    LIVE_ELIGIBLE = "LIVE_ELIGIBLE"
    REJECTED = "REJECTED"
    RETIRED = "RETIRED"


# Allowed forward transitions (certification gate enforced separately for LIVE_ELIGIBLE)
_ALLOWED_TRANSITIONS = {
    StrategyLifecycleState.RESEARCH: {
        StrategyLifecycleState.CANDIDATE,
        StrategyLifecycleState.REJECTED,
        StrategyLifecycleState.RETIRED,
    },
    StrategyLifecycleState.CANDIDATE: {
        StrategyLifecycleState.BACKTESTED,
        StrategyLifecycleState.REJECTED,
        StrategyLifecycleState.RETIRED,
    },
    StrategyLifecycleState.BACKTESTED: {
        StrategyLifecycleState.VALIDATED,
        StrategyLifecycleState.REJECTED,
        StrategyLifecycleState.RETIRED,
    },
    StrategyLifecycleState.VALIDATED: {
        StrategyLifecycleState.CERTIFIED,
        StrategyLifecycleState.REJECTED,
        StrategyLifecycleState.RETIRED,
    },
    StrategyLifecycleState.CERTIFIED: {
        StrategyLifecycleState.SHADOW,
        StrategyLifecycleState.PAPER,
        StrategyLifecycleState.RETIRED,
    },
    StrategyLifecycleState.SHADOW: {
        StrategyLifecycleState.PAPER,
        StrategyLifecycleState.LIVE_ELIGIBLE,
        StrategyLifecycleState.RETIRED,
        StrategyLifecycleState.REJECTED,
    },
    StrategyLifecycleState.PAPER: {
        StrategyLifecycleState.SHADOW,
        StrategyLifecycleState.LIVE_ELIGIBLE,
        StrategyLifecycleState.RETIRED,
        StrategyLifecycleState.REJECTED,
    },
    StrategyLifecycleState.LIVE_ELIGIBLE: {
        StrategyLifecycleState.RETIRED,
        StrategyLifecycleState.REJECTED,
    },
    StrategyLifecycleState.REJECTED: {StrategyLifecycleState.RETIRED},
    StrategyLifecycleState.RETIRED: set(),
}


class ResearchSource(str, Enum):
    INVESTMITRA = "INVESTMITRA"
    MANUAL = "MANUAL"
    PWB_TOOLBOX = "PWB_TOOLBOX"
    ACADEMIC = "ACADEMIC"
    AWESOME_SYSTEMATIC_TRADING = "AWESOME_SYSTEMATIC_TRADING"
    INTERNAL = "INTERNAL"
    AI_EXPERIMENTAL = "AI_EXPERIMENTAL"


@dataclass(frozen=True)
class ResearchHypothesis:
    """InvestMitra / research → NexTrade Quant Lab contract. Never authorises trades."""

    hypothesis_id: str
    title: str
    summary: str
    source: ResearchSource
    asset_universe: str = "NSE_EQUITY"
    economic_rationale: str = ""
    academic_references: tuple = ()
    known_limitations: tuple = ()
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["source"] = self.source.value
        return d


@dataclass(frozen=True)
class StrategyDefinitionDraft:
    """
    Formal strategy specification for research only.
    Must not be confused with live StrategyRegistry entries until CERTIFIED.
    """

    strategy_id: str
    version: str
    name: str
    hypothesis_id: str
    family: str  # e.g. TREND, MEAN_REVERSION, FACTOR, VOLATILITY, REGIME
    entry_rules_summary: str
    exit_rules_summary: str
    universe: str = "NSE_EQUITY"
    timeframe: str = "15m"
    data_requirements: tuple = ()
    features: tuple = ()
    position_sizing_summary: str = ""
    risk_model_summary: str = ""
    transaction_cost_model: str = "BPS_FLAT"
    slippage_model: str = "BPS_FLAT"
    code_commit_hash: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass(frozen=True)
class BacktestMetricsSummary:
    total_trades: int = 0
    win_rate_pct: float = 0.0
    profit_factor: float = 0.0
    sharpe: float = 0.0
    sortino: float = 0.0
    max_drawdown_pct: float = 0.0
    total_return_pct: float = 0.0
    turnover: float = 0.0


@dataclass(frozen=True)
class StrategyCertificationRecord:
    """
    Immutable certification evidence package (research domain).
    LIVE_ELIGIBLE requires a record with status CERTIFIED and non-empty package_hash.
    """

    certification_id: str
    strategy_id: str
    strategy_version: str
    hypothesis_id: str
    research_source: ResearchSource
    backtest_engine: str
    backtest_period_start: str
    backtest_period_end: str
    out_of_sample_period: str = ""
    walk_forward_summary: str = ""
    monte_carlo_summary: str = ""
    metrics: BacktestMetricsSummary = field(default_factory=BacktestMetricsSummary)
    known_failure_modes: tuple = ()
    certification_status: str = "CERTIFIED"  # CERTIFIED | REJECTED | PENDING
    certifier: str = "NEXTRADE_STRATEGY_CERTIFICATION_ENGINE"
    certified_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    package_hash: str = ""
    evidence_refs: Dict[str, str] = field(default_factory=dict)

    def compute_package_hash(self) -> str:
        payload = {
            "certification_id": self.certification_id,
            "strategy_id": self.strategy_id,
            "strategy_version": self.strategy_version,
            "hypothesis_id": self.hypothesis_id,
            "research_source": self.research_source.value,
            "backtest_engine": self.backtest_engine,
            "backtest_period_start": self.backtest_period_start,
            "backtest_period_end": self.backtest_period_end,
            "out_of_sample_period": self.out_of_sample_period,
            "metrics": asdict(self.metrics),
            "certification_status": self.certification_status,
            "certified_at": self.certified_at,
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class StrategyLifecycleError(ValueError):
    pass


def can_transition(
    current: StrategyLifecycleState,
    target: StrategyLifecycleState,
    *,
    has_valid_certification: bool = False,
) -> bool:
    allowed = _ALLOWED_TRANSITIONS.get(current, set())
    if target not in allowed:
        return False
    if target == StrategyLifecycleState.LIVE_ELIGIBLE and not has_valid_certification:
        return False
    return True


def assert_transition(
    current: StrategyLifecycleState,
    target: StrategyLifecycleState,
    *,
    has_valid_certification: bool = False,
) -> None:
    if not can_transition(current, target, has_valid_certification=has_valid_certification):
        raise StrategyLifecycleError(
            f"Illegal lifecycle transition {current.value} → {target.value} "
            f"(certification_present={has_valid_certification})"
        )


# Strategy Research Catalogue taxonomy (discovery layer — not live strategies)
STRATEGY_CATALOGUE_FAMILIES: Dict[str, List[str]] = {
    "TREND_FOLLOWING": [
        "Time Series Momentum",
        "Cross-Sectional Momentum",
        "Moving Average Systems",
    ],
    "MEAN_REVERSION": [
        "Short-Term Reversal",
        "Statistical Mean Reversion",
        "Pairs Trading",
    ],
    "FACTOR": [
        "Momentum",
        "Value",
        "Quality",
        "Low Volatility",
        "Size",
    ],
    "VOLATILITY": [
        "Volatility Breakout",
        "Volatility Targeting",
        "Regime-Based Volatility",
    ],
    "MARKET_REGIME": [
        "Trend Regime",
        "Volatility Regime",
        "Risk-On/Risk-Off",
    ],
    "PORTFOLIO": [
        "Risk Parity",
        "Momentum Allocation",
        "Dynamic Asset Allocation",
    ],
}
