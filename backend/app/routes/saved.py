"""Scoped HTTP routes for the saved P3 workflow."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.evaluation.interpretation import request_interpretation
from app.models import SuiteRevision, TestVersion
from app.schemas.saved import (
    DraftInput,
    ExecutionInput,
    ExecutionView,
    PreviewInput,
    PreviewView,
    ProfileView,
    RerunInput,
    SuiteInput,
    SuiteRevisionInput,
    SuiteView,
    VersionInput,
    VersionView,
)
from app.services.model_profiles import profiles, resolve_archived, resolve_profile, target_provider
from app.storage.access import AccessContext, get_access
from app.storage.definitions import (
    approve_test_version,
    create_suite,
    create_test,
    create_test_version,
    get_suite,
    get_test_version,
    list_suites,
    list_test_versions,
    list_tests,
    revise_suite,
)
from app.storage.errors import AccessDenied, Conflict, NotFound
from app.storage.executions import (
    create_rerun_plan,
    reserve_attempts,
    retrieve_execution,
    save_preview,
)
from app.storage.records import TestReference


class SavedRoute(APIRoute):
    def get_route_handler(self):
        route = super().get_route_handler()

        async def handle(request: Request):
            try:
                return await route(request)
            except (RequestValidationError, ValidationError) as exc:
                errors = [{"loc": e["loc"], "msg": e["msg"]} for e in exc.errors()]
                raise HTTPException(422, errors) from None
            except NotFound as exc:
                raise HTTPException(404, str(exc)) from None
            except AccessDenied as exc:
                raise HTTPException(403, str(exc)) from None
            except Conflict as exc:
                raise HTTPException(409, str(exc)) from None
            except IntegrityError:
                raise HTTPException(409, "The change conflicts with saved records.") from None
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from None

        return handle


router = APIRouter(route_class=SavedRoute)
Access = Annotated[AccessContext, Depends(get_access)]
DB = Annotated[Session, Depends(get_db)]
PageSize = Annotated[int, Query(ge=1, le=100)]
Cursor = Annotated[str, Query(max_length=128)]


def _state(version):
    return (version.approval or {}).get("state", "historical")


def _version_view(version):
    return VersionView(
        test_id=version.test_id,
        test_version=version.version,
        name=version.name,
        state=_state(version),
        definition=version.evaluation_definition,
        approval=version.approval,
        definition_hash=version.definition_hash,
    )


@router.get("/tests", tags=["tests"])
def tests(session: DB, access: Access, after: Cursor = "", limit: PageSize = 100):
    ids = [t.id for t in list_tests(session, access, after=after, limit=limit)]
    latest = (
        select(TestVersion.test_id, func.max(TestVersion.version).label("version"))
        .where(TestVersion.test_id.in_(ids))
        .group_by(TestVersion.test_id)
        .subquery()
    )
    versions = session.scalars(
        select(TestVersion)
        .join(
            latest,
            (TestVersion.test_id == latest.c.test_id) & (TestVersion.version == latest.c.version),
        )
        .order_by(TestVersion.test_id)
    )
    return {
        "items": [
            {"test_id": v.test_id, "name": v.name, "latest_version": v.version, "state": _state(v)}
            for v in versions
        ],
        "next_cursor": ids[-1] if len(ids) == limit else None,
    }


@router.post("/tests", response_model=VersionView, status_code=201, tags=["tests"])
def new_test(body: DraftInput, session: DB, access: Access):
    with session.begin():
        return _version_view(create_test(session, access, body))


@router.get("/tests/{test_id}/versions", tags=["tests"])
def versions(
    test_id: str,
    session: DB,
    access: Access,
    after_version: Annotated[int, Query(ge=0)] = 0,
    limit: PageSize = 100,
):
    rows = list_test_versions(session, access, test_id, after_version=after_version, limit=limit)
    return {
        "items": [
            {"test_id": v.test_id, "test_version": v.version, "name": v.name, "state": _state(v)}
            for v in rows
        ],
        "next_cursor": rows[-1].version if len(rows) == limit else None,
    }


@router.get("/tests/{test_id}/versions/{version}", response_model=VersionView, tags=["tests"])
def version(test_id: str, version: int, session: DB, access: Access):
    return _version_view(
        get_test_version(session, access, TestReference(test_id=test_id, test_version=version))
    )


@router.post(
    "/tests/{test_id}/versions", response_model=VersionView, status_code=201, tags=["tests"]
)
def new_version(test_id: str, body: VersionInput, session: DB, access: Access):
    with session.begin():
        return _version_view(
            create_test_version(
                session, access, test_id, body.definition, expected_version=body.expected_version
            )
        )


@router.post(
    "/tests/{test_id}/versions/{version}/approve",
    response_model=VersionView,
    status_code=201,
    tags=["tests"],
)
def approve(test_id: str, version: int, session: DB, access: Access):
    ref = TestReference(test_id=test_id, test_version=version)
    with session.begin():
        return _version_view(approve_test_version(session, access, ref))


def _approved(session, access, ref):
    row = get_test_version(session, access, ref)
    if not row.definition_hash or _state(row) != "approved":
        raise Conflict("Choose a saved, approved version.")
    return row


@router.get("/model-profiles", response_model=list[ProfileView], tags=["executions"])
def model_profiles(access: Access):
    return [
        ProfileView(
            profile_id=p.profile_id,
            profile_revision=p.profile_revision,
            provider=p.provider,
            requested_model=p.requested_model,
            parameters=p.parameters,
        )
        for p in profiles(get_settings()).values()
    ]


@router.post("/previews", response_model=PreviewView, status_code=201, tags=["executions"])
def preview(body: PreviewInput, session: DB, access: Access):
    settings = get_settings()
    profile = resolve_profile(settings, body.profile_id)
    with session.begin():
        version = _approved(session, access, body.test)
        task, instructions = version.prompt, version.evaluation_definition["resolved_system_prompt"]
    diagnostic = request_interpretation(
        target_provider(settings, profile), profile, task, instructions
    )
    with session.begin():
        saved = save_preview(session, access, body.test, profile, **diagnostic)
        return PreviewView(
            **body.model_dump(),
            preview_id=saved.id,
            status=saved.status,
            interpretation=saved.interpretation,
            error_category=saved.error_category,
            actual_model=saved.actual_model,
        )


@router.get("/suites", tags=["suites"])
def suites(session: DB, access: Access, after: Cursor = "", limit: PageSize = 100):
    ids = [s.id for s in list_suites(session, access, after=after, limit=limit)]
    latest = (
        select(SuiteRevision.suite_id, func.max(SuiteRevision.revision).label("revision"))
        .where(SuiteRevision.suite_id.in_(ids))
        .group_by(SuiteRevision.suite_id)
        .subquery()
    )
    rows = session.scalars(
        select(SuiteRevision)
        .join(
            latest,
            (SuiteRevision.suite_id == latest.c.suite_id)
            & (SuiteRevision.revision == latest.c.revision),
        )
        .order_by(SuiteRevision.suite_id)
    )
    return {
        "items": [
            {"suite_id": s.suite_id, "suite_revision": s.revision, "name": s.name} for s in rows
        ],
        "next_cursor": ids[-1] if len(ids) == limit else None,
    }


@router.get("/suites/{suite_id}/revisions/{revision}", response_model=SuiteView, tags=["suites"])
def suite(suite_id: str, revision: int, session: DB, access: Access):
    saved, items = get_suite(session, access, suite_id, revision)
    versions = {
        v.id: v
        for v in session.scalars(
            select(TestVersion).where(TestVersion.id.in_([item.test_version_id for item in items]))
        )
    }
    return SuiteView(
        suite_id=suite_id,
        suite_revision=revision,
        name=saved.name,
        items=[
            TestReference(test_id=v.test_id, test_version=v.version)
            for v in (versions[item.test_version_id] for item in items)
        ],
    )


@router.post("/suites", response_model=SuiteView, status_code=201, tags=["suites"])
def new_suite(body: SuiteInput, session: DB, access: Access):
    with session.begin():
        for ref in body.items:
            _approved(session, access, ref)
        saved = create_suite(session, access, body.name, body.items)
        return SuiteView(
            suite_id=saved.suite_id, suite_revision=saved.revision, **body.model_dump()
        )


@router.post(
    "/suites/{suite_id}/revisions", response_model=SuiteView, status_code=201, tags=["suites"]
)
def new_suite_revision(suite_id: str, body: SuiteRevisionInput, session: DB, access: Access):
    with session.begin():
        for ref in body.items:
            _approved(session, access, ref)
        saved = revise_suite(
            session,
            access,
            suite_id,
            body.name,
            body.items,
            expected_revision=body.expected_revision,
        )
        return SuiteView(
            suite_id=saved.suite_id,
            suite_revision=saved.revision,
            name=saved.name,
            items=body.items,
        )


@router.post("/executions", response_model=ExecutionView, status_code=202, tags=["executions"])
def execute(body: ExecutionInput, session: DB, access: Access):
    settings = get_settings()
    selected = [resolve_profile(settings, profile_id) for profile_id in body.profile_ids]
    with session.begin():
        return reserve_attempts(
            session,
            access,
            selected,
            test=body.test,
            **(body.suite.model_dump() if body.suite else {}),
            previews={key: choice.model_dump() for key, choice in body.previews.items()},
            idempotency_key=body.idempotency_key,
            dispatch=True,
        )


@router.get("/executions/{execution_id}", response_model=ExecutionView, tags=["executions"])
def execution(execution_id: str, session: DB, access: Access):
    return retrieve_execution(session, access, execution_id)


@router.post(
    "/runs/{run_id}/rerun", response_model=ExecutionView, status_code=202, tags=["executions"]
)
def rerun(run_id: str, body: RerunInput, session: DB, access: Access):
    settings = get_settings()
    profile = resolve_profile(settings, body.profile_id) if body.profile_id is not None else None
    with session.begin():
        return create_rerun_plan(
            session,
            access,
            run_id,
            test=body.test,
            profile=profile,
            idempotency_key=body.idempotency_key,
            resolve_profile=lambda archived: resolve_archived(settings, archived),
            dispatch=True,
        )
