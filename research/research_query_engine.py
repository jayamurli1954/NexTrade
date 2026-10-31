"""
Research Query Engine (RQE) — SanMitra Research Platform.

Filters fundamentals (+ optional technical/market features).
Research-only. No trading_app imports. Shared by NexTrade and InvestMitra.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from research.factor_score_store import FactorScoreStore
from research.feature_store import FeatureStore


@dataclass
class ResearchQuery:
    """Unified research filter (fundamentals + optional RSI/VIX)."""

    fiscal_year: Optional[int] = None  # None = current universe
    as_of_date: Optional[str] = None  # feature join date (on_or_before)
    min_quality: Optional[float] = None
    min_growth: Optional[float] = None
    min_value: Optional[float] = None
    min_health: Optional[float] = None
    min_consistency: Optional[float] = None
    min_overall: Optional[float] = None
    max_rsi: Optional[float] = None
    min_rsi: Optional[float] = None
    min_vix: Optional[float] = None
    max_vix: Optional[float] = None
    improved_quality_years: Optional[int] = None  # e.g. 3 → quality rose vs FY-N
    sector_contains: Optional[str] = None  # reserved; no sector map yet → ignored
    symbols: Optional[Sequence[str]] = None
    limit: int = 50
    sort_by: str = "overall_fundamental"
    sort_desc: bool = True


# Back-compat alias (roadmap / FI plans)
FactorQuery = ResearchQuery


@dataclass
class ResearchQueryResult:
    items: List[Dict[str, Any]] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)


class ResearchQueryEngine:
    def __init__(
        self,
        *,
        factors: Optional[FactorScoreStore] = None,
        features: Optional[FeatureStore] = None,
    ):
        self.factors = factors or FactorScoreStore()
        self.features = features or FeatureStore()

    def query(self, q: ResearchQuery) -> ResearchQueryResult:
        universe = self._load_universe(q.fiscal_year)
        rows: List[Dict[str, Any]] = []

        feature_map: Dict[str, Dict[str, Any]] = {}
        need_features = any(
            x is not None for x in (q.max_rsi, q.min_rsi, q.min_vix, q.max_vix)
        )
        if need_features:
            feature_map = self._feature_as_of_map(q.as_of_date)

        allow = None
        if q.symbols:
            allow = {s.upper() for s in q.symbols}

        for sym, rec in universe.items():
            if allow is not None and sym not in allow:
                continue
            scores = rec.get("scores") or {}
            if not self._pass_factor_filters(scores, q):
                continue

            feat = feature_map.get(sym) or {}
            if need_features and not self._pass_feature_filters(feat, q):
                continue

            if q.improved_quality_years is not None:
                if not self._quality_improved(sym, int(q.improved_quality_years), scores):
                    continue

            # sector_contains reserved — no data yet; do not filter silently wrong
            item = {
                "symbol": sym,
                "fiscal_year": rec.get("fiscal_year") if q.fiscal_year is None else q.fiscal_year,
                "scores": scores,
                "thesis": rec.get("thesis") or [],
                "relatives": rec.get("relatives") or {},
            }
            if feat:
                item["features"] = {
                    "rsi": feat.get("rsi"),
                    "vix": feat.get("vix"),
                    "as_of": feat.get("date"),
                }
            rows.append(item)

        sort_key = q.sort_by or "overall_fundamental"

        def _sort_val(item: Dict[str, Any]) -> float:
            if sort_key in ("rsi", "vix"):
                v = (item.get("features") or {}).get(sort_key)
            else:
                v = (item.get("scores") or {}).get(sort_key)
            try:
                return float(v) if v is not None else float("-inf")
            except (TypeError, ValueError):
                return float("-inf")

        rows.sort(key=_sort_val, reverse=bool(q.sort_desc))
        matched = len(rows)
        limit = max(1, int(q.limit))
        return ResearchQueryResult(
            items=rows[:limit],
            meta={
                "kind": "research_query",
                "source": "research_query_engine",
                "fiscal_year": q.fiscal_year,
                "as_of_date": q.as_of_date,
                "total_matched": matched,
                "returned": min(matched, limit),
                "platform": "SanMitra Research Platform",
                "lookahead_safe": True,
            },
        )

    def _load_universe(self, fiscal_year: Optional[int]) -> Dict[str, Dict[str, Any]]:
        if fiscal_year is None:
            payload = self.factors.load_current() or {"symbols": {}}
            return {str(k).upper(): v for k, v in (payload.get("symbols") or {}).items()}

        path = self.factors.historical_path(int(fiscal_year))
        if not path.exists():
            return {}
        import json

        data = json.loads(path.read_text(encoding="utf-8"))
        out: Dict[str, Dict[str, Any]] = {}
        for sym, rec in (data.get("symbols") or {}).items():
            out[str(sym).upper()] = {
                "scores": (rec or {}).get("scores") or {},
                "fiscal_year": fiscal_year,
                "thesis": (rec or {}).get("thesis") or [],
                "relatives": (rec or {}).get("relatives") or {},
            }
        return out

    def _feature_as_of_map(self, as_of_date: Optional[str]) -> Dict[str, Dict[str, Any]]:
        panel = self.features.load_panel()
        if panel is None or panel.empty:
            return {}
        import pandas as pd

        df = panel.copy()
        df["symbol"] = df["symbol"].astype(str).str.upper()
        df["_d"] = pd.to_datetime(df["date"], errors="coerce")
        if as_of_date:
            as_ts = pd.Timestamp(as_of_date)
            df = df[df["_d"] <= as_ts]
        if df.empty:
            return {}
        df = df.sort_values("_d").groupby("symbol", as_index=False).tail(1)
        out: Dict[str, Dict[str, Any]] = {}
        for _, row in df.iterrows():
            out[str(row["symbol"]).upper()] = row.to_dict()
        return out

    def _quality_improved(self, symbol: str, years: int, current_scores: Dict[str, Any]) -> bool:
        years_list = self.factors.list_historical_years()
        if not years_list:
            return False
        current_q = current_scores.get("quality")
        if current_q is None:
            return False
        # Prefer comparing to fiscal year N years before latest historical
        target_fy = max(years_list) - int(years)
        if target_fy not in years_list:
            # nearest older available
            older = [y for y in years_list if y <= target_fy]
            if not older:
                return False
            target_fy = max(older)
        past = self.factors.load_as_of(symbol, target_fy)
        if not past:
            return False
        past_q = (past.get("scores") or {}).get("quality")
        if past_q is None:
            return False
        try:
            return float(current_q) > float(past_q)
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _pass_factor_filters(scores: Dict[str, Any], q: ResearchQuery) -> bool:
        checks: List[Tuple[str, Optional[float]]] = [
            ("quality", q.min_quality),
            ("growth", q.min_growth),
            ("value", q.min_value),
            ("financial_health", q.min_health),
            ("consistency", q.min_consistency),
            ("overall_fundamental", q.min_overall),
        ]
        for key, minimum in checks:
            if minimum is None:
                continue
            val = scores.get(key)
            if val is None:
                return False
            try:
                if float(val) < float(minimum):
                    return False
            except (TypeError, ValueError):
                return False
        return True

    @staticmethod
    def _pass_feature_filters(feat: Dict[str, Any], q: ResearchQuery) -> bool:
        def _num(key: str) -> Optional[float]:
            v = feat.get(key)
            if v is None or (isinstance(v, float) and v != v):  # NaN
                return None
            try:
                return float(v)
            except (TypeError, ValueError):
                return None

        rsi = _num("rsi")
        vix = _num("vix")
        if q.min_rsi is not None:
            if rsi is None or rsi < float(q.min_rsi):
                return False
        if q.max_rsi is not None:
            if rsi is None or rsi > float(q.max_rsi):
                return False
        if q.min_vix is not None:
            if vix is None or vix < float(q.min_vix):
                return False
        if q.max_vix is not None:
            if vix is None or vix > float(q.max_vix):
                return False
        return True
