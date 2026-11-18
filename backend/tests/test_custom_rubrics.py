"""Saved workflow acceptance over the normal API and PostgreSQL storage."""

import io
import json
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
from threading import Event
from time import monotonic, sleep
from uuid import uuid4

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine, select, text, update
from sqlalchemy.orm import sessionmaker

from alembic import command
from app.config import TargetProfile, get_settings
from app.database import SessionLocal, get_db
from app.evaluation import providers
from app.evaluation.interpretation import PREVIEW_INSTRUCTIONS
from app.evaluation.providers import DemoProvider, ProviderResponse
from app.main import app
from app.models import ModelResponse
from app.models import TestRun as Run
from app.routes import assistant, runs, saved
from app.services import execution_coordinator as coordinator
from app.storage.access import AccessContext, Principal, get_access
from app.storage.executions import claim_attempt, now

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"
DEMO = json.loads((EXAMPLES / "custom-rubrics-demo.json").read_text(encoding="utf-8"))


@pytest.fixture
def workflow(access, monkeypatch):
    settings = get_settings().model_copy(
        update={
            "project_id": access.project_id,
            "llm_provider": "demo",
            "target_profiles": [],
            "assistant_enabled": False,
        }
    )
    monkeypatch.setitem(app.dependency_overrides, get_access, lambda: access)
    monkeypatch.setattr(saved, "get_settings", lambda: settings)
    monkeypatch.setattr(assistant, "get_settings", lambda: settings)
    return TestClient(app), settings


def success(response, status):
    assert response.status_code == status, response.text
    return response.json()


def ref(version):
    return {key: version[key] for key in ("test_id", "test_version")}


def version_path(version):
    return f"/tests/{version['test_id']}/versions/{version['test_version']}"


def approve(client, definition):
    draft = success(client.post("/tests", json=definition), 201)
    approved = success(client.post(version_path(draft) + "/approve"), 201)
    assert approved["state"] == "approved"
    return approved


def reserve(client, *, test=None, suite=None, profiles=None, **options):
    selection = {"test": ref(test)} if test else {"suite": suite}
    return client.post(
        "/executions",
        json={
            **selection,
            "profile_ids": profiles or ["demo-outlook-a"],
            "idempotency_key": uuid4().hex,
            **options,
        },
    )


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"criterion_id": "custom_invalid"}, "32 lowercase hex digits"),
        (
            {"criterion_id": DEMO["outlook"]["definition"]["criteria"][1]["criterion_id"]},
            "only once",
        ),
        ({"method": "custom_rubric_v999"}, "Unsupported custom evaluator"),
        ({"weight": 39.99}, "exactly 100.00"),
        ({"weight": 40.01}, "exactly 100.00"),
        ({"weight": 40.001}, "two decimal places"),
        ({"weight": True}, "finite JSON numbers"),
        ({"weight": 0}, "must be positive"),
        ({"parameters": {"title": "", "instructions": "rules"}}, "at least 1 character"),
        (
            {"parameters": {"title": "Fact", "instructions": "rules", "requires_reference": True}},
            "reference evidence",
        ),
        ({"parameters": {"title": "Large", "instructions": "x" * 6001}}, "at most 6000"),
        (
            {
                "parameters": {
                    "title": "Large",
                    "instructions": "rules",
                    "reference_evidence": "x" * 10001,
                }
            },
            "at most 10000",
        ),
    ],
)
def test_invalid_drafts(workflow, change, message):
    client, _ = workflow
    definition = deepcopy(DEMO["outlook"]["definition"])
    definition["criteria"][0].update(change)
    result = success(client.post("/tests", json=definition), 422)
    assert message in str(result["detail"])
    assert all("input" not in e for e in result["detail"])


