from app.database import SessionLocal
from app.models import (
    Model,
)
from app.models.test import Test as TestDefinition
from app.models.test import TestVersion as TestDefinitionVersion
from app.repositories import get_run_result, save_run_result


def test_run_result_round_trip() -> None:
    expected_result = {
        "run_id": "pytest_run_001",
        "test_id": "pytest_json_test",
        "test_version": 1,
        "test_name": "Pytest JSON test",
        "model": {
            "model_id": "pytest_model",
            "name": "pytest-model",
        },
        "status": "completed",
        "configuration": {
            "temperature": 0,
            "max_tokens": 300,
        },
        "input": {
            "prompt": "Return customer information as JSON.",
        },
        "response": {
            "content": '{"name":"John","age":25}',
        },
        "evaluations": [
            {
                "method": "valid_json",
                "passed": True,
                "score": 1.0,
            }
        ],
        "metrics": {
            "latency_ms": 1240,
            "input_tokens": 18,
            "output_tokens": 12,
        },
        "started_at": "2026-09-19T18:00:00+00:00",
        "completed_at": "2026-09-19T18:00:01.240000+00:00",
        "error": None,
    }

    with SessionLocal() as session:
        transaction = session.begin()

        try:
            test = TestDefinition(
                id="pytest_json_test",
                name="Pytest JSON test",
            )
            model = Model(
                id="pytest_model",
                name="pytest-model",
            )
            test_version = TestDefinitionVersion(
                test=test,
                version=1,
                name="Pytest JSON test",
                prompt=expected_result["input"]["prompt"],
                evaluation_definition={"method": "valid_json"},
            )

            session.add_all([test, model, test_version])
            session.flush()

            save_run_result(session, expected_result)
            stored_result = get_run_result(session, "pytest_run_001")

            assert stored_result == expected_result
        finally:
            transaction.rollback()
