"""Behavioral regression checks for strict JSON and text matching criteria."""

import pytest

from app.evaluation.registry import evaluate_criterion


@pytest.mark.parametrize(
    ("criterion_id", "response", "expected_pass"),
    [
        ("valid_json", '{"name": "Lina"}', True),
        ("valid_json", '{"name": "Lina", "name": "Bob"}', False),
        ("valid_json", '{"value": NaN}', False),
        ("valid_json", '```json\n{"value": 1}\n```', False),
        ("json_object", '{"value": 1}', True),
        ("json_object", "[1]", False),
        ("json_array", "[1]", True),
        ("json_array", '{"value": 1}', False),
    ],
)
def test_strict_json_parsing(criterion_id, response, expected_pass):
    passed, score, detail = evaluate_criterion(criterion_id, response, {}, {})
    assert passed is expected_pass
    assert score == float(expected_pass)
    assert detail


@pytest.mark.parametrize(
    ("criterion_id", "response", "parameters", "expected_pass"),
    [
        ("exact_match", "hello", {"expected": "hello"}, True),
        ("exact_match", "Hello", {"expected": "hello"}, False),
        ("contains_text", "hello world", {"text": "world"}, True),
        ("contains_text", "hello world", {"text": "World"}, False),
        ("case_insensitive_match", "HELLO", {"expected": "hello"}, True),
        ("case_insensitive_match", "HELLO!", {"expected": "hello"}, False),
    ],
)
def test_text_matching_contracts(criterion_id, response, parameters, expected_pass):
    passed, score, detail = evaluate_criterion(criterion_id, response, parameters, {})
    assert passed is expected_pass
    assert score == float(expected_pass)
    assert detail


@pytest.mark.parametrize(
    ("criterion_id", "response", "parameters", "expected_score"),
    [
        ("required_keywords", "alpha beta", {"keywords": ["alpha", "beta"]}, 1.0),
        ("required_keywords", "alpha", {"keywords": ["alpha", "beta"]}, 0.5),
        ("forbidden_keywords", "safe", {"keywords": ["secret"]}, 1.0),
        ("forbidden_keywords", "secret", {"keywords": ["secret"]}, 0.0),
    ],
)
def test_keyword_coverage_scores(criterion_id, response, parameters, expected_score):
    passed, score, detail = evaluate_criterion(criterion_id, response, parameters, {})
    assert passed is (expected_score == 1.0)
    assert score == pytest.approx(expected_score)
    assert detail