def test_draft_approval_versioning_and_assist_off(workflow):
    client, settings = workflow
    definition = deepcopy(DEMO["outlook"]["definition"])
    assert (
        client.post(
            "/assistant/suggest-criteria",
            json={
                "objective": definition["objective"],
                "prompt": definition["prompt"],
            },
        ).status_code
        == 503
    )
    draft = success(client.post("/tests", json=definition), 201)
    assert draft["state"] == "draft"
    assert (
        success(client.get(version_path(draft)), 200)["definition"]["criteria"]
        == definition["criteria"]
    )
    assert reserve(client, test=draft).status_code == 409
    assert (
        client.post(
            "/runs",
            json={
                "test_name": definition["name"],
                "prompt": definition["prompt"],
                "criteria": definition["criteria"],
                "configuration_state": "approved",
            },
        ).status_code
        == 422
    )
    edited = deepcopy(definition)
    edited["criteria"][0]["parameters"]["instructions"] += " Include explicit impact."
    update_body = {"expected_version": 1, "definition": edited}
    versions_path = version_path(draft).rsplit("/", 1)[0]
    newer = success(client.post(versions_path, json=update_body), 201)
    assert client.post(versions_path, json=update_body).status_code == 409
    assert client.post(version_path(draft) + "/approve").status_code == 409
    approved = success(client.post(version_path(newer) + "/approve"), 201)
    assert approved["test_version"] == 3
    assert approved["definition"]["criteria"] == edited["criteria"]
    assert (
        success(client.get(version_path(draft)), 200)["definition"]["criteria"]
        == definition["criteria"]
    )
    assert not coordinator.dispatch_next(settings)


