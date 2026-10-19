"""Behavior and error-contract coverage, without database or provider dependencies."""

import json

import pytest

from app.evaluation.evaluators.structured import (
    PARAMETER_SCHEMAS,
    SCHEMA_DIALECT,
    STRUCTURED_EVALUATORS,
    StructuredConfigurationError,
    StructuredEvaluationError,
    evaluate_structured,
    parse_json_response,
)

VALID_PARAMETERS = {
    "valid_json": {},
    "json_object": {},
    "json_array": {},
    "json_required_keys": {"keys": ["id", "status"]},
    "json_forbidden_keys": {"keys": ["secret"]},
    "json_field_type": {"field": "count", "type": "integer"},
    "json_field_value": {"field": "status", "value": "ready"},
    "json_array_min_length": {"min_length": 2},
    "json_array_max_length": {"max_length": 2},
    "json_schema": {"schema": {"type": "object", "required": ["id"]}},
}


def test_ten_evaluator_contracts_are_available():
    assert len(STRUCTURED_EVALUATORS) == 10
    assert set(STRUCTURED_EVALUATORS) == set(VALID_PARAMETERS) == set(PARAMETER_SCHEMAS)


@pytest.mark.parametrize(
    "criterion_id,response,passed",
    [
        ("valid_json", '{"id": 1}', True),
        ("valid_json", "not JSON", False),
        ("json_object", '{"id": 1}', True),
        ("json_object", "[]", False),
        ("json_array", "[1, 2]", True),
        ("json_array", "{}", False),
        ("json_required_keys", '{"id": null, "status": "ready"}', True),
        ("json_required_keys", '{"id": 1}', False),
        ("json_forbidden_keys", '{"id": 1}', True),
        ("json_forbidden_keys", '{"secret": null}', False),
        ("json_field_type", '{"count": 2}', True),
        ("json_field_type", '{"count": "2"}', False),
        ("json_field_value", '{"status": "ready"}', True),
        ("json_field_value", '{"status": "pending"}', False),
        ("json_array_min_length", "[1, 2]", True),
        ("json_array_min_length", "[1]", False),
        ("json_array_max_length", "[1, 2]", True),
        ("json_array_max_length", "[1, 2, 3]", False),
        ("json_schema", '{"id": 1}', True),
        ("json_schema", "{}", False),
    ],
)
def test_evaluator_outcomes_and_normalized_scores(criterion_id, response, passed):
    result = STRUCTURED_EVALUATORS[criterion_id](
        response=response, parameters=VALID_PARAMETERS[criterion_id], context={"run_id": "example"}
    )
    assert result.passed is passed
    assert result.normalized_score == (1.0 if passed else 0.0)
    assert isinstance(result.detail, str) and result.detail
    assert not hasattr(result, "weight")


@pytest.mark.parametrize("criterion_id", VALID_PARAMETERS)
@pytest.mark.parametrize("response", ["{", "```json\n{}\n```", '{"a": 1} trailing text'])
def test_malformed_responses_are_zero_scores_for_all_evaluators(criterion_id, response):
    result = evaluate_structured(criterion_id, response, VALID_PARAMETERS[criterion_id])
    assert result.passed is False
    assert result.normalized_score == 0.0
    assert "JSON" in result.detail


@pytest.mark.parametrize("response", ["null", "true", "false", "42", "1.5", '"hello"', "[]", "{}"])
def test_valid_json_includes_primitive_values(response):
    assert evaluate_structured("valid_json", response, {}).normalized_score == 1.0


def test_parser_preserves_unicode_and_surrounding_whitespace():
    assert parse_json_response(' \n {"message": "café", "count": 2} \t') == {
        "message": "café",
        "count": 2,
    }


@pytest.mark.parametrize(
    "response",
    [
        "",
        " ",
        "NaN",
        "Infinity",
        "-Infinity",
        "[1e999]",
        "[NaN]",
        "[1,]",
        "{'id': 1}",
        '{"a": 1, "a": 2}',
        '{"a": 1, "\\u0061": 2}',
    ],
)
def test_strict_response_profile_rejects_ambiguous_or_nonfinite_json(response):
    assert evaluate_structured("valid_json", response, {}).normalized_score == 0.0


