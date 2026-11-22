"""Regression tests for Draft 2020 JSON Schema scoring behavior."""

import pytest

from app.evaluation.registry import evaluate_criterion


@pytest.mark.parametrize(
    ("response", "schema", "expected_pass"),
    [
        ('{"count": 2}', {"type": "object"}, True),
        ("[1, 2]", {"type": "object"}, False),
        ('{"count": 2}', {"type": "object", "required": ["count"]}, True),
        ('{"other": 2}', {"type": "object", "required": ["count"]}, False),
        ('{"count": 2}', {"type": "object", "properties": {"count": {"type": "integer"}}}, True),
        ('{"count": true}', {"type": "object", "properties": {"count": {"type": "integer"}}}, False),
        ("[1, 2]", {"type": "array", "minItems": 2}, True),
        ("[1]", {"type": "array", "minItems": 2}, False),
        ("3", {"type": "integer", "minimum": 2}, True),
        ("1", {"type": "integer", "minimum": 2}, False),
        ('"ok"', True, True),
        ('"ok"', False, False),
    ],
)
def test_json_schema_validity(response, schema, expected_pass):
    passed, score, detail = evaluate_criterion("json_schema", response, {"schema": schema}, {})
    assert passed is expected_pass
    assert score == float(expected_pass)
    assert detail


@pytest.mark.parametrize(
    ("response", "expected_pass"),
    [
        ('{"value": 4}', True),
        ('{"value": "bad"}', False),
    ],
)
def test_json_schema_local_reference(response, expected_pass):
    schema = {
        "$defs": {"number": {"type": "integer"}},
        "type": "object",
        "properties": {"value": {"$ref": "#/$defs/number"}},
    }
    passed, score, detail = evaluate_criterion("json_schema", response, {"schema": schema}, {})
    assert passed is expected_pass
    assert score == float(expected_pass)
    assert detail


@pytest.mark.parametrize(
    "schema",
    [
        {"type": "unknown"},
        {"$ref": "https://example.org/schema"},
        {"$ref": "#/$defs/missing"},
        {"$schema": "https://json-schema.org/draft/2019-09/schema"},
    ],
)
def test_json_schema_rejects_invalid_or_external_references(schema):
    with pytest.raises(ValueError):
        evaluate_criterion("json_schema", '{"value": 4}', {"schema": schema}, {})


@pytest.mark.parametrize(
    "response",
    [
        '{"value": 4, "value": 5}',
        '{"value": NaN}',
        '```json\n{"value": 4}\n```',
    ],
)
def test_json_schema_rejects_non_json_responses(response):
    passed, score, detail = evaluate_criterion(
        "json_schema", response, {"schema": {"type": "object"}}, {}
    )
    assert passed is False
    assert score == 0.0
    assert detail
