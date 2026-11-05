"""Repeatable local HTTP history benchmark; synthetic data, no model calls.

Run only against the dedicated P3 test database. Seeds are retained as evidence.
"""

import json
from statistics import mean
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.config import get_settings
from app.database import SessionLocal
from app.models import Model, ModelResponse, Test, TestRun, TestVersion
from app.routes.history import router
from app.storage.access import AccessContext, Principal, get_access


def main():
    from sqlalchemy.engine import make_url

    if make_url(get_settings().database_url).database != "llm_harness_p3_test":
        raise RuntimeError("Benchmark requires the dedicated llm_harness_p3_test database.")
    suffix = uuid4().hex
    access = AccessContext(Principal("benchmark", "benchmark_" + suffix))
    with SessionLocal.begin() as s:
        t = Test(id="benchmark_" + suffix, name="Benchmark", project_id=access.project_id)
        m = Model(id="benchmark_" + suffix, name="synthetic-no-provider")
        s.add_all([t, m])
        s.flush()
        v = TestVersion(
            test_id=t.id, version=1, name=t.name, prompt="benchmark", evaluation_definition={}
        )
        s.add(v)
        s.flush()
        for i in range(100):
            run = TestRun(
                id=f"benchmark_{suffix}_{i:03}",
                test_version_id=v.id,
                model_id=m.id,
                project_id=access.project_id,
                status="completed",
                input_prompt="benchmark " * 500,
                started_at=s.scalar(text("SELECT now()")),
                completed_at=s.scalar(text("SELECT now()")),
                configuration={"provider": "synthetic-benchmark", "overall_score": 0},
            )
            s.add(run)
            s.flush()
            s.add(ModelResponse(run_id=run.id, content="benchmark response " * 3000))
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_access] = lambda: access
    timings = []
    with TestClient(app) as client:
        for _ in range(100):
            start = perf_counter()
            response = client.get("/history/runs?limit=20")
            timings.append((perf_counter() - start) * 1000)
            assert response.status_code == 200 and len(response.json()["items"]) == 20
        payload_bytes = len(response.content)
    with SessionLocal() as s:
        sizes = s.execute(
            text("""SELECT count(*),sum(octet_length(r.input_prompt)+octet_length(m.content)
            +octet_length(r.configuration::text)) FROM test_runs r
            JOIN model_responses m ON m.run_id=r.id
            WHERE r.project_id=:project"""),
            {"project": access.project_id},
        ).one()
        database_bytes = s.scalar(text("SELECT pg_database_size(current_database())"))
    print(
        json.dumps(
            {
                "environment": "local Windows Docker PostgreSQL 16 + FastAPI TestClient",
                "seeded_runs": sizes[0],
                "requests": 100,
                "p95_ms": sorted(timings)[94],
                "mean_ms": mean(timings),
                "first_page_bytes": payload_bytes,
                "seed_prompt_response_configuration_bytes": sizes[1],
                "database_bytes_including_indexes_and_other_tests": database_bytes,
                "azure_target_verified": False,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
