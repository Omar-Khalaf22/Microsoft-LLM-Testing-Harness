"""Schema 4.0 portable evidence. Strict, atomic imports never overwrite run IDs.

Relational surrogate IDs are resolved from test_id/version. Source review IDs are
kept in attribution; local review row IDs remain local database identity keys.
"""

from datetime import UTC, datetime
from decimal import Decimal
from functools import wraps
from typing import Literal

from pydantic import AwareDatetime, Field, JsonValue, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    EvaluationResult,
    Execution,
    HumanReview,
    Model,
    ModelResponse,
    Preview,
    Suite,
    SuiteItem,
    SuiteRevision,
    Test,
    TestRun,
    TestVersion,
    VersionCriterion,
)
from app.storage.access import AccessContext
from app.storage.errors import Conflict, NotFound
from app.storage.records import (
    ProfileSelection,
    Record,
    TestReference,
    canonical_hash,
    configuration_hash,
    reject_secrets,
)


def malformed_evidence_as_validation_error(fn):
    @wraps(fn)
    def validate(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except (KeyError, TypeError, IndexError, AttributeError):
            raise ValueError("Malformed relational evidence or execution snapshot.") from None

    return validate


class CriterionEvidence(Record):
    criterion_id: str
    maximum_points: Decimal = Field(ge=0, le=100, decimal_places=2)
    definition: dict[str, JsonValue]


class DefinitionEvidence(Record):
    test_id: str
    test_version: int = Field(gt=0)
    test_name: str
    test_created_at: AwareDatetime
    creator_id: str | None
    name: str
    prompt: str
    definition: dict[str, JsonValue]
    definition_hash: str | None
    approval: dict[str, JsonValue] | None
    created_at: AwareDatetime
    criteria: list[CriterionEvidence]


class ReviewEvidence(Record):
    source_review_id: int = Field(gt=0)
    reviewer_id: str = Field(min_length=1, max_length=128)
    rating: int = Field(ge=0, le=100, strict=True)
    rationale: str = Field(min_length=1, max_length=4000)
    revision: int = Field(gt=0)
    created_at: AwareDatetime
    attribution: dict[str, JsonValue] | None = None


class EvaluationEvidence(Record):
    method: str
    criterion_id: str | None
    passed: bool | None
    score: Decimal | None = Field(ge=0, le=1)
    status: Literal["completed", "error"] | None
    earned_points: Decimal | None = Field(ge=0, le=100, decimal_places=2)
    maximum_points: Decimal | None = Field(ge=0, le=100, decimal_places=2)
    normalized_score: Decimal | None = Field(ge=0, le=1)
    details: dict[str, JsonValue]

    @model_validator(mode="after")
    def bounds(self):
        if self.earned_points is not None and (
            self.maximum_points is None or self.earned_points > self.maximum_points
        ):
            raise ValueError("Awarded points exceed their maximum.")
        if self.status == "error" and any(
            v is not None
            for v in (self.passed, self.score, self.earned_points, self.normalized_score)
        ):
            raise ValueError("Failed evaluators must retain null scores.")
        if self.status == "completed" and (
            self.earned_points is None or self.normalized_score is None
        ):
            raise ValueError("Completed evaluations require numerical evidence.")
        return self


class RunEvidence(Record):
    run_id: str = Field(min_length=1, max_length=128)
    test: TestReference
    model_id: str
    model_name: str
    status: Literal["pending", "running", "completed", "failed"]
    configuration: dict[str, JsonValue]
    prompt: str
    response: str | None
    created_at: AwareDatetime
    started_at: AwareDatetime | None
    completed_at: AwareDatetime | None
    latency_ms: int | None = Field(ge=0)
    input_tokens: int | None = Field(ge=0)
    output_tokens: int | None = Field(ge=0)
    execution_id: str | None
    rerun_of_run_id: str | None
    suite_position: int | None = Field(gt=0)
    model_position: int | None = Field(gt=0)
    evidence: dict[str, JsonValue] | None
    error: str | None
    evaluations: list[EvaluationEvidence]
    reviews: list[ReviewEvidence]

    @model_validator(mode="after")
    def valid(self):
        if self.completed_at and (not self.started_at or self.completed_at < self.started_at):
            raise ValueError("Invalid run timestamp order.")
        ids = [e.criterion_id for e in self.evaluations if e.criterion_id is not None]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate run criterion.")
        reviews = [(r.reviewer_id, r.revision) for r in self.reviews]
        if len(reviews) != len(set(reviews)):
            raise ValueError("Duplicate review revision.")
        if self.execution_id:
            if self.started_at is None or self.completed_at is None:
                raise ValueError("Terminal P3 evidence requires start/completion timestamps.")
            if not self.suite_position or not self.model_position:
                raise ValueError("Reserved evidence requires attempt positions.")
            if self.status in ("pending", "running"):
                # Transferring a live lease would claim ownership in a different database.
                raise ValueError("Finish or recover active executions before exporting/importing.")
        reject_secrets(self.configuration)
        return self


class SuiteEvidence(Record):
    suite_id: str
    revision: int = Field(gt=0)
    creator_id: str
    name: str
    created_at: AwareDatetime
    items: list[TestReference] = Field(min_length=1, max_length=100)


class ExecutionEvidence(Record):
    execution_id: str
    actor_id: str
    request_hash: str
    snapshot: dict[str, JsonValue]
    status: Literal["completed", "failed"]
    created_at: AwareDatetime


class PreviewEvidence(Record):
    preview_id: str
    actor_id: str
    test: TestReference
    configuration_hash: str
    profile: dict[str, JsonValue]
    status: Literal["completed", "technical_error"]
    actual_model: str | None
    interpretation: dict[str, JsonValue]
    error_category: str | None
    created_at: AwareDatetime


class EvidenceBundle(Record):
    schema_version: Literal["4.0"]
    source: str = Field(min_length=1, max_length=500)
    exported_at: AwareDatetime
    definitions: list[DefinitionEvidence] = Field(max_length=10000)
    suites: list[SuiteEvidence] = Field(default_factory=list, max_length=1000)
    executions: list[ExecutionEvidence] = Field(default_factory=list, max_length=5000)
    previews: list[PreviewEvidence] = Field(default_factory=list, max_length=10000)
    runs: list[RunEvidence] = Field(min_length=1, max_length=5000)

    @model_validator(mode="after")
    @malformed_evidence_as_validation_error
    def relationships(self):
        canonical_hash(self.model_dump(mode="json"))  # reject non-finite nested JSON
        defs = {(d.test_id, d.test_version): d for d in self.definitions}
        runs = {r.run_id: r for r in self.runs}
        executions = {e.execution_id: e for e in self.executions}
        previews = {p.preview_id: p for p in self.previews}
        suites = {(s.suite_id, s.revision): s for s in self.suites}
        if any(
            len(mapping) != len(items)
            for mapping, items in (
                (defs, self.definitions),
                (runs, self.runs),
                (executions, self.executions),
                (previews, self.previews),
                (suites, self.suites),
            )
        ):
            raise ValueError("Duplicate source identifiers.")
        for d in self.definitions:
            members = {c.criterion_id: c for c in d.criteria}
            if len(members) != len(d.criteria):
                raise ValueError("Duplicate version criterion.")
            if d.definition_hash:
                if canonical_hash(d.definition) != d.definition_hash:
                    raise ValueError("Saved definition hash mismatch.")
                if not members or sum(c.maximum_points for c in d.criteria) != 100:
                    raise ValueError("Version allocations must total 100.00.")
                selected = d.definition.get("criteria")
                if selected is not None and (
                    set(members) != {c["criterion_id"] for c in selected}
                    or any(c.maximum_points <= 0 for c in d.criteria)
                ):
                    raise ValueError("Selected criterion membership mismatch.")
                if selected is not None and any(
                    Decimal(str(c["weight"])) != members[c["criterion_id"]].maximum_points
                    for c in selected
                ):
                    raise ValueError("Definition and relational allocations disagree.")
        for suite in self.suites:
            if any((i.test_id, i.test_version) not in defs for i in suite.items):
                raise ValueError("Missing suite test version.")
        for p in self.previews:
            if (p.test.test_id, p.test.test_version) not in defs:
                raise ValueError("Missing preview version.")
            reject_secrets(p.profile)
            d = defs[(p.test.test_id, p.test.test_version)]
            profile = ProfileSelection.model_validate(p.profile)
            if configuration_hash(d.definition, profile) != p.configuration_hash:
                raise ValueError("Preview configuration hash mismatch.")
        positions = set()
        for r in self.runs:
            d = defs.get((r.test.test_id, r.test.test_version))
            if not d or (r.rerun_of_run_id and r.rerun_of_run_id not in runs):
                raise ValueError("Missing run version or rerun source.")
            if r.execution_id:
                execution = executions.get(r.execution_id)
                if not execution:
                    raise ValueError("Missing parent execution.")
                key = (r.execution_id, r.suite_position, r.model_position)
                if key in positions:
                    raise ValueError("Duplicate attempt position.")
                positions.add(key)
                snapshot = r.configuration.get("snapshot", {})
                if (
                    snapshot.get("test_id") != d.test_id
                    or snapshot.get("test_version") != d.test_version
                ):
                    raise ValueError("Frozen run version mismatch.")
                if snapshot.get("definition") != d.definition:
                    raise ValueError("Frozen definition mismatch.")
                profile = ProfileSelection.model_validate(snapshot.get("profile"))
                if configuration_hash(d.definition, profile) != snapshot.get("configuration_hash"):
                    raise ValueError("Attempt configuration hash mismatch.")
                if (
                    r.prompt != d.prompt
                    or not 1 <= r.suite_position <= len(execution.snapshot["tests"])
                    or not 1 <= r.model_position <= len(execution.snapshot["profiles"])
                ):
                    raise ValueError("Attempt is outside its execution membership.")
                if (
                    execution.snapshot["tests"][r.suite_position - 1]["test_id"] != d.test_id
                    or execution.snapshot["tests"][r.suite_position - 1]["test_version"]
                    != d.test_version
                    or execution.snapshot["profiles"][r.model_position - 1] != snapshot["profile"]
                ):
                    raise ValueError("Attempt and execution snapshots disagree.")
                if snapshot.get("preview") and snapshot["preview"]["preview_id"] not in previews:
                    raise ValueError("Missing preview evidence.")
                members = {c.criterion_id: c.maximum_points for c in d.criteria}
                for e in r.evaluations:
                    if e.criterion_id not in members or e.maximum_points != members[e.criterion_id]:
                        raise ValueError("Result does not belong to the run's version.")
                snap = r.configuration.get("result_snapshot")
                if snap:
                    if (
                        snap.get("id") != r.run_id
                        or snap.get("response") != (r.response or "")
                        or snap.get("prompt") != r.prompt
                        or snap.get("status") != r.status
                    ):
                        raise ValueError("Result snapshot disagrees with relational evidence.")
                    captured = {c.get("criterion_id"): c for c in snap.get("criteria", [])}
                    if len(captured) != len(r.evaluations):
                        raise ValueError("Result snapshot criterion mismatch.")
                    for evaluation in r.evaluations:
                        c = captured.get(evaluation.criterion_id, {})
                        for field, value in (
                            ("score", evaluation.earned_points),
                            ("maximum_points", evaluation.maximum_points),
                            ("normalized_score", evaluation.normalized_score),
                        ):
                            actual = c.get(field)
                            if (actual is None) != (value is None) or (
                                actual is not None and Decimal(str(actual)) != value
                            ):
                                raise ValueError("Result snapshot numerical evidence mismatch.")
                        if (
                            c.get("status") != evaluation.status
                            or c.get("passed") != evaluation.passed
                        ):
                            raise ValueError("Result snapshot status mismatch.")
                    score = snap.get("score")
                    failed = any(e.status != "completed" for e in r.evaluations)
                    if failed and score is not None:
                        raise ValueError("Incomplete evaluation cannot have a total.")
                    if r.status == "completed" and (
                        failed
                        or set(members) != {e.criterion_id for e in r.evaluations}
                        or score is None
                        or Decimal(str(score)) != sum(e.earned_points for e in r.evaluations)
                    ):
                        raise ValueError("Invalid completed total.")
                elif r.status == "completed":
                    raise ValueError("Completed P3 evidence requires its result snapshot.")
        for e in self.executions:
            children = [r for r in self.runs if r.execution_id == e.execution_id]
            expected = len(e.snapshot["tests"]) * len(e.snapshot["profiles"])
            if len(children) != expected or e.status != (
                "failed" if any(r.status == "failed" for r in children) else "completed"
            ):
                raise ValueError("Execution closure/progress mismatch.")
            sid = e.snapshot.get("suite_id")
            if sid and (sid, e.snapshot["suite_revision"]) not in suites:
                raise ValueError("Missing suite revision.")
        return self


def export_evidence(session: Session, access: AccessContext, run_ids: list[str]) -> EvidenceBundle:
    if not 1 <= len(run_ids) <= 5000:
        raise ValueError("Select between 1 and 5000 runs.")
    found = {}
    queue = set(run_ids)
    while queue:
        run_id = queue.pop()
        if run_id in found:
            continue
        r = session.get(TestRun, run_id)
        if r is None or r.project_id != access.project_id:
            raise NotFound("Export contains an inaccessible run.")
        found[r.id] = r
        if len(found) > 5000:
            raise ValueError("Execution closure exceeds the export limit.")
        if r.execution_id:
            queue.update(
                session.scalars(select(TestRun.id).where(TestRun.execution_id == r.execution_id))
            )
        if r.rerun_of_run_id:
            queue.add(r.rerun_of_run_id)
    version_ids = {r.test_version_id for r in found.values()}
    parents = {r.execution_id for r in found.values() if r.execution_id}
    executions = [session.get(Execution, eid) for eid in sorted(parents)]
    suite_refs = {
        (e.snapshot["suite_id"], e.snapshot["suite_revision"])
        for e in executions
        if e.snapshot.get("suite_id")
    }
    suites = []
    for sid, rev in sorted(suite_refs):
        sr, suite = session.get(SuiteRevision, (sid, rev)), session.get(Suite, sid)
        items = session.scalars(
            select(SuiteItem)
            .where(SuiteItem.suite_id == sid, SuiteItem.revision == rev)
            .order_by(SuiteItem.position)
        ).all()
        version_ids.update(i.test_version_id for i in items)
        suites.append(
            dict(
                suite_id=sid,
                revision=rev,
                creator_id=suite.creator_id,
                name=sr.name,
                created_at=sr.created_at,
                items=[_ref(session.get(TestVersion, i.test_version_id)) for i in items],
            )
        )
    preview_ids = {
        r.configuration["snapshot"]["preview"]["preview_id"]
        for r in found.values()
        if r.configuration.get("snapshot", {}).get("preview")
    }
    previews = [session.get(Preview, p) for p in sorted(preview_ids)]
    version_ids.update(p.test_version_id for p in previews)
    definitions = []
    for vid in sorted(version_ids):
        v = session.get(TestVersion, vid)
        t = session.get(Test, v.test_id)
        if t.project_id != access.project_id:
            raise NotFound("Export contains inaccessible definitions.")
        definitions.append(
            dict(
                test_id=t.id,
                test_version=v.version,
                test_name=t.name,
                test_created_at=t.created_at,
                creator_id=t.creator_id,
                name=v.name,
                prompt=v.prompt,
                definition=v.evaluation_definition,
                definition_hash=v.definition_hash,
                approval=v.approval,
                created_at=v.created_at,
                criteria=[
                    dict(
                        criterion_id=c.criterion_id,
                        maximum_points=c.maximum_points,
                        definition=c.definition,
                    )
                    for c in session.scalars(
                        select(VersionCriterion).where(VersionCriterion.test_version_id == vid)
                    )
                ],
            )
        )
    runs = []
    for r in sorted(found.values(), key=lambda r: r.id):
        response = session.scalar(select(ModelResponse).where(ModelResponse.run_id == r.id))
        runs.append(
            dict(
                run_id=r.id,
                test=_ref(r.test_version),
                model_id=r.model_id,
                model_name=r.model.name,
                status=r.status,
                configuration=r.configuration,
                prompt=r.input_prompt,
                response=response.content if response else None,
                created_at=r.created_at,
                started_at=r.started_at,
                completed_at=r.completed_at,
                latency_ms=r.latency_ms,
                input_tokens=r.input_tokens,
                output_tokens=r.output_tokens,
                execution_id=r.execution_id,
                rerun_of_run_id=r.rerun_of_run_id,
                suite_position=r.suite_position,
                model_position=r.model_position,
                evidence=r.evidence,
                error=r.error,
                evaluations=[
                    {key: getattr(e, key) for key in EvaluationEvidence.model_fields}
                    for e in r.evaluations
                ],
                reviews=[
                    dict(
                        source_review_id=review.id,
                        **{
                            k: getattr(review, k)
                            for k in ReviewEvidence.model_fields
                            if k != "source_review_id"
                        },
                    )
                    for review in session.scalars(
                        select(HumanReview)
                        .where(HumanReview.run_id == r.id)
                        .order_by(HumanReview.id)
                    )
                ],
            )
        )
    return EvidenceBundle.model_validate(
        dict(
            schema_version="4.0",
            source="llm-testing-harness",
            exported_at=datetime.now(UTC),
            definitions=definitions,
            suites=suites,
            runs=runs,
            executions=[
                dict(
                    execution_id=e.id,
                    actor_id=e.actor_id,
                    request_hash=e.request_hash,
                    snapshot=e.snapshot,
                    status=e.status,
                    created_at=e.created_at,
                )
                for e in executions
            ],
            previews=[
                dict(
                    preview_id=p.id,
                    actor_id=p.actor_id,
                    test=_ref(session.get(TestVersion, p.test_version_id)),
                    configuration_hash=p.configuration_hash,
                    profile=p.profile,
                    status=p.status,
                    actual_model=p.actual_model,
                    interpretation=p.interpretation,
                    error_category=p.error_category,
                    created_at=p.created_at,
                )
                for p in previews
            ],
        )
    )


def _ref(v):
    return {"test_id": v.test_id, "test_version": v.version}


def import_evidence(session: Session, access: AccessContext, bundle: EvidenceBundle) -> dict:
    """Validate first, then insert in one caller-owned transaction. No copy/upsert mode."""
    bundle = EvidenceBundle.model_validate(bundle.model_dump(mode="json"))
    digest = canonical_hash(bundle.model_dump(mode="json"))
    # Check every run conflict before inserting even a definition.
    if session.scalar(
        select(TestRun.id).where(TestRun.id.in_([r.run_id for r in bundle.runs])).limit(1)
    ):
        raise Conflict("A run ID already exists. Strict import cannot overwrite evidence.")
    versions = {}
    for d in bundle.definitions:
        t = session.get(Test, d.test_id)
        if t is None:
            t = Test(
                id=d.test_id,
                name=d.test_name,
                project_id=access.project_id,
                creator_id=d.creator_id,
                created_at=d.test_created_at,
            )
            session.add(t)
            session.flush()
        elif t.project_id != access.project_id:
            raise Conflict("A source test ID collides with another workspace.")
        v = session.scalar(
            select(TestVersion).where(
                TestVersion.test_id == t.id, TestVersion.version == d.test_version
            )
        )
        if v:
            if (
                v.evaluation_definition != d.definition
                or v.name != d.name
                or v.prompt != d.prompt
                or v.definition_hash != d.definition_hash
                or v.approval != d.approval
            ):
                raise Conflict("A saved version ID has different evidence.")
        else:
            v = TestVersion(
                test_id=t.id,
                version=d.test_version,
                name=d.name,
                prompt=d.prompt,
                evaluation_definition=d.definition,
                definition_hash=d.definition_hash,
                approval=d.approval,
                created_at=d.created_at,
            )
            session.add(v)
            session.flush()
            session.add_all(
                [
                    VersionCriterion(
                        test_version_id=v.id,
                        criterion_id=c.criterion_id,
                        maximum_points=c.maximum_points,
                        definition=c.definition,
                    )
                    for c in d.criteria
                ]
            )
            session.flush()
        versions[(d.test_id, d.test_version)] = v.id
    for s in bundle.suites:
        if session.get(SuiteRevision, (s.suite_id, s.revision)):
            raise Conflict("A suite revision ID already exists.")
        suite = session.get(Suite, s.suite_id)
        if not suite:
            session.add(Suite(id=s.suite_id, project_id=access.project_id, creator_id=s.creator_id))
            session.flush()
        elif suite.project_id != access.project_id:
            raise Conflict("Suite ID collision.")
        session.add(
            SuiteRevision(
                suite_id=s.suite_id, revision=s.revision, name=s.name, created_at=s.created_at
            )
        )
        session.flush()
        session.add_all(
            [
                SuiteItem(
                    suite_id=s.suite_id,
                    revision=s.revision,
                    position=i,
                    test_version_id=versions[(r.test_id, r.test_version)],
                )
                for i, r in enumerate(s.items, 1)
            ]
        )
        session.flush()
    for e in bundle.executions:
        if session.get(Execution, e.execution_id):
            raise Conflict("An execution ID already exists.")
        session.add(
            Execution(
                id=e.execution_id,
                project_id=access.project_id,
                actor_id=e.actor_id,
                request_hash=e.request_hash,
                snapshot=e.snapshot,
                status=e.status,
                created_at=e.created_at,
            )
        )
    for p in bundle.previews:
        if session.get(Preview, p.preview_id):
            raise Conflict("A preview ID already exists.")
        session.add(
            Preview(
                id=p.preview_id,
                project_id=access.project_id,
                actor_id=p.actor_id,
                test_version_id=versions[(p.test.test_id, p.test.test_version)],
                configuration_hash=p.configuration_hash,
                profile=p.profile,
                status=p.status,
                actual_model=p.actual_model,
                interpretation=p.interpretation,
                error_category=p.error_category,
                created_at=p.created_at,
            )
        )
    session.flush()
    # Topological order preserves rerun foreign keys; reject cycles instead of guessing.
    todo = {r.run_id: r for r in bundle.runs}
    inserted = set()
    while todo:
        ready = [r for r in todo.values() if not r.rerun_of_run_id or r.rerun_of_run_id in inserted]
        if not ready:
            raise ValueError("Rerun relationships contain a cycle.")
        for r in ready:
            model = session.get(Model, r.model_id)
            if model and model.name != r.model_name:
                raise Conflict("Model ID has different identity.")
            if not model:
                session.add(Model(id=r.model_id, name=r.model_name))
                session.flush()
            run = TestRun(
                id=r.run_id,
                test_version_id=versions[(r.test.test_id, r.test.test_version)],
                project_id=access.project_id,
                model_id=r.model_id,
                # Insert running so relational evaluation insert guards can validate
                # membership before setting the imported terminal state.
                status="running" if r.execution_id else r.status,
                configuration=r.configuration,
                input_prompt=r.prompt,
                started_at=r.started_at,
                completed_at=None if r.execution_id else r.completed_at,
                created_at=r.created_at,
                execution_id=r.execution_id,
                rerun_of_run_id=r.rerun_of_run_id,
                suite_position=r.suite_position,
                model_position=r.model_position,
                latency_ms=r.latency_ms,
                input_tokens=r.input_tokens,
                output_tokens=r.output_tokens,
                evidence=r.evidence,
                error=r.error,
            )
            session.add(run)
            session.flush()
            if r.response is not None:
                session.add(ModelResponse(run_id=r.run_id, content=r.response))
            session.add_all(
                [
                    EvaluationResult(
                        run_id=r.run_id,
                        test_version_id=run.test_version_id if r.execution_id else None,
                        **e.model_dump(),
                    )
                    for e in r.evaluations
                ]
            )
            session.add_all(
                [
                    HumanReview(
                        run_id=r.run_id,
                        reviewer_id=v.reviewer_id,
                        rating=v.rating,
                        rationale=v.rationale,
                        revision=v.revision,
                        created_at=v.created_at,
                        attribution={
                            "source": bundle.source,
                            "source_review_id": v.source_review_id,
                            "bundle_hash": digest,
                            "imported_by": access.principal.subject,
                            "source_attribution": v.attribution,
                        },
                    )
                    for v in r.reviews
                ]
            )
            session.flush()
            if r.execution_id:
                run.status, run.completed_at = r.status, r.completed_at
                session.flush()
            inserted.add(r.run_id)
            del todo[r.run_id]
    return {"imported_run_ids": sorted(inserted), "bundle_hash": digest, "mode": "strict"}
