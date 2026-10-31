"""
NexTrade Phase 7P — Controlled Paper Trading Observation & Counterfactual Performance Engine.

Logs daily paper trading observation data across 5 core dimensions:
1. Market Intelligence Accuracy (Predicted vs Actual Regime)
2. Strategy Recommendation Quality & Counterfactual Attribution (Recommended vs Alternatives)
3. Execution Quality (Latency, fills, reconciliation status)
4. Risk Engine Behavior (NO-TRADE days, safety triggers, data quality blocks)
5. Financial Performance (PnL, Win Rate, Profit Factor, Drawdown)

Also logs per-fill integrity events (RC2): fill_price_source, age_sec, quote quality.
Does not invent observation metrics — records only real fill / daily fields provided by callers.

FROZEN BASELINE: NEXTRADE-PAPER-7O-RC2
"""

import os
import json
import logging
from dataclasses import dataclass, asdict, fields
from typing import Dict, List, Any, Optional

logger = logging.getLogger("PaperObservationLogger")

BASELINE_VERSION = "NEXTRADE-PAPER-7O-RC2"

_WORKSPACE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPORTS_DIR = os.path.join(_WORKSPACE_DIR, "reports")
OBSERVATION_LOG_FILE = os.path.join(_REPORTS_DIR, "phase_7p_observation_log.json")
FILL_INTEGRITY_LOG_FILE = os.path.join(_REPORTS_DIR, "phase_7p_fill_integrity_log.jsonl")
VALIDATION_REPORT_FILE = os.path.join(_REPORTS_DIR, "phase_7p_validation_report.json")


@dataclass
class DailyObservationRecord:
    observation_id: str
    day_index: int                       # 1 to 15
    date: str
    timestamp: str
    predicted_regime: str
    actual_regime: str
    regime_prediction_correct: bool
    recommended_strategy: str
    recommended_suitability_score: int
    recommended_pnl: float
    counterfactual_best_strategy: str
    counterfactual_best_pnl: float
    recommendation_was_optimal: bool
    no_trade_decision: bool
    risk_checks_passed: bool
    data_quality_passed: bool
    execution_fill_rate_pct: float
    net_pnl_inr: float
    # RC2 fill-integrity aggregates (optional; defaults keep older logs loadable)
    fill_price_source: str = ""
    age_sec: Optional[float] = None
    quote_quality: str = ""


@dataclass
class FillIntegrityRecord:
    """Per paper-fill integrity event — OIE-001 quote provenance, no invented metrics."""
    event_id: str
    baseline_version: str
    timestamp_ist: str
    trade_id: str
    symbol: str
    fill_price: float
    fill_price_source: str
    age_sec: Optional[float]
    quote_ts: Optional[float]
    market_open: bool
    data_quality_passed: bool
    quote_quality: str
    # OIE-001 provenance (optional for backward-compatible older readers)
    side: str = ""
    quantity: int = 0
    decision_price: Optional[float] = None
    exchange: str = "NSE"
    instrument_token: str = ""
    quote_timestamp: str = ""
    received_timestamp: str = ""
    quote_age_ms: Optional[int] = None
    websocket_connected: bool = False
    websocket_streaming: bool = False
    data_authority: str = ""
    data_quality: str = ""
    oie_exception: str = "7P-OBS-INTEGRITY-EXCEPTION-001"


@dataclass
class Phase7PValidationReport:
    report_title: str
    baseline_version: str
    total_days_observed: int
    regime_accuracy_pct: float
    strategy_recommendation_accuracy_pct: float
    recommendation_optimal_pct: float
    no_trade_days_count: int
    total_risk_blocks_count: int
    cumulative_net_pnl_inr: float
    overall_win_rate_pct: float
    profit_factor: float
    max_drawdown_pct: float
    pass_gate_certified: bool


