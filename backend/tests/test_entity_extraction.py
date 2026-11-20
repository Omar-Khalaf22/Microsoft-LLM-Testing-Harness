"""Tests for reference based structured entity extraction."""

import pytest

from app.evaluation.registry import evaluate_criterion, validate_criterion


def params(expected, minimum=0.8):
    return {"reference_entities": expected, "ignore_case": True, "minimum_f1": minimum}


def test_perfect_match():
    passed, score, detail = evaluate_criterion(
        "entity_extraction", '["microsoft", "TAMPA"]', params(["Microsoft", "Tampa"]), {}
    )
    assert passed
    assert score == 1.0
    assert "F1" in detail


def test_partial_match():
    passed, score, _ = evaluate_criterion(
        "entity_extraction", '["Microsoft", "Other"]', params(["Microsoft", "Tampa"]), {}
    )
    assert not passed
    assert score == 0.5


def test_empty_sets():
    passed, score, _ = evaluate_criterion("entity_extraction", "[]", params([]), {})
    assert passed
    assert score == 1.0


@pytest.mark.parametrize("response", ["not json", "{}", '["a", "a"]', "[42]"])
def test_invalid_response_rejected(response):
    with pytest.raises(ValueError):
        evaluate_criterion("entity_extraction", response, params(["a"]), {})


def test_invalid_threshold_rejected():
    with pytest.raises(ValueError):
        validate_criterion("entity_extraction", params(["a"], 1.5))
