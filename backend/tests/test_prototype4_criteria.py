"""Regression tests for newly enabled Prototype 4 deterministic criteria."""

import pytest

from app.evaluation.registry import evaluate_criterion, validate_criterion


@pytest.mark.parametrize(
    "criterion,response,params,expected",
    [
        ("xml_validity", "<root/>", {}, True),
        ("schema_required_keys", "{\"answer\": 1}", {"keys": ["answer"]}, True),
        ("schema_required_keys", "{\"other\": 1}", {"keys": ["answer"]}, False),
        ("schema_forbidden_keys", "{\"answer\": 1}", {"keys": ["password"]}, True),
        ("schema_forbidden_keys", "{\"password\": 1}", {"keys": ["password"]}, False),
        ("keyword_density", "test test other", {"keyword": "test", "minimum_ratio": 0.5, "maximum_ratio": 1}, True),
        ("keyword_density", "other other", {"keyword": "test", "minimum_ratio": 0.5, "maximum_ratio": 1}, False),
        ("repetition_penalty", "one two three", {"maximum_repeat_ratio": 0}, True),
        ("repetition_penalty", "one one", {"maximum_repeat_ratio": 0}, False),
        ("markdown_format", "# Heading", {"required_element": "heading"}, True),
        ("markdown_format", "Plain text", {"required_element": "heading"}, False),
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
        ("duplicate_detection", "A\nB", {"maximum_duplicate_lines": 0}, True),
        ("duplicate_detection", "A\na", {"maximum_duplicate_lines": 0}, False),
        (
            "table_structure",
            "| A | B |\n| --- | --- |\n| 1 | 2 |",
            {"minimum_columns": 2, "minimum_data_rows": 1},
            True,
        ),
        (
            "table_structure",
            "| A | B |\n| 1 | 2 |",
            {"minimum_columns": 2, "minimum_data_rows": 1},
            False,
        ),
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
        ("schema_required_keys", {"keys": []}),
        ("markdown_format", {"required_element": "unknown"}),
        ("duplicate_detection", {"maximum_duplicate_lines": -1}),
        ("table_structure", {"minimum_columns": 1, "minimum_data_rows": 1}),
    ],
)
def test_invalid_configurations(criterion, params):
    with pytest.raises(ValueError):
        validate_criterion(criterion, params)
