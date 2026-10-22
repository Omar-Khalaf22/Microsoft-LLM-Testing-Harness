from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from starlette.concurrency import run_in_threadpool

from app.assistant.provider import AssistantError, OpenAIRecommendationProvider
from app.assistant.schemas import SuggestionRequest
from app.assistant.service import suggest
from app.config import get_settings
from app.database import SessionLocal
from app.evaluation.providers import DemoProvider
from app.repositories.recommendations import RecommendationRepository

router = APIRouter()


def get_recommendation_repository():
    return RecommendationRepository(SessionLocal)


def get_assistant_provider():
    settings = get_settings()
    if settings.llm_provider.strip().lower() == "demo":
        return DemoProvider()
    if settings.llm_provider.strip().lower() != "openai":
        raise HTTPException(
            503,
            detail={
                "code": "assistant_unavailable",
                "message": "Configure a supported provider to generate suggestions.",
            },
        )
    key = settings.openai_api_key.get_secret_value().strip()
    if not key or key == "your-openai-api-key-here":
        raise HTTPException(
            503,
            detail={
                "code": "assistant_unavailable",
                "message": "Configure the assistant API key before generating suggestions.",
            },
        )
    return OpenAIRecommendationProvider(
        key, settings.openai_base_url, settings.assistant_timeout_seconds
    )


@router.post("/assistant/suggest-criteria")
async def suggest_criteria(
    request: SuggestionRequest,
    provider: Annotated[object, Depends(get_assistant_provider)],
    repository: Annotated[RecommendationRepository, Depends(get_recommendation_repository)],
):
    try:
        result = await suggest(request, provider, get_settings().assistant_model)
    except AssistantError as error:
        raise HTTPException(
            error.status_code, detail={"code": error.code, "message": error.message}
        ) from None
    except Exception:
        raise HTTPException(
            502,
            detail={
                "code": "invalid_recommendation",
                "message": (
                    "The assistant could not produce a valid configuration. Retry or "
                    "select criteria manually."
                ),
            },
        ) from None
    try:
        await run_in_threadpool(repository.save, result)
    except Exception:
        raise HTTPException(
            500,
            detail={
                "code": "storage_failure",
                "message": "Suggestions could not be saved. Retry before approving them.",
            },
        ) from None
    return result
