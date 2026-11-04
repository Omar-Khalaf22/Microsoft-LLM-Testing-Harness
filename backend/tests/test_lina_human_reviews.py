"""Strict human review request validation."""
import pytest
from pydantic import ValidationError
from app.schemas.human_reviews import HumanReviewCreate

@pytest.mark.parametrize("rating",[-1,101,True,2.5,"50"])
def test_reject_invalid_ratings(rating):
    with pytest.raises(ValidationError):
        HumanReviewCreate(reviewer_id="reviewer",rating=rating,rationale="A reason")

def test_valid_boundaries():
    for score in (0,100):
        assert HumanReviewCreate(reviewer_id="r",rating=score,rationale="Valid").rating==score

def test_reject_blank():
    with pytest.raises(ValidationError):
        HumanReviewCreate(reviewer_id=" ",rating=50,rationale="Valid")
    with pytest.raises(ValidationError):
        HumanReviewCreate(reviewer_id="r",rating=50,rationale=" ")
