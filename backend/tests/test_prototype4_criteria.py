"""Regression tests for newly enabled Prototype 4 deterministic criteria."""

import pytest

from app.evaluation.registry import evaluate_criterion, validate_criterion


@pytest.mark.parametrize(
    "criterion,response,params,expected",
    [
        ("xml_validity", "<root/>", {}, True),
        ("xml_validity", "<root>", {}, False),
        ("date_format", "2026-11-18", {"format": "%Y-%m-%d"}, True),
        ("date_format", "2026-13-18", {"format": "%Y-%m-%d"}, False),
        ("code_syntax", "print('ok')", {}, True),
        ("code_syntax", "def :", {}, False),
        ("citation_presence", "Claim [1]", {"minimum": 1}, True),
        ("citation_presence", "No source", {"minimum": 1}, False),
        ("markdown_links", "[source](https://example.org)", {"minimum": 1}, True),
        ("markdown_links", "https://example.org", {"minimum": 1}, False),
        ("required_links", "https://example.org", {"urls": ["https://example.org"]}, True),
        ("required_links", "none", {"urls": ["https://example.org"]}, False),
        ("list_length", "- one\n- two", {"minimum": 2, "maximum": 2}, True),
        ("list_length", "- one", {"minimum": 2, "maximum": 2}, False),
        ("numeric_units", "12 kg", {"unit": "kg"}, True),
        ("numeric_units", "12 lb", {"unit": "kg"}, False),
    ],
)
def test_new_criteria(criterion, response, params, expected):
    passed, score, detail = evaluate_criterion(criterion, response, params, {})
    assert passed is expected
    assert 0 <= score <= 1
    assert detail


@pytest.mark.parametrize(
    "criterion,params",
    [
        ("date_format", {}),
        ("citation_presence", {"minimum": 0}),
        ("required_links", {"urls": []}),
        ("list_length", {"minimum": 2, "maximum": 1}),
        ("numeric_units", {"unit": ""}),
    ],
)
def test_invalid_configurations(criterion, params):
    with pytest.raises(ValueError):
        validate_criterion(criterion, params)