def test_preview_confirm_retry_privacy_and_exact_rerun(workflow, monkeypatch):
    client, settings = workflow
    settings.llm_provider = "openai"
    settings.openai_api_key = SecretStr("test-transport-only")
    settings.target_profiles = [
        TargetProfile(profile_id=p, model=p, temperature=0.2)
        for p in ("test-target-a", "test-target-b")
    ]
    settings.judge_model, settings.judge_profile_id = "test-judge", "judge-profile"
    public_task = "Return a JSON list using the target task materials."
    public_instructions = "Target-facing material."
    private_expected = "PRIVATE_BUILTIN_VALUE"
    answer = json.dumps([private_expected])
    recorded = []

    def fake_transport(request, timeout):
        payload = json.loads(request.data)
        recorded.append(payload)
        system, user = [m["content"] for m in payload["messages"]]
        if system == PREVIEW_INSTRUCTIONS:
            if len(recorded) == 1:
                output = "broken preview"
            else:
                output = json.dumps(
                    {
                        "purpose": "Test JSON",
                        "deliverable": "A list",
                        "constraints": "Follow instructions",
                        "success_conditions": "Valid JSON",
                    }
                )
        elif payload["model"] == "test-judge":
            with SessionLocal() as session:
                assert (
                    session.scalar(
                        select(ModelResponse.content)
                        .join(Run)
                        .where(Run.project_id == settings.project_id, Run.status == "running")
                    )
                    == answer
                )
            grade = json.loads(user)
            assert grade["response"] == answer
            assert grade["rubric"]["scoring_rules"]
            assert grade["task"]["prompt"] == public_task
            assert grade["task"]["instructions"] == public_instructions
            factual = grade["rubric"]["requires_reference"]
            output = json.dumps(
                {
                    "score": 0 if factual else 0.123456789123,
                    "rationale": "A valid separate judgment.",
                    "evidence": [
                        {
                            "source": "reference" if factual else "answer",
                            "excerpt": "PRIVATE_CUSTOM_PACKET" if factual else private_expected,
                        }
                    ],
                }
            )
        else:
            output = answer
        return io.BytesIO(
            json.dumps(
                {
                    "model": payload["model"] + "-reported",
                    "usage": {"prompt_tokens": 3, "completion_tokens": 4},
                    "choices": [{"message": {"content": output}}],
                }
            ).encode()
        )

    monkeypatch.setattr(providers, "urlopen", fake_transport)
    rows = deepcopy(DEMO["outlook"]["definition"]["criteria"][:2])
    rows[0]["parameters"]["reference_evidence"] = "PRIVATE_CUSTOM_PACKET"
    rows[1]["parameters"].update(reference_evidence="", requires_reference=False)
    rows.append(
        {
            "criterion_id": "json_schema",
            "weight": 25,
            "parameters": {"schema": {"type": "array", "contains": {"const": private_expected}}},
        }
    )
    definition = {
        "name": "Mixed private rubric",
        "objective": "PRIVATE_OBJECTIVE",
        "prompt": public_task,
        "base_system_prompt": public_instructions,
        "criteria": rows,
    }
    approved = approve(client, definition)
    profile = "test-target-a"
    preview_body = {"test": ref(approved), "profile_id": profile}
    failed = success(client.post("/previews", json=preview_body), 201)
    assert failed["error_category"] == "invalid_response"
    bad_choice = {"1:1": {"preview_id": failed["preview_id"], "confirmed": True}}
    assert (
        reserve(client, test=approved, profiles=[profile], previews=bad_choice).status_code == 409
    )
    acknowledged = {"1:1": {"preview_id": failed["preview_id"], "acknowledge_error": True}}
    ack = success(reserve(client, test=approved, profiles=[profile], previews=acknowledged), 202)
    assert coordinator.dispatch_next(settings)
    good = success(client.post("/previews", json=preview_body), 201)
    assert good["status"] == "completed"
    assert (
        reserve(
            client,
            test=approved,
            profiles=[profile],
            previews={"1:1": {"preview_id": good["preview_id"]}},
        ).status_code
        == 422
    )
    confirmed = {"1:1": {"preview_id": good["preview_id"], "confirmed": True}}
    assert (
        reserve(client, test=approved, profiles=["test-target-b"], previews=confirmed).status_code
        == 409
    )
    idem = uuid4().hex
    plan = success(
        reserve(
            client, test=approved, profiles=[profile], previews=confirmed, idempotency_key=idem
        ),
        202,
    )
    repeat = success(
        reserve(
            client, test=approved, profiles=[profile], previews=confirmed, idempotency_key=idem
        ),
        202,
    )
    assert plan["execution_id"] == repeat["execution_id"] != ack["execution_id"]
    assert plan["attempts"] == repeat["attempts"]
    assert (
        reserve(client, test=approved, profiles=["test-target-b"], idempotency_key=idem).status_code
        == 409
    )
    assert coordinator.dispatch_next(settings)
    run_id = plan["attempts"][0]["run_id"]
    result = success(client.get(f"/runs/{run_id}"), 200)
    assert result["score"] == 29.32
    assert [r["score"] for r in result["criteria"]] == [0, 4.32, 25]
    assert [r["criterion_id"] for r in result["criteria"]] == [r["criterion_id"] for r in rows]
    assert result["criteria"][0]["evidence_excerpts"][0]["source"] == "reference"
    assert result["criteria"][1]["evidence_excerpts"][0]["source"] == "answer"
    assert result["criteria"][0]["status"] == "completed"
    assert result["metadata"]["judge_profile_id"] == "judge-profile"
    assert result["metadata"]["provider_reported_model"] == "test-target-a-reported"
    assert (
        result["metadata"]["evaluation_metrics"]["judge_calls"][0]["actual_model"]
        == "test-judge-reported"
    )
    saved_bundle = success(client.post("/evidence/export", json={"run_ids": [run_id]}), 200)
    assert (
        saved_bundle["runs"][0]["configuration"]["result_snapshot"]["criteria"][1][
            "normalized_score"
        ]
        == 0.123456789123
    )

    edited = deepcopy(definition)
    edited["criteria"][0]["parameters"]["title"] = "A changed title"
    draft = success(
        client.post(
            version_path(approved).rsplit("/", 1)[0],
            json={"definition": edited, "expected_version": approved["test_version"]},
        ),
        201,
    )
    later = success(client.post(version_path(draft) + "/approve"), 201)
    assert reserve(client, test=later, profiles=[profile], previews=confirmed).status_code == 409
    rerun = success(
        client.post(f"/runs/{run_id}/rerun", json={"idempotency_key": uuid4().hex}), 202
    )
    assert coordinator.dispatch_next(settings)
    rerun_id = rerun["attempts"][0]["run_id"]
    again = success(client.get(f"/runs/{rerun_id}"), 200)
    assert again["metadata"]["test_version"] == approved["test_version"]
    assert again["metadata"]["rerun_of_run_id"] == run_id
    assert again["criteria"] == result["criteria"]
    assert success(client.get(f"/runs/{run_id}"), 200) == result

    target_calls = [p for p in recorded if p["model"] != "test-judge"]
    assert len(target_calls) == 5
    for payload in target_calls:
        serialized = json.dumps(payload)
        assert all(
            secret not in serialized
            for secret in (
                private_expected,
                "PRIVATE_CUSTOM_PACKET",
                "PRIVATE_OBJECTIVE",
                "scoring_rules",
                "rationale",
            )
        )
        assert payload["temperature"] == 0.2
        system, user = [m["content"] for m in payload["messages"]]
        if system == PREVIEW_INSTRUCTIONS:
            assert json.loads(user) == {
                "task_prompt": public_task,
                "task_instructions": public_instructions,
            }
        else:
            assert (system, user) == (public_instructions, public_task)


