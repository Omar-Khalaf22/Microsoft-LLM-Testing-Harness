"""Run the configured model, evaluate the approved rubric, and commit immutable evidence."""

from datetime import UTC, datetime
from time import perf_counter
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

from app.assistant.prompts import resolve_system_prompt
from app.config import get_settings

from .configuration import criterion_definition, validate_selection
from .models import CriterionResult, TestRequest, TestResult
from .providers import DemoProvider, OpenAICompatibleProvider
from .registry import CATALOG_REVISION, get_criterion
from .repository import ResultRepository
from .scoring import score_response
from .validators import evaluate_selected
from .weights import ScoringWeights


def _total_tokens(usage: dict) -> int | None:
    """Return reported token usage without inventing missing values."""
    if not isinstance(usage, dict):
        return None
    total = usage.get("total_tokens")
    if type(total) is int and total >= 0:
        return total
    input_tokens = usage.get("input_tokens")
    output_tokens = usage.get("output_tokens")
    if all(type(value) is int and value >= 0 for value in (input_tokens, output_tokens)):
        return input_tokens + output_tokens
    return None


class TestExecutor:
    def __init__(
        self,
        provider: DemoProvider | OpenAICompatibleProvider,
        repository: ResultRepository,
        *,
        judge_context: dict | None = None,
    ):
        self.provider = provider
        self.repository = repository
        self.judge_context = judge_context

    def execute(self, request: TestRequest) -> TestResult:
        selected = validate_selection(request.criteria) if request.criteria is not None else None
        if selected is None:
            ScoringWeights.model_validate(request.weights)
        if selected and request.configuration_state != "approved":
            raise ValueError("Approve the criteria before execution.")
        definitions = request.frozen_criterion_definitions
        if definitions is None and selected:
            definitions = [criterion_definition(row) for row in selected]
        started_at = datetime.now(UTC).isoformat()
        started = perf_counter()
        instructions = request.frozen_system_prompt or resolve_system_prompt(
            request.base_system_prompt, request.custom_system_prompt
        )
        response = ""
        model = request.model
        usage = {"input_tokens": None, "output_tokens": None}
        score = None
        error = None
        criteria = []
        context = {}
        reported_model = None
        target_started = perf_counter()
        try:
            generated = self.provider.generate(
                request.prompt, request.model, request.temperature, system_prompt=instructions
            )
            if not isinstance(generated.text, str):
                raise TypeError("The provider returned no textual response.")
            if len(generated.text) > 100_000 or "\x00" in generated.text:
                raise ValueError("Provider response exceeds the supported size.")
            response, model, usage = (
                generated.text,
                generated.model or request.model,
                generated.usage,
            )
            reported_model = generated.model if getattr(generated, "model_reported", True) else None
        except Exception:
            error = {
                "code": "provider_failure",
                "message": "The model request failed. Retry or check the provider configuration.",
            }
        target_ms = max(0, round((perf_counter() - target_started) * 1000))
        if error is None and request.reserved_run_id:
            self.repository.checkpoint(generated, target_ms)
        evaluation_started = perf_counter()
        if error is None:
            if selected is None:
                try:
                    score, criteria = score_response(
                        request.prompt,
                        response,
                        request.expected_keywords,
                        request.minimum_length,
                        request.minimum_sentences,
                        request.forbidden_terms,
                        request.weights,
                    )
                except Exception:
                    from .evaluators.legacy import WEIGHT_IDS

                    score = None
                    error = {
                        "code": "evaluation_incomplete",
                        "message": "An evaluator could not finish. The total is unavailable.",
                    }
                    criteria = [
                        CriterionResult(
                            get_criterion(cid)["name"],
                            None,
                            None,
                            "The legacy evaluation could not complete.",
                            cid,
                            request.weights[key],
                            None,
                            "error",
                        )
                        for key, cid in WEIGHT_IDS.items()
                    ]
            else:
                context = {
                    "prompt": request.prompt,
                    "objective": request.objective,
                    "approved_instructions": instructions,
                    "recorded_execution_metrics": {
                        "latency_ms": target_ms,
                        "total_tokens": _total_tokens(usage),
                    },
                }
                if any(d["evaluator_type"] == "rubric" for d in definitions):
                    settings = get_settings()
                    context.update(
                        self.judge_context
                        or {
                            "judge_model": settings.judge_model,
                            "judge_profile_id": settings.judge_profile_id,
                            "judge_profile_revision": settings.judge_profile_revision,
                        }
                    )
                    if (
                        not self.judge_context
                        and settings.judge_model
                        and settings.openai_api_key.get_secret_value().strip()
                    ):
                        context["judge_provider"] = OpenAICompatibleProvider(
                            api_key=settings.openai_api_key.get_secret_value().strip(),
                            base_url=settings.openai_base_url,
                        )
                score, outcomes = evaluate_selected(response, selected, context)
                criteria = [
                    CriterionResult(
                        name=definition["name"],
                        **{k: v for k, v in row.items() if k not in {"id", "name"}},
                    )
                    for row, definition in zip(outcomes, definitions, strict=True)
                ]
                if score is None:
                    error = {
                        "code": "evaluation_incomplete",
                        "message": "An evaluator could not finish. The total is unavailable.",
                    }
        elif selected:
            criteria = [
                CriterionResult(
                    definition["name"],
                    None,
                    None,
                    "Evaluation did not run because the model request failed.",
                    x["criterion_id"],
                    x["weight"],
                    None,
                    "error",
                )
                for x, definition in zip(selected, definitions, strict=True)
            ]
        if error and selected is None and not criteria:
            from .evaluators.legacy import WEIGHT_IDS

            criteria = [
                CriterionResult(
                    get_criterion(cid)["name"],
                    None,
                    None,
                    "Evaluation did not run because the model request failed.",
                    cid,
                    request.weights[key],
                    None,
                    "error",
                )
                for key, cid in WEIGHT_IDS.items()
            ]
        endpoint = getattr(self.provider, "base_url", None)
        if isinstance(endpoint, str):
            parts = urlsplit(endpoint)
            endpoint = urlunsplit(
                (parts.scheme, parts.netloc.rsplit("@", 1)[-1], parts.path, "", "")
            )
        else:
            endpoint = None
        result = TestResult(
            id=request.reserved_run_id or str(uuid4()),
            status="failed" if error else "completed",
            prompt=request.prompt,
            model=model,
            provider=self.provider.name,
            response=response,
            score=score,
            criteria=criteria,
            latency_ms=max(1, round((perf_counter() - started) * 1000)),
            created_at=datetime.now(UTC).isoformat(),
            error=error,
            metadata={
                "base_system_prompt": request.base_system_prompt,
                "custom_system_prompt": request.custom_system_prompt,
                "resolved_system_prompt": instructions,
                "requested_model": request.model,
                "temperature": request.temperature,
                "expected_keywords": request.expected_keywords,
                "minimum_length": request.minimum_length,
                "minimum_sentences": request.minimum_sentences,
                "forbidden_terms": request.forbidden_terms,
                "scoring_weights": request.weights if selected is None else None,
                "usage": usage,
                "schema_version": "3.0",
                "started_at": started_at,
                "objective": request.objective,
                "criteria": selected,
                "configuration_state": "approved",
                "catalog_revision": CATALOG_REVISION,
                "recommendation_id": request.recommendation_id,
                "generated_configuration": request.recommendation_snapshot,
                "approved_at": started_at,
                "criterion_definitions": definitions,
                "endpoint": endpoint,
                "rubric_evidence": context.get("rubric_evidence", {}) if selected else {},
                "target_metrics": {"latency_ms": target_ms, "usage": usage},
                "provider_reported_model": reported_model,
                "evaluation_metrics": {
                    "latency_ms": max(0, round((perf_counter() - evaluation_started) * 1000)),
                    "judge_calls": context.get("judge_calls", []),
                },
                "latency_semantics": "target_plus_evaluation",
                "judge_profile_id": context.get("judge_profile_id"),
                "judge_profile_revision": context.get("judge_profile_revision"),
                "judge_model": context.get("judge_model"),
                "judge_provider": getattr(context.get("judge_provider"), "name", None),
                "resolved_judge_models": (
                    context.get("resolved_judge_models", {}) if selected else {}
                ),
            },
        )
        return (
            self.repository.save(
                result,
                test_id=request.test_id,
                test_name=request.test_name,
                test_version=request.test_version,
            )
            or result
        )

    def recent_results(self, limit: int = 10) -> list[dict]:
        return self.repository.recent(limit)
