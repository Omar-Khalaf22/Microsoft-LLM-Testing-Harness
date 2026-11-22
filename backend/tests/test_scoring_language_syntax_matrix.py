"""Regression tests for language scripts, SQL preparation, and HTML rules."""

import pytest

from app.evaluation.registry import evaluate_criterion


@pytest.mark.parametrize("criterion_id", ["language_detection", "response_language"])
@pytest.mark.parametrize(
    ("response", "expected_pass", "expected_score"),
    [("مرحبا", True, 1.0), ("hello", False, 0.0)],
)
def test_arabic_script_evidence(criterion_id, response, expected_pass, expected_score):
    parameters = {"expected_language": "ar", "minimum_script_fraction": 0.8}
    passed, score, detail = evaluate_criterion(criterion_id, response, parameters, {})
    assert passed is expected_pass
    assert score == pytest.approx(expected_score)
    assert detail


@pytest.mark.parametrize("criterion_id", ["language_detection", "response_language"])
def test_script_detection_requires_letters(criterion_id):
    parameters = {"expected_language": "en", "minimum_script_fraction": 0.8}
    with pytest.raises(ValueError):
        evaluate_criterion(criterion_id, "123", parameters, {})


@pytest.mark.parametrize(
    ("response", "expected_pass"),
    [
        ("SELECT 1", True),
        ("SELECT (", False),
        ("DELETE FROM users", False),
        ("", False),
    ],
)
def test_sql_syntax_preparation(response, expected_pass):
    passed, score, detail = evaluate_criterion("sql_syntax", response, {}, {})
    assert passed is expected_pass
    assert score == float(expected_pass)
    assert detail


@pytest.mark.parametrize(
    ("response", "expected_pass"),
    [
        ("<p>Safe text</p>", True),
        ("<script>alert(1)</script>", False),
        ('<a href="javascript:alert(1)">Link</a>', False),
        ('<p onclick="alert(1)">Click</p>', False),
        ('<a href="https://example.org">Link</a>', True),
    ],
)
def test_html_safety_scanner(response, expected_pass):
    passed, score, detail = evaluate_criterion("html_safety", response, {}, {})
    assert passed is expected_pass
    assert score == float(expected_pass)
    assert detail