@pytest.mark.parametrize("failure", ["malformed", "range", "provider", "wrong-source"])
def test_partial_evidence_in_ordered_suite(workflow, monkeypatch, failure):
    client, settings = workflow
    outlook = approve(client, DEMO["outlook"]["definition"])
    built_in = approve(
        client,
        {
            "name": "Built-in only",
            "prompt": "Return some text.",
            "criteria": [
                {"criterion_id": "minimum_characters", "parameters": {"count": 1}, "weight": 100}
            ],
        },
    )
    suite = success(
        client.post(
            "/suites",
            json={
                "name": "Two pinned items",
                "items": [ref(outlook), ref(built_in)],
            },
        ),
        201,
    )

    class Judge(providers.DemoJudgeProvider):
        def generate(self, prompt, model, temperature, system_prompt):
            if json.loads(prompt)["rubric"]["title"] == "Support for major claims":
                if failure == "provider":
                    raise RuntimeError("private provider exception")
                malformed = {
                    "malformed": "not json",
                    "range": '{"score":1.001,"rationale":"Bad range","evidence":[]}',
                    "wrong-source": json.dumps(
                        {
                            "score": 1,
                            "rationale": "Bad source",
                            "evidence": [
                                {
                                    "source": "reference",
                                    "excerpt": DEMO["outlook"]["cases"][0]["answer"],
                                }
                            ],
                        }
                    ),
                }
                return ProviderResponse(malformed[failure], model, {})
            return super().generate(prompt, model, temperature, system_prompt)

    monkeypatch.setattr(
        coordinator,
        "judge_context",
        lambda _: {
            "judge_provider": Judge(),
            "judge_model": "test-judge",
        },
    )
    plan = success(
        reserve(client, suite={k: suite[k] for k in ("suite_id", "suite_revision")}), 202
    )
    assert [a["suite_position"] for a in plan["attempts"]] == [1, 2]
    assert plan["progress"]["pending"] == 2
    assert coordinator.dispatch_next(settings)
    assert coordinator.dispatch_next(settings)
    finished = success(client.get(f"/executions/{plan['execution_id']}"), 200)
    assert finished["progress"] == {"pending": 0, "running": 0, "completed": 1, "failed": 1}
    failed, completed = [success(client.get(f"/runs/{a['run_id']}"), 200) for a in plan["attempts"]]
    assert failed["error"]["code"] == "evaluation_incomplete"
    assert failed["response"] == DEMO["outlook"]["cases"][0]["answer"]
    assert failed["score"] is None
    assert [row["score"] for row in failed["criteria"]] == [30, None, 10]
    assert failed["criteria"][0]["evidence_excerpts"]
    assert failed["criteria"][1]["status"] == "error"
    assert completed["score"] == 100
    bundle = success(client.post("/evidence/export", json={"run_ids": [failed["id"]]}), 200)
    assert len(bundle["runs"]) == 2


def test_target_failure_and_lease_recovery(workflow, access, monkeypatch):
    client, settings = workflow
    approved = approve(client, DEMO["outlook"]["definition"])
    plan = success(reserve(client, test=approved), 202)
    run_id = plan["attempts"][0]["run_id"]
    entered, release = Event(), Event()

    class FailingTarget(DemoProvider):
        def generate(self, *args, **kwargs):
            entered.set()
            release.wait(5)
            raise RuntimeError("target failed")

    monkeypatch.setattr(coordinator, "target_provider", lambda *_: FailingTarget())
    monkeypatch.setattr(coordinator, "HEARTBEAT_SECONDS", 0.01)

    def lease():
        with SessionLocal() as session:
            return session.get(Run, run_id).lease_until

    with ThreadPoolExecutor(max_workers=1) as pool:
        worker = pool.submit(coordinator.dispatch_next, settings)
        try:
            assert entered.wait(5)
            initial_lease = lease()
            until = monotonic() + 3
            while lease() <= initial_lease and monotonic() < until:
                sleep(0.03)
            assert lease() > initial_lease
            assert not coordinator.dispatch_next(settings)
        finally:
            release.set()
        assert worker.result(timeout=5)
    result = success(client.get(f"/runs/{run_id}"), 200)
    assert result["error"]["code"] == "provider_failure"
    assert result["score"] is None and result["response"] == ""

    orphan = success(reserve(client, test=approved), 202)["attempts"][0]["run_id"]
    with SessionLocal.begin() as session:
        claim_attempt(session, access, orphan)
        session.execute(
            update(Run)
            .where(Run.id == orphan)
            .values(lease_until=now(session) - timedelta(seconds=1))
        )
    entered.clear()
    assert coordinator.dispatch_next(settings)
    assert not entered.is_set()
    result = success(client.get(f"/runs/{orphan}"), 200)
    assert result["status"] == "failed" and result["error"]["code"] == "interrupted"
    assert result["metadata"]["execution_id"]


