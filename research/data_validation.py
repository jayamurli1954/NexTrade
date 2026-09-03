"""
Data Validation Engine (DVE-1) — research data quality, perf smoke, repeatability.

SanMitra Research Platform. Research-only.
CLI: python -m research.run_data_validation
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import pandas as pd


def default_validation_dir(root: Optional[Path] = None) -> Path:
    base = root or Path(__file__).resolve().parents[1]
    return base / "research" / "data" / "validation"


# VG-1.1 performance targets
PERF_TARGETS = {
    "feature_panel_ms": 100.0,
    "research_search_ms": 500.0,
}


@dataclass
class ValidationIssue:
    severity: str  # error | warn | info
    code: str
    message: str
    context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidationReport:
    ok: bool
    checked_at: str
    target: str
    issues: List[ValidationIssue] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "checked_at": self.checked_at,
            "target": self.target,
            "issues": [asdict(i) for i in self.issues],
            "stats": self.stats,
        }


def sha256_file(path: Path) -> Optional[str]:
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class DataValidationEngine:
    def validate_feature_panel(
        self,
        df: pd.DataFrame,
        *,
        target: str = "feature_store",
        coverage_floors: Optional[Dict[str, float]] = None,
    ) -> ValidationReport:
        issues: List[ValidationIssue] = []
        now = datetime.now(timezone.utc).isoformat()
        floors = coverage_floors or {
            "quality": 50.0,
            "growth": 50.0,
            "value": 50.0,
            "financial_health": 50.0,
            "consistency": 50.0,
            "overall_fundamental": 50.0,
            "rsi": 40.0,
        }
        if df is None or df.empty:
            issues.append(ValidationIssue("warn", "EMPTY_PANEL", "Feature panel is empty"))
            return ValidationReport(ok=True, checked_at=now, target=target, issues=issues, stats={"rows": 0})

        rows = int(len(df))
        stats: Dict[str, Any] = {"rows": rows}

        if "date" not in df.columns or "symbol" not in df.columns:
            issues.append(ValidationIssue("error", "MISSING_KEYS", "Panel requires date and symbol columns"))
            return ValidationReport(ok=False, checked_at=now, target=target, issues=issues, stats=stats)

        dup = int(df.duplicated(subset=["date", "symbol"]).sum())
        stats["duplicate_date_symbol"] = dup
        if dup > 0:
            issues.append(
                ValidationIssue("error", "DUPLICATE_ROWS", f"{dup} duplicate (date, symbol) rows", {"count": dup})
            )

        if "rsi" in df.columns:
            bad = df["rsi"].dropna()
            bad = bad[(bad < 0) | (bad > 100)]
            if len(bad):
                issues.append(
                    ValidationIssue("error", "RSI_RANGE", f"{len(bad)} RSI values outside 0–100")
                )

        coverage: Dict[str, float] = {}
        for col in df.columns:
            if col in ("date", "symbol"):
                continue
            non_null = int(df[col].notna().sum())
            coverage[col] = round(100.0 * non_null / rows, 2) if rows else 0.0
        stats["coverage_pct"] = coverage

        # Latest-date cross-section (more meaningful for "usable today")
        latest_cov: Dict[str, float] = {}
        try:
            latest = str(pd.to_datetime(df["date"], errors="coerce").max().date())
            latest_df = df[df["date"].astype(str) == latest]
            n_latest = int(len(latest_df))
            stats["latest_date"] = latest
            stats["latest_rows"] = n_latest
            if n_latest:
                for col in df.columns:
                    if col in ("date", "symbol"):
                        continue
                    latest_cov[col] = round(100.0 * int(latest_df[col].notna().sum()) / n_latest, 2)
            stats["latest_coverage_pct"] = latest_cov
        except Exception:
            latest_cov = {}

        # Full-panel floors: warn on sparse hist (value often null pre-peer window)
        sparse_ok_warn = {"value"}
        for col, pct in coverage.items():
            if pct == 0 and col in ("pcr", "oi"):
                issues.append(
                    ValidationIssue("info", "PENDING_FEATURE", f"{col} coverage 0% (expected pending)", {"feature": col})
                )
            elif col in floors and pct < floors[col]:
                if col in sparse_ok_warn:
                    issues.append(
                        ValidationIssue(
                            "warn",
                            "LOW_COVERAGE_HIST",
                            f"{col} full-panel coverage {pct}% (known hist sparsity; see latest_coverage)",
                            {"feature": col, "coverage_pct": pct, "floor": floors[col]},
                        )
                    )
                else:
                    severity = "error" if pct < 30 else "warn"
                    issues.append(
                        ValidationIssue(
                            severity,
                            "LOW_COVERAGE",
                            f"{col} coverage {pct}% (floor {floors[col]}%)",
                            {"feature": col, "coverage_pct": pct, "floor": floors[col]},
                        )
                    )

        # Hard floors on latest cross-section for core fundamentals (except value until denser)
        for col, floor in (("quality", 70.0), ("growth", 70.0), ("overall_fundamental", 70.0), ("rsi", 80.0)):
            pct = latest_cov.get(col)
            if pct is not None and pct < floor:
                issues.append(
                    ValidationIssue(
                        "error",
                        "LOW_LATEST_COVERAGE",
                        f"{col} latest-date coverage {pct}% (floor {floor}%)",
                        {"feature": col, "coverage_pct": pct, "floor": floor},
                    )
                )

        ok = not any(i.severity == "error" for i in issues)
        return ValidationReport(ok=ok, checked_at=now, target=target, issues=issues, stats=stats)

    def validate_factor_store(self, factor_root: Optional[Path] = None) -> ValidationReport:
        from research.factor_score_store import FactorScoreStore

        issues: List[ValidationIssue] = []
        now = datetime.now(timezone.utc).isoformat()
        store = FactorScoreStore(factor_root) if factor_root else FactorScoreStore()
        current = store.load_current()
        stats: Dict[str, Any] = {}
        if not current:
            issues.append(ValidationIssue("error", "NO_CURRENT_FACTORS", "factor_scores.json missing or empty"))
            return ValidationReport(ok=False, checked_at=now, target="factor_store", issues=issues, stats=stats)

        symbols = current.get("symbols") or {}
        stats["symbol_count"] = len(symbols)
        missing_overall = [
            s for s, rec in symbols.items() if (rec.get("scores") or {}).get("overall_fundamental") is None
        ]
        stats["missing_overall"] = len(missing_overall)
        if missing_overall:
            issues.append(
                ValidationIssue(
                    "warn",
                    "MISSING_OVERALL",
                    f"{len(missing_overall)} symbols without overall_fundamental",
                    {"symbols": missing_overall[:20]},
                )
            )
        if len(symbols) < 50:
            issues.append(
                ValidationIssue("error", "LOW_UNIVERSE", f"Only {len(symbols)} symbols in current factor store")
            )

        years = store.list_historical_years()
        stats["historical_years"] = years
        if not years:
            issues.append(ValidationIssue("warn", "NO_HISTORY", "No historical factor year files"))

        ok = not any(i.severity == "error" for i in issues)
        return ValidationReport(ok=ok, checked_at=now, target="factor_store", issues=issues, stats=stats)

    def validate_pit_spotcheck(
        self,
        *,
        symbol: str = "TCS",
        as_of: str = "2022-06-01",
        factor_root: Optional[Path] = None,
    ) -> ValidationReport:
        """FY ending after as_of must not be used for PIT scores."""
        from research.feature_store import FeatureStore

        issues: List[ValidationIssue] = []
        now = datetime.now(timezone.utc).isoformat()
        fs = FeatureStore()
        # Use store helper via temporary series if available
        from research.factor_score_store import FactorScoreStore

        store = FactorScoreStore(factor_root) if factor_root else FactorScoreStore()
        series = fs._factor_series_by_symbol(store).get(symbol.upper()) or []
        chosen = FeatureStore._pit_scores(series, as_of)
        stats: Dict[str, Any] = {"symbol": symbol.upper(), "as_of": as_of, "fy_available": [y for y, _ in series]}

        as_ts = pd.Timestamp(as_of)
        # Any FY with end > as_of must not be selected: verify by checking chosen matches max fy_end <= as_of
        eligible = [(fy, sc) for fy, sc in series if pd.Timestamp(f"{fy}-03-31") <= as_ts]
        expected = eligible[-1][1] if eligible else None
        if expected is None and chosen is None:
            issues.append(ValidationIssue("info", "PIT_NO_DATA", f"No PIT scores for {symbol} as of {as_of}"))
        elif expected != chosen:
            issues.append(
                ValidationIssue(
                    "error",
                    "PIT_VIOLATION",
                    f"PIT scores for {symbol} as of {as_of} do not match eligible FY set",
                )
            )
        else:
            stats["pit_ok"] = True
            # Explicit look-ahead: ensure no FY after as_of leaked
            future = [fy for fy, _ in series if pd.Timestamp(f"{fy}-03-31") > as_ts]
            stats["future_fys_present"] = future
            if chosen and future:
                # chosen quality should equal eligible, not a future-only path — already compared
                pass

        ok = not any(i.severity == "error" for i in issues)
        return ValidationReport(ok=ok, checked_at=now, target="pit_spotcheck", issues=issues, stats=stats)

    def measure_performance(self, *, hard: bool = False) -> ValidationReport:
        """
        Perf smoke. hard=True (VAL-H): miss target → error.
        hard=False (VG-1 smoke): miss → warn; 10x → error.
        """
        from research.research_service import ResearchSearchRequest, ResearchService

        issues: List[ValidationIssue] = []
        now = datetime.now(timezone.utc).isoformat()
        svc = ResearchService()
        stats: Dict[str, Any] = {"targets": dict(PERF_TARGETS), "hard": hard}

        # Warm search then measure
        svc.search(ResearchSearchRequest(min_quality=50, limit=5))
        t0 = time.perf_counter()
        svc.search(ResearchSearchRequest(min_quality=80, min_growth=70, min_value=60, limit=50))
        search_ms = (time.perf_counter() - t0) * 1000.0
        stats["research_search_ms"] = round(search_ms, 2)

        # feature_panel: pick a symbol from factors if possible
        payload = svc.factors.load_current() or {}
        symbols = list((payload.get("symbols") or {}).keys())
        sym = symbols[0] if symbols else "TCS"
        as_of = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        svc.feature_panel(sym, as_of)  # warm (loads panel cache)
        t1 = time.perf_counter()
        svc.feature_panel(sym, as_of)
        panel_ms = (time.perf_counter() - t1) * 1000.0
        stats["feature_panel_ms"] = round(panel_ms, 2)
        stats["perf_symbol"] = sym

        def _over(metric: str, ms: float, target: float) -> None:
            if ms <= target:
                return
            sev = "error" if hard or ms > target * 10 else "warn"
            code = f"PERF_{metric.upper()}" + ("_HARD" if sev == "error" and not hard else "")
            if hard:
                code = f"PERF_{metric.upper()}_FAIL"
            issues.append(
                ValidationIssue(sev, code, f"{metric} {ms:.1f}ms > {target}ms", {"ms": ms, "target": target})
            )

        _over("feature_panel", panel_ms, PERF_TARGETS["feature_panel_ms"])
        _over("research_search", search_ms, PERF_TARGETS["research_search_ms"])

        ok = not any(i.severity == "error" for i in issues)
        return ValidationReport(ok=ok, checked_at=now, target="performance", issues=issues, stats=stats)

    def artifact_hashes(self, paths: Sequence[Path]) -> Dict[str, Optional[str]]:
        return {str(p): sha256_file(Path(p)) for p in paths}

    def verify_repeatability(self, paths: Sequence[Path]) -> ValidationReport:
        """Hash each file twice; must match (identity check on disk)."""
        issues: List[ValidationIssue] = []
        now = datetime.now(timezone.utc).isoformat()
        stats: Dict[str, Any] = {"hashes": {}}
        for path in paths:
            p = Path(path)
            h1 = sha256_file(p)
            h2 = sha256_file(p)
            stats["hashes"][str(p)] = h1
            if h1 is None:
                issues.append(ValidationIssue("warn", "HASH_MISSING", f"Missing artifact: {p}"))
            elif h1 != h2:
                issues.append(ValidationIssue("error", "HASH_MISMATCH", f"Unstable hash for {p}"))
        ok = not any(i.severity == "error" for i in issues)
        return ValidationReport(ok=ok, checked_at=now, target="repeatability", issues=issues, stats=stats)

    def save_report(self, report: ValidationReport, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
        return path

    def build_release_readiness(
        self,
        *,
        reports: Dict[str, ValidationReport],
        known_gaps_path: Optional[Path] = None,
    ) -> Dict[str, Any]:
        def _status(r: Optional[ValidationReport]) -> str:
            if r is None:
                return "FAIL"
            return "PASS" if r.ok else "FAIL"

        gaps = []
        gap_path = known_gaps_path or (default_validation_dir() / "known_gaps.json")
        if gap_path.exists():
            try:
                gaps_doc = json.loads(gap_path.read_text(encoding="utf-8"))
                for cat, items in (gaps_doc.get("categories") or {}).items():
                    gaps.extend(items if isinstance(items, list) else [])
            except Exception:
                gaps = []

        analytics_manifest = (
            Path(__file__).resolve().parents[0] / "data" / "analytics" / "manifests" / "analytics_build.json"
        )
        analytics_fallback = Path(__file__).resolve().parents[0] / "data" / "analytics" / "factor_distributions.json"
        feature_ok = _status(reports.get("feature_store"))
        factor_ok = _status(reports.get("factor_store"))
        perf_ok = _status(reports.get("performance"))
        val_ok = _status(reports.get("aggregate"))
        analytics_ok = "PASS" if (analytics_manifest.exists() or analytics_fallback.exists()) else "FAIL"

        sections = {
            "Feature Store": feature_ok,
            "Validation": val_ok,
            "Analytics": analytics_ok,
            "Research Service": perf_ok,
            "Factor Store": factor_ok,
        }
        overall_pass = all(v == "PASS" for v in sections.values())
        sections["Research Platform"] = "PASS" if overall_pass else "FAIL"

        return {
            "built_at": datetime.now(timezone.utc).isoformat(),
            "platform": "SanMitra Research Platform",
            "sections": sections,
            "known_issues_count": len(gaps),
            "overall": "PASS" if overall_pass else "FAIL",
            "note": "Executive release readiness. Research-only. Not execution authority.",
        }


def run_full_validation(*, out_dir: Optional[Path] = None) -> Dict[str, Any]:
    """DVE-1 entry: panel + factors + PIT + perf + hashes → release readiness."""
    from research.feature_store import FeatureStore

    out = Path(out_dir) if out_dir else default_validation_dir()
    out.mkdir(parents=True, exist_ok=True)
    dve = DataValidationEngine()
    fs = FeatureStore()
    panel = fs.load_panel()

    reports: Dict[str, ValidationReport] = {}
    reports["feature_store"] = dve.validate_feature_panel(panel)
    reports["factor_store"] = dve.validate_factor_store()
    reports["pit_spotcheck"] = dve.validate_pit_spotcheck()
    reports["performance"] = dve.measure_performance()

    panel_path = fs.panel_path
    factor_path = Path(__file__).resolve().parents[0] / "data" / "fundamentals" / "current" / "factor_scores.json"
    reports["repeatability"] = dve.verify_repeatability([panel_path, factor_path])

    all_issues: List[ValidationIssue] = []
    for r in reports.values():
        all_issues.extend(r.issues)
    ok = all(r.ok for r in reports.values())
    aggregate = ValidationReport(
        ok=ok,
        checked_at=datetime.now(timezone.utc).isoformat(),
        target="dve1_full",
        issues=all_issues,
        stats={
            "targets": {k: v.to_dict() for k, v in reports.items()},
            "artifact_hashes": reports["repeatability"].stats.get("hashes"),
            "performance": reports["performance"].stats,
        },
    )
    reports["aggregate"] = aggregate

    dve.save_report(aggregate, out / "validation_latest.json")
    # Also mirror next to feature store (legacy path)
    dve.save_report(aggregate, fs.root / "manifests" / "validation_latest.json")

    readiness = dve.build_release_readiness(reports=reports, known_gaps_path=out / "known_gaps.json")
    (out / "release_readiness_latest.json").write_text(json.dumps(readiness, indent=2), encoding="utf-8")

    md_lines = [
        "# Release Readiness",
        "",
        f"Overall: **{readiness['overall']}**",
        f"Known issues: {readiness['known_issues_count']}",
        "",
    ]
    for name, status in (readiness.get("sections") or {}).items():
        md_lines.append(f"- {name}: {status}")
    (out / "release_readiness_latest.md").write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    return {
        "ok": ok,
        "validation_path": str(out / "validation_latest.json"),
        "release_readiness": readiness,
        "issue_count": len(all_issues),
        "error_count": sum(1 for i in all_issues if i.severity == "error"),
    }
