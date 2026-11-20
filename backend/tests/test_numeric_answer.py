"""Tests for single numeric answer validation."""

import pytest

from app.evaluation.registry import evaluate_criterion, validate_criterion


def test_exact_decimal_answer():
    parameters = {"expected_value": "0.3", "absolute_tolerance": "0"}
    passed, score, _ = evaluate_criterion("mathematical_correctness", "0.30", parameters, {}
    assert passed
    assert score == 1.0


def test_numeric_tolerance():
    parameters = {"expected_value": "3.14", "absolute_tolerance": "0.01"}
    passed, score, _ = evaluate_criterion("mathematical_correctness", "3.145", parameters, {}
    assert passed
    assert score == 1.0
    passed, score, _ = evaluate_criterion("mathematical_correctness", "3.16", parameters, {}
    assert not passed
    assert score == 0.0


@pytest.mark.parametrize("response", ["2 + 2 = 4", "NaN", "1,000", ""])
def test_non_numeric_response_fails(response):
    parameters = {"expected_value": "4", "absolute_tolerance": "0"}
    passed, score, _ = evaluate_criterion("mathematical_correctness", response, parameters, {}
    assert not passed
    assert score == 0.0


@pytest.mark.parametrize(
    "parameters",
    [
        {"expected_value": "NaN", "absolute_tolerance": "0"},
        {"expected_value": "1", "absolute_tolerance": "-1"},
        {"expected_value": "1", "absolute_tolerance": "abc"},
    ],
)
def test_invalid_numeric_parameters(parameters):
    with pytest.raises(ValueError):
        validate_criterion("mathematical_correctness", parameters)
