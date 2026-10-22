"""Prototype 2 API → evaluator → PostgreSQL → fresh-client retrieval, with no paid calls."""

from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database import SessionLocal
from app.evaluation.executor import TestExecutor as Executor
from app.evaluation.providers import DemoProvider
from app.models import EvaluationResult, TestVersion
from app.models.recommendation import CriteriaRecommendation
from app.repositories.prototype_runs import PostgresResultRepository
from app.routes import assistant, criteria, runs


@pytest.fixture
def app():
    app = FastAPI()
    app.include_router(runs.router)
    app.include_router(assistant.router)
    app.include_router(criteria.router)
    repo = PostgresResultRepository(SessionLocal)
    app.dependency_overrides[runs.get_executor] = lambda: Executor(DemoProvider(), repo)
    app.dependency_overrides[assistant.get_assistant_provider] = lambda: DemoProvider()
    return app


def config():
    return {
        "test_name": "P2 " + uuid4().hex,
        "prompt": "Return JSON with count 3",
        "objective": "Produce a JSON object",
        "model": "demo-json-v1",
        "base_system_prompt": "Return precise JSON.",
        "custom_system_prompt": "Keep count numeric.",
        "criteria": [
            {"criterion_id": "valid_json", "parameters": {}, "weight": 33.33},
            {"criterion_id": "json_object", "parameters": {}, "weight": 33.33},
            {
                "criterion_id": "json_field_type",
                "parameters": {"field": "count", "type": "integer"},
                "weight": 33.34,
            },
        ],
        "configuration_state": "approved",
    }


def test_suggestions_approval_execution_and_exact_snapshot_reload(app):
    body = config()
    with TestClient(app) as client:
        definitions = client.get("/evaluation/criteria").json()
        assert len(definitions["criteria"]) == 36
        rec = client.post(
            "/assistant/suggest-criteria",
            json={"objective": body["objective"], "test_prompt": body["prompt"]},
        )
        assert rec.status_code == 200, rec.text
        generated = rec.json()
        body["recommendation_id"] = generated["recommendation_id"]
        with SessionLocal() as s:
            assert (
                s.get(CriteriaRecommendation, generated["recommendation_id"]).snapshot == generated
            )
        response = client.post("/runs", json=body)
        assert response.status_code == 200, response.text
        first = response.json()
        assert first["score"] == 100 and "passed" not in first
        assert first["metadata"]["criteria"] == body["criteria"]
        assert first["metadata"]["generated_configuration"] == generated
        assert first["metadata"]["configuration_state"] == "approved"
        tid = first["metadata"]["test_id"]
        assert client.get("/runs/" + first["id"]).json() == first
        repeated = client.post("/runs", json={**body, "test_id": tid, "temperature": 0.8}).json()
        assert repeated["metadata"]["test_version"] == 1
        revised = client.post(
            "/runs", json={**body, "test_id": tid, "custom_system_prompt": "Use no Markdown."}
        ).json()
        assert revised["metadata"]["test_version"] == 2
        older = client.post("/runs", json={**body, "test_id": tid, "test_version": 1}).json()
        assert older["metadata"]["test_version"] == 1
    # A fresh client loads all evidence from SQL, including the original generated configuration.
    with TestClient(app) as client:
        assert client.get("/runs/" + first["id"]).json() == first
    with SessionLocal() as s:
        evaluations = s.scalars(
            select(EvaluationResult).where(EvaluationResult.run_id == first["id"])
        ).all()
        assert [float(x.earned_points) for x in evaluations] == [33.33, 33.33, 33.34]
        assert all(x.normalized_score == 1 for x in evaluations)
        version = s.scalar(
            select(TestVersion).where(TestVersion.test_id == tid, TestVersion.version == 1)
        )
        assert version.evaluation_definition["criteria"] == body["criteria"]


