"""
Feature Registry — provenance, versioning, and family for every research feature.

SanMitra Research Platform. Research-only.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


REQUIRED_KEYS = ("name", "version", "family", "source", "frequency", "status")


def default_registry_path(root: Optional[Path] = None) -> Path:
    base = root or Path(__file__).resolve().parents[1]
    return base / "research" / "data" / "feature_store" / "registry.json"


DEFAULT_REGISTRY: Dict[str, Dict[str, Any]] = {
    "rsi": {
        "name": "RSI",
        "version": "1.0",
        "family": "technical",
        "source": "technical_engine",
        "transformation": "rsi_14_close",
        "frequency": "daily",
        "status": "research",
        "description": "14-period RSI on equity close",
    },
    "ema20": {
        "name": "EMA20",
        "version": "1.0",
        "family": "technical",
        "source": "technical_engine",
        "transformation": "ema_20_close",
        "frequency": "daily",
        "status": "research",
    },
    "ema50": {
        "name": "EMA50",
        "version": "1.0",
        "family": "technical",
        "source": "technical_engine",
        "transformation": "ema_50_close",
        "frequency": "daily",
        "status": "research",
    },
    "atr": {
        "name": "ATR",
        "version": "1.0",
        "family": "technical",
        "source": "technical_engine",
        "transformation": "atr_14",
        "frequency": "daily",
        "status": "research",
    },
    "adx": {
        "name": "ADX",
        "version": "1.0",
        "family": "technical",
        "source": "technical_engine",
        "transformation": "adx_14",
        "frequency": "daily",
        "status": "research",
    },
    "quality": {
        "name": "Quality",
        "version": "1.1",
        "family": "fundamental",
        "source": "fundamental_factor_engine",
        "transformation": "factor_weights_v1_1",
        "frequency": "as_of_fiscal",
        "status": "research",
    },
    "growth": {
        "name": "Growth",
        "version": "1.1",
        "family": "fundamental",
        "source": "fundamental_factor_engine",
        "transformation": "factor_weights_v1_1",
        "frequency": "as_of_fiscal",
        "status": "research",
    },
    "value": {
        "name": "Value",
        "version": "1.1",
        "family": "fundamental",
        "source": "fundamental_factor_engine",
        "transformation": "factor_weights_v1_1",
        "frequency": "as_of_fiscal",
        "status": "research",
    },
    "financial_health": {
        "name": "Health",
        "version": "1.1",
        "family": "fundamental",
        "source": "fundamental_factor_engine",
        "transformation": "factor_weights_v1_1",
        "frequency": "as_of_fiscal",
        "status": "research",
    },
    "consistency": {
        "name": "Consistency",
        "version": "1.1",
        "family": "fundamental",
        "source": "fundamental_factor_engine",
        "transformation": "factor_weights_v1_1",
        "frequency": "as_of_fiscal",
        "status": "research",
    },
    "overall_fundamental": {
        "name": "OverallFundamental",
        "version": "1.1",
        "family": "fundamental",
        "source": "fundamental_factor_engine",
        "transformation": "overall_blend_v1_1",
        "frequency": "as_of_fiscal",
        "status": "research",
    },
    "vix": {
        "name": "VIX",
        "version": "1.0",
        "family": "market",
        "source": "market_warehouse",
        "transformation": "india_vix_close",
        "frequency": "daily",
        "status": "research",
    },
    "pcr": {
        "name": "PCR",
        "version": "0.0",
        "family": "market",
        "source": "market_warehouse",
        "transformation": "put_call_oi_ratio",
        "frequency": "daily",
        "status": "pending",
        "description": "Reserved until MDW-4",
    },
    "oi": {
        "name": "OI",
        "version": "0.0",
        "family": "market",
        "source": "market_warehouse",
        "transformation": "options_open_interest",
        "frequency": "daily",
        "status": "pending",
        "description": "Reserved until MDW-3",
    },
}


@dataclass
class FeatureRegistry:
    path: Path
    entries: Dict[str, Dict[str, Any]]

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "FeatureRegistry":
        p = Path(path) if path else default_registry_path()
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            entries = data.get("features") if "features" in data else data
        else:
            entries = dict(DEFAULT_REGISTRY)
        reg = cls(path=p, entries=dict(entries))
        reg.validate()
        return reg

    def save(self) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "platform": "SanMitra Research Platform",
            "features": self.entries,
        }
        self.validate()
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return self.path

    def validate(self) -> None:
        for key, meta in self.entries.items():
            missing = [k for k in REQUIRED_KEYS if k not in meta]
            if missing:
                raise ValueError(f"Feature '{key}' missing registry keys: {missing}")

    def get(self, feature_id: str) -> Optional[Dict[str, Any]]:
        return self.entries.get(feature_id)

    def provenance_label(self, feature_id: str) -> str:
        meta = self.entries.get(feature_id) or {}
        src = meta.get("source", "unknown")
        ver = meta.get("version", "?")
        return f"{src}@{ver}"

    def versions_map(self, feature_ids: List[str]) -> Dict[str, str]:
        out: Dict[str, str] = {}
        for fid in feature_ids:
            meta = self.entries.get(fid)
            if meta:
                out[fid] = str(meta.get("version"))
        return out

    def ensure_defaults(self) -> None:
        for k, v in DEFAULT_REGISTRY.items():
            self.entries.setdefault(k, dict(v))


def bootstrap_registry(path: Optional[Path] = None) -> FeatureRegistry:
    reg = FeatureRegistry(path=Path(path) if path else default_registry_path(), entries=dict(DEFAULT_REGISTRY))
    reg.save()
    return reg
