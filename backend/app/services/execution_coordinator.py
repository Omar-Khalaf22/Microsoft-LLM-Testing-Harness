"""Dispatch committed P3 reservations using ordered attempts and short leases."""

import logging
from contextlib import asynccontextmanager, contextmanager
from threading import Event, Thread

from sqlalchemy import func, or_, select, true
from sqlalchemy.exc import SQLAlchemyError

from app.config import get_settings
from app.database import SessionLocal
from app.evaluation.executor import TestExecutor
from app.models import Execution, TestRun
from app.services.model_profiles import judge_context, resolve_archived, target_provider
from app.storage.access import AccessContext, Principal
from app.storage.errors import Conflict
from app.storage.executions import (
    claim_attempt,
    get_attempt,
    heartbeat_attempt,
    interrupt_owned_attempt,
    recover_expired_attempt,
    request_for_attempt,
)
from app.storage.executor_adapter import ReservedResultRepository
from app.storage.records import ProfileSelection

logger = logging.getLogger("harness.operations")
HEARTBEAT_SECONDS = 30


@asynccontextmanager
async def execution_lifespan(app):
    stop = Event()
    settings = get_settings()
    worker = Thread(target=_worker, args=(settings, stop), name="reserved-runs", daemon=True)
    worker.start()
    try:
        yield
    finally:
        stop.set()
        worker.join(timeout=1)


def _worker(settings, stop):
    while not stop.is_set():
        try:
            if dispatch_next(settings):
                continue
        except (Conflict, SQLAlchemyError):
            logger.warning("execution_dispatch category=storage_unavailable")
        stop.wait(0.5)


def dispatch_next(settings, sessions=SessionLocal):
    """Process the earliest dispatchable attempt. Imported/inline records never enter the queue."""
    first = (
        select(TestRun.id, TestRun.status, TestRun.lease_until)
        .where(TestRun.execution_id == Execution.id, TestRun.status.in_(("pending", "running")))
        .order_by(TestRun.suite_position, TestRun.model_position)
        .limit(1)
        .lateral()
    )
    with sessions.begin() as session:
        candidate = session.execute(
            select(Execution.actor_id, first.c.id, first.c.status)
            .select_from(Execution)
            .join(first, true())
            .where(
                Execution.project_id == settings.project_id,
                Execution.status.in_(("pending", "running")),
                Execution.snapshot["dispatch"].as_boolean().is_(True),
                or_(first.c.status == "pending", first.c.lease_until <= func.clock_timestamp()),
            )
            .order_by(Execution.created_at, Execution.id)
            .limit(1)
            .with_for_update(of=Execution, skip_locked=True)
        ).first()
        if candidate is None:
            return False
        actor, run_id, status = candidate
        access = AccessContext(Principal(actor, settings.project_id))
        if status == "running":
            recover_expired_attempt(session, access, run_id)
            return True
        token = claim_attempt(session, access, run_id)
    _execute(settings, sessions, access, run_id, token)
    return True


def _execute(settings, sessions, access, run_id, token):
    try:
        with sessions.begin() as session:
            heartbeat_attempt(session, access, run_id, token)
            run = get_attempt(session, access, run_id)
            archived = ProfileSelection.model_validate(run.configuration["snapshot"]["profile"])
            request = request_for_attempt(session, access, run_id)
        profile = resolve_archived(settings, archived)
        repository = ReservedResultRepository(sessions, access, run_id, token)
        with _heartbeat(sessions, access, run_id, token):
            TestExecutor(
                target_provider(settings, profile),
                repository,
                judge_context=judge_context(settings),
            ).execute(request)
    except Exception:
        logger.warning("attempt_failed id=%s category=interrupted", run_id)
        try:
            with sessions.begin() as session:
                interrupt_owned_attempt(session, access, run_id, token)
        except Conflict:
            pass  # A stale worker cannot modify an attempt after lease loss.


@contextmanager
def _heartbeat(sessions, access, run_id, token):
    stop = Event()

    def renew():
        while not stop.wait(HEARTBEAT_SECONDS):
            try:
                with sessions.begin() as session:
                    heartbeat_attempt(session, access, run_id, token)
            except Conflict:
                return
            except SQLAlchemyError:
                logger.warning("heartbeat_failed id=%s category=storage_unavailable", run_id)

    worker = Thread(target=renew, name="attempt-heartbeat", daemon=True)
    worker.start()
    try:
        yield
    finally:
        stop.set()
        worker.join(timeout=1)
