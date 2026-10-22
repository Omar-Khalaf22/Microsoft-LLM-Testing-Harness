from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.assistant.provider import AssistantError, OpenAIRecommendationProvider
from app.assistant.registry import CriteriaRegistry, RegistryUnavailable, get_runtime_registry
from app.assistant.schemas import SuggestCriteriaRequest, SuggestCriteriaResponse
from app.assistant.service import RecommendationService
from app.config import get_settings

router = APIRouter(prefix="/assistant", tags=["assistant"])


def get_registry() -> CriteriaRegistry:
    return get_runtime_registry()


def get_service() -> RecommendationService:
    try:
        registry = get_registry()
    except RegistryUnavailable:
        raise HTTPException(
            503,
            detail={"code": "registry_unavailable", "message": "Criteria registry is unavailable."},
        ) from None
    return RecommendationService(registry, OpenAIRecommendationProvider(get_settings()))


@router.post("/suggest-criteria", response_model=SuggestCriteriaResponse)
async def suggest_criteria(
    request: SuggestCriteriaRequest,
    service: Annotated[RecommendationService, Depends(get_service)],
) -> SuggestCriteriaResponse:
    try:
        return await service.suggest(request)
    except AssistantError as exc:
        raise HTTPException(
            exc.status_code, detail={"code": exc.code, "message": exc.message}
        ) from None
