"""Human review endpoints never modify automated scores."""
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.repositories.human_reviews import RunNotFound, add_review, list_reviews
from app.schemas.human_reviews import HumanReviewCreate, HumanReviewResponse

router = APIRouter(tags=["human reviews"])

@router.post("/runs/{run_id}/reviews", response_model=HumanReviewResponse, status_code=201)
def post_review(run_id: str, request: HumanReviewCreate,
                session: Annotated[Session, Depends(get_db)]):
    try:
        with session.begin():
            result = add_review(session, run_id, request)
        return result
    except RunNotFound:
        raise HTTPException(404, "Run does not exist") from None

@router.get("/runs/{run_id}/reviews", response_model=list[HumanReviewResponse])
def get_reviews(run_id: str, session: Annotated[Session, Depends(get_db)]):
    try:
        return list_reviews(session, run_id)
    except RunNotFound:
        raise HTTPException(404, "Run does not exist") from None