def test_mining_fixture_membership_and_uniqueness(workflow):
    client, settings = workflow
    fixture = DEMO["mining"]
    approved = approve(client, fixture["definition"])
    plan = success(
        reserve(client, test=approved, profiles=[c["profile"] for c in fixture["cases"]]), 202
    )
    for attempt, case in zip(plan["attempts"], fixture["cases"], strict=True):
        assert coordinator.dispatch_next(settings)
        run = success(client.get(f"/runs/{attempt['run_id']}"), 200)
        assert run["score"] == case["points"]
        assert json.loads(run["response"]) == case["answer"]
        assert run["criteria"][0]["criterion_id"] == "json_schema"


def test_scoped_history_and_legacy_and_custom_evidence_roundtrip(workflow, access, monkeypatch):
    client, settings = workflow
    approved = approve(client, DEMO["outlook"]["definition"])
    plan = success(reserve(client, test=approved), 202)
    assert coordinator.dispatch_next(settings)
    run_id = plan["attempts"][0]["run_id"]
    result = success(client.get(f"/runs/{run_id}"), 200)
    assert result["score"] == 75
    assert [r["score"] for r in result["criteria"]] == [30, 35, 10]
    success(
        client.post(
            f"/runs/{run_id}/reviews", json={"rating": 83, "rationale": "Separate review."}
        ),
        201,
    )
    bundle = success(client.post("/evidence/export", json={"run_ids": [run_id]}), 200)
    other = AccessContext(Principal("other", "workspace_" + uuid4().hex))
    monkeypatch.setitem(app.dependency_overrides, get_access, lambda: other)
    assert client.get(version_path(approved)).status_code == 404
    assert client.get(f"/runs/{run_id}").status_code == 404
    assert client.get(f"/executions/{plan['execution_id']}").status_code == 404
    assert client.get(f"/runs/{run_id}/reviews").status_code == 404
    assert client.post("/evidence/export", json={"run_ids": [run_id]}).status_code == 404
    assert success(client.get("/history/runs"), 200)["items"] == []

    schema = "custom_import_" + uuid4().hex
    with SessionLocal.begin() as session:
        session.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(
        settings.database_url, connect_args={"options": f"-csearch_path={schema}"}
    )
    isolated = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    try:
        with engine.begin() as connection:
            config = Config("alembic.ini")
            config.attributes["connection"] = connection
            command.upgrade(config, "head")

        def imported_db():
            with isolated() as session:
                yield session

        monkeypatch.setitem(app.dependency_overrides, get_db, imported_db)
        monkeypatch.setattr(runs, "SessionLocal", isolated)
        legacy = json.loads((EXAMPLES / "prototype3-evidence-4.0.json").read_text(encoding="utf-8"))
        success(client.post("/evidence/import", json=legacy), 201)
        archived = success(client.get(f"/runs/{legacy['runs'][0]['run_id']}"), 200)
        assert archived["criteria"][0]["criterion_id"] == "valid_json"
        altered = deepcopy(bundle)
        snapshot = altered["runs"][0]["configuration"]["result_snapshot"]
        snapshot["metadata"]["criteria"][0]["parameters"]["instructions"] = "Changed after the run."
        assert client.post("/evidence/import", json=altered).status_code == 422
        success(client.post("/evidence/import", json=bundle), 201)
        assert success(client.get(f"/runs/{run_id}"), 200) == result
        restored = success(client.post("/evidence/export", json={"run_ids": [run_id]}), 200)
        assert restored["definitions"] == bundle["definitions"]
        assert restored["runs"][0]["evaluations"] == bundle["runs"][0]["evaluations"]
        assert restored["runs"][0]["reviews"][0]["rating"] == 83
        assert client.post("/evidence/import", json=bundle).status_code == 409
    finally:
        engine.dispose()
        with SessionLocal.begin() as session:
            session.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
