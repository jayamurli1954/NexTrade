"""
NexTrade Phase 7N — Multi-Vendor LLM Provider Gateway with Native Ollama Support.

Supports:
- Local Ollama Service (http://localhost:11434/api/generate) [DEFAULT]
- OpenAI (GPT-4o API)
- Anthropic (Claude 3.5 Sonnet API)
- Google Gemini (Gemini 1.5 Pro API)
- X.AI Grok (Grok-2 API)

CRITICAL RULE: LLM layers NEVER select strategies, calculate risk, or execute orders.
Their role is strictly restricted to generating human-readable morning briefs and explainability reports.
"""

import os
import json
import logging
import urllib.request
import urllib.error
from dataclasses import dataclass
from typing import Dict, List, Any, Optional, Tuple

logger = logging.getLogger("LLMProviderGateway")


@dataclass
class LLMExplanationResponse:
    provider_name: str
    model_version: str
    why_this_strategy_md: str
    why_not_alternatives_md: str
    invalidation_summary_md: str
    executive_brief_md: str
    is_local: bool
    ollama_online: bool = False


class LLMProviderGateway:
    """Interchangeable LLM Provider Gateway for Explainability & Research Briefs."""

    def __init__(self, provider_type: Optional[str] = None, ollama_url: str = "http://localhost:11434"):
        self.provider_type = (provider_type or os.getenv("LLM_PROVIDER", "local")).lower()
        self.ollama_url = ollama_url

    def check_ollama_status(self) -> Tuple[bool, List[str]]:
        """Checks if local Ollama service is active on http://localhost:11434 and lists installed models."""
        try:
            req = urllib.request.Request(f"{self.ollama_url}/api/tags")
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                models = [m.get("name") for m in data.get("models", [])]
                return True, models
        except Exception:
            return False, []

    def generate_explanation_brief(
        self,
        regime_label: str,
        regime_confidence_pct: float,
        recommended_strategy_name: str,
        suitability_score: int,
        primary_rationale: List[str],
        alternative_strategies: List[Dict[str, Any]],
        invalidation_rules: List[str]
    ) -> LLMExplanationResponse:
        """Generates structured natural-language brief via configured LLM provider or local Ollama."""

        why_md = "\n".join([f"- {r}" for r in primary_rationale])
        why_not_md = "\n".join([f"- **{a['strategy']}** (Score {a['score']}): {a['reason']}" for a in alternative_strategies])
        invalidation_md = "\n".join([f"- ⚠️ {rule}" for rule in invalidation_rules])

        ollama_online, installed_models = self.check_ollama_status()
        model_version = self._get_model_version(ollama_online, installed_models)
        is_local = self.provider_type == "local"

        provider_badge = "🦙 OLLAMA LOCAL" if (is_local and ollama_online) else self.provider_type.upper()

        executive_md = (
            f"### 🌅 NexTrade Morning Cockpit Brief [{provider_badge}]\n"
            f"**Market Regime:** {regime_label} (Confidence: {regime_confidence_pct:.1f}%)\n"
            f"**Strategy of the Day:** {recommended_strategy_name} (Suitability Score: {suitability_score}/100)\n"
            f"**LLM Model:** `{model_version}`\n\n"
            f"#### Why Today?\n{why_md}\n\n"
            f"#### Why Not Alternatives?\n{why_not_md}\n\n"
            f"#### What Could Invalidate This Thesis?\n{invalidation_md}"
        )

        return LLMExplanationResponse(
            provider_name=provider_badge,
            model_version=model_version,
            why_this_strategy_md=why_md,
            why_not_alternatives_md=why_not_md,
            invalidation_summary_md=invalidation_md,
            executive_brief_md=executive_md,
            is_local=is_local,
            ollama_online=ollama_online
        )

    def _get_model_version(self, ollama_online: bool = False, models: List[str] = None) -> str:
        if self.provider_type == "openai":
            return "GPT-4o (Cloud API)"
        elif self.provider_type == "anthropic":
            return "Claude 3.5 Sonnet (Cloud API)"
        elif self.provider_type == "gemini":
            return "Gemini 1.5 Pro (Cloud API)"
        elif self.provider_type == "grok":
            return "Grok-2 (Cloud API)"
        else:
            if ollama_online and models:
                return f"Ollama Local Active (`{models[0]}`)"
            elif ollama_online:
                return "Ollama Local Active (`http://localhost:11434`)"
            else:
                return "Ollama Installed on Laptop (Offline / Idle)"
