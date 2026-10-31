"""
Research Analytics Engine (RAE) — SanMitra Research Platform.

RAE-1 distributions · RAE-2 history · RAE-3 correlation · RAE-4 improvement leaders · RAE-7 coverage
Research-only. Not execution authority.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import pandas as pd

from research.factor_score_store import FactorScoreStore
from research.feature_store import FeatureStore, FUNDAMENTAL_COLS, MARKET_COLS, TECHNICAL_COLS

FACTOR_KEYS = list(FUNDAMENTAL_COLS)


def default_analytics_dir(root: Optional[Path] = None) -> Path:
    # __file__ = research/analytics/__init__.py → parents[1] = research/
    base = root or Path(__file__).resolve().parents[1]
    return base / "data" / "analytics"


def _current_scores_frame(store: FactorScoreStore) -> pd.DataFrame:
    payload = store.load_current() or {"symbols": {}}
    rows: List[Dict[str, Any]] = []
    for sym, rec in (payload.get("symbols") or {}).items():
        scores = rec.get("scores") or {}
        row = {"symbol": sym.upper(), "fiscal_year": rec.get("fiscal_year")}
        for k in FACTOR_KEYS:
            row[k] = scores.get(k)
        rows.append(row)
    return pd.DataFrame(rows)


def _history_long(store: FactorScoreStore) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    for year in store.list_historical_years():
        path = store.historical_path(year)
        if not path.exists():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        for sym, rec in (payload.get("symbols") or {}).items():
            scores = (rec or {}).get("scores") or {}
            row = {"symbol": sym.upper(), "fiscal_year": int(year)}
            for k in FACTOR_KEYS:
                row[k] = scores.get(k)
            rows.append(row)
    return pd.DataFrame(rows)


def rae1_factor_distributions(df: pd.DataFrame) -> Dict[str, Any]:
    """Quantiles + simple histogram bins for each factor (current cross-section)."""
    out: Dict[str, Any] = {"factors": {}, "universe_size": int(len(df))}
    quantiles = [0.0, 0.1, 0.25, 0.5, 0.75, 0.9, 1.0]
    for key in FACTOR_KEYS:
        if key not in df.columns:
            continue
        s = pd.to_numeric(df[key], errors="coerce").dropna()
        if s.empty:
            out["factors"][key] = {"n": 0}
            continue
        q = {f"p{int(p * 100)}": round(float(s.quantile(p)), 2) for p in quantiles}
        # 10 equal-width bins from 0..100 (scores are 0-100)
        bins = list(range(0, 110, 10))
        cats = pd.cut(s.clip(0, 100), bins=bins, include_lowest=True, right=False)
        hist = {str(i): int(c) for i, c in cats.value_counts().sort_index().items()}
        out["factors"][key] = {
            "n": int(len(s)),
            "mean": round(float(s.mean()), 2),
            "std": round(float(s.std(ddof=0)), 2) if len(s) > 1 else 0.0,
            "quantiles": q,
            "histogram_bins": hist,
        }
    return out


def rae2_factor_history_panel(long_df: pd.DataFrame) -> pd.DataFrame:
    """Long panel: symbol, fiscal_year, factors…"""
    if long_df is None or long_df.empty:
        return pd.DataFrame(columns=["symbol", "fiscal_year"] + FACTOR_KEYS)
    cols = ["symbol", "fiscal_year"] + [k for k in FACTOR_KEYS if k in long_df.columns]
    return long_df[cols].sort_values(["symbol", "fiscal_year"]).reset_index(drop=True)


def rae3_factor_correlation(df: pd.DataFrame) -> Dict[str, Any]:
    cols = [k for k in FACTOR_KEYS if k in df.columns]
    if not cols or df.empty:
        return {"matrix": {}, "n": 0}
    sub = df[cols].apply(pd.to_numeric, errors="coerce")
    corr = sub.corr(method="pearson")
    matrix = {
        r: {c: (None if pd.isna(corr.loc[r, c]) else round(float(corr.loc[r, c]), 4)) for c in corr.columns}
        for r in corr.index
    }
    return {"matrix": matrix, "n": int(sub.dropna(how="all").shape[0]), "method": "pearson"}


def rae4_improvement_leaders(
    long_df: pd.DataFrame,
    *,
    metrics: Sequence[str] = ("quality", "overall_fundamental"),
    windows: Sequence[int] = (1, 3),
    top_n: int = 25,
) -> Dict[str, Any]:
    """
    Δ over 1Y / 3Y using fiscal_year gaps. Only uses historical years (no look-ahead).
    """
    if long_df is None or long_df.empty:
        return {"leaders": {}, "n_symbols": 0}

    leaders: Dict[str, Any] = {}
    for metric in metrics:
        if metric not in long_df.columns:
            continue
        metric_leaders: Dict[str, List[Dict[str, Any]]] = {}
        for window in windows:
            rows: List[Dict[str, Any]] = []
            for sym, g in long_df.groupby("symbol"):
                g = g.sort_values("fiscal_year")
                if len(g) < 2:
                    continue
                latest_year = int(g["fiscal_year"].iloc[-1])
                target_year = latest_year - int(window)
                latest_val = pd.to_numeric(g[metric].iloc[-1], errors="coerce")
                prior = g[g["fiscal_year"] == target_year]
                if prior.empty or pd.isna(latest_val):
                    # fallback: take row window steps back if exact year missing
                    if len(g) > window:
                        prior_val = pd.to_numeric(g[metric].iloc[-1 - window], errors="coerce")
                        prior_year = int(g["fiscal_year"].iloc[-1 - window])
                    else:
                        continue
                else:
                    prior_val = pd.to_numeric(prior[metric].iloc[-1], errors="coerce")
                    prior_year = target_year
                if pd.isna(prior_val):
                    continue
                delta = float(latest_val) - float(prior_val)
                rows.append(
                    {
                        "symbol": sym,
                        "metric": metric,
                        "window_years": int(window),
                        "from_fy": prior_year,
                        "to_fy": latest_year,
                        "from_value": round(float(prior_val), 2),
                        "to_value": round(float(latest_val), 2),
                        "delta": round(delta, 2),
                    }
                )
            rows.sort(key=lambda r: r["delta"], reverse=True)
            metric_leaders[f"delta_{window}y"] = {
                "top": rows[:top_n],
                "bottom": list(reversed(rows[-top_n:])) if rows else [],
            }
        leaders[metric] = metric_leaders
    return {"leaders": leaders, "n_symbols": int(long_df["symbol"].nunique())}


def rae7_feature_coverage(panel: pd.DataFrame) -> Dict[str, Any]:
    """Coverage % per feature column (Feature Store panel)."""
    if panel is None or panel.empty:
        return {"rows": 0, "coverage": {}, "status": {}}
    rows = int(len(panel))
    coverage: Dict[str, Any] = {}
    status: Dict[str, str] = {}
    pending = {"pcr", "oi"}
    for col in list(TECHNICAL_COLS) + list(FUNDAMENTAL_COLS) + list(MARKET_COLS):
        if col not in panel.columns:
            coverage[col] = 0.0
            status[col] = "missing_column"
            continue
        pct = round(100.0 * float(panel[col].notna().sum()) / rows, 2) if rows else 0.0
        coverage[col] = pct
        if col in pending and pct == 0:
            status[col] = "pending"
        elif pct >= 95:
            status[col] = "healthy"
        elif pct >= 50:
            status[col] = "partial"
        else:
            status[col] = "low"
    return {
        "rows": rows,
        "symbols": int(panel["symbol"].nunique()) if "symbol" in panel.columns else 0,
        "coverage": coverage,
        "status": status,
    }


class ResearchAnalyticsEngine:
    def __init__(
        self,
        *,
        factor_store: Optional[FactorScoreStore] = None,
        feature_store: Optional[FeatureStore] = None,
        out_dir: Optional[Path] = None,
    ):
        self.factors = factor_store or FactorScoreStore()
        self.features = feature_store or FeatureStore()
        self.out_dir = Path(out_dir) if out_dir else default_analytics_dir()
        self.out_dir.mkdir(parents=True, exist_ok=True)
        (self.out_dir / "manifests").mkdir(parents=True, exist_ok=True)

    def build_all(self) -> Dict[str, Any]:
        current = _current_scores_frame(self.factors)
        history = _history_long(self.factors)
        panel = self.features.load_panel()

        distributions = rae1_factor_distributions(current)
        history_panel = rae2_factor_history_panel(history)
        correlation = rae3_factor_correlation(current)
        leaders = rae4_improvement_leaders(history)
        coverage = rae7_feature_coverage(panel)

        # Write artifacts
        (self.out_dir / "factor_distributions.json").write_text(
            json.dumps(distributions, indent=2), encoding="utf-8"
        )
        history_panel.to_csv(self.out_dir / "factor_history_panel.csv", index=False)
        (self.out_dir / "factor_correlation.json").write_text(
            json.dumps(correlation, indent=2), encoding="utf-8"
        )
        (self.out_dir / "improvement_leaders.json").write_text(
            json.dumps(leaders, indent=2), encoding="utf-8"
        )
        # flat leaders CSV (top overall 1y)
        flat_rows: List[Dict[str, Any]] = []
        for metric, windows in (leaders.get("leaders") or {}).items():
            for wkey, block in windows.items():
                for row in block.get("top") or []:
                    flat_rows.append(row)
        pd.DataFrame(flat_rows).to_csv(self.out_dir / "improvement_leaders.csv", index=False)

        (self.out_dir / "feature_coverage.json").write_text(
            json.dumps(coverage, indent=2), encoding="utf-8"
        )
        cov_table = [
            {"feature": k, "coverage_pct": v, "status": coverage.get("status", {}).get(k)}
            for k, v in (coverage.get("coverage") or {}).items()
        ]
        pd.DataFrame(cov_table).to_csv(self.out_dir / "feature_coverage.csv", index=False)

        manifest = {
            "built_at": datetime.now(timezone.utc).isoformat(),
            "platform": "SanMitra Research Platform",
            "products": ["RAE-1", "RAE-2", "RAE-3", "RAE-4", "RAE-7"],
            "current_universe": int(len(current)),
            "history_rows": int(len(history_panel)),
            "feature_panel_rows": int(coverage.get("rows") or 0),
            "note": "Research-only analytics. Not execution authority.",
        }
        (self.out_dir / "manifests" / "analytics_build.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )
        return manifest
