"""Reservation, response checkpoint and guarded finalization. Never call providers here.

All functions accept a caller-owned Session. Commit reservation/claim/checkpoint in
separate short transactions before any provider or judge request.
"""

from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.evaluation.models import TestRequest, TestResult
from app.models import (
    EvaluationResult,
    Execution,
    Model,
    ModelResponse,
    Preview,
    TestRun,
    TestVersion,
    VersionCriterion,
)
from app.storage.access import AccessContext
from app.storage.definitions import get_suite, get_test_version
from app.storage.errors import Conflict, NotFound
from app.storage.records import ProfileSelection, TestReference, canonical_hash, configuration_hash


def now(session):
    return session.scalar(select(func.clock_timestamp()))


def _version_snapshot(version):
    return {
        "test_id": version.test_id,
        "test_version": version.version,
        "test_name": version.name,
        "definition": version.evaluation_definition,
        "definition_hash": version.definition_hash,
    }


def reserve_attempts(
    session: Session,
    access: AccessContext,
    profiles: list[ProfileSelection],
    *,
    test: TestReference | None = None,
    suite_id: str | None = None,
    suite_revision: int | None = None,
    idempotency_key: str | None = None,
    previews: dict[str, dict] | None = None,
    rerun_of_run_id: str | None = None,
) -> dict:
    if not 1 <= len(profiles) <= 10:
        raise ValueError("Select between 1 and 10 server-resolved profiles.")
    profiles = [ProfileSelection.model_validate(p.model_dump()) for p in profiles]
    if (test is None) == (suite_id is None) or (suite_id and not suite_revision):
        raise ValueError("Supply one exact test or suite revision.")
    if idempotency_key is not None and not 1 <= len(idempotency_key) <= 128:
        raise ValueError("Invalid idempotency identifier.")
    request = {
        "test": test.model_dump() if test else None,
        "suite_id": suite_id,
        "suite_revision": suite_revision,
        "profiles": [p.model_dump() for p in profiles],
        "previews": previews or {},
        "rerun_of_run_id": rerun_of_run_id,
    }
    digest = canonical_hash(request)
    if idempotency_key:
        # Transaction-scoped advisory lock also serializes the absent-row case.
        lock_key = canonical_hash([access.project_id, access.principal.subject, idempotency_key])
        session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": int(lock_key[:15], 16)})
        prior = session.scalar(
            select(Execution).where(
                Execution.project_id == access.project_id,
                Execution.actor_id == access.principal.subject,
                Execution.idempotency_key == idempotency_key,
            )
        )
        if prior:
            if prior.request_hash != digest:
                raise Conflict("Idempotency identifier was used with different inputs.")
            return retrieve_execution(session, access, prior.id)
    if test:
        versions = [get_test_version(session, access, test)]
    else:
        _, items = get_suite(session, access, suite_id, suite_revision)
        versions = [session.get(TestVersion, item.test_version_id) for item in items]
    for version in versions:
        # Legacy execution-time versions lack attributable saved approval.
        if not version.definition_hash or (version.approval or {}).get("state") != "approved":
            raise Conflict("Save and approve an executable version before reserving attempts.")
        from app.storage.records import SavedDefinition

        SavedDefinition.model_validate(
            {k: version.evaluation_definition[k] for k in SavedDefinition.model_fields}
        )
    if rerun_of_run_id:
        get_attempt(session, access, rerun_of_run_id)
    expected_preview_keys = {
        f"{i}:{j}" for i in range(1, len(versions) + 1) for j in range(1, len(profiles) + 1)
    }
    if set(previews or {}) - expected_preview_keys:
        raise Conflict("Preview references do not identify an execution attempt.")
    for i, version in enumerate(versions, 1):
        for j, profile in enumerate(profiles, 1):
            preview_ref = (previews or {}).get(f"{i}:{j}")
            if preview_ref:
                validate_preview(session, access, version, profile, **preview_ref)
    snapshot = {
        "suite_id": suite_id,
        "suite_revision": suite_revision,
        "tests": [_version_snapshot(v) for v in versions],
        "profiles": [p.model_dump(mode="json") for p in profiles],
    }
    execution = Execution(
        id="exec_" + uuid4().hex,
        project_id=access.project_id,
        actor_id=access.principal.subject,
        idempotency_key=idempotency_key,
        request_hash=digest,
        snapshot=snapshot,
        status="pending",
    )
    session.add(execution)
    session.flush()
    for i, version in enumerate(versions, 1):
        for j, profile in enumerate(profiles, 1):
            preview_ref = (previews or {}).get(f"{i}:{j}")
            # Endpoint/profile identity remains distinct even when aliases/reporting match.
            model_id = "profile_" + canonical_hash(
                [profile.profile_id, profile.profile_revision, profile.endpoint_id]
            )
            session.execute(
                insert(Model)
                .values(id=model_id, name=profile.requested_model)
                .on_conflict_do_nothing(index_elements=[Model.id])
            )
            frozen = {
                **_version_snapshot(version),
                "profile": profile.model_dump(mode="json"),
                "configuration_hash": configuration_hash(version.evaluation_definition, profile),
                "preview": preview_ref,
            }
            session.add(
                TestRun(
                    id="run_" + uuid4().hex,
                    project_id=access.project_id,
                    execution_id=execution.id,
                    test_version_id=version.id,
                    model_id=model_id,
                    status="pending",
                    input_prompt=version.prompt,
                    configuration={"snapshot": frozen},
                    suite_position=i,
                    model_position=j,
                    rerun_of_run_id=rerun_of_run_id,
                )
            )
    session.flush()
    return retrieve_execution(session, access, execution.id)


