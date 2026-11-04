"""Transactional append only human review history."""
from sqlalchemy import func, select

from app.models.run import TestRun
from app.models.human_review import HumanReview

class RunNotFound(LookupError):
    pass

def add_review(session, run_id, request):
    run = session.scalar(select(TestRun).where(TestRun.id == run_id).with_for_update())
    if run is None:
        raise RunNotFound("Run does not exist")
    last = session.scalar(select(func.max(HumanReview.revision)).where(
        HumanReview.run_id == run_id,
        HumanReview.reviewer_id == request.reviewer_id,
    )) or 0
    review = HumanReview(run_id=run_id, reviewer_id=request.reviewer_id,
                         rating=request.rating, rationale=request.rationale, revision=last + 1)
    session.add(review)
    session.flush()
    session.refresh(review)
    return review

def list_reviews(session, run_id):
    if session.get(TestRun, run_id) is None:
        raise RunNotFound("Run does not exist")
    return list(session.scalars(select(HumanReview).where(HumanReview.run_id == run_id)
                                .order_by(HumanReview.created_at, HumanReview.id)))
