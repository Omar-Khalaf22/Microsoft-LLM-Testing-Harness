"""Boundary regressions for deterministic text scoring criteria."""

import pytest

from app.evaluation.registry import evaluate_criterion


@pytest.mark.parametrize(
    ("criterion_id", "response", "parameters", "expected_pass", "expected_score"),
    [
        ("minimum_characters", "", {"count": 0}, True, 1.0),
        ("minimum_characters", "abc", {"count": 3}, True, 1.0),
        ("minimum_characters", "ab", {"count": 4}, False, 0.5),
        ("maximum_characters", "", {"count": 0}, True, 1.0),
        ("maximum_characters", "abc", {"count": 3}, True, 1.0),
        ("maximum_characters", "abcd", {"count": 3}, False, 0.0),
        ("minimum_sentences", "One.", {"count": 1}, True, 1.0),
        ("minimum_sentences", "One.", {"count": 2}, False, 0.5),
        ("minimum_sentences", "One. Two.", {"count": 2}, True, 1.0),
        ("required_phrases", "Alpha beta", {"phrases": ["Alpha"]}, True, 1.0),
        ("required_phrases", "Alpha", {"phrases": ["Alpha", "Beta"]}, False, 0.5),
        ("forbidden_phrases", "Alpha", {"phrases": ["Beta"]}, True, 1.0),
        ("forbidden_phrases", "Alpha beta", {"phrases": ["Beta"]}, False, 0.0),
        ("required_keywords", "ALPHA beta", {"keywords": ["alpha"]}, True, 1.0),
        ("forbidden_keywords", "ALPHA", {"keywords": ["alpha"]}, False, 0.0),
    ],
)
def test_content_boundary_scores(
    criterion_id, response, parameters, expected_pass, expected_score
):
    passed, score, detail = evaluate_criterion(criterion_id, response, parameters, {})
    assert passed is expected_pass
    assert score == pytest.approx(expected_score)
    assert detail


@pytest.mark.parametrize(
    ("criterion_id", "parameters"),
    [
        ("minimum_characters", {"count": -1}),
        ("maximum_characters", {"count": -1}),
        ("minimum_sentences", {"count": -1}),
        ("required_phrases", {"phrases": []}),
        ("forbidden_keywords", {"keywords": []}),
    ],
)
def test_invalid_content_thresholds_rejected(criterion_id, parameters):
    with pytest.raises(ValueError):
        evaluate_criterion(criterion_id, "example", parameters, {})
