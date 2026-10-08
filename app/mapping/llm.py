"""Optional, bounded LLM reranking for already-local mapping candidates."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Protocol

import httpx
from pydantic import BaseModel, Field, ValidationError


REDACTED_FIELD_TOKENS = ("patient_id", "name", "phone", "id_number", "address", "身份证")


class LLMRerankResult(BaseModel):
    """Strict, target-bounded provider output."""

    candidate_target: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[str] = Field(default_factory=list, max_length=4)
    transform_proposal: str = Field(default="identity", max_length=64)
    abstain: bool


@dataclass(frozen=True)
class RerankOutcome:
    """Sanitized decision and provenance for an attempted provider call."""

    result: LLMRerankResult | None
    status: str
    provider: str
    model: str
    context_hash: str | None
    response_hash: str | None


class LLMMappingProvider(Protocol):
    """Provider-neutral adapter contract."""

    def rerank(self, context: dict[str, object]) -> RerankOutcome:
        """Return a strict result or a safe fallback outcome."""


def _hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def build_safe_rerank_context(profile: dict[str, object], candidates: list[dict[str, object]]) -> dict[str, object] | None:
    """Allow only bounded schema metadata; reject identifier-like source fields."""
    field = str(profile["field"])
    if any(token in field.lower() for token in REDACTED_FIELD_TOKENS):
        return None
    safe_summary = profile.get("safe_summary")
    if not isinstance(safe_summary, dict) or safe_summary.get("classification") != "metadata_safe":
        return None
    return {
        "profile": {
            "field": field,
            "inferred_type": str(profile["inferred_type"]),
            "unit": profile.get("unit"),
            "safe_summary": {
                "classification": "metadata_safe",
                "non_null_count": safe_summary.get("non_null_count"),
                "distinct_count": safe_summary.get("distinct_count"),
                "sample_kind": safe_summary.get("sample_kind"),
            },
        },
        "candidates": [
            {"target": str(candidate["target"]), "domain": str(candidate["domain"]), "rank": int(candidate["rank"])}
            for candidate in candidates[:10]
        ],
    }


class DeepSeekMappingProvider:
    """OpenAI-compatible DeepSeek JSON-mode adapter; no key means no request."""

    def __init__(self, api_key: str, base_url: str, model: str, timeout_seconds: int) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds

    def rerank(self, context: dict[str, object]) -> RerankOutcome:
        context_hash = _hash(context)
        if not self.api_key:
            return RerankOutcome(None, "provider_not_configured", "deepseek", self.model, context_hash, None)
        prompt = {
            "task": "Choose only one provided target for a healthcare source field, or abstain.",
            "rules": ["Do not invent targets.", "Return JSON only.", "Use identity unless a safe transform is necessary."],
            "context": context,
        }
        try:
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "response_format": {"type": "json_object"},
                    "messages": [{"role": "user", "content": json.dumps(prompt, separators=(",", ":"))}],
                    "temperature": 0,
                },
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            raw_content = response.json()["choices"][0]["message"]["content"]
            response_hash = _hash(raw_content)
            result = LLMRerankResult.model_validate_json(raw_content)
            allowed_targets = {str(candidate["target"]) for candidate in context["candidates"]}
            if result.candidate_target not in allowed_targets and not result.abstain:
                return RerankOutcome(None, "invalid_target", "deepseek", self.model, context_hash, response_hash)
            if result.abstain:
                result = result.model_copy(update={"candidate_target": None})
            return RerankOutcome(result, "completed", "deepseek", self.model, context_hash, response_hash)
        except (httpx.HTTPError, KeyError, TypeError, json.JSONDecodeError, ValidationError):
            return RerankOutcome(None, "provider_fallback", "deepseek", self.model, context_hash, None)
