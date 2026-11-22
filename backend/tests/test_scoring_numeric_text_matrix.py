"""Parameterized numeric and explicit text rule scoring regressions."""

import pytest

from app.evaluation.registry import evaluate_criterion

CASES = [
    (
        "mathematical_correctness",
        "3.14",
        {"expected_value": "3.14", "absolute_tolerance": "0"},
        True,
        1.0,
    ),
    (
        "mathematical_correctness",
        "3.15",
        {"expected_value": "3.14", "absolute_tolerance": "0.01"},
        True,
        1.0,
    ),
    (
        "mathematical_correctness",
        "3.16",
        {"expected_value": "3.14", "absolute_tolerance": "0.01"},
        False,
        0.0,
    ),
    (
        "mathematical_correctness",
        "answer: 3.14",
        {"expected_value": "3.14", "absolute_tolerance": "0"},
        False,
        0.0,
    ),
    (
        "profanity_detection",
        "Good morning.",
        {"prohibited_terms": ["bad"]},
        True,
        1.0,
    ),
    (
        "profanity_detection",
        "BAD!",
        {"prohibited_terms": ["bad"]},
        False,
        0.0,
    ),
    (
        "profanity_detection",
        "badger",
        {"prohibited_terms": ["bad"]},
        True,
        1.0,
    ),
    (
        "spelling",
        "hello world",
        {"allowed_words": ["hello", "world"], "minimum_score": 1},
        True,
        1.0,
    ),
    (
        "spelling",
        "hello unknown",
        {"allowed_words": ["hello", "world"], "minimum_score": 1},
        False,
        0.5,
    ),
    (
        "grammar",
        "We could have done it.",
        {"forbidden_phrases": ["could of"], "ignore_case": True, "maximum_violations": 0},
        True,
        1.0,
    ),
    (
        "grammar",
        "We could of done it.",
        {"forbidden_phrases": ["could of"], "ignore_case": True, "maximum_violations": 0},
        False,
        0.5,
    ),
    (
        "copyright_compliance",
        "Original response.",
        {"protected_excerpts": ["protected excerpt"], "ignore_case": True},
        True,
        1.0,
    ),
    (
        "copyright_compliance",
        "PROTECTED EXCERPT",
        {"protected_excerpts": ["protected excerpt"], "ignore_case": True},
        False,
        0.0,
    ),
]


@pytest.mark.parametrize(
    ("criterion_id", "response", "parameters", "expected_pass", "expected_score"),
    CASES,
    ids=[f"{case[0]}_{index}" for index, case in enumerate(CASES)],
)
def test_numeric_and_text_rule_scores(
    criterion_id, response, parameters, expected_pass, expected_score
):
    passed, score, detail = evaluate_criterion(criterion_id, response, parameters, {})
    assert passed is expected_pass
    assert score == pytest.approx(expected_score)
    assert isinstance(detail, str)
    assert detail.strip()
