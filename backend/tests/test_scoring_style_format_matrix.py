"""Scoring regressions for lexical style, readability, and response formats.

Readability and lexical scores are deterministic proxies, not model judgments.
"""

import pytest

from app.evaluation.registry import evaluate_criterion

STYLE_PARAMS = {
    "positive_terms": ["great", "excellent"],
    "negative_terms": ["bad", "awful"],
    "target_score": 1.0,
    "tolerance": 0.25,
}


@pytest.mark.parametrize("criterion_id", ["sentiment_alignment", "tone_consistency"])
@pytest.mark.parametrize(
    ("response", "expected_pass", "expected_score"),
    [
        ("GREAT excellent", True, 1.0),
        ("great bad", False, 0.5),
        ("bad awful", False, 0.0),
        ("neutral words", False, 0.5),
    ],
)
def test_lexical_style_scores(criterion_id, response, expected_pass, expected_score):
    passed, score, detail = evaluate_criterion(criterion_id, response, STYLE_PARAMS, {})
    assert passed is expected_pass
    assert score == pytest.approx(expected_score)
    assert detail


@pytest.mark.parametrize(
    ("criterion_id", "response", "parameters", "expected_pass", "expected_score"),
    [
        (
            "clarity", "One two. Three four.",
            {"minimum_ratio": 1, "minimum_words": 2, "maximum_words": 2}, True, 1.0,
        ),
        (
            "clarity", "One two. Three.",
            {"minimum_ratio": 1, "minimum_words": 2, "maximum_words": 2}, False, 0.5,
        ),
        (
            "coherence", "One two. Three four.",
            {"minimum_ratio": 1, "minimum_words": 0, "maximum_words": 1000}, True, 1.0,
        ),
        (
            "coherence", "One two. One two.",
            {"minimum_ratio": 1, "minimum_words": 0, "maximum_words": 1000}, False, 0.5,
        ),
    ],
    ids=["clarity_all", "clarity_partial", "coherence_unique", "coherence_repeated"],
)
def test_readability_proxy_scores(
    criterion_id, response, parameters, expected_pass, expected_score
):
    passed, score, detail = evaluate_criterion(criterion_id, response, parameters, {})
    assert passed is expected_pass
    assert score == pytest.approx(expected_score)
    assert detail


@pytest.mark.parametrize(
    ("format_name", "response", "expected_pass"),
    [
        ("json", '{"value": 1}', True),
        ("json", "not json", False),
        ("json_object", '{"value": 1}', True),
        ("json_object", "[1, 2]", False),
        ("markdown_heading", "# Heading", True),
        ("markdown_heading", "Heading", False),
        ("fenced_code", "```python\nprint(1)\n```", True),
        ("fenced_code", "print(1)", False),
        ("plain_text", "Ordinary prose.", True),
        ("plain_text", "# Heading", False),
    ],
)
def test_format_compliance_scores(format_name, response, expected_pass):
    passed, score, detail = evaluate_criterion(
        "format_compliance", response, {"format": format_name}, {}
    )
    assert passed is expected_pass
    assert score == float(expected_pass)
    assert detail
