"""Regression tests for response format compliance."""

import pytest

from app.evaluation.registry import evaluate_criterion, validate_criterion


@pytest.mark.parametrize(
    ("format_name", "response", "expected"),
    [
        ("json", '{"ok": true}', True),
        ("json", "[1, 2]", True),
        ("json", "null", False),
        ("json", "{bad}", False),
        ("json_object", '{"ok": true}', True),
        ("json_object", "[1]", False),
        ("markdown_heading", "# Title\nText", True),
        ("markdown_heading", "Just text", False),
        ("fenced_code", "```python\nprint(1)\n```", True),
        ("fenced_code", "print(1)", False),
        ("plain_text", "Ordinary text.", True),
        ("plain_text", "# Heading", False),
    ],
)
def test_format_scoring(format_name, response, expected):
    passed, score, detail = evaluate_criterion(
        "format_compliance", response, {"format": format_name}, {}
    )
    assert passed is expected
    assert score == float(expected)
    assert format_name in detail


def test_invalid_format_rejected():
    with pytest.raises(ValueError):
        validate_criterion("format_compliance", {"format": "xml"})
