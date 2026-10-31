"""
Research Service — SanMitra Research Platform API facade.

Consumers: NexTrade research, InvestMitra, AI — never execution.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Dict, List, Optional

from research.factor_score_store import FactorScoreStore
from research.feature_registry import FeatureRegistry, bootstrap_registry
from research.feature_store import (
    FUNDAMENTAL_COLS,
    MARKET_COLS,
    TECHNICAL_COLS,
    FeatureStore,
)
from research.fundamental_service import FundamentalService, get_fundamental_service
from research.research_query_engine import ResearchQuery, ResearchQueryEngine


@dataclass
class ResearchSearchRequest:
    """Unified search — maps onto ResearchQuery (B3)."""

    kind: str = "factors"  # factors | features | symbol
    symbol: Optional[str] = None
    fiscal_year: Optional[int] = None
    as_of_date: Optional[str] = None
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
    improved_quality_years: Optional[int] = None
    limit: int = 50
    sort_by: str = "overall_fundamental"


@dataclass
class ResearchSearchResult:
    items: List[Dict[str, Any]] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)


class ResearchService:
    def __init__(
        self,
        *,
        fundamental: Optional[FundamentalService] = None,
        factors: Optional[FactorScoreStore] = None,
        features: Optional[FeatureStore] = None,
        registry: Optional[FeatureRegistry] = None,
        warehouse: Any = None,
        query_engine: Optional[ResearchQueryEngine] = None,
    ):
        self.fundamental = fundamental or get_fundamental_service()
        self.factors = factors or FactorScoreStore()
        self.features = features or FeatureStore()
        self.registry = registry
        self.warehouse = warehouse
        self.query_engine = query_engine or ResearchQueryEngine(
            factors=self.factors, features=self.features
        )

    def _registry(self) -> FeatureRegistry:
        if self.registry is not None:
            return self.registry
        try:
            return FeatureRegistry.load(self.features.registry_path)
        except Exception:
            return bootstrap_registry(self.features.registry_path)

    def symbol_intelligence(self, symbol: str) -> Optional[Dict[str, Any]]:
        return self.fundamental.get_symbol_intelligence(symbol)

    def features_for(self, symbol: str, date: str) -> Optional[Dict[str, Any]]:
        """Flat row alias — prefer feature_panel()."""
        return self.features.get_row(symbol, date)

    def feature_panel(self, symbol: str, as_of_date: str) -> Optional[Dict[str, Any]]:
        """
        Canonical research object: technical / fundamental / market + metadata.
        """
        row = self.features.get_row(symbol, as_of_date)
        if row is None:
            # fallback: current fundamental intelligence only
            intel = self.symbol_intelligence(symbol)
            if not intel:
                return None
            scores = intel.get("factor_scores") or {}
            reg = self._registry()
            fids = list(FUNDAMENTAL_COLS)
            return {
                "symbol": symbol.upper(),
                "as_of": as_of_date,
                "technical": {k: None for k in TECHNICAL_COLS},
                "fundamental": {k: scores.get(k) for k in FUNDAMENTAL_COLS},
                "market": {k: None for k in MARKET_COLS},
                "metadata": {
                    "feature_store_version": "1.0",
                    "build_date": intel.get("generated_at"),
                    "as_of": as_of_date,
                    "lookahead_safe": True,
                    "feature_versions": reg.versions_map(fids),
                    "provenance": {k: reg.provenance_label(k) for k in fids},
                    "source": "fundamental_service_fallback",
                    "platform": "SanMitra Research Platform",
                },
            }

        def _pick(cols):
            return {k: row.get(k) for k in cols}

        reg = self._registry()
        all_ids = list(TECHNICAL_COLS) + list(FUNDAMENTAL_COLS) + list(MARKET_COLS)
        manifest = {}
        if self.features.manifest_path.exists():
            import json

            try:
                manifest = json.loads(self.features.manifest_path.read_text(encoding="utf-8"))
            except Exception:
                manifest = {}

        return {
            "symbol": str(row.get("symbol") or symbol).upper(),
            "as_of": str(row.get("date") or as_of_date),
            "technical": _pick(TECHNICAL_COLS),
            "fundamental": _pick(FUNDAMENTAL_COLS),
            "market": _pick(MARKET_COLS),
            "metadata": {
                "feature_store_version": str(manifest.get("feature_store_version") or "1.0"),
                "build_date": manifest.get("updated_at"),
                "as_of": str(row.get("date") or as_of_date),
                "lookahead_safe": bool(manifest.get("lookahead_safe", True)),
                "feature_versions": reg.versions_map(all_ids),
                "provenance": {k: reg.provenance_label(k) for k in all_ids},
                "source": "feature_store",
                "platform": "SanMitra Research Platform",
            },
        }

    def search(self, req: ResearchSearchRequest) -> ResearchSearchResult:
        if req.kind == "symbol" and req.symbol:
            intel = self.symbol_intelligence(req.symbol)
            return ResearchSearchResult(
                items=[intel] if intel else [],
                meta={"kind": "symbol", "source": "fundamental_service"},
            )

        q = ResearchQuery(
            fiscal_year=req.fiscal_year,
            as_of_date=req.as_of_date,
            min_quality=req.min_quality,
            min_growth=req.min_growth,
            min_value=req.min_value,
            min_health=req.min_health,
            min_consistency=req.min_consistency,
            min_overall=req.min_overall,
            max_rsi=req.max_rsi,
            min_rsi=req.min_rsi,
            min_vix=req.min_vix,
            max_vix=req.max_vix,
            improved_quality_years=req.improved_quality_years,
            limit=req.limit,
            sort_by=req.sort_by,
        )
        result = self.query_engine.query(q)
        meta = dict(result.meta)
        meta["factor_version"] = self.fundamental.factor_version()
        meta["delegated_to"] = "research_query_engine"
        return ResearchSearchResult(items=result.items, meta=meta)


@lru_cache(maxsize=1)
def get_research_service() -> ResearchService:
    return ResearchService()
