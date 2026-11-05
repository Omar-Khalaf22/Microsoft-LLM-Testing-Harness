"""Saved tests and ordered suites. Caller owns the transaction; no internal commits."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.evaluation.evaluators.legacy import WEIGHT_IDS
from app.evaluation.registry import get_criterion
from app.models import Suite, SuiteItem, SuiteRevision, Test, TestVersion, VersionCriterion
from app.storage.access import AccessContext
from app.storage.errors import Conflict, NotFound
from app.storage.records import SavedDefinition, TestReference, canonical_hash


def get_test_version(session: Session, access: AccessContext, ref: TestReference) -> TestVersion:
    row = session.scalar(
        select(TestVersion)
        .join(Test)
        .where(
            Test.id == ref.test_id,
            Test.project_id == access.project_id,
            TestVersion.version == ref.test_version,
        )
    )
    if row is None:
        raise NotFound("Saved test version does not exist in this workspace.")
    return row


def list_tests(session: Session, access: AccessContext, *, after: str = "", limit: int = 20):
    if not 1 <= limit <= 100:
        raise ValueError("Limit must be between 1 and 100.")
    return list(
        session.scalars(
            select(Test)
            .where(Test.project_id == access.project_id, Test.id > after)
            .order_by(Test.id)
            .limit(limit)
        )
    )


def list_test_versions(
    session: Session,
    access: AccessContext,
    test_id: str,
    *,
    after_version: int = 0,
    limit: int = 20,
) -> list[TestVersion]:
    parent = session.get(Test, test_id)
    if parent is None or parent.project_id != access.project_id:
        raise NotFound("Saved test does not exist.")
    if after_version < 0 or not 1 <= limit <= 100:
        raise ValueError("Use a nonnegative version cursor and a limit between 1 and 100.")
    return list(
        session.scalars(
            select(TestVersion)
            .where(TestVersion.test_id == test_id, TestVersion.version > after_version)
            .order_by(TestVersion.version)
            .limit(limit)
        )
    )


def create_test(
    session: Session, access: AccessContext, definition: SavedDefinition
) -> TestVersion:
    definition = SavedDefinition.model_validate(definition.model_dump())
    row = Test(
        id="test_" + uuid4().hex,
        name=definition.name,
        project_id=access.project_id,
        creator_id=access.principal.subject,
    )
    session.add(row)
    session.flush()
    return _version(session, access, row, definition, 1)


def create_test_version(
    session: Session,
    access: AccessContext,
    test_id: str,
    definition: SavedDefinition,
    *,
    expected_version: int,
) -> TestVersion:
    definition = SavedDefinition.model_validate(definition.model_dump())
    row = session.scalar(
        select(Test)
        .where(Test.id == test_id, Test.project_id == access.project_id)
        .with_for_update()
    )
    if row is None:
        raise NotFound("Saved test does not exist.")
    latest = session.scalar(
        select(func.max(TestVersion.version)).where(TestVersion.test_id == row.id)
    )
    if latest != expected_version:
        raise Conflict("Test changed. Reload the latest version.")
    return _version(session, access, row, definition, latest + 1)


def _version(session, access, test, definition, number):
    frozen = definition.frozen()
    version = TestVersion(
        test_id=test.id,
        version=number,
        name=definition.name,
        prompt=definition.prompt,
        evaluation_definition=frozen,
        definition_hash=canonical_hash(frozen),
        approval={
            "state": definition.state,
            "actor_id": access.principal.subject,
            "recorded_at": datetime.now(UTC).isoformat(),
        },
    )
    session.add(version)
    session.flush()
    if definition.criteria is not None:
        selected = [(c["criterion_id"], c["weight"]) for c in definition.criteria]
    else:
        selected = [(cid, definition.legacy["weights"][key]) for key, cid in WEIGHT_IDS.items()]
    session.add_all(
        [
            VersionCriterion(
                test_version_id=version.id,
                criterion_id=cid,
                maximum_points=Decimal(str(points)),
                definition=get_criterion(cid),
            )
            for cid, points in selected
        ]
    )
    session.flush()
    return version


def create_suite(
    session: Session, access: AccessContext, name: str, items: list[TestReference]
) -> SuiteRevision:
    row = Suite(
        id="suite_" + uuid4().hex, project_id=access.project_id, creator_id=access.principal.subject
    )
    session.add(row)
    session.flush()
    return _suite_revision(session, access, row.id, 1, name, items)


def revise_suite(
    session: Session,
    access: AccessContext,
    suite_id: str,
    name: str,
    items: list[TestReference],
    *,
    expected_revision: int,
) -> SuiteRevision:
    row = session.scalar(
        select(Suite)
        .where(Suite.id == suite_id, Suite.project_id == access.project_id)
        .with_for_update()
    )
    if row is None:
        raise NotFound("Suite does not exist.")
    latest = session.scalar(
        select(func.max(SuiteRevision.revision)).where(SuiteRevision.suite_id == suite_id)
    )
    if latest != expected_revision:
        raise Conflict("Suite changed. Reload the latest revision.")
    return _suite_revision(session, access, suite_id, latest + 1, name, items)


def _suite_revision(session, access, suite_id, revision, name, items):
    if not name.strip() or len(name) > 100 or not 1 <= len(items) <= 100:
        raise ValueError("A named suite requires between 1 and 100 items.")
    versions = [get_test_version(session, access, ref) for ref in items]
    row = SuiteRevision(suite_id=suite_id, revision=revision, name=name)
    session.add(row)
    session.flush()
    session.add_all(
        [
            SuiteItem(suite_id=suite_id, revision=revision, position=i, test_version_id=v.id)
            for i, v in enumerate(versions, 1)
        ]
    )
    session.flush()
    return row


def get_suite(session: Session, access: AccessContext, suite_id: str, revision: int):
    row = session.scalar(
        select(SuiteRevision)
        .join(Suite, Suite.id == SuiteRevision.suite_id)
        .where(
            Suite.id == suite_id,
            Suite.project_id == access.project_id,
            SuiteRevision.revision == revision,
        )
    )
    if row is None:
        raise NotFound("Suite revision does not exist.")
    items = list(
        session.scalars(
            select(SuiteItem)
            .where(SuiteItem.suite_id == suite_id, SuiteItem.revision == revision)
            .order_by(SuiteItem.position)
        )
    )
    return row, items


def list_suites(session: Session, access: AccessContext, *, after: str = "", limit: int = 20):
    if not 1 <= limit <= 100:
        raise ValueError("Limit must be between 1 and 100.")
    return list(
        session.scalars(
            select(Suite)
            .where(Suite.project_id == access.project_id, Suite.id > after)
            .order_by(Suite.id)
            .limit(limit)
        )
    )
