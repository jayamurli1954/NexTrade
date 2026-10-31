"""
Fundamental Service — single read API for Opportunity / Analyzer / future Portfolio / AI.

FI-2: display provenance only. Does not recompute factors or affect execution gates.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

from research.factor_score_store import FactorScoreStore

logger = logging.getLogger("FundamentalService")

_FACTOR_LABELS = {
    "quality": "Quality",
    "growth": "Growth",
    "value": "Value",
    "financial_health": "Health",
    "consistency": "Consistency",
    "overall_fundamental": "Overall",
}


def badge_for_score(score: Optional[float]) -> str:
    if score is None:
        return "N/A"
    if score >= 80:
        return "Excellent"
    if score >= 65:
        return "Good"
    if score >= 50:
        return "Fair"
    if score >= 35:
        return "Weak"
    return "Poor"


def _delta(current: Optional[float], prior: Optional[float]) -> Optional[float]:
    if current is None or prior is None:
        return None
    return round(float(current) - float(prior), 1)


def _trend_arrow(delta: Optional[float]) -> Optional[str]:
    if delta is None:
        return None
    if delta > 0.05:
        return f"▲ +{delta:.0f}" if delta == int(delta) else f"▲ +{delta}"
    if delta < -0.05:
        return f"▼ {delta:.0f}" if delta == int(delta) else f"▼ {delta}"
    return "→ 0"


def build_ai_summary(
    *,
    direction: str,
    why_technical: List[str],
    factor_scores: Optional[Dict[str, Any]],
    thesis: Optional[List[str]] = None,
) -> str:
    """Rule-based summary — no LLM. Bridge to future AI assistant."""
    tech_bits = [t for t in (why_technical or []) if t][:2]
    tech_clause = "; ".join(tech_bits) if tech_bits else "mixed technical evidence"

    action = (direction or "BUY").upper()
    if action == "BUY":
        tech_lead = f"Technicals suggest a constructive setup ({tech_clause})."
    elif action == "SELL":
        tech_lead = f"Technicals suggest a defensive / short setup ({tech_clause})."
    else:
        tech_lead = f"Technicals are mixed ({tech_clause})."

    scores = factor_scores or {}
    overall = scores.get("overall_fundamental")
    quality = scores.get("quality")
    value = scores.get("value")
    health = scores.get("financial_health")
    growth = scores.get("growth")

    fund_parts: List[str] = []
    if quality is not None:
        fund_parts.append(f"{badge_for_score(quality).lower()} business quality")
    if value is not None:
        fund_parts.append(f"{badge_for_score(value).lower()} valuation")
    if health is not None:
        fund_parts.append(f"{badge_for_score(health).lower()} financial health")
    if growth is not None and growth >= 65:
        fund_parts.append("supportive growth")
    elif growth is not None and growth <= 40:
        fund_parts.append("soft near-term growth")

    if fund_parts:
        fund_clause = "Fundamentals indicate " + ", ".join(fund_parts[:-1])
        if len(fund_parts) > 1:
            fund_clause += f", and {fund_parts[-1]}"
        else:
            fund_clause = "Fundamentals indicate " + fund_parts[0]
        fund_clause += "."
    else:
        fund_clause = "Fundamental factor scores are unavailable for this symbol."

    if overall is not None and overall >= 70:
        close = "Overall the opportunity is technically attractive while fundamentals remain supportive."
    elif overall is not None and overall < 45:
        close = "Treat as a technical opportunity with weaker fundamental support."
    elif overall is not None:
        close = "Overall a balanced technical opportunity with moderate fundamental backing."
    else:
        close = "Overall assessment rests primarily on the technical evidence."

    return f"{tech_lead} {fund_clause} {close}"


class FundamentalService:
    """
    One API / one cache / one version for fundamental display consumers.
    """

    def __init__(self, store: Optional[FactorScoreStore] = None):
        self.store = store or FactorScoreStore()
        self._current_cache: Optional[Dict[str, Any]] = None
        self._manifest_cache: Optional[Dict[str, Any]] = None

    def _current_payload(self) -> Dict[str, Any]:
        if self._current_cache is None:
            self._current_cache = self.store.load_current() or {"symbols": {}}
        return self._current_cache

    def invalidate_cache(self) -> None:
        self._current_cache = None
        self._manifest_cache = None

    def factor_version(self) -> str:
        man = self._manifest()
        return str(man.get("config_version") or "1.1")

    def _manifest(self) -> Dict[str, Any]:
        if self._manifest_cache is None:
            path = self.store.manifest_path()
            if path.exists():
                import json

                self._manifest_cache = json.loads(path.read_text(encoding="utf-8"))
            else:
                self._manifest_cache = {}
        return self._manifest_cache

    def get_symbol_intelligence(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Full Investment Intelligence payload for a symbol (display-only).
        """
        sym = symbol.upper().strip()
        payload = self._current_payload()
        rec = (payload.get("symbols") or {}).get(sym)
        if not rec:
            return None

        scores = dict(rec.get("scores") or {})
        fiscal_year = rec.get("fiscal_year")
        trends = self._score_trends(sym, scores, fiscal_year)
        badges = {k: badge_for_score(scores.get(k)) for k in _FACTOR_LABELS if k in scores}

        return {
            "symbol": sym,
            "factor_version": self.factor_version(),
            "generated_at": payload.get("built_at") or rec.get("as_of"),
            "fiscal_year": fiscal_year,
            "as_of_label": f"As of FY {fiscal_year}" if fiscal_year else "As of latest factors",
            "factor_scores": scores,
            "factor_badges": badges,
            "factor_trends": trends,
            "valuation_relatives": rec.get("relatives") or {},
            "investment_thesis": list(rec.get("thesis") or []),
            "inputs_used": list(rec.get("inputs_used") or []),
            "missing_inputs": list(rec.get("missing_inputs") or []),
            "source": "factor_store",
        }

    def _score_trends(
        self,
        symbol: str,
        current_scores: Dict[str, Any],
        fiscal_year: Optional[int],
    ) -> Dict[str, Any]:
        if not fiscal_year:
            return {}
        prior_year = int(fiscal_year) - 1
        prior = self.store.load_as_of(symbol, prior_year)
        if not prior:
            return {}
        prior_scores = prior.get("scores") or {}
        out: Dict[str, Any] = {}
        for key in (
            "quality",
            "growth",
            "value",
            "financial_health",
            "consistency",
            "overall_fundamental",
        ):
            d = _delta(current_scores.get(key), prior_scores.get(key))
            out[key] = {
                "prior_fy": prior_year,
                "prior": prior_scores.get(key),
                "delta": d,
                "label": _trend_arrow(d),
            }
        return out


@lru_cache(maxsize=1)
def get_fundamental_service() -> FundamentalService:
    return FundamentalService()
