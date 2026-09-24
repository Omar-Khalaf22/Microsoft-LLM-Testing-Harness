from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models import (
    EvaluationResult,
    Model,
    ModelResponse,
    TestRun,
    TestVersion,
)


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))

    if parsed.tzinfo is None:
        raise ValueError("Run timestamps must include a timezone.")

    return parsed


def save_run_result(
    session: Session,
    result: dict[str, Any],
) -> TestRun:
    run_id = str(result["run_id"])

    if session.get(TestRun, run_id) is not None:
        raise ValueError(f"Run {run_id!r} already exists.")

    test_version = session.scalar(
        select(TestVersion).where(
            TestVersion.test_id == result["test_id"],
            TestVersion.version == result["test_version"],
        )
    )

    if test_version is None:
        raise ValueError("The referenced test and test version do not exist.")

    model_data = result["model"]
    model = session.get(Model, model_data["model_id"])

    if model is None:
        raise ValueError(f"Model {model_data['model_id']!r} does not exist.")

    if model.name != model_data["name"]:
        raise ValueError("The supplied model name does not match the stored model.")

    metrics = result.get("metrics", {})
    completed_at = result.get("completed_at")
    error = result.get("error")

    if error is not None and not isinstance(error, str):
        raise ValueError("The error field must be a string or null.")

    run = TestRun(
        id=run_id,
        test_version_id=test_version.id,
        model_id=model.id,
        status=result["status"],
        configuration=dict(result.get("configuration", {})),
        input_prompt=result["input"]["prompt"],
        latency_ms=metrics.get("latency_ms"),
        input_tokens=metrics.get("input_tokens"),
        output_tokens=metrics.get("output_tokens"),
        started_at=_parse_datetime(result["started_at"]),
        completed_at=(_parse_datetime(completed_at) if completed_at is not None else None),
        error=error,
    )

    response_data = result.get("response")

    if response_data is not None and response_data.get("content") is not None:
        run.response = ModelResponse(
            content=str(response_data["content"]),
        )

    for evaluation in result.get("evaluations", []):
        run.evaluations.append(
            EvaluationResult(
                method=evaluation["method"],
                passed=evaluation["passed"],
                score=Decimal(str(evaluation["score"])),
                details=dict(evaluation.get("details", {})),
            )
        )

    session.add(run)
    session.flush()

    return run


def get_run_result(
    session: Session,
    run_id: str,
) -> dict[str, Any] | None:
    statement = (
        select(TestRun)
        .where(TestRun.id == run_id)
        .options(
            joinedload(TestRun.test_version),
            joinedload(TestRun.model),
            joinedload(TestRun.response),
            selectinload(TestRun.evaluations),
        )
    )

    run = session.scalar(statement)

    if run is None:
        return None

    evaluations = []

    for evaluation in run.evaluations:
        evaluation_data: dict[str, Any] = {
            "method": evaluation.method,
            "passed": evaluation.passed,
            "score": float(evaluation.score),
        }

        if evaluation.details:
            evaluation_data["details"] = evaluation.details

        evaluations.append(evaluation_data)

    return {
        "run_id": run.id,
        "test_id": run.test_version.test_id,
        "test_version": run.test_version.version,
        "test_name": run.test_version.name,
        "model": {
            "model_id": run.model.id,
            "name": run.model.name,
        },
        "status": run.status,
        "configuration": run.configuration,
        "input": {
            "prompt": run.input_prompt,
        },
        "response": {
            "content": (run.response.content if run.response is not None else None),
        },
        "evaluations": evaluations,
        "metrics": {
            "latency_ms": run.latency_ms,
            "input_tokens": run.input_tokens,
            "output_tokens": run.output_tokens,
        },
        "started_at": run.started_at.isoformat(),
        "completed_at": (run.completed_at.isoformat() if run.completed_at is not None else None),
        "error": run.error,
    }
