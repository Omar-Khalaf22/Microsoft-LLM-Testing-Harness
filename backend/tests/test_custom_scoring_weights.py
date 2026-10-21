"""Custom scoring tests for the integrated run workflow."""

import pytest
from pydantic import ValidationError

from app.evaluation.scoring import score_response
from app.schemas.runs import RunCreateRequest


def test_custom_weights_affect_score():
    weights = {
        "keywords": 0,
        "relevance": 0,
        "length": 0,
        "sentences": 0,
        "forbidden": 0,
        "nonempty": 100,
    }
    score, criteria = score_response("hello", "hello", [], 0, 1, [], weights)
    assert score == 100
    assert sum(item.score for item in criteria) == 100


def test_custom_weights_reject_invalid_total():
    with pytest.raises(ValidationError):
        RunCreateRequest(
            test_name="Example",
            prompt="Say hello",
            scoring_weights={
                "keywords": 30,
                "relevance": 20,
                "length": 15,
                "sentences": 15,
                "forbidden": 10,
                "nonempty": 9,
            },
        )


def test_custom_weights_accept_exact_total():
    request = RunCreateRequest(
        test_name="Example",
        prompt="Say hello",
        scoring_weights={
            "keywords": 30,
            "relevance": 20,
            "length": 15,
            "sentences": 15,
            "forbidden": 10,
            "nonempty": 10,
        },
    )
    assert sum(request.scoring_weights.values()) == 100
