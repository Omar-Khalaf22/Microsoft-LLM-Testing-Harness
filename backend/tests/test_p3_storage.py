"""Real PostgreSQL transactions, concurrent callers and persisted API evidence."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError

from app.database import SessionLocal
from app.evaluation.executor import TestExecutor as Executor
from app.evaluation.providers import DemoProvider
from app.models import Execution, HumanReview, ModelResponse
from app.models import TestRun as Run
from app.models import TestVersion as Version
from app.routes import evidence, history, human_reviews, runs
from app.storage.access import AccessContext, Principal, get_access
from app.storage.definitions import (
    create_suite,
    create_test,
    create_test_version,
    get_test_version,
    list_test_versions,
    revise_suite,
)
from app.storage.errors import Conflict, NotFound
from app.storage.executions import (
    claim_attempt,
    create_rerun_plan,
    heartbeat_attempt,
    recover_expired_attempt,
    request_for_attempt,
    reserve_attempts,
    retrieve_execution,
    save_preview,
    save_target_response,
)
from app.storage.executor_adapter import ReservedResultRepository
from app.storage.history import list_history_summaries
from app.storage.records import ProfileSelection, SavedDefinition, TestReference
from app.storage.transfer import EvidenceBundle, export_evidence, import_evidence


@pytest.fixture
def access():
    return AccessContext(Principal("actor", "pytest_" + uuid4().hex))


def definition(**kw):
    return SavedDefinition(
        name="JSON test",
        objective="Return machine readable data",
        prompt="Return JSON with count 3. Preserve  spaces.\n",
        state="approved",
        criteria=[{"criterion_id": "valid_json", "parameters": {}, "weight": 100}],
        **kw,
    )


def profile(**kw):
    return ProfileSelection(
        profile_id="demo",
        profile_revision=1,
        provider="local_demo",
        endpoint_id="demo-endpoint",
        requested_model="demo-json-v1",
        **kw,
    )


def setup(access, *, defn=None):
    with SessionLocal.begin() as s:
        v = create_test(s, access, defn or definition())
        return TestReference(test_id=v.test_id, test_version=v.version)


def reserve(access, ref, **kwargs):
    with SessionLocal.begin() as s:
        return reserve_attempts(s, access, [profile()], test=ref, **kwargs)


def execute(access, run_id, provider=None, judge_context=None):
    with SessionLocal.begin() as s:
        token = claim_attempt(s, access, run_id)
        request = request_for_attempt(s, access, run_id)
    repo = ReservedResultRepository(SessionLocal, access, run_id, token)
    return Executor(provider or DemoProvider(), repo, judge_context=judge_context).execute(request)


def api(access):
    app = FastAPI()
    for router in (history.router, evidence.router, human_reviews.router, runs.router):
        app.include_router(router)
    app.dependency_overrides[get_access] = lambda: access
    return TestClient(app)


def test_saved_before_execution_and_concurrent_expected_version(access):
    ref = setup(access)
    with SessionLocal() as s:
        v = get_test_version(s, access, ref)
        assert v.prompt.endswith("  spaces.\n")
        assert v.evaluation_definition["resolved_system_prompt"]
        assert (
            s.scalar(select(func.count()).select_from(Run).where(Run.test_version_id == v.id)) == 0
        )

    def revise(_):
        try:
            with SessionLocal.begin() as s:
                create_test_version(s, access, ref.test_id, definition(), expected_version=1)
            return "created"
        except Conflict:
            return "stale"

    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(revise, range(2))) == ["created", "stale"]
    with SessionLocal() as s:
        assert [v.version for v in list_test_versions(s, access, ref.test_id)] == [1, 2]
        assert [v.version for v in list_test_versions(s, access, ref.test_id, after_version=1)] == [
            2
        ]
    with SessionLocal.begin() as s:
        v = get_test_version(s, access, ref)
        with pytest.raises(IntegrityError):
            s.execute(update(Version).where(Version.id == v.id).values(prompt="rewritten"))


def test_suite_snapshot_order_duplicate_positions_and_revision_guard(access):
    ref = setup(access)
    with SessionLocal.begin() as s:
        suite = create_suite(s, access, "Repeated exact version", [ref, ref])
        sid = suite.suite_id
        plan = reserve_attempts(s, access, [profile(), profile()], suite_id=sid, suite_revision=1)
    assert [(r["suite_position"], r["model_position"]) for r in plan["attempts"]] == [
        (1, 1),
        (1, 2),
        (2, 1),
        (2, 2),
    ]
    with SessionLocal.begin() as s:
        revise_suite(s, access, sid, "Changed", [ref], expected_revision=1)
    with SessionLocal.begin() as s:
        with pytest.raises(Conflict):
            revise_suite(s, access, sid, "Stale", [ref], expected_revision=1)
    with SessionLocal() as s:
        assert len(s.get(Execution, plan["execution_id"]).snapshot["tests"]) == 2
        assert all(s.get(Run, r["run_id"]).started_at is None for r in plan["attempts"])


def test_idempotent_reservation_concurrency_and_conflicting_request(access):
    ref = setup(access)
    with ThreadPoolExecutor(2) as pool:
        plans = list(pool.map(lambda _: reserve(access, ref, idempotency_key="same"), range(2)))
    assert plans[0] == plans[1]
    with SessionLocal.begin() as s:
        with pytest.raises(Conflict):
            reserve_attempts(s, access, [profile(), profile()], test=ref, idempotency_key="same")


def test_committed_ids_checkpoint_finalize_and_rerun_retains_evidence(access):
    ref = setup(access)
    plan = reserve(access, ref)
    run_id = plan["attempts"][0]["run_id"]

    class ObserveProvider(DemoProvider):
        def generate(self, *args, **kwargs):
            with SessionLocal() as s:
                assert s.get(Run, run_id).status == "running"
                assert s.get(Version, s.get(Run, run_id).test_version_id).version == 1
            return super().generate(*args, **kwargs)

    result = execute(access, run_id, ObserveProvider())
    assert result.id == run_id and result.score == 100
    with SessionLocal() as s:
        assert retrieve_execution(s, access, plan["execution_id"])["status"] == "completed"
        assert s.get(Run, run_id).evidence["target"]["latency_ms"] >= 0
    with api(access) as client:
        first = client.post(
            f"/runs/{run_id}/reviews",
            json={"reviewer_id": "spoof", "rating": 0, "rationale": "Keep response"},
        )
        assert first.status_code == 201, first.text
        assert first.json()["reviewer_id"] == "actor"
        assert client.get(f"/runs/{run_id}").json()["score"] == 100
    with SessionLocal.begin() as s:
        rerun = create_rerun_plan(s, access, run_id)
        new_id = rerun["attempts"][0]["run_id"]
        assert new_id != run_id and s.get(Run, new_id).rerun_of_run_id == run_id
        assert (
            s.scalar(
                select(func.count()).select_from(HumanReview).where(HumanReview.run_id == new_id)
            )
            == 0
        )
    with SessionLocal.begin() as s:
        with pytest.raises(IntegrityError):
            s.execute(update(Run).where(Run.id == run_id).values(error="overwritten"))


def test_claim_guard_live_lease_recovery_and_preserved_response(access):
    ref = setup(access)
    run_id = reserve(access, ref)["attempts"][0]["run_id"]

    def claim(_):
        try:
            with SessionLocal.begin() as s:
                return claim_attempt(s, access, run_id)
        except Conflict:
            return None

    with ThreadPoolExecutor(2) as pool:
        tokens = list(pool.map(claim, range(2)))
    assert sum(t is not None for t in tokens) == 1
    token = next(t for t in tokens if t)
    with SessionLocal.begin() as s:
        heartbeat_attempt(s, access, run_id, token)
        save_target_response(
            s,
            access,
            run_id,
            token,
            content="retained",
            actual_model="demo-json-v1",
            latency_ms=0,
            usage={},
        )
    with SessionLocal.begin() as s:
        with pytest.raises(Conflict):
            recover_expired_attempt(s, access, run_id)
    with SessionLocal.begin() as s:
        # Simulate passage of lease time without sleeping or invoking providers.
        s.execute(
            update(Run)
            .where(Run.id == run_id)
            .values(lease_until=func.now() - timedelta(seconds=1))
        )
    with SessionLocal.begin() as s:
        recover_expired_attempt(s, access, run_id)
    with SessionLocal() as s:
        assert s.get(Run, run_id).error == "interrupted"
        assert (
            s.scalar(select(ModelResponse.content).where(ModelResponse.run_id == run_id))
            == "retained"
        )
    with SessionLocal.begin() as s:
        with pytest.raises(Conflict):
            claim_attempt(s, access, run_id)


def test_judge_failure_retains_target_and_total_null(access):
    defn = SavedDefinition(
        name="Factual",
        prompt="What is 2+2?",
        state="approved",
        criteria=[
            {
                "criterion_id": "factual_accuracy",
                "parameters": {"reference_evidence": "2+2=4"},
                "weight": 100,
            }
        ],
    )
    ref = setup(access, defn=defn)
    run_id = reserve(access, ref)["attempts"][0]["run_id"]

    class BrokenJudge:
        def generate(self, *args, **kwargs):
            with SessionLocal() as s:
                assert s.scalar(select(ModelResponse.content).where(ModelResponse.run_id == run_id))
            raise TimeoutError()

    result = execute(
        access, run_id, judge_context={"judge_provider": BrokenJudge(), "judge_model": "judge"}
    )
    assert result.status == "failed" and result.score is None and result.response
    assert result.criteria[0].score is None


def test_zero_is_completed_and_wrong_result_cannot_finalize(access):
    ref = setup(access)
    run_id = reserve(access, ref)["attempts"][0]["run_id"]
    result = execute(access, run_id, DemoProviderForText("not json"))
    assert result.score == 0 and result.status == "completed"
    with SessionLocal.begin() as s:
        with pytest.raises(Conflict):
            from app.storage.executions import finalize_attempt

            finalize_attempt(s, access, run_id, "stale", replace(result, score=99))


class DemoProviderForText(DemoProvider):
    def __init__(self, text):
        self.text = text

    def generate(self, *args, **kwargs):
        return replace(super().generate(*args, **kwargs), text=self.text)


def test_preview_stale_wrong_model_and_technical_failure_ack(access):
    ref = setup(access)
    with SessionLocal.begin() as s:
        p = save_preview(
            s, access, ref, profile(), status="technical_error", error_category="timeout"
        )
        pid = p.id
    with SessionLocal.begin() as s:
        with pytest.raises(Conflict):
            reserve_attempts(
                s, access, [profile()], test=ref, previews={"1:1": {"preview_id": pid}}
            )
    with SessionLocal.begin() as s:
        plan = reserve_attempts(
            s,
            access,
            [profile()],
            test=ref,
            previews={"1:1": {"preview_id": pid, "acknowledge_error": True}},
        )
        assert plan["attempts"]
    with SessionLocal.begin() as s:
        other = profile().model_copy(update={"profile_revision": 2})
        with pytest.raises(Conflict):
            reserve_attempts(
                s,
                access,
                [other],
                test=ref,
                previews={"1:1": {"preview_id": pid, "acknowledge_error": True}},
            )


def test_history_scope_keyset_malformed_and_summary_excludes_evidence(access):
    ref = setup(access)
    for _ in range(3):
        reserve(access, ref)
    with SessionLocal() as s:
        page = list_history_summaries(s, access, limit=2)
    assert len(page["items"]) == 2 and page["next_cursor"]
    assert not {"prompt", "response", "criteria", "configuration"} & set(page["items"][0])
    reserve(access, ref)
    with SessionLocal() as s:
        next_page = list_history_summaries(s, access, limit=2, cursor=page["next_cursor"])
        assert len(next_page["items"]) == 1
        assert not set(i["id"] for i in next_page["items"]) & {i["id"] for i in page["items"]}
        with pytest.raises(ValueError):
            list_history_summaries(s, access, cursor="bad!")
        other = AccessContext(Principal("other", "other"))
        assert list_history_summaries(s, other)["items"] == []
        with pytest.raises(NotFound):
            get_test_version(s, other, ref)


def test_concurrent_reviews_revision_history_and_missing_run(access):
    run_id = reserve(access, setup(access))["attempts"][0]["run_id"]
    execute(access, run_id)

    def review(rating):
        with api(access) as client:
            r = client.post(
                f"/runs/{run_id}/reviews", json={"rating": rating, "rationale": "Review"}
            )
            assert r.status_code == 201, r.text
            return r.json()["revision"]

    with ThreadPoolExecutor(3) as pool:
        assert sorted(pool.map(review, [1, 2, 3])) == [1, 2, 3]
    with api(access) as client:
        assert len(client.get(f"/runs/{run_id}/reviews").json()) == 3
        assert client.get("/runs/missing/reviews").status_code == 404
        assert client.get(f"/runs/{run_id}").json()["score"] == 100
    with api(AccessContext(Principal("other", "other"))) as client:
        assert client.get(f"/runs/{run_id}/reviews").status_code == 404


def test_strict_export_schema_validation_and_conflict_atomicity(access):
    run_id = reserve(access, setup(access))["attempts"][0]["run_id"]
    execute(access, run_id)
    with SessionLocal() as s:
        bundle = export_evidence(s, access, [run_id])
    payload = bundle.model_dump(mode="json")
    assert EvidenceBundle.model_validate_json(bundle.model_dump_json()).runs[0].run_id == run_id
    with api(access) as client:
        assert client.post("/evidence/import", json=payload).status_code == 409
        assert (
            client.post("/evidence/import", json={**payload, "schema_version": "99"}).status_code
            == 422
        )
        corrupt = bundle.model_dump(mode="json")
        corrupt["runs"][0]["evaluations"][0]["earned_points"] = "101"
        assert client.post("/evidence/import", json=corrupt).status_code == 422
    with SessionLocal() as s:
        assert s.get(Run, run_id).configuration == bundle.runs[0].configuration


def test_actual_roundtrip_into_separate_postgres_schema(access):
    # Separate schema provides a real second database namespace with its own
    # migrations/identity sequences; no mutation of exported originals is needed.
    from alembic.config import Config
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from alembic import command
    from app.config import get_settings

    run_id = reserve(access, setup(access))["attempts"][0]["run_id"]
    execute(access, run_id)
    with api(access) as client:
        client.post(f"/runs/{run_id}/reviews", json={"rating": 87, "rationale": "Human evidence"})
    with SessionLocal() as s:
        bundle = export_evidence(s, access, [run_id])
    schema = "transfer_" + uuid4().hex
    with SessionLocal.begin() as s:
        s.execute(text(f'CREATE SCHEMA "{schema}"'))
    # Alembic accepts PGOPTIONS through a connection URL query parameter.
    engine = create_engine(
        get_settings().database_url, connect_args={"options": f"-csearch_path={schema}"}
    )
    try:
        with engine.begin() as connection:
            config = Config("alembic.ini")
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        factory = sessionmaker(engine, expire_on_commit=False)
        with factory.begin() as s:
            result = import_evidence(s, access, bundle)
            assert result["imported_run_ids"] == [run_id]
        with factory() as s:
            again = export_evidence(s, access, [run_id])
            assert again.runs[0].response == bundle.runs[0].response
            assert again.runs[0].evaluations == bundle.runs[0].evaluations
            assert again.runs[0].reviews[0].reviewer_id == "actor"
            assert again.runs[0].reviews[0].attribution["imported_by"] == "actor"
    finally:
        engine.dispose()
        with SessionLocal.begin() as s:
            s.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))


def test_mixed_execution_retains_successful_sibling_after_provider_failure(access):
    ref = setup(access)
    with SessionLocal.begin() as s:
        plan = reserve_attempts(s, access, [profile(), profile()], test=ref)
    good, bad = [a["run_id"] for a in plan["attempts"]]
    execute(access, good)

    class Unavailable(DemoProvider):
        def generate(self, *args, **kwargs):
            raise TimeoutError("Private provider details must not escape")

    failed = execute(access, bad, Unavailable())
    assert failed.status == "failed" and failed.score is None
    assert "Private provider" not in str(failed.to_dict())
    with SessionLocal() as s:
        state = retrieve_execution(s, access, plan["execution_id"])
        assert state["status"] == "failed" and state["progress"]["completed"] == 1
        assert s.get(Run, good).configuration["overall_score"] == 100
        assert s.scalar(select(ModelResponse.content).where(ModelResponse.run_id == good))


def test_preview_success_is_separate_from_fresh_scored_context(access):
    ref = setup(access)
    with SessionLocal.begin() as s:
        preview = save_preview(
            s,
            access,
            ref,
            profile(),
            status="completed",
            actual_model="demo-json-v1",
            interpretation={
                "purpose": "diagnostic only",
                "deliverable": "JSON",
                "constraints": "count 3",
                "success_conditions": "valid JSON",
            },
        )
        plan = reserve_attempts(
            s, access, [profile()], test=ref, previews={"1:1": {"preview_id": preview.id}}
        )

    class FreshContext(DemoProvider):
        def generate(self, prompt, *args, **kwargs):
            assert prompt == definition().prompt
            assert "diagnostic only" not in prompt + kwargs.get("system_prompt", "")
            return super().generate(prompt, *args, **kwargs)

    assert execute(access, plan["attempts"][0]["run_id"], FreshContext()).score == 100


def test_rerun_requires_terminal_source_and_current_remote_profile_resolution(access):
    ref = setup(access)
    remote = profile().model_copy(update={"provider": "openai_compatible"})
    with SessionLocal.begin() as s:
        plan = reserve_attempts(s, access, [remote], test=ref)
    run_id = plan["attempts"][0]["run_id"]
    with SessionLocal.begin() as s:
        with pytest.raises(Conflict):
            create_rerun_plan(s, access, run_id)

    class FakeCompatible(DemoProvider):
        name = "openai_compatible"

    execute(access, run_id, FakeCompatible())
    with SessionLocal.begin() as s:
        with pytest.raises(Conflict):
            create_rerun_plan(s, access, run_id)
    with SessionLocal.begin() as s:
        rerun = create_rerun_plan(s, access, run_id, resolve_profile=lambda archived: archived)
        assert rerun["attempts"][0]["run_id"] != run_id
