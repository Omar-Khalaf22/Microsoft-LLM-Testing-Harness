"""Adapt inline Run API contracts to the existing evaluation executor."""

from app.evaluation.executor import TestExecutor
from app.evaluation.models import TestRequest
from app.schemas.runs import RunCreateRequest, RunResponse


def create_run(request: RunCreateRequest, *, executor: TestExecutor) -> RunResponse:
    """Execute once and validate the result; exceptions propagate to the caller."""
    evaluation_request = TestRequest(
        prompt=request.prompt,
        model=request.model,
        temperature=request.temperature,
        expected_keywords=request.expected_keywords,
        minimum_length=request.minimum_length,
        minimum_sentences=request.minimum_sentences,
        forbidden_terms=request.forbidden_terms,
        test_id=request.test_id,
        test_name=request.test_name,
        test_version=request.test_version,
    )
    result = executor.execute(evaluation_request)
    return RunResponse.model_validate(result.to_dict())
