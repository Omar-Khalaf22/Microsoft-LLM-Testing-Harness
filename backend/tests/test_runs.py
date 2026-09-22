"""Test-first contract for the inline Run service and router.

Target modules intentionally do not exist yet. Imports happen in fixtures so each
missing dependency is reported as a setup error, without hiding existing tests.
"""

from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.evaluation import providers
from app.evaluation.executor import TestExecutor as EvaluationExecutor
from app.evaluation.models import CriterionResult
from app.evaluation.models import TestRequest as EvaluationRequest
from app.evaluation.models import TestResult as EvaluationResult
from app.schemas.runs import RunCreateRequest, RunResponse


@pytest.fixture(autouse=True)
def no_provider_network(monkeypatch):
    def blocked(*args, **kwargs):
        pytest.fail("Run tests must not make provider network calls")

    monkeypatch.setattr(providers, "urlopen", blocked)


@pytest.fixture
def run_service():
    from app.services import run_service

    return run_service


@pytest.fixture
def request_model():
    return RunCreateRequest(
        prompt="Explain secure JSON storage",
        model="requested-model",
        temperature=0.7,
        expected_keywords=["JSON", "metadata"],
        minimum_length=120,
        minimum_sentences=3,
        forbidden_terms=["unavailable"],
    )


@pytest.fixture
def execution_result():
    # Deliberately not a passing evaluation; the service must preserve the result.
    return EvaluationResult(
        id="bf6babaa-431e-4b04-8182-25499cb75c3f",
        status="completed",
        prompt="Explain secure JSON storage",
        model="returned-model",
        provider="openai_compatible",
        response="JSON storage needs care.",
        score=42.5,
        passed=False,
        criteria=[CriterionResult("Keyword coverage", False, 15.0, "Missing: metadata")],
        latency_ms=123,
        created_at="2026-09-22T12:00:00+00:00",
        metadata={
            "requested_model": "requested-model",
            "temperature": 0.7,
            "expected_keywords": ["JSON", "metadata"],
            "minimum_length": 120,
            "minimum_sentences": 3,
            "forbidden_terms": ["unavailable"],
            "usage": {"input_tokens": 4, "output_tokens": 5},
            "schema_version": "1.0",
        },
    )


@pytest.fixture
def executor(execution_result):
    # A spec constrains the fake to the existing executor's public interface.
    fake = Mock(spec_set=EvaluationExecutor)
    fake.execute.return_value = execution_result
    return fake


@pytest.fixture
def client(executor):
    from app.routes import runs

    app = FastAPI()
    app.include_router(runs.router)
    app.dependency_overrides[runs.get_executor] = lambda: executor
    # Keep server exceptions enabled: an unhandled error must fail the test.
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_service_adapts_all_inputs_and_executes_once(run_service, request_model, executor):
    run_service.create_run(request_model, executor=executor)

    executor.execute.assert_called_once_with(
        EvaluationRequest(
            prompt="Explain secure JSON storage",
            model="requested-model",
            temperature=0.7,
            expected_keywords=["JSON", "metadata"],
            minimum_length=120,
            minimum_sentences=3,
            forbidden_terms=["unavailable"],
        )
    )


def test_service_preserves_result_and_failed_evaluation(
    run_service, request_model, executor, execution_result
):
    response = run_service.create_run(request_model, executor=executor)

    assert isinstance(response, RunResponse)
    assert response.model_dump(mode="json") == execution_result.to_dict()
    assert response.status == "completed"
    assert response.passed is False
    executor.execute.assert_called_once()


@pytest.mark.parametrize("error_type", [RuntimeError, KeyError, OSError])
def test_service_propagates_executor_errors(run_service, request_model, executor, error_type):
    error = error_type("Internal execution or persistence failure")
    executor.execute.side_effect = error

    with pytest.raises(error_type) as caught:
        run_service.create_run(request_model, executor=executor)

    assert caught.value is error
    executor.execute.assert_called_once()


def test_post_runs_returns_completed_result(client, request_model, executor, execution_result):
    response = client.post("/runs", json=request_model.model_dump(mode="json"))

    assert response.status_code == 200
    assert response.json() == execution_result.to_dict()
    assert RunResponse.model_validate(response.json()).passed is False
    executor.execute.assert_called_once_with(EvaluationRequest(**request_model.model_dump()))


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"prompt": None},
        {"prompt": "   "},
        {"prompt": "x" * 10_001},
        {"prompt": "Hello", "temperature": 2.1},
        {"prompt": "Hello", "minimum_length": -1},
        {"prompt": "Hello", "minimum_sentences": 0},
        {"prompt": "Hello", "expected_keywords": "JSON, metadata"},
        {"prompt": "Hello", "forbidden_terms": ["x"] * 21},
        [],
    ],
    ids=[
        "missing-prompt",
        "null-prompt",
        "blank-prompt",
        "long-prompt",
        "temperature-range",
        "length-range",
        "sentence-range",
        "terms-not-array",
        "too-many-terms",
        "body-not-object",
    ],
)
def test_post_runs_rejects_invalid_input_before_execution(client, executor, body):
    response = client.post("/runs", json=body)

    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)
    executor.execute.assert_not_called()


def test_post_runs_rejects_malformed_json_before_execution(client, executor):
    response = client.post("/runs", content="{broken", headers={"Content-Type": "application/json"})

    assert response.status_code == 422
    executor.execute.assert_not_called()


@pytest.mark.parametrize("error_type", [RuntimeError, KeyError, OSError])
def test_post_runs_hides_internal_failure_details(client, request_model, executor, error_type):
    executor.execute.side_effect = error_type(
        "Sensitive internal detail: Bearer fake-key-for-test-only; Traceback /private/path"
    )

    response = client.post("/runs", json=request_model.model_dump(mode="json"))

    assert response.status_code == 500
    assert response.json() == {"detail": "The run could not be completed."}
    executor.execute.assert_called_once()


def test_real_app_exposes_post_runs(monkeypatch, request_model, executor, execution_result):
    # Settings require a URL at import time; this test never opens a DB connection.
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+psycopg://llm_harness:test@localhost:5432/llm_harness_test"
    )
    from app.main import app
    from app.routes import runs

    original_overrides = app.dependency_overrides.copy()
    with monkeypatch.context() as overrides:
        overrides.setitem(app.dependency_overrides, runs.get_executor, lambda: executor)
        with TestClient(app) as real_client:
            response = real_client.post("/runs", json=request_model.model_dump(mode="json"))

        assert response.status_code == 200
        assert response.json() == execution_result.to_dict()
        executor.execute.assert_called_once_with(EvaluationRequest(**request_model.model_dump()))
    assert app.dependency_overrides == original_overrides
