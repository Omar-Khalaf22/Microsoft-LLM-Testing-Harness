"""Tests for typed named entity accuracy."""

import pytest

from app.evaluation.registry import evaluate_criterion, validate_criterion


def params():
    return {
        "reference_entities": [
            {"text": "Microsoft", "label": "ORG"},
            {"text": "Tampa", "label": "LOC"},
        ],
        "ignore_case": True,
        "minimum_f1": 0.8,
    }


def test_perfect_typed_match():
    response = '[{"text":"microsoft","label":"ORG"},{"text":"Tampa","label":"LOC"}]'
    passed, score, detail = evaluate_criterion("named_entity_accuracy", response, params(), {})
    assert passed
    assert score == 1.0
    assert "F1" in detail


def test_wrong_label_reduces_score():
    response = '[{"text":"Microsoft","label":"LOC"},{"text":"Tampa","label":"LOC"}]'
    passed, score, _ = evaluate_criterion("named_entity_accuracy", response, params(), {})
    assert not passed
    assert score == 0.5


@pytest.mark.parametrize(
    "response",
    [
        "not json",
        "{}",
        '[{"text":"Microsoft"}]',
        '[{"text":"Microsoft","label":"ORG"},{"text":"Microsoft","label":"ORG"}]',
    ],
)
def test_invalid_prediction_rejected(response):
    with pytest.raises(ValueError):
        evaluate_criterion("named_entity_accuracy", response, params(), {})


def test_invalid_reference_rejected():
    with pytest.raises(ValueError):
        validate_criterion(
            "named_entity_accuracy",
            {"reference_entities": [{"text": "A"}], "ignore_case": True, "minimum_f1": 0.8},
        )
