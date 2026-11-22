"""Fast behavioral scoring regression cases for deterministic criteria."""

import pytest

from app.evaluation.registry import evaluate_criterion

CASES = [
    ("required_keywords", "Alpha beta", {"keywords": ["alpha", "beta"]}, True, 1.0),
    ("required_keywords", "Alpha", {"keywords": ["alpha", "beta"]}, False, 0.5),
    ("forbidden_keywords", "safe", {"keywords": ["secret"]}, True, 1.0),
    ("forbidden_keywords", "secret", {"keywords": ["secret"]}, False, 0.0),
    ("required_phrases", "Hello world", {"phrases": ["hello world"]}, True, 1.0),
    ("required_phrases", "Hello", {"phrases": ["hello world"]}, False, 0.0),
    ("forbidden_phrases", "safe", {"phrases": ["secret"]}, True, 1.0),
    ("forbidden_phrases", "secret", {"phrases": ["secret"]}, False, 0.0),
    ("exact_match", "Hello", {"expected": "Hello"}, True, 1.0),
    ("exact_match", "hello", {"expected": "Hello"}, False, 0.0),
    ("contains_text", "Hello world", {"text": "world"}, True, 1.0),
    ("contains_text", "Hello world", {"text": "WORLD"}, False, 0.0),
    ("case_insensitive_match", "HELLO", {"expected": "hello"}, True, 1.0),
    ("case_insensitive_match", "hello!", {"expected": "hello"}, False, 0.0),
    ("minimum_characters", "abc", {"count": 3}, True, 1.0),
    ("minimum_characters", "ab", {"count": 4}, False, 0.5),
    ("maximum_characters", "abc", {"count": 3}, True, 1.0),
    ("maximum_characters", "abcd", {"count": 3}, False, 0.0),
    ("minimum_sentences", "One. Two.", {"count": 2}, True, 1.0),
    ("minimum_sentences", "One.", {"count": 2}, False, 0.5),
    ("conciseness", "one two", {"maximum_words": 2}, True, 1.0),
    ("conciseness", "one two three four", {"maximum_words": 2}, False, 0.5),
]


@pytest.mark.parametrize(
    ("criterion_id", "response", "parameters", "expected_pass", "expected_score"),
    CASES,
    ids=[f"{case[0]}_{index}" for index, case in enumerate(CASES)],
)
def test_deterministic_scoring_contract(
    criterion_id, response, parameters, expected_pass, expected_score
):
    passed, score, detail = evaluate_criterion(criterion_id, response, parameters, {})
    assert passed is expected_pass
    assert score == pytest.approx(expected_score)
    assert isinstance(detail, str)
    assert detail.strip()


@pytest.mark.parametrize("criterion_id", ["required_keywords", "required_phrases"])
def test_required_terms_reject_missing_configuration(criterion_id):
    key = "keywords" if criterion_id.endswith("keywords") else "phrases"
    with pytest.raises(ValueError):
        evaluate_criterion(criterion_id, "text", {key: []}, {})
