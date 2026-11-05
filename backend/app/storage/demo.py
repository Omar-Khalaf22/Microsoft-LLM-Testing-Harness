"""Explicit local storage handoff example. Makes no paid/network model requests."""

import json

from app.config import get_settings
from app.database import SessionLocal
from app.evaluation.executor import TestExecutor
from app.evaluation.providers import DemoProvider
from app.storage.access import get_access
from app.storage.definitions import create_test
from app.storage.executions import claim_attempt, request_for_attempt, reserve_attempts
from app.storage.executor_adapter import ReservedResultRepository
from app.storage.records import ProfileSelection, SavedDefinition, TestReference


def main():
    if get_settings().app_env != "development":
        raise RuntimeError("The demonstration requires explicit development mode.")
    access = get_access(None)
    with SessionLocal.begin() as session:
        version = create_test(
            session,
            access,
            SavedDefinition(
                name="Storage handoff example",
                prompt="Return JSON with count 3",
                objective="Produce machine readable data",
                state="approved",
                criteria=[{"criterion_id": "valid_json", "parameters": {}, "weight": 100}],
            ),
        )
        ref = TestReference(test_id=version.test_id, test_version=version.version)
    profile = ProfileSelection(
        profile_id="local-demo",
        profile_revision=1,
        provider="local_demo",
        endpoint_id="local-demo",
        requested_model="demo-json-v1",
    )
    with SessionLocal.begin() as session:
        plan = reserve_attempts(session, access, [profile], test=ref)
    run_id = plan["attempts"][0]["run_id"]
    with SessionLocal.begin() as session:
        token = claim_attempt(session, access, run_id)
        request = request_for_attempt(session, access, run_id)
    repository = ReservedResultRepository(SessionLocal, access, run_id, token)
    result = TestExecutor(DemoProvider(), repository).execute(request)
    print(
        json.dumps(
            {
                "test": ref.model_dump(),
                "execution_id": plan["execution_id"],
                "run_id": result.id,
                "score": result.score,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
