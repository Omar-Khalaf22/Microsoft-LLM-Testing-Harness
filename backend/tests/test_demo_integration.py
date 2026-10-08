"""Real PostgreSQL, real API/executor, mocked OpenAI transport. No API credits."""

import io
import json
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.config import Settings
from app.database import SessionLocal
from app.evaluation import providers
from app.evaluation.scoring import score_response
from app.evaluation.weights import default_weights
from app.models import TestRun, TestVersion
from app.repositories import prototype_runs
from app.routes import runs


@pytest.fixture
def configured_app(monkeypatch):
    # Never load a developer's credential. Only HTTP transport is replaced.
    monkeypatch.setattr(
        runs,
        "get_settings",
        lambda: Settings(
            _env_file=None,
            database_url="postgresql+psycopg://unused/unused",
            llm_provider="openai",
            openai_api_key="fake-test-only",
            openai_base_url="https://example.invalid/v1",
        ),
    )

    def respond(*args, **kwargs):
        return io.BytesIO(
            json.dumps(
                {
                    "choices": [
                        {"message": {"content": "JSON testing is useful. Metadata persists."}}
                    ],
                    "model": "gpt-4.1-mini",
                    "usage": {"prompt_tokens": 5, "completion_tokens": 8},
                }
            ).encode()
        )

    transport = Mock(side_effect=respond)
    monkeypatch.setattr(providers, "urlopen", transport)
    app = FastAPI()
    app.include_router(runs.router)
    return app, transport


def test_mocked_openai_commits_weights_and_reloads_versions(configured_app):
    app, transport = configured_app
    weights = {
        "keyword": 0,
        "relevance": 0,
        "length": 0,
        "sentences": 0,
        "forbidden": 0,
        "valid": 100,
    }
    body = {
        "test_name": "Persisted test " + uuid4().hex,
        "prompt": "Explain JSON testing",
        "model": "gpt-4.1-mini",
        "temperature": 0.3,
        "weights": weights,
    }
    with TestClient(app) as client:
        response = client.post("/runs", json=body)
        assert response.status_code == 200, response.text
        first = response.json()
        assert first["score"] == 100
        assert first["provider"] == "openai_compatible"
        assert first["metadata"]["scoring_weights"] == weights
        assert first["metadata"]["usage"] == {"input_tokens": 5, "output_tokens": 8}
        assert "fake-test-only" not in response.text
        outbound = json.loads(transport.call_args.args[0].data)
        assert outbound["model"] == body["model"]
        assert outbound["temperature"] == 0.3
        test_id = first["metadata"]["test_id"]
        with SessionLocal() as session:
            persisted = session.get(TestRun, first["id"])
            assert persisted is not None
            assert persisted.started_at <= persisted.completed_at
            version = session.get(TestVersion, persisted.test_version_id)
            assert version.evaluation_definition["scoring_weights"] == weights
        second = client.post(
            "/runs", json={**body, "test_id": test_id, "weights": default_weights()}
        ).json()
        assert second["metadata"]["test_version"] == 2
        old = client.post("/runs", json={**body, "test_id": test_id, "test_version": 1}).json()
        assert old["metadata"]["test_version"] == 1
        again = client.post(
            "/runs", json={**body, "test_id": test_id, "test_version": 1, "temperature": 0.8}
        ).json()
        assert again["metadata"]["test_version"] == 1
        before = transport.call_count
        bad = client.post("/runs", json={**body, "test_id": test_id, "test_version": 999})
        assert bad.status_code == 404
        assert transport.call_count == before
    # Fresh application and client; history must come from committed PostgreSQL.
    reloaded = FastAPI()
    reloaded.include_router(runs.router)
    with TestClient(reloaded) as client:
        history = client.get("/runs?limit=100").json()
        assert next(row for row in history if row["id"] == first["id"]) == first
        assert next(row for row in history if row["id"] == second["id"]) == second


@pytest.mark.parametrize(
    "weights",
    [
        {**default_weights(), "valid": 9},
        {**default_weights(), "valid": -1},
        {**default_weights(), "valid": "10"},
        {**default_weights(), "typo": 0},
    ],
)
def test_invalid_weights_precede_provider_construction(monkeypatch, weights):
    constructor = Mock(side_effect=AssertionError("Must not construct provider"))
    monkeypatch.setattr(runs, "OpenAICompatibleProvider", constructor)
    app = FastAPI()
    app.include_router(runs.router)
    with TestClient(app) as client:
        assert (
            client.post(
                "/runs", json={"test_name": "Invalid", "prompt": "Hello", "weights": weights}
            ).status_code
            == 422
        )
    constructor.assert_not_called()


def test_failed_storage_rolls_back_and_returns_sanitized_error(configured_app, monkeypatch):
    app, _ = configured_app
    with SessionLocal() as session:
        before = session.scalar(select(func.count()).select_from(TestVersion))
    monkeypatch.setattr(
        prototype_runs, "save_run_result", Mock(side_effect=RuntimeError("private"))
    )
    with TestClient(app) as client:
        response = client.post("/runs", json={"test_name": "Rollback", "prompt": "Hello"})
        assert response.status_code == 500
        assert response.json() == {"detail": "The run could not be completed."}
    with SessionLocal() as session:
        assert session.scalar(select(func.count()).select_from(TestVersion)) == before


def test_lina_zero_weights_and_empty_prompt_terms():
    weights = {
        "keyword": 0,
        "relevance": 100,
        "length": 0,
        "sentences": 0,
        "forbidden": 0,
        "valid": 0,
    }
    score, criteria = score_response("the and", "", ["missing"], 10, 2, [], weights)
    assert score == 100
    assert criteria[1].passed
    assert criteria[0].score == 0
    assert not criteria[0].passed