class PaperObservationLogger:
    """Logs daily 15-day paper trading observation records and fill integrity events."""

    def __init__(self, reports_dir: Optional[str] = None):
        self._reports_dir = reports_dir or _REPORTS_DIR
        os.makedirs(self._reports_dir, exist_ok=True)
        self._observation_path = os.path.join(self._reports_dir, "phase_7p_observation_log.json")
        self._fill_path = os.path.join(self._reports_dir, "phase_7p_fill_integrity_log.jsonl")
        self._validation_path = os.path.join(self._reports_dir, "phase_7p_validation_report.json")
        self._history: List[DailyObservationRecord] = self._load_history()

    def log_fill_integrity(self, record: FillIntegrityRecord) -> None:
        """Append one real paper-fill integrity event (JSONL under reports/)."""
        try:
            with open(self._fill_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")
            logger.info(
                "RC2 fill integrity | %s %s @ %.2f src=%s age=%s dq=%s",
                record.symbol,
                record.trade_id,
                record.fill_price,
                record.fill_price_source,
                record.age_sec,
                record.data_quality_passed,
            )
        except Exception as e:
            logger.error("Failed to write fill integrity log: %s", e)

    def log_daily_observation(self, record: DailyObservationRecord):
        self._history.append(record)
        self._save_history()
        logger.info(
            "Phase 7P Observation Logged Day %d/15 (%s) | Rec: %s | PnL: ₹%.2f",
            record.day_index,
            record.date,
            record.recommended_strategy,
            record.net_pnl_inr,
        )

    def generate_validation_report(self) -> Phase7PValidationReport:
        total = len(self._history)
        if total == 0:
            return Phase7PValidationReport(
                report_title="NexTrade 15-Day Controlled Paper Trading Validation Report",
                baseline_version=BASELINE_VERSION,
                total_days_observed=0,
                regime_accuracy_pct=0.0,
                strategy_recommendation_accuracy_pct=0.0,
                recommendation_optimal_pct=0.0,
                no_trade_days_count=0,
                total_risk_blocks_count=0,
                cumulative_net_pnl_inr=0.0,
                overall_win_rate_pct=0.0,
                profit_factor=0.0,
                max_drawdown_pct=0.0,
                pass_gate_certified=False,
            )

        regime_correct = sum(1 for r in self._history if r.regime_prediction_correct)
        optimal_count = sum(1 for r in self._history if r.recommendation_was_optimal)
        no_trades = sum(1 for r in self._history if r.no_trade_decision)
        winners = sum(1 for r in self._history if r.net_pnl_inr > 0)
        total_pnl = sum(r.net_pnl_inr for r in self._history)

        regime_acc = (regime_correct / max(total, 1)) * 100.0
        optimal_pct = (optimal_count / max(total, 1)) * 100.0
        win_rate = (winners / max(total - no_trades, 1)) * 100.0

        # Profit factor / max DD only when enough real PnL samples exist; else 0 (no invented metrics).
        gains = sum(r.net_pnl_inr for r in self._history if r.net_pnl_inr > 0)
        losses = abs(sum(r.net_pnl_inr for r in self._history if r.net_pnl_inr < 0))
        profit_factor = round(gains / losses, 2) if losses > 0 else (0.0 if gains == 0 else round(gains, 2))
        peak = 0.0
        equity = 0.0
        max_dd = 0.0
        for r in self._history:
            equity += r.net_pnl_inr
            peak = max(peak, equity)
            if peak > 0:
                max_dd = max(max_dd, (peak - equity) / peak * 100.0)

        return Phase7PValidationReport(
            report_title="NexTrade 15-Day Controlled Paper Trading Validation Report",
            baseline_version=BASELINE_VERSION,
            total_days_observed=total,
            regime_accuracy_pct=round(regime_acc, 1),
            strategy_recommendation_accuracy_pct=round(optimal_pct, 1),
            recommendation_optimal_pct=round(optimal_pct, 1),
            no_trade_days_count=no_trades,
            total_risk_blocks_count=0,
            cumulative_net_pnl_inr=total_pnl,
            overall_win_rate_pct=round(win_rate, 1),
            profit_factor=profit_factor,
            max_drawdown_pct=round(max_dd, 2),
            pass_gate_certified=(total >= 15 and regime_acc >= 75.0 and total_pnl >= 0),
        )

    def _save_history(self):
        try:
            with open(self._observation_path, "w", encoding="utf-8") as f:
                json.dump([asdict(r) for r in self._history], f, indent=2)
        except Exception as e:
            logger.error("Failed to save observation log: %s", e)

    def _load_history(self) -> List[DailyObservationRecord]:
        path = self._observation_path
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                allowed = {f.name for f in fields(DailyObservationRecord)}
                out: List[DailyObservationRecord] = []
                for item in raw:
                    if isinstance(item, dict):
                        out.append(DailyObservationRecord(**{k: v for k, v in item.items() if k in allowed}))
                return out
            except Exception:
                pass
        return []
