"""Regression tests for bounded Unicode script scoring."""

import pytest

from app.evaluation.registry import evaluate_criterion, validate_criterion


@pytest.mark.parametrize("criterion_id", ["language_detection", "response_language"])
def test_arabic_script(criterion_id):
    passed, score, detail = evaluate_criterion(
        criterion_id,
        "مرحبا بالعالم",
        {"expected_language": "ar", "minimum_script_fraction": 0.8},
        {},
    )
    assert passed
    assert score == 1.0
    assert "ar script" in detail


@pytest.mark.parametrize("criterion_id", ["language_detection", "response_language"])
def test_mismatched_script(criterion_id):
    passed, score, _ = evaluate_criterion(
        criterion_id,
        "Hello world",
        {"expected_language": "ar", "minimum_script_fraction": 0.8},
        {},
    )
    assert not passed
    assert score == 0.0


def test_reject_empty_text():
    with pytest.raises(ValueError, match="without letters"):
        evaluate_criterion(
            "response_language",
            "123 !!!",
            {"expected_language": "en", "minimum_script_fraction": 0.8},
            {},
        )


def test_reject_invalid_language():
    with pytest.raises(ValueError):
        validate_criterion(
            "response_language",
            {"expected_language": "xx", "minimum_script_fraction": 0.8},
        )
