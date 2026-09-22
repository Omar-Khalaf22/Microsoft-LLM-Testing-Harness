"""Validated request and result models for machine evaluation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


class ValidationError(ValueError):
    """Raised when a test request is invalid."""


@dataclass(frozen=True)
class TestRequest:
    prompt: str
    expected_keywords: list[str] = field(default_factory=list)
    model: str = "gpt-4.1-mini"
    temperature: float = 0.2
    minimum_length: int = 40
    minimum_sentences: int = 2
    forbidden_terms: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TestRequest:
        prompt = str(data.get("prompt", "")).strip()
        if not prompt:
            raise ValidationError("A prompt is required.")
        if len(prompt) > 10_000:
            raise ValidationError("Prompt must be 10,000 characters or fewer.")

        keywords = _parse_terms(data.get("expected_keywords", []), "Expected keywords")
        forbidden_terms = _parse_terms(
            data.get("forbidden_terms", []), "Forbidden terms"
        )

        try:
            temperature = float(data.get("temperature", 0.2))
            minimum_length = int(data.get("minimum_length", 40))
            minimum_sentences = int(data.get("minimum_sentences", 2))
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                "Temperature, minimum length, and minimum sentences must be numbers."
            ) from exc

        if not 0 <= temperature <= 2:
            raise ValidationError("Temperature must be between 0 and 2.")
        if not 0 <= minimum_length <= 10_000:
            raise ValidationError("Minimum length must be between 0 and 10,000.")
        if not 1 <= minimum_sentences <= 20:
            raise ValidationError("Minimum sentences must be between 1 and 20.")

        model = str(data.get("model", "gpt-4.1-mini")).strip() or "gpt-4.1-mini"
        return cls(
            prompt=prompt,
            expected_keywords=keywords[:20],
            model=model,
            temperature=temperature,
            minimum_length=minimum_length,
            minimum_sentences=minimum_sentences,
            forbidden_terms=forbidden_terms[:20],
        )


def _parse_terms(value: Any, label: str) -> list[str]:
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    raise ValidationError(f"{label} must be a list or comma separated text.")


@dataclass(frozen=True)
class CriterionResult:
    name: str
    passed: bool
    score: float
    detail: str


@dataclass(frozen=True)
class TestResult:
    id: str
    status: str
    prompt: str
    model: str
    provider: str
    response: str
    score: float
    passed: bool
    criteria: list[CriterionResult]
    latency_ms: int
    created_at: str
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
