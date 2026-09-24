"""Bridge the inline evaluation result to the Week 5 PostgreSQL schema."""

from __future__ import annotations

from dataclasses import replace
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.evaluation.models import TestResult
from app.models import Model, Test, TestRun, TestVersion
from app.repositories.runs import get_run_result, save_run_result


class UnknownTestError(ValueError):
    """The user selected a test that is not present in the database."""


class PostgresResultRepository:
    def __init__(self, session_factory: sessionmaker[Session]):
        self.session_factory = session_factory

    def save(
        self,
        result: TestResult,
        *,
        test_id: str | None = None,
        test_name: str | None = None,
        test_version: int | None = None,
    ) -> TestResult:
        """Save a run and version its name, prompt, and scoring definition."""
        name = (test_name or result.prompt[:100]).strip()
        definition = {
            "expected_keywords": result.metadata["expected_keywords"],
            "minimum_length": result.metadata["minimum_length"],
            "minimum_sentences": result.metadata["minimum_sentences"],
            "forbidden_terms": result.metadata["forbidden_terms"],
        }

        with self.session_factory.begin() as session:
            if test_id is None:
                test = Test(id=f"test_{uuid4().hex}", name=name)
                session.add(test)
                session.flush()
            else:
                # Lock the parent before checking the latest version. Concurrent
                # revisions of one test cannot choose the same version number.
                test = session.scalar(select(Test).where(Test.id == test_id).with_for_update())
                if test is None:
                    raise UnknownTestError("The selected test no longer exists.")

            latest = session.scalar(
                select(TestVersion)
                .where(TestVersion.test_id == test.id)
                .order_by(TestVersion.version.desc())
                .limit(1)
            )
            selected = latest
            if test_version is not None:
                selected = session.scalar(
                    select(TestVersion).where(
                        TestVersion.test_id == test.id,
                        TestVersion.version == test_version,
                    )
                )
                if selected is None:
                    raise UnknownTestError("The selected test version no longer exists.")
            if (
                selected is None
                or selected.name != name
                or selected.prompt != result.prompt
                or selected.evaluation_definition != definition
            ):
                version = TestVersion(
                    test_id=test.id,
                    version=1 if latest is None else latest.version + 1,
                    name=name,
                    prompt=result.prompt,
                    evaluation_definition=definition,
                )
                session.add(version)
                session.flush()
            else:
                version = selected

            model = session.get(Model, result.model)
            if model is None:
                model = Model(id=result.model, name=result.model)
                session.add(model)
                session.flush()

            metadata = {
                **result.metadata,
                "test_id": test.id,
                "test_version": version.version,
                "test_name": version.name,
            }
            usage = metadata.get("usage", {})
            save_run_result(
                session,
                {
                    "run_id": result.id,
                    "test_id": test.id,
                    "test_version": version.version,
                    "model": {"model_id": model.id, "name": model.name},
                    "status": result.status,
                    "configuration": {
                        "temperature": metadata["temperature"],
                        "provider": result.provider,
                        "overall_score": result.score,
                        "passed": result.passed,
                        "metadata": metadata,
                    },
                    "input": {"prompt": result.prompt},
                    "response": {"content": result.response},
                    "evaluations": [
                        {
                            "method": criterion.name,
                            "passed": criterion.passed,
                            "score": criterion.score / 100,
                            "details": {"detail": criterion.detail},
                        }
                        for criterion in result.criteria
                    ],
                    "metrics": {
                        "latency_ms": result.latency_ms,
                        "input_tokens": usage.get("input_tokens", 0),
                        "output_tokens": usage.get("output_tokens", 0),
                    },
                    "started_at": result.created_at,
                    "completed_at": result.created_at,
                    "error": None,
                },
            )

        # Return only once the transaction committed, so the UI cannot show an
        # apparently successful run that has not actually been saved.
        return replace(result, metadata=metadata)

    def recent(self, limit: int = 20) -> list[dict[str, Any]]:
        with self.session_factory() as session:
            run_ids = session.scalars(
                select(TestRun.id)
                .order_by(TestRun.started_at.desc(), TestRun.id.desc())
                .limit(limit)
            ).all()
            return [self._as_api_result(get_run_result(session, run_id)) for run_id in run_ids]

    @staticmethod
    def _as_api_result(saved: dict[str, Any] | None) -> dict[str, Any]:
        if saved is None:
            raise LookupError("A saved run disappeared during retrieval.")

        configuration = saved["configuration"]
        criteria = saved["evaluations"]
        metadata = configuration.get("metadata")
        if metadata is None:
            # Runs imported before the HTTP integration lack the extra UI fields.
            # Keep them visible without pretending their scoring rules can be edited here.
            metadata = {
                "requested_model": saved["model"]["name"],
                "temperature": configuration.get("temperature", 0.2),
                "expected_keywords": [],
                "minimum_length": 0,
                "minimum_sentences": 1,
                "forbidden_terms": [],
                "usage": {
                    "input_tokens": saved["metrics"]["input_tokens"] or 0,
                    "output_tokens": saved["metrics"]["output_tokens"] or 0,
                },
                "schema_version": "imported",
            }
        # Names for older runs come from the relational version, including rows
        # backfilled by migration 0003. Do not rely on old metadata having a name.
        metadata = {**metadata, "test_name": saved["test_name"]}
        score = configuration.get("overall_score")
        if score is None:
            score = (
                round(100 * sum(item["score"] for item in criteria) / len(criteria), 1)
                if criteria
                else 0
            )
        return {
            "id": saved["run_id"],
            "status": saved["status"],
            "prompt": saved["input"]["prompt"],
            "model": saved["model"]["name"],
            "provider": configuration.get("provider", "imported"),
            "response": saved["response"]["content"] or "",
            "score": score,
            "passed": configuration.get(
                "passed", bool(criteria) and all(c["passed"] for c in criteria)
            ),
            "criteria": [
                {
                    "name": criterion["method"],
                    "passed": criterion["passed"],
                    "score": round(criterion["score"] * 100, 1),
                    "detail": criterion.get("details", {}).get("detail", ""),
                }
                for criterion in criteria
            ],
            "latency_ms": saved["metrics"]["latency_ms"] or 0,
            "created_at": saved["started_at"],
            "metadata": metadata,
        }
