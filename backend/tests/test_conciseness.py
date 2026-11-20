"""Tests for bounded conciseness scoring."""

import pytest

from app.evaluation.registry import evaluate_criterion, validate_criterion


def test_under_limit():
    passed, score, detail = evaluate_criterion(
        "conciseness", "A short answer", {"maximum_words": 3}, {}
    )
    assert passed
    assert score == 1.0
    assert "Words: 3" in detail


def test_over_limit():
    passed, score, _ = evaluate_criterion(
        "conciseness", "One two three four", {"maximum_words": 2}, {}
    )
    assert not passed
    assert score == 0.5


def test_empty_response():
    passed, score, _ = evaluate_criterion(
        "conciseness", "", {"maximum_words": 1}, {}
    )
    assert passed
    assert score == 1.0


@pytest.mark.parametrize("limit", [0, -1, 10001, 1.5])
def test_invalid_word_limit(limit):
    with pytest.raises(ValueError):
        validate_criterion("conciseness", {"maximum_words": limit})
