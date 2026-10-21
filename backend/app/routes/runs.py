"""HTTP boundary for running tests and reading saved run history."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select

from app.config import get_settings
from app.database import SessionLocal
from app.evaluation.executor import TestExecutor
from app.evaluation.providers import DemoProvider, OpenAICompatibleProvider
from app.models import Test, TestVersion
from app.repositories.prototype_runs import PostgresResultRepository, UnknownTestError
from app.schemas.runs import RunCreateRequest, RunResponse
from app.services.run_service import create_run

router = APIRouter()


def get_executor(request: RunCreateRequest) -> TestExecutor:
    """Choose the provider and store API runs in PostgreSQL.

    The body parameter requires validation before this dependency runs.
    """
    try:
        settings = get_settings()
        provider_name = settings.llm_provider.strip().lower()
        if provider_name == "demo":
            provider = DemoProvider()
        elif provider_name == "openai":
            provider = OpenAICompatibleProvider(
                api_key=settings.openai_api_key.get_secret_value().strip(),
                base_url=settings.openai_base_url,
            )
        else:
            raise ValueError("Unsupported provider configuration")
        return TestExecutor(provider, PostgresResultRepository(SessionLocal))
    except Exception:
        # Dependency errors occur before the route function's error boundary.
        raise HTTPException(status_code=500, detail="The run could not be completed.") from None


def get_result_repository() -> PostgresResultRepository:
    return PostgresResultRepository(SessionLocal)


@router.get("/runs", response_model=list[RunResponse])
def list_runs(
    repository: Annotated[PostgresResultRepository, Depends(get_result_repository)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[RunResponse]:
    try:
        return [RunResponse.model_validate(row) for row in repository.recent(limit)]
    except Exception:
        raise HTTPException(status_code=500, detail="Saved runs could not be loaded.") from None


@router.post("/runs", response_model=RunResponse, status_code=200)
def post_run(
    request: RunCreateRequest,
    executor: Annotated[TestExecutor, Depends(get_executor)],
) -> RunResponse:
    if request.test_id:
        try:
            with SessionLocal() as session:
                if session.get(Test, request.test_id) is None:
                    raise HTTPException(
                        status_code=404, detail="The selected test no longer exists."
                    )
                if request.test_version is not None:
                    version = session.scalar(
                        select(TestVersion.id).where(
                            TestVersion.test_id == request.test_id,
                            TestVersion.version == request.test_version,
                        )
                    )
                    if version is None:
                        raise HTTPException(
                            status_code=404, detail="The selected test version no longer exists."
                        )
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=500, detail="The run could not be completed.") from None
    try:
        return create_run(request, executor=executor)
    except UnknownTestError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except Exception:
        # Includes raw provider parsing errors and service response-validation errors.
        raise HTTPException(status_code=500, detail="The run could not be completed.") from None