@pytest.mark.parametrize(
    "patch",
    [
        {"configuration_state": "draft"},
        {"configuration_state": None},
        {"criteria": [{"criterion_id": "semantic_similarity", "parameters": {}, "weight": 100}]},
        {"criteria": [{"criterion_id": "json_field_type", "parameters": {}, "weight": 100}]},
        {"criteria": [{"criterion_id": "valid_json", "parameters": {}, "weight": 0}]},
        {"criteria": [{"criterion_id": "valid_json", "parameters": {}, "weight": 99.99}]},
        {"criteria": [{"criterion_id": "valid_json", "parameters": {}, "weight": 100.001}]},
    ],
)
def test_invalid_criteria_rejected_before_provider(app, patch):
    provider = Mock(side_effect=AssertionError("Must not construct provider"))
    app.dependency_overrides[runs.get_executor] = provider
    with TestClient(app) as c:
        assert c.post("/runs", json={**config(), **patch}).status_code == 422
    provider.assert_not_called()


def test_unknown_saved_run_is_404(app):
    with TestClient(app) as c:
        assert c.get("/runs/" + uuid4().hex).status_code == 404


def test_provider_failure_is_saved_with_null_total_and_unknown_usage(app):
    provider = Mock(name="provider")
    provider.name = "mock"
    provider.generate.side_effect = RuntimeError("private credential")
    repo = PostgresResultRepository(SessionLocal)
    app.dependency_overrides[runs.get_executor] = lambda: Executor(provider, repo)
    with TestClient(app) as c:
        response = c.post("/runs", json=config())
        assert response.status_code == 502, response.text
        saved = c.get("/runs/" + response.json()["detail"]["run_id"]).json()
        assert saved["score"] is None and saved["status"] == "failed"
        assert saved["metadata"]["usage"] == {"input_tokens": None, "output_tokens": None}
        assert all(x["status"] == "error" and x["score"] is None for x in saved["criteria"])
        assert "private credential" not in str(saved)


def test_evaluator_failure_keeps_other_evidence_and_withholds_total(app, monkeypatch):
    from app.evaluation import validators

    original = validators.evaluate_criterion

    def sometimes(cid, *args):
        if cid == "json_object":
            raise RuntimeError("private error")
        return original(cid, *args)

    monkeypatch.setattr(validators, "evaluate_criterion", sometimes)
    with TestClient(app) as c:
        r = c.post("/runs", json=config())
        assert r.status_code == 200, r.text
        saved = r.json()
        assert saved["score"] is None
        assert [x["score"] for x in saved["criteria"]] == [33.33, None, 33.34]
        assert c.get("/runs/" + saved["id"]).json() == saved
    with SessionLocal() as s:
        row = s.scalar(
            select(EvaluationResult).where(
                EvaluationResult.run_id == saved["id"], EvaluationResult.status == "error"
            )
        )
        assert row.score is None and row.passed is None and row.earned_points is None


def test_criteria_edits_create_versions_without_rewriting_prior_results(app):
    body = config()
    with TestClient(app) as client:
        first = client.post("/runs", json=body).json()
        changed = [dict(x) for x in body["criteria"]]
        changed[0]["weight"] = 40
        changed[1]["weight"] = 20
        changed[2] = {
            "criterion_id": "json_field_type",
            "parameters": {"field": "count", "type": "string"},
            "weight": 40,
        }
        second = client.post(
            "/runs", json={**body, "test_id": first["metadata"]["test_id"], "criteria": changed}
        ).json()
        assert second["metadata"]["test_version"] == 2
        assert second["score"] == 60
        assert client.get("/runs/" + first["id"]).json() == first
        again = client.post(
            "/runs", json={**body, "test_id": first["metadata"]["test_id"], "test_version": 1}
        ).json()
        assert again["metadata"]["test_version"] == 1 and again["score"] == 100


def test_legacy_evaluator_failure_is_saved_as_incomplete(app, monkeypatch):
    from app.evaluation import executor

    def broken(*args, **kwargs):
        raise RuntimeError("internal private failure")

    monkeypatch.setattr(executor, "score_response", broken)
    with TestClient(app) as client:
        r = client.post("/runs", json={"test_name": "Legacy failure", "prompt": "Hello"})
        assert r.status_code == 200, r.text
        result = r.json()
        assert result["score"] is None and len(result["criteria"]) == 6
        assert all(c["status"] == "error" and c["score"] is None for c in result["criteria"])
        assert client.get("/runs/" + result["id"]).json() == result
