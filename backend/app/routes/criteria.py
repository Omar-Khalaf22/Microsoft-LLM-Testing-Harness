from fastapi import APIRouter

from app.evaluation.registry import CATALOG_REVISION, list_supported_criteria

router = APIRouter()


@router.get("/evaluation/criteria")
def list_criteria():
    return {"catalog_revision": CATALOG_REVISION, "criteria": list_supported_criteria()}