@pytest.mark.parametrize("criterion_id", ["json_required_keys", "json_forbidden_keys"])
def test_key_checks_require_objects(criterion_id):
    assert not evaluate_structured(criterion_id, '"secret"', VALID_PARAMETERS[criterion_id]).passed


@pytest.mark.parametrize("criterion_id", ["json_field_type", "json_field_value"])
@pytest.mark.parametrize("response", ["{}", "[]", "null"])
def test_missing_fields_and_wrong_containers_fail(criterion_id, response):
    assert not evaluate_structured(criterion_id, response, VALID_PARAMETERS[criterion_id]).passed


@pytest.mark.parametrize(
    "value,expected_type,passed",
    [
        (1, "integer", True),
        (1.0, "integer", True),
        (1.5, "integer", False),
        (1, "number", True),
        (1.5, "number", True),
        (True, "integer", False),
        (True, "number", False),
        (True, "boolean", True),
        (0, "boolean", False),
        ("1", "number", False),
        ("text", "string", True),
        (None, "null", True),
        ({}, "object", True),
        ([], "array", True),
        (None, "object", False),
    ],
)
def test_json_type_semantics(value, expected_type, passed):
    result = evaluate_structured(
        "json_field_type", json.dumps({"field": value}), {"field": "field", "type": expected_type}
    )
    assert result.passed is passed


@pytest.mark.parametrize(
    "actual,expected,passed",
    [
        (1, True, False),
        (True, 1, False),
        (1, "1", False),
        (1, 1.0, True),
        (None, None, True),
        ([1, 2], [2, 1], False),
        ([1, 2], [1, 2], True),
        ({"a": True}, {"a": 1}, False),
        ([True], [1], False),
        ({"a": 1, "b": 2}, {"b": 2, "a": 1}, True),
    ],
)
def test_exact_json_values_without_coercion(actual, expected, passed):
    result = evaluate_structured(
        "json_field_value", json.dumps({"value": actual}), {"field": "value", "value": expected}
    )
    assert result.passed is passed


def test_field_names_are_literal_top_level_keys():
    params = {"field": "a.b", "value": 1}
    assert evaluate_structured("json_field_value", '{"a.b": 1}', params).passed
    assert not evaluate_structured("json_field_value", '{"a": {"b": 1}}', params).passed


@pytest.mark.parametrize(
    "criterion_id,key",
    [
        ("json_array_min_length", "min_length"),
        ("json_array_max_length", "max_length"),
    ],
)
def test_zero_length_boundaries_and_wrong_container(criterion_id, key):
    assert evaluate_structured(criterion_id, "[]", {key: 0}).passed
    assert not evaluate_structured(criterion_id, "{}", {key: 0}).passed


@pytest.mark.parametrize("criterion_id", VALID_PARAMETERS)
def test_unknown_parameter_is_a_configuration_error_even_with_bad_response(criterion_id):
    with pytest.raises(StructuredConfigurationError):
        evaluate_structured(criterion_id, "{", {**VALID_PARAMETERS[criterion_id], "typo": 1})


@pytest.mark.parametrize(
    "criterion_id,parameters",
    [
        ("json_required_keys", {}),
        ("json_required_keys", {"keys": []}),
        ("json_required_keys", {"keys": "id"}),
        ("json_forbidden_keys", {"keys": [1]}),
        ("json_field_type", {"field": "x", "type": "int"}),
        ("json_field_type", {"field": 3, "type": "string"}),
        ("json_field_value", {"field": "x"}),
        ("json_field_value", {"field": "x", "value": (1,)}),
        ("json_field_value", {"field": "x", "value": {1: "coerced key"}}),
        ("json_field_value", {"field": "x", "value": float("nan")}),
        ("json_array_min_length", {"min_length": -1}),
        ("json_array_min_length", {"min_length": True}),
        ("json_array_min_length", {"min_length": 1.0}),
        ("json_array_max_length", {"max_length": "2"}),
        ("json_schema", {"schema": "{}"}),
    ],
)
def test_invalid_parameters_raise_instead_of_scoring_zero(criterion_id, parameters):
    with pytest.raises(StructuredConfigurationError):
        evaluate_structured(criterion_id, "{", parameters)


