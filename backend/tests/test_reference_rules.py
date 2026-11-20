"""Tests for explicit reference coverage and phrase rules."""

import pytest

from app.evaluation.registry import evaluate_criterion, validate_criterion


def test_completeness_coverage():
    params = {
        "required_facts": ["Microsoft", "Tampa"],
        "ignore_case": True,
        "minimum_coverage": 0.75,
    }
    passed, score, _ = evaluate_criterion("completeness", "microsoft", params, {})
    assert not passed
    assert score == 0.5
    passed, score, _ = evaluate_criterion("completeness", "Microsoft Tampa", params, {})
    assert passed
    assert score == 1.0


def test_contradiction_phrases():
    params = {"contradicting_phrases": ["always false"], "ignore_case": True}
    passed, score, _ = evaluate_criterion(
        "contradiction_detection", "This is ALWAYS FALSE", params, {}
    )
    assert not passed
    assert score == 0.0


def test_answer_markers():
    params = {"answer_markers": ["42"], "ignore_case": True}
    passed, score, _ = evaluate_criterion("answerability", "The answer is 42", params, {})
    assert passed
    assert score == 1.0
    passed, score, _ = evaluate_criterion("answerability", "Unknown", params, {})
    assert not passed
    assert score == 0.0


@pytest.mark.parametrize(
    ("criterion_id", "parameters"),
    [
        (
            "completeness",
            {"required_facts": [], "ignore_case": True, "minimum_coverage": 1},
        ),
        (
            "contradiction_detection",
            {"contradicting_phrases": [], "ignore_case": True},
        ),
        ("answerability", {"answer_markers": [], "ignore_case": True}),
    ],
)
def test_invalid_reference_rules(criterion_id, parameters):
    with pytest.raises(ValueError):
        validate_criterion(criterion_id, parameters)
