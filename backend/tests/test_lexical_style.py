"""Tests for configured lexical style scores."""

import pytest

from app.evaluation.registry import evaluate_criterion, validate_criterion


def params():
    return {
        "positive_terms": ["great", "excellent"],
        "negative_terms": ["bad", "awful"],
        "target_score": 1.0,
        "tolerance": 0.25,
    }


@pytest.mark.parametrize("criterion_id", ["sentiment_alignment", "tone_consistency"])
def test_positive_alignment(criterion_id):
    passed, score, _ = evaluate_criterion(criterion_id, "Great excellent work", params(), {})
    assert passed
    assert score == 1.0


def test_negative_style_fails():
    passed, score, _ = evaluate_criterion("sentiment_alignment", "Bad awful", params(), {})
    assert not passed
    assert score == 0.0


def test_no_matching_terms():
    passed, score, _ = evaluate_criterion("tone_consistency", "Neutral response", params(), {})
    assert not passed
    assert score == 0.5


@pytest.mark.parametrize("field", ["positive_terms", "negative_terms"])
def test_empty_vocabulary_rejected(field):
    parameters = params()
    parameters[field] = []
    with pytest.raises(ValueError):
        validate_criterion("sentiment_alignment", parameters)
