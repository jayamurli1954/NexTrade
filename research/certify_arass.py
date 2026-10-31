"""
Generate ARASS Strategy Certification package (research domain only).

Does NOT promote to PAPER / LIVE_ELIGIBLE.
Uses existing backtest result JSON as evidence.

Usage:
  python -m research.certify_arass
  python -m research.certify_arass --result backtesting/results/arass_NIFTY_2024-01-01_2026-07-31.json
"""

from __future__ import annotations

import argparse
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from contracts.strategy_research import (
    BacktestMetricsSummary,
    ResearchSource,
    StrategyCertificationRecord,
    StrategyLifecycleState,
)
from research.arass.definition import build_arass_hypothesis, build_arass_strategy_draft
from research.backtest_protocol import BacktestConstraints, BacktestCostModel, BacktestResult
from research.certification_store import CertificationStore
from research.data_validation import default_validation_dir
from research.feature_store import FeatureStore
from research.strategy_certification_engine import StrategyCertificationEngine

logger = logging.getLogger("CertifyArass")

DEFAULT_RESULT = Path("backtesting/results/arass_NIFTY_2024-01-01_2026-07-31.json")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_arass_result(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def result_to_backtest(path: Path, draft) -> BacktestResult:
    raw = load_arass_result(path)
    m = raw.get("metrics") or {}
    metrics = BacktestMetricsSummary(
        total_trades=int(m.get("total_trades") or 0),
        win_rate_pct=float(m.get("win_rate_pct") or 0),
        profit_factor=float(m.get("profit_factor") or 0),
        sharpe=float(m.get("sharpe") or 0),
        sortino=float(m.get("sortino") or 0),
        max_drawdown_pct=float(m.get("max_drawdown_pct") or 0),
        total_return_pct=float(m.get("total_return_pct") or 0),
        turnover=float(m.get("exposure_pct") or 0),
    )
    # Infer period from filename or trades
    period_start, period_end = "2024-01-01", "2026-07-31"
    stem = path.stem  # arass_NIFTY_2024-01-01_2026-07-31
    parts = stem.split("_")
    if len(parts) >= 4:
        period_start, period_end = parts[-2], parts[-1]
    trades = raw.get("trades") or []
    if trades:
        period_start = str(trades[0].get("entry_day") or period_start)
        period_end = str(trades[-1].get("entry_day") or period_end)

    return BacktestResult(
        run_id=str(raw.get("run_id") or f"arass-{uuid.uuid4().hex[:10]}"),
        engine_name="NEXTRADE_ARASS_RESEARCH_V1",
        strategy_id=draft.strategy_id,
        strategy_version=draft.version,
        period_start=period_start,
        period_end=period_end,
        metrics=metrics,
        cost_model=BacktestCostModel(),
        constraints=BacktestConstraints(initial_capital=1_000_000.0),
        trades=trades[:5],  # sample only in package memory
        notes=str(raw.get("notes") or ""),
        extras={
            "provenance": raw.get("provenance"),
            "options_hits": raw.get("options_hits"),
            "options_misses": raw.get("options_misses"),
            "filter_stats": raw.get("filter_stats"),
            "source_result_path": str(path),
        },
    )


def build_arass_certification_package(
    *,
    result_path: Optional[Path] = None,
    status: str = "PENDING",
) -> Dict[str, Any]:
    """
    Persist ARASS certification evidence.

    Default status PENDING: metrics do not meet promotion bar;
    package exists for Validation Phase VAL-E. Never sets LIVE_ELIGIBLE.
    """
    root = _repo_root()
    path = Path(result_path) if result_path else root / DEFAULT_RESULT
    if not path.is_absolute():
        path = root / path
    if not path.exists():
        raise FileNotFoundError(f"ARASS result not found: {path}")

    hyp = build_arass_hypothesis()
    draft = build_arass_strategy_draft()
    bt = result_to_backtest(path, draft)

    fs = FeatureStore()
    feature_manifest = {}
    if fs.manifest_path.exists():
        feature_manifest = json.loads(fs.manifest_path.read_text(encoding="utf-8"))

    store = CertificationStore()
    eng = StrategyCertificationEngine(store=store)
    eng.submit_hypothesis(hyp)
    eng.register_draft(draft, initial_state=StrategyLifecycleState.BACKTESTED)

    failure_modes = (
        "Negative total return / expectancy on 2024–2026 research window",
        "High options OHLC miss rate → many synthetic BS fills in older runs",
        "Trade sample size small relative to filter candidate days",
        "Not eligible for paper/live promotion without improved OOS evidence",
        "Phase 7P freeze: no execution gate changes",
    )

    evidence = {
        "backtest_run_id": bt.run_id,
        "backtest_result_path": str(path),
        "feature_store_version": str(feature_manifest.get("feature_store_version") or "1.0"),
        "feature_build_mode": str(feature_manifest.get("mode") or ""),
        "feature_panel_rows": str(feature_manifest.get("rows") or ""),
        "validation_phase": "VAL-E",
        "oie_exception": "7P-OBS-INTEGRITY-EXCEPTION-001",
        "live_eligible": "false",
        "paper_promoted": "false",
    }
    try:
        evidence["backtest_result_path"] = str(path.relative_to(root))
    except ValueError:
        pass

    # Prefer PENDING when metrics fail a simple promotion bar
    m = bt.metrics
    promote_ok = (
        m.total_trades >= 30
        and m.total_return_pct > 0
        and m.profit_factor >= 1.0
        and m.max_drawdown_pct < 25
    )
    final_status = "CERTIFIED" if (status == "CERTIFIED" and promote_ok) else status
    if status == "AUTO":
        final_status = "CERTIFIED" if promote_ok else "PENDING"

    provisional = StrategyCertificationRecord(
        certification_id=f"cert-arass-{uuid.uuid4().hex[:10]}",
        strategy_id=draft.strategy_id,
        strategy_version=draft.version,
        hypothesis_id=draft.hypothesis_id,
        research_source=ResearchSource.INTERNAL,
        backtest_engine=bt.engine_name,
        backtest_period_start=bt.period_start,
        backtest_period_end=bt.period_end,
        out_of_sample_period="",
        walk_forward_summary="Not run in this package (AST-7B deferred)",
        monte_carlo_summary="Not run in this package (AST-7B deferred)",
        metrics=m,
        known_failure_modes=failure_modes,
        certification_status=final_status,
        certifier="NEXTRADE_VALIDATION_PHASE_VAL_E",
        package_hash="",
        evidence_refs=evidence,
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
        certification_status=final_status,
        certifier=provisional.certifier,
        certified_at=provisional.certified_at,
        package_hash=package_hash,
        evidence_refs=evidence,
    )

    # Persist via store; keep engine state at BACKTESTED/VALIDATED — never LIVE
    store.save(record)
    key = eng._key(draft.strategy_id, draft.version)
    eng._certs[key] = record
    if final_status == "CERTIFIED":
        eng._states[key] = StrategyLifecycleState.CERTIFIED
    else:
        eng._states[key] = StrategyLifecycleState.VALIDATED

    assert eng.get_state(draft.strategy_id, draft.version) != StrategyLifecycleState.LIVE_ELIGIBLE
    assert not eng.is_live_eligible(draft.strategy_id, draft.version)

    package = {
        "built_at": datetime.now(timezone.utc).isoformat(),
        "platform": "SanMitra Research Platform",
        "freeze_note": "Research certification package only. Not PAPER/LIVE. Phase 7P freeze intact.",
        "strategy": {
            "strategy_id": draft.strategy_id,
            "version": draft.version,
            "name": draft.name,
            "hypothesis_id": draft.hypothesis_id,
            "lifecycle_state": eng.get_state(draft.strategy_id, draft.version).value,
            "live_eligible": False,
            "paper_promoted": False,
        },
        "data_used": list(draft.data_requirements),
        "feature_version": evidence["feature_store_version"],
        "feature_build_mode": evidence["feature_build_mode"],
        "backtest": {
            "run_id": bt.run_id,
            "period_start": bt.period_start,
            "period_end": bt.period_end,
            "engine": bt.engine_name,
            "result_path": evidence["backtest_result_path"],
            "metrics": {
                "total_trades": m.total_trades,
                "win_rate_pct": m.win_rate_pct,
                "profit_factor": m.profit_factor,
                "sharpe": m.sharpe,
                "max_drawdown_pct": m.max_drawdown_pct,
                "total_return_pct": m.total_return_pct,
            },
        },
        "paper_trading": {
            "status": "IN_PROGRESS_OBSERVATION",
            "fill_integrity_log": "reports/phase_7p_fill_integrity_log.jsonl",
        },
        "certification": {
            "certification_id": record.certification_id,
            "status": record.certification_status,
            "package_hash": record.package_hash,
            "certifier": record.certifier,
            "known_failure_modes": list(record.known_failure_modes),
            "evidence_refs": record.evidence_refs,
        },
        "promotion_bar_met": promote_ok,
    }

    out_dir = default_validation_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "arass_certification_package.json"
    out_path.write_text(json.dumps(package, indent=2), encoding="utf-8")
    logger.info(
        "ARASS package %s status=%s hash=%s → %s (live_eligible=false)",
        record.certification_id,
        record.certification_status,
        record.package_hash[:12],
        out_path,
    )
    return package


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO)
    ap = argparse.ArgumentParser(description="Generate ARASS research certification package")
    ap.add_argument("--result", default=str(DEFAULT_RESULT), help="Path to ARASS backtest JSON")
    ap.add_argument(
        "--status",
        default="AUTO",
        choices=["AUTO", "PENDING", "CERTIFIED", "REJECTED"],
        help="AUTO uses promotion bar; default outcome for current metrics is PENDING",
    )
    args = ap.parse_args(argv)
    package = build_arass_certification_package(result_path=Path(args.result), status=args.status)
    print(json.dumps(package, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
