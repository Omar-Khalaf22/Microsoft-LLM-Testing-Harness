"""S-01.2/TC-01.2 and prompt-snapshot coverage for S-06.1/TC-06.1.

Use a migrated disposable PostgreSQL database, as with the existing persistence
suite. Model requests use DemoProvider; only test-owned test/version/run rows
are removed. The separate-process case verifies process-independent persistence.
"""

import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.assistant import prompts
from app.database import SessionLocal
from app.evaluation.executor import TestExecutor as Executor
from app.evaluation.models import TestRequest as EvaluationRequest
from app.evaluation.providers import DemoProvider
from app.evaluation.repository import JsonResultRepository
from app.models import Model, TestRun, TestVersion
from app.models import Test as SavedTest
from app.repositories import prototype_runs
from app.repositories.prototype_runs import PostgresResultRepository
from app.repositories.runs import get_run_result, save_run_result
from app.routes import runs


@pytest.fixture
def harness():
    name = f"P2 prompt persistence {uuid4().hex}"
    repository = PostgresResultRepository(SessionLocal)
    request = {
        "test_name": name,
        "prompt": "Explain JSON testing and configuration history.",
        "model": "demo-strong-v1",
        "temperature": 0.2,
        "expected_keywords": ["JSON"],
        "minimum_length": 10,
        "minimum_sentences": 1,
        "forbidden_terms": [],
        "base_system_prompt": "Be precise.",
        "custom_system_prompt": "Use concise sentences.",
    }
    app = FastAPI()
    app.include_router(runs.router)
    app.dependency_overrides[runs.get_executor] = lambda: Executor(DemoProvider(), repository)
    app.dependency_overrides[runs.get_result_repository] = lambda: repository
    try:
        with TestClient(app) as client:
            yield client, request, repository
    finally:
        with SessionLocal.begin() as session:
            test_ids = select(SavedTest.id).where(SavedTest.name == name)
            version_ids = select(TestVersion.id).where(TestVersion.test_id.in_(test_ids))
            session.execute(delete(TestRun).where(TestRun.test_version_id.in_(version_ids)))
            session.execute(delete(TestVersion).where(TestVersion.test_id.in_(test_ids)))
            session.execute(delete(SavedTest).where(SavedTest.name == name))


def _post(client, request):
    response = client.post("/runs", json=request)
    assert response.status_code == 200, response.text
    assert "passed" not in response.json()
    return response.json()


def _snapshot(run_id):
    with SessionLocal() as session:
        result = get_run_result(session, run_id)
    assert result is not None
    return result


def _version(test_id, number):
    with SessionLocal() as session:
        version = session.scalar(
            select(TestVersion).where(TestVersion.test_id == test_id, TestVersion.version == number)
        )
        assert version is not None
        return version.evaluation_definition


@pytest.mark.parametrize("field", ["base_system_prompt", "custom_system_prompt"])
def test_tc_01_2_changed_instructions_create_version_and_preserve_old_run(harness, field):
    client, request, _ = harness
    first = _post(client, request)
    test_id = first["metadata"]["test_id"]
    original_snapshot = _snapshot(first["id"])
    assert "passed" not in original_snapshot["configuration"]
    original_definition = _version(test_id, 1)

    revised = _post(client, {**request, "test_id": test_id, field: "Use different instructions."})
    assert revised["metadata"]["test_version"] == 2
    assert first["id"] != revised["id"]
    assert _snapshot(first["id"]) == original_snapshot
    assert _version(test_id, 1) == original_definition
    captured = _version(test_id, 2)["system_prompt_configuration"]
    for key in prototype_runs.SYSTEM_PROMPT_FIELDS:
        assert captured[key] == revised["metadata"][key]

    # Explicitly supplying the original configuration can reuse the old version.
    repeated = _post(client, {**request, "test_id": test_id, "test_version": 1})
    assert repeated["metadata"]["test_version"] == 1
    assert len({first["id"], revised["id"], repeated["id"]}) == 3
    assert _snapshot(first["id"]) == original_snapshot


def test_tc_01_2_identical_prompts_and_changed_execution_settings_reuse_version(harness):
    client, request, _ = harness
    first = _post(client, request)
    test_id = first["metadata"]["test_id"]
    repeated = _post(client, {**request, "test_id": test_id})
    changed_settings = _post(
        client, {**request, "test_id": test_id, "model": "demo-partial-v1", "temperature": 0.7}
    )
    assert {row["metadata"]["test_version"] for row in [first, repeated, changed_settings]} == {1}
    assert len({row["id"] for row in [first, repeated, changed_settings]}) == 3
    assert _snapshot(first["id"])["configuration"]["temperature"] == 0.2
    assert _snapshot(changed_settings["id"])["configuration"]["temperature"] == 0.7


