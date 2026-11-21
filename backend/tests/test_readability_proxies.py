"""Tests for configured readability and repetition proxy scoring."""

import pytest

from app.evaluation.registry import evaluate_criterion, validate_criterion


def params():
    return {"minimum_ratio": 1.0, "minimum_words": 2, "maximum_words": 5}


def test_clarity_sentence_lengths():
    passed, score, _ = evaluate_criterion(
        "clarity", "A short sentence. Another clear sentence.", params(), {}
    )
    assert passed
    assert score == 1.0


def test_clarity_long_sentence():
    passed, score, _ = evaluate_criterion(
        "clarity", "A very long sentence with many extra words.", params(), {}
    )
    assert not passed
    assert score == 0.0


def test_coherence_repetition():
    passed, score, _ = evaluate_criterion(
        "coherence", "Repeat this. Repeat this.", params(), {}
    )
    assert not passed
    assert score == 0.5


def test_coherence_unique_sentences():
    passed, score, _ = evaluate_criterion(
        "coherence", "First statement. Second statement.", params(), {}
    )
    assert passed
    assert score == 1.0


@pytest.mark.parametrize("criterion_id", ["clarity", "coherence"])
def test_empty_response(criterion_id):
    passed, score, _ = evaluate_criterion(criterion_id, "", params(), {})
    assert not passed
    assert score == 0.0


def test_invalid_ratio():
    invalid = params()
    invalid["minimum_ratio"] = 2.0
    with pytest.raises(ValueError):
        validate_criterion("clarity", invalid)
