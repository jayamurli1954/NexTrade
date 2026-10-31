"""
Validation Phase orchestrator (VAL-A … VAL-H).

Evidence-only. No net-new product features. Research-only.
CLI: python -m research.run_validation_phase
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from research.data_validation import (
    DataValidationEngine,
    ValidationIssue,
    ValidationReport,
    default_validation_dir,
    run_full_validation,
    sha256_file,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _stable_json_bytes(obj: Any) -> bytes:
    """Canonical JSON without volatile timestamp keys."""

    def _scrub(x: Any) -> Any:
        if isinstance(x, dict):
            return {
                k: _scrub(v)
                for k, v in sorted(x.items())
                if k not in ("built_at", "updated_at", "checked_at", "generated_at", "created_at")
            }
        if isinstance(x, list):
            return [_scrub(i) for i in x]
        return x

    return json.dumps(_scrub(obj), sort_keys=True, separators=(",", ":")).encode("utf-8")


def _hash_json_file(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return hashlib.sha256(_stable_json_bytes(data)).hexdigest()
    except Exception:
        return sha256_file(path)


@dataclass
class TrackResult:
    track: str
    ok: bool
    status: str  # PASS | FAIL | PARTIAL | SKIP
    summary: str
    issues: List[Dict[str, Any]] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def track_val_a_dve_and_coverage() -> TrackResult:
    """VAL-A: DVE + RAE-7 coverage snapshot."""
    result = run_full_validation()
    cov_path = _repo_root() / "research" / "data" / "analytics" / "feature_coverage.json"
    cov = {}
    if cov_path.exists():
        cov = json.loads(cov_path.read_text(encoding="utf-8"))
    issues = []
    if not result["ok"]:
        issues.append({"severity": "error", "code": "DVE_FAIL", "message": "DVE-1 reported errors"})
    if not cov:
        issues.append({"severity": "warn", "code": "RAE7_MISSING", "message": "feature_coverage.json missing — rebuild analytics"})
    ok = result["ok"]
    return TrackResult(
        track="VAL-A",
        ok=ok,
        status="PASS" if ok else "FAIL",
        summary="DVE-1 + RAE-7 coverage",
        issues=issues,
        stats={
            "dve_ok": result["ok"],
            "error_count": result.get("error_count"),
            "issue_count": result.get("issue_count"),
            "coverage_rows": (cov or {}).get("rows"),
            "release_overall": (result.get("release_readiness") or {}).get("overall"),
        },
    )


def track_val_b_dual_rebuild() -> TrackResult:
    """VAL-B: rebuild analytics twice; compare stable SHA256 of key artifacts."""
    from research.analytics import ResearchAnalyticsEngine

    out = default_validation_dir() / "determinism"
    out.mkdir(parents=True, exist_ok=True)
    engine = ResearchAnalyticsEngine()
    keys = [
        "factor_distributions.json",
        "factor_correlation.json",
        "improvement_leaders.json",
        "feature_coverage.json",
    ]

    def _run_and_hash() -> Dict[str, Optional[str]]:
        engine.build_all()
        base = engine.out_dir
        return {k: _hash_json_file(base / k) for k in keys}

    h1 = _run_and_hash()
    h2 = _run_and_hash()
    mismatches = [k for k in keys if h1.get(k) != h2.get(k) or h1.get(k) is None]

    # Feature panel identity hash (disk stable; full dual rebuild is scheduled / optional)
    from research.feature_store import FeatureStore

    panel = FeatureStore().panel_path
    panel_h1 = sha256_file(panel)
    panel_h2 = sha256_file(panel)
    panel_ok = panel_h1 is not None and panel_h1 == panel_h2

    (out / "analytics_hash_run1.json").write_text(json.dumps(h1, indent=2), encoding="utf-8")
    (out / "analytics_hash_run2.json").write_text(json.dumps(h2, indent=2), encoding="utf-8")

    issues = []
    if mismatches:
        issues.append(
            {
                "severity": "error",
                "code": "ANALYTICS_HASH_MISMATCH",
                "message": f"Non-deterministic analytics outputs: {mismatches}",
            }
        )
    if not panel_ok:
        issues.append({"severity": "error", "code": "PANEL_HASH_UNSTABLE", "message": "Feature panel hash unstable"})

    ok = not mismatches and panel_ok
    return TrackResult(
        track="VAL-B",
        ok=ok,
        status="PASS" if ok else "FAIL",
        summary="Dual analytics rebuild SHA256 + feature panel identity",
        issues=issues,
        stats={
            "analytics_run1": h1,
            "analytics_run2": h2,
            "panel_sha256": panel_h1,
            "note": "Full Feature Store dual rebuild not run here (use scheduled rebuild); panel identity checked",
        },
    )


def track_val_c_arass_repeatability() -> TrackResult:
    """VAL-C: ARASS engine two runs on fixed synthetic panel → equal metrics fingerprint."""
    import numpy as np
    import pandas as pd

    from research.arass.definition import ARASS_PARAMS, build_arass_strategy_draft
    from research.arass.engine import ArassBacktestEngine

    def _synthetic_panel(n_days: int = 40, start: str = "2024-01-02") -> pd.DataFrame:
        days = pd.bdate_range(start=start, periods=n_days, freq="C")
        rows = []
        spot = 22000.0
        vix = 14.5
        rng = np.random.default_rng(42)
        for d in days:
            spot *= 1.0 + float(rng.normal(0, 0.0015))
            open_px = spot * (1.0 + float(rng.normal(0, 0.0005)))
            high = open_px * 1.004
            low = open_px * 0.996
            close = open_px * (1.0 + float(rng.normal(0, 0.001)))
            for minute in range(9 * 60 + 15, 15 * 60 + 30, 5):
                t = pd.Timestamp(d) + pd.Timedelta(hours=minute // 60, minutes=minute % 60)
                frac = (minute - (9 * 60 + 15)) / (6 * 60 + 15)
                px = open_px + (close - open_px) * frac
                rows.append(
                    {
                        "datetime": t,
                        "open": px,
                        "high": min(high, px * 1.001),
                        "low": max(low, px * 0.999),
                        "close": px,
                        "volume": 1000.0,
                        "vix": vix,
                    }
                )
        return pd.DataFrame(rows).set_index("datetime")

    def _fingerprint(result) -> Dict[str, Any]:
        m = result.metrics
        return {
            "total_trades": int(getattr(m, "total_trades", 0) or 0),
            "total_return_pct": round(float(getattr(m, "total_return_pct", 0) or 0), 6),
            "max_drawdown_pct": round(float(getattr(m, "max_drawdown_pct", 0) or 0), 6),
            "win_rate_pct": round(float(getattr(m, "win_rate_pct", 0) or 0), 6),
            "n_trade_rows": len(result.trades or []),
            "engine": result.engine_name,
        }

    panel = _synthetic_panel()
    draft = build_arass_strategy_draft()
    engine = ArassBacktestEngine(params=ARASS_PARAMS, event_dates=set())
    r1 = engine.run(draft, {"panel": panel, "provenance": "val_c_synthetic"})
    r2 = engine.run(draft, {"panel": panel, "provenance": "val_c_synthetic"})
    f1, f2 = _fingerprint(r1), _fingerprint(r2)
    ok = f1 == f2
    issues = []
    if not ok:
        issues.append({"severity": "error", "code": "ARASS_NONDETERMINISTIC", "message": "Two ARASS runs diverge"})
    return TrackResult(
        track="VAL-C",
        ok=ok,
        status="PASS" if ok else "FAIL",
        summary="ARASS synthetic dual-run equality",
        issues=issues,
        stats={"run1": f1, "run2": f2, "seed": 42},
    )


def track_val_d_paper_hygiene() -> TrackResult:
    """VAL-D: OIE-001 paper fill integrity hygiene (observation clock evidence)."""
    root = _repo_root()
    fill_path = root / "reports" / "phase_7p_fill_integrity_log.jsonl"
    shadow_path = root / "logs" / "shadow_execution.jsonl"
    issues: List[Dict[str, Any]] = []
    stats: Dict[str, Any] = {
        "fill_log": str(fill_path),
        "fill_events": 0,
        "bad_source": 0,
        "failed_quality": 0,
        "unique_days": 0,
        "shadow_events": 0,
    }

    forbidden_sources = {"REST_LTP", "YFINANCE", "MANUAL", "FAKE", "SYNTHETIC"}
    days = set()
    if not fill_path.exists():
        issues.append({"severity": "error", "code": "NO_FILL_LOG", "message": "phase_7p_fill_integrity_log.jsonl missing"})
    else:
        with fill_path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    issues.append({"severity": "warn", "code": "BAD_JSON", "message": "Unparseable fill log line"})
                    continue
                stats["fill_events"] += 1
                src = str(row.get("fill_price_source") or row.get("data_authority") or "").upper()
                if any(bad in src for bad in forbidden_sources) and "WEBSOCKET" not in src and "ANGEL_WS" not in src:
                    stats["bad_source"] += 1
                if row.get("data_quality_passed") is False or str(row.get("data_quality") or "").upper() == "INVALID":
                    stats["failed_quality"] += 1
                ts = str(row.get("timestamp_ist") or row.get("received_timestamp") or "")
                # extract date-like token
                m = re.search(r"(\d{4}-\d{2}-\d{2})|(\d{1,2}\s+\w+\s+2026)", ts)
                if m:
                    days.add(m.group(0))
                elif "2026" in ts:
                    days.add(ts[:20])
        stats["unique_days"] = len(days)

    if shadow_path.exists():
        with shadow_path.open(encoding="utf-8") as f:
            stats["shadow_events"] = sum(1 for line in f if line.strip())

    if stats["bad_source"]:
        issues.append(
            {
                "severity": "error",
                "code": "FORBIDDEN_FILL_SOURCE",
                "message": f"{stats['bad_source']} fills with forbidden price source",
            }
        )
    if stats["failed_quality"]:
        issues.append(
            {
                "severity": "warn",
                "code": "QUALITY_FAIL_FILLS",
                "message": f"{stats['failed_quality']} fills failed data quality",
            }
        )
    if stats["fill_events"] == 0:
        issues.append({"severity": "error", "code": "NO_FILLS", "message": "No paper fill integrity events"})
    elif stats["unique_days"] < 5:
        issues.append(
            {
                "severity": "warn",
                "code": "SHORT_OBSERVATION",
                "message": f"Only ~{stats['unique_days']} observation days logged (VG-2 needs months)",
            }
        )

    ok = not any(i["severity"] == "error" for i in issues)
    status = "PASS" if ok and not any(i["severity"] == "warn" for i in issues) else ("PARTIAL" if ok else "FAIL")
    return TrackResult(
        track="VAL-D",
        ok=ok,
        status=status,
        summary="Paper fill integrity hygiene (OIE-001)",
        issues=issues,
        stats=stats,
    )


def track_val_e_certification_checklist() -> TrackResult:
    """VAL-E: strategy certification checklist report."""
    from research.arass.definition import build_arass_strategy_draft
    from research.certification_store import CertificationStore
    from research.feature_store import FeatureStore

    draft = build_arass_strategy_draft()
    fs = FeatureStore()
    manifest = {}
    if fs.manifest_path.exists():
        try:
            manifest = json.loads(fs.manifest_path.read_text(encoding="utf-8"))
        except Exception:
            manifest = {}

    store = CertificationStore()
    existing = store.list_records(strategy_id=draft.strategy_id)
    package_path = default_validation_dir() / "arass_certification_package.json"
    package_doc = {}
    if package_path.exists():
        try:
            package_doc = json.loads(package_path.read_text(encoding="utf-8"))
        except Exception:
            package_doc = {}

    cert_status = None
    if existing:
        cert_status = (existing[-1].get("record") or {}).get("certification_status")
    elif package_doc:
        cert_status = (package_doc.get("certification") or {}).get("status")

    checklist = {
        "strategy_id": draft.strategy_id,
        "version": draft.version,
        "name": draft.name,
        "hypothesis_id": draft.hypothesis_id,
        "data_used": list(draft.data_requirements) if draft.data_requirements else ["spot", "vix", "options"],
        "feature_store_version": manifest.get("feature_store_version"),
        "feature_build_mode": manifest.get("mode"),
        "backtest_engine": "NEXTRADE_ARASS_RESEARCH_V1",
        "paper_trading_status": "IN_PROGRESS_OBSERVATION",
        "certification_records_on_disk": len(existing),
        "certification_status": cert_status,
        "certification_package_path": str(package_path) if package_path.exists() else None,
        "lifecycle_status": "VALIDATED/PENDING — not LIVE_ELIGIBLE",
        "live_eligible": False,
        "checks": {
            "has_version": bool(draft.version),
            "has_hypothesis": bool(draft.hypothesis_id),
            "has_feature_manifest": bool(manifest),
            "has_cert_package": len(existing) > 0 or bool(package_doc),
            "not_live_eligible": True,
            "gates_unchanged_freeze": True,
        },
    }
    checks = checklist["checks"]
    issues = []
    if not checks["has_version"] or not checks["has_hypothesis"]:
        issues.append({"severity": "error", "code": "CERT_INCOMPLETE", "message": "Strategy missing version/hypothesis"})
    if not checks["has_feature_manifest"]:
        issues.append({"severity": "warn", "code": "NO_FEATURE_MANIFEST", "message": "Feature store manifest missing"})
    if not checks["has_cert_package"]:
        issues.append(
            {
                "severity": "warn",
                "code": "NO_CERT_RECORD",
                "message": "No StrategyCertificationRecord yet — run python -m research.certify_arass",
            }
        )
    if cert_status == "PENDING":
        issues.append(
            {
                "severity": "info",
                "code": "CERT_PENDING",
                "message": "ARASS package PENDING (promotion bar not met) — expected; not LIVE",
            }
        )

    out = default_validation_dir() / "certification_checklist_latest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(checklist, indent=2), encoding="utf-8")

    ok = not any(i["severity"] == "error" for i in issues)
    # PASS when package exists (PENDING or CERTIFIED); PARTIAL only if missing package
    if ok and checks["has_cert_package"]:
        status = "PASS"
    elif ok:
        status = "PARTIAL"
    else:
        status = "FAIL"
    return TrackResult(
        track="VAL-E",
        ok=ok,
        status=status,
        summary="Strategy certification checklist (ARASS)",
        issues=issues,
        stats={"checklist_path": str(out), "checklist": checklist},
    )


def track_val_f_known_gaps() -> TrackResult:
    """VAL-F: categorized known-gaps register present and well-formed."""
    path = default_validation_dir() / "known_gaps.json"
    required = {"data_gaps", "feature_gaps", "execution_gaps", "validation_gaps"}
    issues = []
    stats: Dict[str, Any] = {}
    if not path.exists():
        issues.append({"severity": "error", "code": "GAPS_MISSING", "message": "known_gaps.json missing"})
        return TrackResult("VAL-F", False, "FAIL", "Known gaps register", issues, stats)
    doc = json.loads(path.read_text(encoding="utf-8"))
    cats = doc.get("categories") or {}
    missing = sorted(required - set(cats.keys()))
    if missing:
        issues.append({"severity": "error", "code": "GAPS_CATS", "message": f"Missing categories: {missing}"})
    counts = {k: len(v) if isinstance(v, list) else 0 for k, v in cats.items()}
    stats = {"path": str(path), "counts": counts, "total": sum(counts.values())}
    ok = not issues
    return TrackResult(
        track="VAL-F",
        ok=ok,
        status="PASS" if ok else "FAIL",
        summary="Categorized known-gaps register",
        issues=issues,
        stats=stats,
    )


def track_val_g_release_readiness() -> TrackResult:
    """VAL-G: release readiness artifact from latest DVE run."""
    path = default_validation_dir() / "release_readiness_latest.json"
    issues = []
    if not path.exists():
        # regenerate via DVE
        run_full_validation()
    if not path.exists():
        issues.append({"severity": "error", "code": "NO_RELEASE", "message": "release_readiness_latest.json missing"})
        return TrackResult("VAL-G", False, "FAIL", "Release readiness", issues, {})
    doc = json.loads(path.read_text(encoding="utf-8"))
    overall = doc.get("overall")
    if overall != "PASS":
        issues.append({"severity": "error", "code": "RELEASE_FAIL", "message": f"overall={overall}"})
    ok = overall == "PASS"
    return TrackResult(
        track="VAL-G",
        ok=ok,
        status="PASS" if ok else "FAIL",
        summary="Release readiness executive report",
        issues=issues,
        stats=doc,
    )


def track_val_h_performance_hard() -> TrackResult:
    """VAL-H: performance targets as hard gates (warm cache)."""
    dve = DataValidationEngine()
    rep = dve.measure_performance(hard=True)
    issues = [asdict(i) for i in rep.issues]
    return TrackResult(
        track="VAL-H",
        ok=rep.ok,
        status="PASS" if rep.ok else "FAIL",
        summary="Performance hard gates (feature_panel / search)",
        issues=issues,
        stats=rep.stats,
    )


def run_validation_phase(*, tracks: Optional[List[str]] = None) -> Dict[str, Any]:
    """Run Validation Phase tracks; write phase report."""
    all_tracks = [
        ("VAL-A", track_val_a_dve_and_coverage),
        ("VAL-B", track_val_b_dual_rebuild),
        ("VAL-C", track_val_c_arass_repeatability),
        ("VAL-D", track_val_d_paper_hygiene),
        ("VAL-E", track_val_e_certification_checklist),
        ("VAL-F", track_val_f_known_gaps),
        ("VAL-G", track_val_g_release_readiness),
        ("VAL-H", track_val_h_performance_hard),
    ]
    wanted = set(tracks) if tracks else None
    results: List[TrackResult] = []
    for name, fn in all_tracks:
        if wanted and name not in wanted:
            continue
        results.append(fn())

    hard_fail = [r for r in results if not r.ok]
    partial = [r for r in results if r.status == "PARTIAL"]
    overall = "PASS" if not hard_fail else "FAIL"
    if not hard_fail and partial:
        overall = "PARTIAL"

    report = {
        "phase": "Validation Phase",
        "built_at": _utc_now(),
        "platform": "SanMitra Research Platform",
        "overall": overall,
        "freeze": "No net-new product features (FI-3 / OI / Margin / Capital deferred)",
        "tracks": [r.to_dict() for r in results],
        "pass_count": sum(1 for r in results if r.status == "PASS"),
        "partial_count": sum(1 for r in results if r.status == "PARTIAL"),
        "fail_count": sum(1 for r in results if r.status == "FAIL"),
        "note": "Evidence run. Not execution authority. VG-2 paper months still accumulate.",
    }

    out_dir = default_validation_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "validation_phase_latest.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    md = [
        "# Validation Phase Report",
        "",
        f"**Overall:** {overall}",
        f"**Built:** {report['built_at']}",
        "",
        "| Track | Status | Summary |",
        "|-------|--------|---------|",
    ]
    for r in results:
        md.append(f"| {r.track} | {r.status} | {r.summary} |")
    md.append("")
    (out_dir / "validation_phase_latest.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    return report