def test_changed_effective_default_is_versioned_without_rewriting_earlier_defaults(
    harness, monkeypatch
):
    client, request, _ = harness
    request = {**request, "base_system_prompt": None, "custom_system_prompt": None}
    first = _post(client, request)
    original_snapshot = _snapshot(first["id"])
    original_prompt = first["metadata"]["resolved_system_prompt"]
    monkeypatch.setattr(prompts, "DEFAULT_SYSTEM_PROMPT", "A later default instruction.")
    revised = _post(client, {**request, "test_id": first["metadata"]["test_id"]})
    assert revised["metadata"]["test_version"] == 2
    assert revised["metadata"]["resolved_system_prompt"] == "A later default instruction."
    assert original_prompt != revised["metadata"]["resolved_system_prompt"]
    assert _snapshot(first["id"]) == original_snapshot


def test_submitted_and_resolved_instruction_text_are_both_preserved(harness):
    client, request, _ = harness
    request = {
        **request,
        "base_system_prompt": "  Be precise.\n",
        "custom_system_prompt": "  Describe café data.\t",
    }
    first = _post(client, request)
    captured = _version(first["metadata"]["test_id"], 1)["system_prompt_configuration"]
    assert captured["base_system_prompt"] == request["base_system_prompt"]
    assert captured["custom_system_prompt"] == request["custom_system_prompt"]
    assert captured["resolved_system_prompt"] == (
        "Be precise.\n\nAdditional instructions:\nDescribe café data."
    )
    revised = _post(
        client,
        {
            **request,
            "test_id": first["metadata"]["test_id"],
            "base_system_prompt": "Be precise.",
        },
    )
    # A different submitted configuration gets a new version, even when the
    # existing provider's whitespace normalization produces identical messages.
    assert revised["metadata"]["test_version"] == 2
    assert revised["metadata"]["resolved_system_prompt"] == captured["resolved_system_prompt"]


def test_legacy_instruction_configuration_stays_unknown_and_is_not_backfilled(harness, tmp_path):
    client, request, _ = harness
    # Build a synthetic older result, then seed it without the fields that the
    # historical implementation did not capture. No existing row is rewritten.
    legacy = Executor(DemoProvider(), JsonResultRepository(tmp_path / "legacy.jsonl")).execute(
        EvaluationRequest(**request)
    )
    test_id = f"legacy_prompt_{uuid4().hex}"
    metadata = {
        key: value
        for key, value in legacy.metadata.items()
        if key not in prototype_runs.SYSTEM_PROMPT_FIELDS
    }
    metadata.update(test_id=test_id, test_version=1, test_name=request["test_name"])
    definition = {
        key: metadata[key]
        for key in (
            "expected_keywords",
            "minimum_length",
            "minimum_sentences",
            "forbidden_terms",
            "scoring_weights",
        )
    }
    with SessionLocal.begin() as session:
        session.add(SavedTest(id=test_id, name=request["test_name"]))
        if session.get(Model, legacy.model) is None:
            session.add(Model(id=legacy.model, name=legacy.model))
        session.flush()
        session.add(
            TestVersion(
                test_id=test_id,
                version=1,
                name=request["test_name"],
                prompt=legacy.prompt,
                evaluation_definition=definition,
            )
        )
        session.flush()
        save_run_result(
            session,
            {
                "run_id": legacy.id,
                "test_id": test_id,
                "test_version": 1,
                "model": {"model_id": legacy.model, "name": legacy.model},
                "status": legacy.status,
                "configuration": {
                    "temperature": metadata["temperature"],
                    "provider": legacy.provider,
                    "overall_score": legacy.score,
                    # Historical fixture only: current views ignore this label.
                    "passed": False,
                    "metadata": metadata,
                },
                "input": {"prompt": legacy.prompt},
                "response": {"content": legacy.response},
                "evaluations": [
                    {
                        "method": item.name,
                        "passed": item.passed,
                        "score": item.score / 100,
                        "details": {"detail": item.detail},
                    }
                    for item in legacy.criteria
                ],
                "metrics": {"latency_ms": legacy.latency_ms},
                "started_at": metadata["started_at"],
                "completed_at": legacy.created_at,
                "error": None,
            },
        )
    original = _snapshot(legacy.id)
    revised = _post(client, {**request, "test_id": test_id, "test_version": 1})
    assert revised["metadata"]["test_version"] == 2
    assert _version(test_id, 1) == definition
    assert "system_prompt_configuration" not in _version(test_id, 1)
    assert _snapshot(legacy.id) == original
    history = client.get("/runs?limit=100").json()
    old = next(row for row in history if row["id"] == legacy.id)
    assert all(field not in old["metadata"] for field in prototype_runs.SYSTEM_PROMPT_FIELDS)
    assert "passed" not in old
    assert old["score"] == legacy.score
    assert _snapshot(legacy.id)["configuration"]["passed"] is False


