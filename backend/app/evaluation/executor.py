"""Run the configured model, evaluate the approved rubric, and commit immutable evidence."""

from datetime import UTC, datetime
from time import perf_counter
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

from app.assistant.prompts import resolve_system_prompt

from .configuration import validate_selection
from .models import CriterionResult, TestRequest, TestResult
from .providers import DemoProvider, OpenAICompatibleProvider
from .registry import CATALOG_REVISION, get_criterion
from .repository import ResultRepository
from .scoring import score_response
from .validators import evaluate_selected
from .weights import ScoringWeights


class TestExecutor:
    def __init__(
        self, provider: DemoProvider | OpenAICompatibleProvider, repository: ResultRepository
    ):
        self.provider = provider
        self.repository = repository

    def execute(self, request: TestRequest) -> TestResult:
        selected = validate_selection(request.criteria) if request.criteria is not None else None
        if selected is None:
            ScoringWeights.model_validate(request.weights)
        if selected and request.configuration_state != "approved":
            raise ValueError("Approve the criteria before execution.")
        started_at = datetime.now(UTC).isoformat()
        started = perf_counter()
        instructions = resolve_system_prompt(
            request.base_system_prompt, request.custom_system_prompt
        )
        response = ""
        model = request.model
        usage = {"input_tokens": None, "output_tokens": None}
        score = None
        error = None
        criteria = []
        try:
            generated = self.provider.generate(
                request.prompt, request.model, request.temperature, system_prompt=instructions
            )
            if not isinstance(generated.text, str):
                raise TypeError("The provider returned no textual response.")
            if len(generated.text) > 100_000:
                raise ValueError("Provider response exceeds the supported size.")
            response, model, usage = (
                generated.text,
                generated.model or request.model,
                generated.usage,
            )
        except Exception:
            error = {
                "code": "provider_failure",
                "message": "The model request failed. Retry or check the provider configuration.",
            }
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
                score, outcomes = evaluate_selected(response, selected, {"prompt": request.prompt})
                criteria = [
                    CriterionResult(**{k: v for k, v in row.items() if k != "id"})
                    for row in outcomes
                ]
                if score is None:
                    error = {
                        "code": "evaluation_incomplete",
                        "message": "An evaluator could not finish. The total is unavailable.",
                    }
        elif selected:
            criteria = [
                CriterionResult(
                    get_criterion(x["criterion_id"])["name"],
                    None,
                    None,
                    "Evaluation did not run because the model request failed.",
                    x["criterion_id"],
                    x["weight"],
                    None,
                    "error",
                )
                for x in selected
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
            id=str(uuid4()),
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
                "criterion_definitions": [get_criterion(x["criterion_id"]) for x in selected]
                if selected
                else None,
                "endpoint": endpoint,
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
