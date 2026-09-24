"""The browser API must return committed runs and their immutable test versions."""

from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.database import SessionLocal
from app.evaluation.executor import TestExecutor
from app.evaluation.providers import DemoProvider
from app.models import EvaluationResult, ModelResponse, Test, TestRun, TestVersion
from app.repositories.prototype_runs import PostgresResultRepository
from app.routes import runs


def _clean_test(test_id: str) -> None:
    with SessionLocal.begin() as session:
        version_ids = select(TestVersion.id).where(TestVersion.test_id == test_id)
        run_ids = select(TestRun.id).where(TestRun.test_version_id.in_(version_ids))
        session.execute(delete(EvaluationResult).where(EvaluationResult.run_id.in_(run_ids)))
        session.execute(delete(ModelResponse).where(ModelResponse.run_id.in_(run_ids)))
        session.execute(delete(TestRun).where(TestRun.test_version_id.in_(version_ids)))
        session.execute(delete(TestVersion).where(TestVersion.test_id == test_id))
        session.execute(delete(Test).where(Test.id == test_id))


def test_api_history_survives_reload_and_versions_change_only_with_definition() -> None:
    repository = PostgresResultRepository(SessionLocal)
    app = FastAPI()
    app.include_router(runs.router)
    app.dependency_overrides[runs.get_executor] = lambda: TestExecutor(DemoProvider(), repository)
    app.dependency_overrides[runs.get_result_repository] = lambda: repository

    request = {
        "test_name": "JSON check",
        "prompt": f"Explain JSON testing {uuid4().hex}",
        "model": "demo-strong-v1",
        "temperature": 0.2,
        "expected_keywords": ["JSON"],
        "minimum_length": 10,
        "minimum_sentences": 1,
        "forbidden_terms": [],
    }
    test_id = None
    try:
        with TestClient(app) as client:
            first_response = client.post("/runs", json=request)
            assert first_response.status_code == 200
            first = first_response.json()
            test_id = first["metadata"]["test_id"]
            assert first["metadata"]["test_version"] == 1
            assert first["metadata"]["test_name"] == "JSON check"

            # Identical rules and prompt, different run configuration.
            repeat_response = client.post(
                "/runs", json={**request, "test_id": test_id, "temperature": 0.7}
            )
            assert repeat_response.status_code == 200
            repeat = repeat_response.json()
            assert repeat["metadata"]["test_version"] == 1

            revised_response = client.post(
                "/runs", json={**request, "test_id": test_id, "expected_keywords": ["metadata"]}
            )
            assert revised_response.status_code == 200
            revised = revised_response.json()
            assert revised["metadata"]["test_version"] == 2

            renamed_response = client.post(
                "/runs",
                json={
                    **request,
                    "test_id": test_id,
                    "test_name": "JSON check revised",
                    "expected_keywords": ["metadata"],
                },
            )
            assert renamed_response.status_code == 200
            renamed = renamed_response.json()
            assert renamed["metadata"]["test_version"] == 3
            assert renamed["metadata"]["test_name"] == "JSON check revised"

            # Loading the first version from history should rerun that version,
            # even after later revisions exist.
            old_version_response = client.post(
                "/runs", json={**request, "test_id": test_id, "test_version": 1}
            )
            assert old_version_response.status_code == 200
            old_version = old_version_response.json()
            assert old_version["metadata"]["test_version"] == 1
            assert old_version["metadata"]["test_name"] == "JSON check"

        # A fresh repository/client session reads PostgreSQL rather than React state.
        with TestClient(app) as reloaded_client:
            history_response = reloaded_client.get("/runs?limit=20")
            assert history_response.status_code == 200
            history = history_response.json()
            saved = {run["id"]: run for run in history}
            for run in [first, repeat, revised, renamed, old_version]:
                assert saved[run["id"]] == run
            assert saved[first["id"]]["metadata"]["test_version"] == 1
            assert saved[revised["id"]]["metadata"]["test_version"] == 2
            assert saved[renamed["id"]]["metadata"]["test_version"] == 3

            unknown = reloaded_client.post(
                "/runs", json={**request, "test_id": f"missing_{uuid4().hex}"}
            )
            assert unknown.status_code == 404
    finally:
        if test_id is not None:
            _clean_test(test_id)


def test_imported_run_can_be_displayed_in_history() -> None:
    from app.models import Model
    from app.models import Test as TestDefinition
    from app.models import TestVersion as Version
    from app.repositories.runs import save_run_result

    test_id = f"imported_{uuid4().hex}"
    model_id = f"imported_model_{uuid4().hex}"
    run_id = f"imported_run_{uuid4().hex}"
    try:
        with SessionLocal.begin() as session:
            session.add_all(
                [
                    TestDefinition(id=test_id, name="Imported JSON check"),
                    Model(id=model_id, name="imported-model"),
                ]
            )
            session.flush()
            session.add(
                Version(
                    test_id=test_id,
                    version=1,
                    name="Imported JSON check",
                    prompt="Return JSON",
                    evaluation_definition={"method": "valid_json"},
                )
            )
            session.flush()
            save_run_result(
                session,
                {
                    "run_id": run_id,
                    "test_id": test_id,
                    "test_version": 1,
                    "model": {"model_id": model_id, "name": "imported-model"},
                    "status": "completed",
                    "configuration": {"temperature": 0.0},
                    "input": {"prompt": "Return JSON"},
                    "response": {"content": '{"ok":true}'},
                    "evaluations": [{"method": "valid_json", "passed": True, "score": 1.0}],
                    "metrics": {"latency_ms": 23, "input_tokens": 2, "output_tokens": 3},
                    "started_at": "2026-09-19T18:00:00+00:00",
                    "completed_at": "2026-09-19T18:00:01+00:00",
                    "error": None,
                },
            )
        result = PostgresResultRepository(SessionLocal).recent(limit=100)
        imported = next(row for row in result if row["id"] == run_id)
        assert imported["score"] == 100
        assert imported["metadata"]["schema_version"] == "imported"
        assert imported["metadata"]["test_name"] == "Imported JSON check"
        assert "test_id" not in imported["metadata"]
    finally:
        _clean_test(test_id)
        with SessionLocal.begin() as session:
            session.execute(delete(Model).where(Model.id == model_id))