def test_new_version_and_run_roll_back_together_on_repository_write_error(harness, monkeypatch):
    client, request, _ = harness
    first = _post(client, request)
    original = _snapshot(first["id"])
    test_id = first["metadata"]["test_id"]

    def fail_write(*args, **kwargs):
        raise RuntimeError("Injected repository write failure")

    monkeypatch.setattr(prototype_runs, "save_run_result", fail_write)
    failed = client.post(
        "/runs", json={**request, "test_id": test_id, "custom_system_prompt": "Changed"}
    )
    assert failed.status_code == 500
    with SessionLocal() as session:
        versions = session.scalars(select(TestVersion).where(TestVersion.test_id == test_id)).all()
        assert len(versions) == 1
        saved_runs = session.scalars(
            select(TestRun).where(TestRun.test_version_id == versions[0].id)
        ).all()
        assert [run.id for run in saved_runs] == [first["id"]]
    assert _snapshot(first["id"]) == original


def test_concurrent_instruction_edits_get_distinct_sequential_versions(harness):
    client, request, repository = harness
    first = _post(client, request)
    test_id = first["metadata"]["test_id"]
    barrier = Barrier(2)

    def run(label):
        barrier.wait(timeout=10)
        return Executor(DemoProvider(), repository).execute(
            EvaluationRequest(**{**request, "test_id": test_id, "custom_system_prompt": label})
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, ["First concurrent edit", "Second concurrent edit"]))
    assert {result.metadata["test_version"] for result in results} == {2, 3}
    for result in results:
        version = _version(test_id, result.metadata["test_version"])
        assert (
            version["system_prompt_configuration"]["custom_system_prompt"]
            == (result.metadata["custom_system_prompt"])
        )
    assert (
        _version(test_id, 1)["system_prompt_configuration"]["custom_system_prompt"]
        == (request["custom_system_prompt"])
    )


_PROCESS_WRITER = """
import json, sys
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.database import SessionLocal
from app.evaluation.executor import TestExecutor
from app.evaluation.providers import DemoProvider
from app.repositories.prototype_runs import PostgresResultRepository
from app.repositories.runs import get_run_result
from app.routes import runs
repository = PostgresResultRepository(SessionLocal)
app = FastAPI()
app.include_router(runs.router)
app.dependency_overrides[runs.get_executor] = lambda: TestExecutor(DemoProvider(), repository)
with TestClient(app) as client:
    response = client.post('/runs', json=json.loads(sys.argv[1]))
    assert response.status_code == 200, response.text
    result = response.json()
with SessionLocal() as session:
    snapshot = get_run_result(session, result['id'])
print(json.dumps(snapshot))
"""

_PROCESS_READER = """
import json, sys
from app.database import SessionLocal
from app.repositories.runs import get_run_result
with SessionLocal() as session:
    snapshot = get_run_result(session, sys.argv[1])
print(json.dumps(snapshot))
"""


def _run_process(script, argument):
    result = subprocess.run(
        [sys.executable, "-c", script, argument],
        cwd=Path(__file__).resolve().parents[1],
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    return json.loads(result.stdout)


def test_tc_06_1_snapshot_survives_application_process_restart(harness):
    _, request, _ = harness
    # The writer process exits before a different interpreter retrieves the run.
    # Nothing from its API client, repository, or SQL session is kept in memory.
    written = _run_process(_PROCESS_WRITER, json.dumps(request))
    reloaded = _run_process(_PROCESS_READER, written["run_id"])
    assert reloaded == written
    assert (
        reloaded["configuration"]["metadata"]["base_system_prompt"]
        == (request["base_system_prompt"])
    )
    assert (
        reloaded["configuration"]["metadata"]["custom_system_prompt"]
        == (request["custom_system_prompt"])
    )
