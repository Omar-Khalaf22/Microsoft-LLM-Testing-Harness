"""Nested JSON Schema regression cases for the shared scoring registry."""

import pytest

from app.evaluation.registry import evaluate_criterion


@pytest.mark.parametrize(
    ("response", "schema", "expected"),
    [
        ('{"a": 1}', {"additionalProperties": False, "properties": {"a": {}}}, True),
        ('{"b": 1}', {"additionalProperties": False, "properties": {"a": {}}}, False),
        ('{"a": [1, 2]}', {"properties": {"a": {"minItems": 2}}}, True),
        ('{"a": [1]}', {"properties": {"a": {"minItems": 2}}}, False),
        ('{"a": "yes"}', {"properties": {"a": {"enum": ["yes", "no"]}}}, True),
        ('{"a": "maybe"}', {"properties": {"a": {"enum": ["yes", "no"]}}}, False),
        ("[1, 2]", {"uniqueItems": True}, True),
        ("[1, 1]", {"uniqueItems": True}, False),
        ("3", {"allOf": [{"type": "integer"}, {"minimum": 2}]}, True),
        ("1", {"allOf": [{"type": "integer"}, {"minimum": 2}]}, False),
        ('"abc"', {"pattern": "^[a-z]+$"}, True),
        ('"123"', {"pattern": "^[a-z]+$"}, False),
    ],
)
def test_nested_schema_rules(response, schema, expected):
    passed, score, detail = evaluate_criterion("json_schema", response, {"schema": schema}, {})
    assert passed is expected
    assert score == float(expected)
    assert detail


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        ('{"person": {"age": 21}}', True),
        ('{"person": {"age": "21"}}', False),
        ('{"person": {}}', False),
    ],
)
def test_nested_required_properties(response, expected):
    schema = {
        "type": "object",
        "properties": {
            "person": {
                "type": "object",
                "required": ["age"],
                "properties": {"age": {"type": "integer"}},
            }
        },
    }
    passed, score, detail = evaluate_criterion("json_schema", response, {"schema": schema}, {})
    assert passed is expected
    assert score == float(expected)
    assert detail