@pytest.mark.parametrize("parameters", [None, [], "{}", 1])
def test_parameters_must_be_objects(parameters):
    with pytest.raises(StructuredConfigurationError):
        evaluate_structured("valid_json", "{}", parameters)


def test_unknown_criterion_is_configuration_error():
    with pytest.raises(StructuredConfigurationError, match="Unknown structured criterion"):
        evaluate_structured("not_registered", "{}", {})


@pytest.mark.parametrize("response", [None, 3, {}, []])
def test_nontext_response_is_an_execution_error(response):
    with pytest.raises(StructuredEvaluationError):
        evaluate_structured("valid_json", response, {})


def test_excessive_response_nesting_is_an_execution_error():
    with pytest.raises(StructuredEvaluationError):
        evaluate_structured("valid_json", "[" * 2000 + "0" + "]" * 2000, {})


@pytest.mark.parametrize(
    "schema",
    [
        {"type": "made_up"},
        {"required": "id"},
        {"minItems": -1},
        {"$schema": "http://json-schema.org/draft-07/schema#"},
        {"$defs": {"x": {"$schema": "http://json-schema.org/draft-07/schema#"}}},
        {"$ref": "#/$defs/missing"},
        {"$ref": "https://example.invalid/schema.json"},
        {"properties": {"unused": {"$ref": "file:///not-a-schema.json"}}},
    ],
)
def test_invalid_or_unsupported_schemas_are_configuration_errors_before_parsing(schema):
    with pytest.raises(StructuredConfigurationError):
        evaluate_structured("json_schema", "{", {"schema": schema})


def test_nested_schema_with_local_refs_and_extra_property_rejection():
    schema = {
        "$schema": SCHEMA_DIALECT,
        "$defs": {"count": {"type": "integer", "minimum": 0}},
        "type": "object",
        "properties": {
            "items": {"type": "array", "minItems": 1, "items": {"$ref": "#/$defs/count"}},
        },
        "required": ["items"],
        "additionalProperties": False,
    }
    assert evaluate_structured("json_schema", '{"items": [0, 2]}', {"schema": schema}).passed
    for response in ['{"items": []}', '{"items": [-1]}', '{"items": [2], "extra": 1}']:
        result = evaluate_structured("json_schema", response, {"schema": schema})
        assert not result.passed
        assert "Schema mismatch" in result.detail


def test_schema_annotations_are_not_mistaken_for_subschemas():
    schema = {"const": {"$ref": "this is data", "$schema": "also data"}}
    response = '{"$ref": "this is data", "$schema": "also data"}'
    assert evaluate_structured("json_schema", response, {"schema": schema}).passed


@pytest.mark.parametrize("schema,passed", [(True, True), (False, False)])
def test_boolean_schemas(schema, passed):
    assert evaluate_structured("json_schema", "null", {"schema": schema}).passed is passed


def test_schema_dialect_trailing_fragment_is_supported():
    schema = {"$schema": SCHEMA_DIALECT + "#", "type": "integer"}
    assert evaluate_structured("json_schema", "1", {"schema": schema}).passed


def test_recursive_schema_without_progress_is_an_execution_error():
    with pytest.raises(StructuredEvaluationError):
        evaluate_structured("json_schema", "{}", {"schema": {"$ref": "#"}})


def test_context_does_not_change_or_mutate_evaluation_inputs():
    params = {"field": "count", "type": "integer"}
    context = {"weight": 20, "run_id": "sample"}
    result = evaluate_structured("json_field_type", '{"count": 3}', params, context)
    assert result.normalized_score == 1.0
    assert context == {"weight": 20, "run_id": "sample"}
    assert params == {"field": "count", "type": "integer"}
