"""DDD: numerical totals have no overall pass/fail classification.

These tests need no PostgreSQL service or external model requests. PostgreSQL
write/history assertions also live in test_prompt_persistence.py.
"""

import json
from copy import deepcopy
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.evaluation.executor import TestExecutor as Executor
from app.evaluation.providers import DemoProvider, ProviderResponse
from app.evaluation.repository import JsonResultRepository
from app.repositories.prototype_runs import PostgresResultRepository
from app.routes import runs
from app.schemas.runs import RunResponse


@pytest.mark.parametrize("response_length", [0, 74, 75, 76, 100])
def test_execution_api_and_json_storage_keep_numeric_score_without_threshold(
    tmp_path, response_length
):
    provider = Mock(spec=DemoProvider)
    provider.name = "local_demo"
    provider.generate.return_value = ProviderResponse("x" * response_length, "demo-strong-v1", {})
    path = tmp_path / "results.jsonl"
    repository = JsonResultRepository(path)
    executor = Executor(provider, repository)
    app = FastAPI()
    app.include_router(runs.router)
    app.dependency_overrides[runs.get_executor] = lambda: executor
    app.dependency_overrides[runs.get_result_repository] = lambda: repository
    request = {
        "test_name": "Numeric score contract",
        "prompt": "Return a response with 100 characters.",
        "minimum_length": 100,
        "weights": {
            "keyword": 0,
            "relevance": 0,
            "length": 100,
            "sentences": 0,
            "forbidden": 0,
            "valid": 0,
        },
    }
    with TestClient(app) as client:
        response = client.post("/runs", json=request)
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["status"] == "completed"
        assert result["score"] == response_length
        assert "passed" not in result
        history = client.get("/runs")
        assert history.status_code == 200, history.text
        assert history.json() == [result]
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored == result
    assert "passed" not in stored
    provider.generate.assert_called_once()


@pytest.mark.parametrize("legacy_passed", [False, True])
def test_legacy_json_history_omits_overall_judgment_without_rewriting_file(tmp_path, legacy_passed):
    row = {
        "id": "historic-run",
        "status": "completed",
        "prompt": "Return JSON.",
        "model": "historic-model",
        "provider": "local_demo",
        "response": '{"ok":true}',
        "score": 42.5,
        "passed": legacy_passed,
        "criteria": [],
        "latency_ms": 12,
        "created_at": "2026-10-21T12:00:00+00:00",
        "metadata": {},
    }
    path = tmp_path / "history.jsonl"
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    original = path.read_bytes()
    repository = JsonResultRepository(path)
    app = FastAPI()
    app.include_router(runs.router)
    app.dependency_overrides[runs.get_result_repository] = lambda: repository
    with TestClient(app) as client:
        response = client.get("/runs")
    assert response.status_code == 200, response.text
    result = response.json()[0]
    assert result["score"] == 42.5
    assert "passed" not in result
    assert path.read_bytes() == original


@pytest.mark.parametrize("legacy_passed", [False, True, None])
def test_postgres_history_projection_ignores_legacy_judgment_and_preserves_snapshot(
    legacy_passed,
):
    saved = {
        "run_id": "historic-sql-run",
        "status": "completed",
        "test_name": "Historic numeric result",
        "model": {"name": "historic-model"},
        "configuration": {
            "overall_score": 42.5,
            "passed": legacy_passed,
            "metadata": {"requested_model": "historic-model"},
        },
        "input": {"prompt": "Return JSON."},
        "response": {"content": '{"ok":true}'},
        "evaluations": [
            {
                "method": "Example condition",
                "passed": True,
                "score": 0.425,
                "details": {"detail": "Recorded criterion evidence"},
            }
        ],
        "metrics": {"latency_ms": 12},
        "started_at": "2026-10-21T12:00:00+00:00",
        "completed_at": "2026-10-21T12:00:01+00:00",
    }
    if legacy_passed is None:
        saved["configuration"].pop("passed")
    original = deepcopy(saved)
    result = PostgresResultRepository._as_api_result(saved)
    assert result["score"] == 42.5
    assert "passed" not in result
    assert result["criteria"][0]["score"] == 42.5
    assert saved == original


def test_public_run_schema_has_no_overall_pass_fail_field():
    schema = RunResponse.model_json_schema()
    assert "score" in schema["properties"]
    assert "passed" not in schema["properties"]
    assert "passed" not in schema["required"]