def retrieve_execution(session: Session, access: AccessContext, execution_id: str) -> dict:
    row = session.get(Execution, execution_id)
    if row is None or row.project_id != access.project_id:
        raise NotFound("Execution does not exist.")
    attempts = session.scalars(
        select(TestRun)
        .where(TestRun.execution_id == row.id)
        .order_by(TestRun.suite_position, TestRun.model_position)
    ).all()
    counts = {
        status: sum(r.status == status for r in attempts)
        for status in ("pending", "running", "completed", "failed")
    }
    return {
        "execution_id": row.id,
        "status": row.status,
        "progress": counts,
        "attempts": [
            {
                "run_id": r.id,
                "status": r.status,
                "suite_position": r.suite_position,
                "model_position": r.model_position,
                "test_id": r.configuration["snapshot"]["test_id"],
                "test_version": r.configuration["snapshot"]["test_version"],
            }
            for r in attempts
        ],
    }


def get_attempt(session: Session, access: AccessContext, run_id: str) -> TestRun:
    row = session.get(TestRun, run_id)
    if row is None or row.project_id != access.project_id:
        raise NotFound("Run does not exist.")
    return row


def _locked(session, access, run_id):
    row = get_attempt(session, access, run_id)
    if row.execution_id is None:
        raise Conflict("Run was not reserved through P3 storage.")
    # Same lock order for every attempt mutation prevents parent/child deadlocks.
    parent = session.scalar(
        select(Execution).where(Execution.id == row.execution_id).with_for_update()
    )
    row = session.scalar(
        select(TestRun)
        .where(TestRun.id == run_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return row, parent


def claim_attempt(
    session: Session, access: AccessContext, run_id: str, *, lease_seconds: int = 120
):
    if not 30 <= lease_seconds <= 900:
        raise ValueError("Lease duration must be between 30 and 900 seconds.")
    row, parent = _locked(session, access, run_id)
    if row.status != "pending":
        raise Conflict("Attempt is already claimed or terminal.")
    row.status, row.started_at = "running", now(session)
    row.lease_token = uuid4().hex
    row.lease_until = row.started_at + timedelta(seconds=lease_seconds)
    parent.status = "running"
    session.flush()
    return row.lease_token


def _owned(session, access, run_id, token):
    row, parent = _locked(session, access, run_id)
    if (
        row.status != "running"
        or not token
        or row.lease_token != token
        or row.lease_until <= now(session)
    ):
        raise Conflict("Attempt ownership expired or changed.")
    return row, parent


def heartbeat_attempt(
    session: Session, access: AccessContext, run_id: str, token: str, *, lease_seconds: int = 120
):
    if not 30 <= lease_seconds <= 900:
        raise ValueError("Invalid lease duration.")
    row, _ = _owned(session, access, run_id, token)
    row.lease_until = now(session) + timedelta(seconds=lease_seconds)
    session.flush()


def save_target_response(
    session: Session,
    access: AccessContext,
    run_id: str,
    token: str,
    *,
    content: str,
    actual_model: str | None,
    latency_ms: int,
    usage: dict,
):
    row, _ = _owned(session, access, run_id, token)
    if (
        not isinstance(content, str)
        or len(content) > 100_000
        or (
            actual_model is not None
            and (not isinstance(actual_model, str) or not actual_model.strip())
        )
    ):
        raise ValueError("Invalid target response.")
    if (
        type(latency_ms) is not int
        or latency_ms < 0
        or any(
            value is not None and (type(value) is not int or value < 0) for value in usage.values()
        )
        or set(usage) - {"input_tokens", "output_tokens"}
    ):
        raise ValueError("Invalid target metrics.")
    if session.scalar(select(ModelResponse.id).where(ModelResponse.run_id == row.id)):
        raise Conflict("Target response was already checkpointed.")
    session.add(ModelResponse(run_id=row.id, content=content))
    row.input_tokens, row.output_tokens = usage.get("input_tokens"), usage.get("output_tokens")
    row.evidence = {
        "target": {"actual_model": actual_model, "latency_ms": latency_ms, "usage": usage}
    }
    session.flush()


def update_parent_progress(session: Session, parent: Execution):
    session.flush()
    states = session.scalars(select(TestRun.status).where(TestRun.execution_id == parent.id)).all()
    parent.status = (
        ("failed" if "failed" in states else "completed")
        if all(s in ("completed", "failed") for s in states)
        else ("running" if any(s != "pending" for s in states) else "pending")
    )
    session.flush()


def finalize_attempt(
    session: Session, access: AccessContext, run_id: str, token: str, result: TestResult
) -> TestResult:
    row, parent = _owned(session, access, run_id, token)
    frozen = row.configuration["snapshot"]
    if (
        result.id != run_id
        or result.prompt != row.input_prompt
        or result.status not in ("completed", "failed")
        or result.provider != frozen["profile"]["provider"]
    ):
        raise Conflict("Result does not match the reserved attempt.")
    target = session.scalar(select(ModelResponse).where(ModelResponse.run_id == row.id))
    if target is None and not (result.error and result.error["code"] == "provider_failure"):
        raise Conflict("Checkpoint the target response before evaluating/finalizing.")
    if target and (
        target.content != result.response
        or (
            row.evidence["target"]["actual_model"] is not None
            and row.evidence["target"]["actual_model"] != result.model
        )
    ):
        raise Conflict("Result changed the checkpointed target evidence.")
    membership = {
        c.criterion_id: c
        for c in session.scalars(
            select(VersionCriterion).where(VersionCriterion.test_version_id == row.test_version_id)
        )
    }
    if len(result.criteria) != len(membership) or {c.criterion_id for c in result.criteria} != set(
        membership
    ):
        raise Conflict("Result criteria do not match the frozen rubric.")
    total = Decimal(0)
    complete = True
    for c in result.criteria:
        member = membership[c.criterion_id]
        if c.maximum_points is None or Decimal(str(c.maximum_points)) != member.maximum_points:
            raise ValueError("Criterion maximum does not match the frozen version.")
        if c.status == "completed":
            if c.score is None or c.normalized_score is None:
                raise ValueError("Completed criteria require numerical evidence.")
            points, normalized = Decimal(str(c.score)), Decimal(str(c.normalized_score))
            if (
                not points.is_finite()
                or not normalized.is_finite()
                or not (0 <= points <= member.maximum_points and 0 <= normalized <= 1)
            ):
                raise ValueError("Criterion score is outside its bounds.")
            total += points
        else:
            complete = False
            if c.status != "error" or any(
                x is not None for x in (c.score, c.passed, c.normalized_score)
            ):
                raise ValueError("Failed evaluations cannot substitute zero.")
        session.add(
            EvaluationResult(
                run_id=row.id,
                test_version_id=row.test_version_id,
                criterion_id=c.criterion_id,
                method=c.name,
                passed=c.passed,
                status=c.status,
                score=Decimal(str(c.score)) / 100 if c.score is not None else None,
                earned_points=c.score,
                maximum_points=c.maximum_points,
                normalized_score=c.normalized_score,
                details={
                    "detail": c.detail,
                    "evaluator_model": c.evaluator_model,
                    "rationale": c.rationale,
                    "evidence": c.evidence,
                },
            )
        )
    if result.status == "completed" and (not complete or result.error):
        raise ValueError("A completed attempt requires every evaluation to be valid.")
    if result.error or not complete:
        if result.score is not None or result.status != "failed":
            raise ValueError("Incomplete evaluation requires a null total and failed status.")
    elif result.score is None or Decimal(str(result.score)) != total:
        raise ValueError("Total must equal the sum of awarded criterion points.")
    session.flush()  # evaluation insert guards see the running state
    metadata = {
        **result.metadata,
        "test_id": frozen["test_id"],
        "test_version": frozen["test_version"],
        "test_name": frozen["test_name"],
        "execution_id": row.execution_id,
        "rerun_of_run_id": row.rerun_of_run_id,
        "profile": frozen["profile"],
        "approved_at": row.test_version.approval["recorded_at"],
        "approval": row.test_version.approval,
    }
    from dataclasses import replace

    result = replace(result, metadata=metadata)
    row.configuration = {
        **row.configuration,
        "result_snapshot": result.to_dict(),
        "overall_score": result.score,
    }
    row.evidence = {**(row.evidence or {}), "evaluation": result.metadata.get("evaluation_metrics")}
    row.status, row.completed_at = result.status, now(session)
    row.latency_ms = result.latency_ms
    row.error = result.error["code"] if result.error else None
    row.lease_token, row.lease_until = None, None
    update_parent_progress(session, parent)
    return result


def recover_expired_attempt(session: Session, access: AccessContext, run_id: str):
    row, parent = _locked(session, access, run_id)
    if row.status != "running" or row.lease_until > now(session):
        raise Conflict("Attempt is terminal or still owned by a live lease.")
    # Do not retry an ambiguous remote side effect. Explicit rerun gets new IDs.
    row.status, row.completed_at, row.error = "failed", now(session), "interrupted"
    row.lease_token, row.lease_until = None, None
    update_parent_progress(session, parent)


def save_preview(
    session: Session,
    access: AccessContext,
    test: TestReference,
    profile: ProfileSelection,
    *,
    status: str,
    actual_model: str | None = None,
    interpretation: dict | None = None,
    error_category: str | None = None,
) -> Preview:
    version = get_test_version(session, access, test)
    if status not in ("completed", "technical_error"):
        raise ValueError("Invalid preview status.")
    fields = {"purpose", "deliverable", "constraints", "success_conditions"}
    if status == "completed" and (
        not actual_model
        or not interpretation
        or set(interpretation) != fields
        or any(not isinstance(v, str) or not v.strip() for v in interpretation.values())
    ):
        raise ValueError(
            "Completed preview requires all interpretation fields and actual identity."
        )
    if status == "technical_error" and error_category not in (
        "timeout",
        "provider_unavailable",
        "invalid_response",
    ):
        raise ValueError("Use a sanitized technical error category.")
    row = Preview(
        id="preview_" + uuid4().hex,
        project_id=access.project_id,
        actor_id=access.principal.subject,
        test_version_id=version.id,
        configuration_hash=configuration_hash(version.evaluation_definition, profile),
        profile=profile.model_dump(mode="json"),
        status=status,
        actual_model=actual_model,
        interpretation=interpretation or {},
        error_category=error_category,
    )
    session.add(row)
    session.flush()
    return row


def validate_preview(session, access, version, profile, preview_id, acknowledge_error=False):
    row = get_preview(session, access, preview_id)
    if row.test_version_id != version.id or row.configuration_hash != configuration_hash(
        version.evaluation_definition, profile
    ):
        raise Conflict("Preview is stale or belongs to another test/model configuration.")
    if row.status == "technical_error" and acknowledge_error is not True:
        raise Conflict("Acknowledge the technical preview failure or retry it.")


def get_preview(session: Session, access: AccessContext, preview_id: str) -> Preview:
    row = session.get(Preview, preview_id)
    if row is None or row.project_id != access.project_id:
        raise NotFound("Preview does not exist.")
    return row


def create_rerun_plan(
    session: Session,
    access: AccessContext,
    run_id: str,
    *,
    profile: ProfileSelection | None = None,
    test: TestReference | None = None,
    idempotency_key: str | None = None,
    resolve_profile=None,
):
    original = get_attempt(session, access, run_id)
    if original.status not in ("completed", "failed"):
        raise Conflict("The original attempt must be terminal before rerunning.")
    snapshot = original.configuration.get("snapshot")
    if snapshot is None and (profile is None or test is None):
        raise Conflict(
            "Historical profile/approval is unknown. Supply an approved saved version/profile."
        )
    if snapshot:
        if profile is None:
            archived = ProfileSelection.model_validate(snapshot["profile"])
            if resolve_profile is not None:
                profile = resolve_profile(archived)
                profile = ProfileSelection.model_validate(profile.model_dump())
                if profile != archived:
                    raise Conflict(
                        "Historical profile changed. Supply an explicit permitted override."
                    )
            elif archived.provider == "local_demo":
                profile = archived
            else:
                raise Conflict(
                    "Resolve the historical profile's current availability before rerunning."
                )
        test = test or TestReference(
            test_id=snapshot["test_id"], test_version=snapshot["test_version"]
        )
    return reserve_attempts(
        session,
        access,
        [profile],
        test=test,
        idempotency_key=idempotency_key,
        rerun_of_run_id=run_id,
    )


def request_for_attempt(session: Session, access: AccessContext, run_id: str) -> TestRequest:
    row = get_attempt(session, access, run_id)
    frozen = row.configuration["snapshot"]
    definition, profile = frozen["definition"], frozen["profile"]
    if set(profile["parameters"]) - {"temperature"}:
        raise Conflict(
            "The current executor adapter supports temperature only; "
            "extend the provider adapter first."
        )
    # Revalidate executable support, but never resolve a new default or change the snapshot.
    from app.storage.records import SavedDefinition

    SavedDefinition.model_validate({k: definition[k] for k in SavedDefinition.model_fields})
    return TestRequest(
        prompt=definition["prompt"],
        objective=definition["objective"],
        model=profile["requested_model"],
        temperature=profile["parameters"].get("temperature"),
        criteria=definition["criteria"],
        configuration_state="approved",
        base_system_prompt=definition["base_system_prompt"],
        custom_system_prompt=definition["custom_system_prompt"],
        frozen_system_prompt=definition["resolved_system_prompt"],
        reserved_run_id=row.id,
        test_id=frozen["test_id"],
        test_version=frozen["test_version"],
        test_name=frozen["test_name"],
        **(definition.get("legacy") or {}),
    )
