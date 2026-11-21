"""Tests for configured contradiction pair scoring."""

import pytest

from app.evaluation.registry import evaluate_criterion, validate_criterion


def params():
    return {
        "contradiction_pairs": [["service is available", "service is unavailable"]],
        "ignore_case": True,
        "maximum_contradictions": 0,
    }


def test_consistent_assertion():
    passed, score, _ = evaluate_criterion(
        "reasoning_consistency", "The service is available.", params(), {}
    )
    assert passed
    assert score == 1.0


def test_explicit_contradiction():
    response = "Service is available. Later: service is unavailable."
    passed, score, detail = evaluate_criterion(
        "reasoning_consistency", response, params(), {}
    )
    assert not passed
    assert score == 0.0
    assert "detected: 1/1" in detail


def test_no_assertions_is_not_flagged():
    passed, score, _ = evaluate_criterion(
        "reasoning_consistency", "No service information.", params(), {}
    )
    assert passed
    assert score == 1.0


@pytest.mark.parametrize("pairs", [[], [["one"]], [["one", "two", "three"]]])
def test_invalid_pairs(pairs):
    parameters = params()
    parameters["contradiction_pairs"] = pairs
    with pytest.raises(ValueError):
        validate_criterion("reasoning_consistency", parameters)
