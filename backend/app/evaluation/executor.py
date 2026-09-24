"""Orchestrates model execution, scoring, and storage."""

from __future__ import annotations

from datetime import UTC, datetime
from time import perf_counter
from uuid import uuid4

from .models import TestRequest, TestResult
from .providers import DemoProvider, OpenAICompatibleProvider
from .repository import ResultRepository
from .scoring import score_response


class TestExecutor:
    def __init__(
        self,
        provider: DemoProvider | OpenAICompatibleProvider,
        repository: ResultRepository,
    ):
        self.provider = provider
        self.repository = repository

    def execute(self, request: TestRequest) -> TestResult:
        started = perf_counter()
        generated = self.provider.generate(request.prompt, request.model, request.temperature)
        score, criteria = score_response(
            request.prompt,
            generated.text,
            request.expected_keywords,
            request.minimum_length,
            request.minimum_sentences,
            request.forbidden_terms,
        )
        latency_ms = max(1, round((perf_counter() - started) * 1000))
        result = TestResult(
            id=str(uuid4()),
            status="completed",
            prompt=request.prompt,
            model=generated.model,
            provider=self.provider.name,
            response=generated.text,
            score=score,
            passed=score >= 75,
            criteria=criteria,
            latency_ms=latency_ms,
            created_at=datetime.now(UTC).isoformat(),
            metadata={
                "requested_model": request.model,
                "temperature": request.temperature,
                "expected_keywords": request.expected_keywords,
                "minimum_length": request.minimum_length,
                "minimum_sentences": request.minimum_sentences,
                "forbidden_terms": request.forbidden_terms,
                "usage": generated.usage,
                "schema_version": "1.0",
            },
        )
        # SQL storage enriches the result with its saved test identity/version.
        # The standalone JSONL demo keeps returning the original result.
        return self.repository.save(result, test_id=request.test_id) or result

    def recent_results(self, limit: int = 10) -> list[dict]:
        return self.repository.recent(limit)
