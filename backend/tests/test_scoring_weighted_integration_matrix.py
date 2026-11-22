"""Integration regressions for weighted response scoring."""

import pytest

from app.evaluation.points import earned_points, total_points
from app.evaluation.scoring import score_response
from app.evaluation.weights import ScoringWeights, default_weights


def test_default_scoring_allocations_total_one_hundred():
    weights = default_weights()
    assert sum(weights.values()) == 100
    assert ScoringWeights.model_validate(weights).model_dump() == weights


def test_score_matches_criterion_points_and_metadata():
    total, criteria = score_response(
        prompt="Explain database indexes",
        response="Database indexes speed up queries. They improve lookup performance.",
        keywords=["indexes", "queries"],
        minimum_length=10,
    )
    assert len(criteria) == 6
    assert len({item.criterion_id for item in criteria}) == 6
    assert total == total_points([item.score for item in criteria])
    assert sum(item.maximum_points for item in criteria) == 100
    for item in criteria:
        assert 0 <= item.score <= item.maximum_points
        assert 0 <= item.normalized_score <= 1
        assert item.score == earned_points(item.normalized_score, item.maximum_points)


def test_custom_weights_assign_all_points_to_keywords():
    weights = {
        "keyword": 100.0,
        "relevance": 0.0,
        "length": 0.0,
        "sentences": 0.0,
        "forbidden": 0.0,
        "valid": 0.0,
    }
    total, criteria = score_response(
        prompt="Describe databases",
        response="Databases are useful.",
        keywords=["Databases", "missing"],
        minimum_length=1,
        weights=weights,
    )
    assert total == 50.0
    assert criteria[0].score == 50.0
    assert all(item.score == 0.0 for item in criteria[1:])


def test_empty_response_stays_within_allocated_points():
    total, criteria = score_response(
        prompt="Explain a query",
        response="",
        keywords=["query"],
        minimum_length=20,
        minimum_sentences=2,
        forbidden_terms=["secret"],
    )
    assert total == total_points([item.score for item in criteria])
    assert 0 <= total <= 100
    assert criteria[-1].passed is False


@pytest.mark.parametrize(
    "weights",
    [
        {"keyword": 101.0},
        {"keyword": -1.0},
        {"keyword": float("nan")},
        {"keyword": float("inf")},
        {"keyword": True},
        {"unknown": 1.0},
    ],
)
def test_invalid_weight_configurations_are_rejected(weights):
    with pytest.raises(ValueError):
        score_response("prompt", "response", [], 1, weights=weights)


@pytest.mark.parametrize(
    ("ratio", "maximum", "expected"),
    [
        (0.0, 100.0, 0.0),
        (1.0, 100.0, 100.0),
        (0.5, 33.33, 16.67),
        (0.3333333333, 30.0, 10.0),
    ],
)
def test_point_rounding_is_deterministic(ratio, maximum, expected):
    assert earned_points(ratio, maximum) == expected
