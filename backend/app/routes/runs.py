"""HTTP boundary for the temporary inline-input Run workflow."""

import os
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.evaluation.executor import TestExecutor
from app.evaluation.providers import DemoProvider, OpenAICompatibleProvider
from app.evaluation.repository import JsonResultRepository
from app.schemas.runs import RunCreateRequest, RunResponse
from app.services.run_service import create_run

router = APIRouter()


def get_executor() -> TestExecutor:
    """Use process environment like the demo, with a separate API result file.

    Construction is request-scoped. The existing repository lock does not protect
    this temporary file across requests/processes; concurrent storage needs follow-up.
    These environment variables are not currently part of app.config.Settings.
    """
    try:
        provider_name = os.getenv("LLM_PROVIDER", "demo").strip().lower()
        if provider_name == "demo":
            provider = DemoProvider()
        elif provider_name == "openai":
            provider = OpenAICompatibleProvider(
                api_key=os.getenv("OPENAI_API_KEY", ""),
                base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            )
        else:
            raise ValueError("Unsupported provider configuration")
        path = Path(__file__).resolve().parents[2] / "data" / "api_results.jsonl"
        return TestExecutor(provider, JsonResultRepository(path))
    except Exception:
        # Dependency errors occur before the route function's error boundary.
        raise HTTPException(status_code=500, detail="The run could not be completed.") from None


@router.post("/runs", response_model=RunResponse, status_code=200)
def post_run(
    request: RunCreateRequest,
    executor: Annotated[TestExecutor, Depends(get_executor)],
) -> RunResponse:
    try:
        return create_run(request, executor=executor)
    except Exception:
        # Includes raw provider parsing errors and service response-validation errors.
        raise HTTPException(status_code=500, detail="The run could not be completed.") from None
