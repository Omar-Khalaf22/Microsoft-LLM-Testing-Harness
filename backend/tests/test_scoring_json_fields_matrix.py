"""Behavioral regression checks for structured JSON field and array rules."""

import pytest

from app.evaluation.registry import evaluate_criterion


@pytest.mark.parametrize(
    ("criterion_id", "response", "parameters", "expected_pass"),
    [
        ("json_required_keys", '{"a": 1}', {"keys": ["a"]}, True),
        ("json_required_keys", '{"a": 1}', {"keys": ["b"]}, False),
        ("json_forbidden_keys", '{"a": 1}', {"keys": ["b"]}, True),
        ("json_forbidden_keys", '{"a": 1}', {"keys": ["a"]}, False),
        ("json_field_type", '{"count": 3}', {"field": "count", "type": "integer"}, True),
        ("json_field_type", '{"count": true}', {"field": "count", "type": "integer"}, False),
        ("json_field_value", '{"count": 3}', {"field": "count", "value": 3}, True),
        ("json_field_value", '{"count": true}', {"field": "count", "value": 1}, False),
        ("json_array_min_length", "[1, 2]", {"min_length": 2}, True),
        ("json_array_min_length", "[1]", {"min_length": 2}, False),
        ("json_array_max_length", "[1]", {"max_length": 1}, True),
        ("json_array_max_length", "[1, 2]", {"max_length": 1}, False),
    ],
)
def test_structured_json_contracts(criterion_id, response, parameters, expected_pass):
    passed, score, detail = evaluate_criterion(criterion_id, response, parameters, {})
    assert passed is expected_pass
    assert score == float(expected_pass)
    assert detail


@pytest.mark.parametrize(
    ("criterion_id", "parameters"),
    [
        ("json_required_keys", {"keys": []}),
        ("json_forbidden_keys", {"keys": []}),
        ("json_field_type", {"field": "count", "type": "unknown"}),
        ("json_array_min_length", {"min_length": -1}),
        ("json_array_max_length", {"max_length": -1}),
    ],
)
def test_structured_json_invalid_parameters(criterion_id, parameters):
    with pytest.raises(ValueError):
        evaluate_criterion(criterion_id, "{}", parameters, {})


@pytest.mark.parametrize(
    ("criterion_id", "parameters"),
    [
        ("json_required_keys", {"keys": ["a"]}),
        ("json_forbidden_keys", {"keys": ["a"]}),
        ("json_field_type", {"field": "a", "type": "string"}),
        ("json_field_value", {"field": "a", "value": 1}),
    ],
)
def test_json_object_required_for_field_rules(criterion_id, parameters):
    passed, score, detail = evaluate_criterion(criterion_id, "[1]", parameters, {})
    assert passed is False
    assert score == 0.0
    assert detail
