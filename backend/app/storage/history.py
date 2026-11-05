"""Scope-first keyset pagination selecting summaries rather than evidence blobs."""

import base64
import json
from datetime import datetime

from sqlalchemy import Numeric, cast, func, select, tuple_
from sqlalchemy.orm import Session

from app.models import Model, TestRun, TestVersion
from app.storage.access import AccessContext


def _cursor(created_at, run_id, project):
    return (
        base64.urlsafe_b64encode(
            json.dumps([1, created_at.isoformat(), run_id, project], separators=(",", ":")).encode()
        )
        .decode()
        .rstrip("=")
    )


def _decode(cursor, project):
    try:
        if len(cursor) > 1024:
            raise ValueError()
        data = json.loads(
            base64.b64decode(cursor + "=" * (-len(cursor) % 4), altchars=b"-_", validate=True)
        )
        if len(data) != 4 or data[0] != 1 or data[3] != project or not isinstance(data[2], str):
            raise ValueError()
        time = datetime.fromisoformat(data[1])
        if time.tzinfo is None or not data[2]:
            raise ValueError()
        return time, data[2]
    except Exception:
        raise ValueError("Invalid history cursor.") from None


def list_history_summaries(
    session: Session, access: AccessContext, *, limit: int = 20, cursor: str | None = None
) -> dict:
    if not 1 <= limit <= 100:
        raise ValueError("Limit must be between 1 and 100.")
    config = TestRun.configuration
    stmt = (
        select(
            TestRun.id,
            TestRun.status,
            TestRun.created_at,
            TestRun.latency_ms,
            TestRun.execution_id,
            TestRun.rerun_of_run_id,
            TestVersion.test_id,
            TestVersion.version,
            TestVersion.name,
            func.coalesce(
                config["result_snapshot"]["model"].astext,
                TestRun.evidence["target"]["actual_model"].astext,
                Model.name,
            ).label("model"),
            func.coalesce(
                config["result_snapshot"]["provider"].astext,
                config["snapshot"]["profile"]["provider"].astext,
                config["provider"].astext,
                "imported",
            ).label("provider"),
            cast(
                func.coalesce(
                    config["result_snapshot"]["score"].astext, config["overall_score"].astext
                ),
                Numeric,
            ).label("score"),
        )
        .join(TestVersion, TestVersion.id == TestRun.test_version_id)
        .join(Model, Model.id == TestRun.model_id)
        .where(TestRun.project_id == access.project_id)
    )
    if cursor:
        time, run_id = _decode(cursor, access.project_id)
        stmt = stmt.where(tuple_(TestRun.created_at, TestRun.id) < tuple_(time, run_id))
    rows = session.execute(
        stmt.order_by(TestRun.created_at.desc(), TestRun.id.desc()).limit(limit + 1)
    ).all()
    items = [
        {
            "id": r.id,
            "status": r.status,
            "created_at": r.created_at.isoformat(),
            "model": r.model,
            "provider": r.provider,
            "score": float(r.score) if r.score is not None else None,
            "latency_ms": r.latency_ms,
            "metadata": {
                "test_id": r.test_id,
                "test_version": r.version,
                "test_name": r.name,
                "execution_id": r.execution_id,
                "rerun_of_run_id": r.rerun_of_run_id,
            },
        }
        for r in rows[:limit]
    ]
    return {
        "items": items,
        "next_cursor": _cursor(rows[limit - 1].created_at, rows[limit - 1].id, access.project_id)
        if len(rows) > limit
        else None,
    }
