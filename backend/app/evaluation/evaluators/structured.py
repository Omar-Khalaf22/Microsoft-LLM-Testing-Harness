"""Structured-output checks for Prototype 2, independent of the legacy scorer.

Each callable in STRUCTURED_EVALUATORS accepts (response, parameters, context).
The context argument is reserved for the shared evaluator interface. Results
describe this criterion only; the scoring layer applies user-selected points.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from functools import partial
from math import isfinite
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from referencing import Registry
from referencing.exceptions import Unresolvable
from referencing.jsonschema import DRAFT202012

SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"
JSON_TYPES = ["object", "array", "string", "number", "integer", "boolean", "null"]


class StructuredConfigurationError(ValueError):
    """The criterion cannot run with the supplied ID or parameters."""


class StructuredEvaluationError(RuntimeError):
    """Evaluation could not finish; this is not a zero-scoring response."""


@dataclass(frozen=True)
class StructuredEvaluationResult:
    """Unweighted outcome, distinct from the legacy weighted CriterionResult."""

    passed: bool
    normalized_score: float
    detail: str


def _parameter_schema(properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


# These contracts belong to this evaluator module. Lina's shared registry can
# import them; this is not a second application-wide supported-criteria catalog.
PARAMETER_SCHEMAS = {
    "valid_json": _parameter_schema({}),
    "json_object": _parameter_schema({}),
    "json_array": _parameter_schema({}),
    "json_required_keys": _parameter_schema(
        {"keys": {"type": "array", "items": {"type": "string"}, "minItems": 1}}
    ),
    "json_forbidden_keys": _parameter_schema(
        {"keys": {"type": "array", "items": {"type": "string"}, "minItems": 1}}
    ),
    "json_field_type": _parameter_schema(
        {"field": {"type": "string"}, "type": {"enum": JSON_TYPES}}
    ),
    "json_field_value": _parameter_schema({"field": {"type": "string"}, "value": {}}),
    "json_array_min_length": _parameter_schema({"min_length": {"type": "integer", "minimum": 0}}),
    "json_array_max_length": _parameter_schema({"max_length": {"type": "integer", "minimum": 0}}),
    "json_schema": _parameter_schema({"schema": {"type": ["object", "boolean"]}}),
}


def _assert_json_value(value: Any) -> None:
    """Require JSON-native values, without Python's tuple/key/NaN coercions."""
    if type(value) in (str, bool, int, type(None)):
        return
    if type(value) is float and isfinite(value):
        return
    if type(value) is list:
        for item in value:
            _assert_json_value(item)
        return
    if type(value) is dict and all(type(key) is str for key in value):
        for item in value.values():
            _assert_json_value(item)
        return
    raise ValueError("Values must use JSON types and finite numbers.")


def _schema_validator(schema: dict[str, Any] | bool) -> Draft202012Validator:
    """Support Draft 2020-12 with local references and no network retrieval."""
    try:
        Draft202012Validator.check_schema(schema)
        root = DRAFT202012.create_resource(schema)
        resources = [(root, Registry().resolver_with_root(root))]
        while resources:
            resource, resolver = resources.pop()
            contents = resource.contents
            if isinstance(contents, dict):
                dialect = contents.get("$schema", SCHEMA_DIALECT)
                if dialect.removesuffix("#") != SCHEMA_DIALECT:
                    raise StructuredConfigurationError(
                        "Only JSON Schema Draft 2020-12 is supported."
                    )
                for keyword in ("$ref", "$dynamicRef"):
                    if keyword in contents:
                        reference = contents[keyword]
                        if not reference.startswith("#"):
                            raise StructuredConfigurationError(
                                "Schema references must be local fragments such as #/$defs/item."
                            )
                        Draft202012Validator.check_schema(resolver.lookup(reference).contents)
            resources.extend(
                (child, resolver.in_subresource(child)) for child in resource.subresources()
            )
        return Draft202012Validator(schema, registry=Registry())
    except SchemaError as exc:
        raise StructuredConfigurationError(f"Invalid JSON Schema: {exc.message}") from exc
    except Unresolvable as exc:
        raise StructuredConfigurationError(
            "A local schema reference could not be resolved."
        ) from exc
    except RecursionError as exc:
        raise StructuredConfigurationError("Schema nesting exceeds the evaluator limit.") from exc


def validate_structured_parameters(criterion_id: str, parameters: Mapping[str, Any]) -> None:
    """Validate configuration before attempting to parse the model response."""
    if not isinstance(criterion_id, str) or criterion_id not in PARAMETER_SCHEMAS:
        raise StructuredConfigurationError(f"Unknown structured criterion: {criterion_id!r}.")
    if not isinstance(parameters, Mapping):
        raise StructuredConfigurationError("Parameters must be a JSON object.")
    values = dict(parameters)
    try:
        _assert_json_value(values)
    except (ValueError, RecursionError) as exc:
        raise StructuredConfigurationError("Parameters must contain only JSON values.") from exc
    error = next(Draft202012Validator(PARAMETER_SCHEMAS[criterion_id]).iter_errors(values), None)
    if error is not None:
        raise StructuredConfigurationError(f"Invalid {criterion_id} parameters: {error.message}")
    for key in ("min_length", "max_length"):
        if key in values and type(values[key]) is not int:
            raise StructuredConfigurationError(f"{key} must be a nonnegative integer.")
    if criterion_id == "json_schema":
        _schema_validator(values["schema"])


def _reject_constant(value: str) -> None:
    raise ValueError(f"Non-JSON numeric constant: {value}.")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate object key: {key!r}.")
        result[key] = value
    return result


def parse_json_response(response: str) -> Any:
    """Parse the complete response under the harness's strict JSON profile.

    Whitespace and primitive JSON values are accepted. Duplicate keys, nonfinite
    numbers, code fences, and extra text are rejected. No fragments are extracted.
    """
    if not isinstance(response, str):
        raise StructuredEvaluationError("The model response must be text.")
    try:
        value = json.loads(
            response, parse_constant=_reject_constant, object_pairs_hook=_unique_object
        )
        _assert_json_value(value)
        return value
    except RecursionError as exc:
        raise StructuredEvaluationError("Response nesting exceeds the evaluator limit.") from exc


def _result(passed: bool, detail: str) -> StructuredEvaluationResult:
    return StructuredEvaluationResult(passed, 1.0 if passed else 0.0, detail)


def evaluate_structured(
    criterion_id: str,
    response: str,
    parameters: Mapping[str, Any],
    context: Mapping[str, Any] | None = None,
) -> StructuredEvaluationResult:
    """Run one structured criterion; configuration/execution errors propagate.

    A malformed or noncompliant response yields a valid result with score 0.
    An unusable criterion configuration raises StructuredConfigurationError.
    Evaluator execution failures raise StructuredEvaluationError. Neither error
    is converted into an invented response score.
    """
    validate_structured_parameters(criterion_id, parameters)
    try:
        data = parse_json_response(response)
    except ValueError as exc:
        return _result(False, f"Response is not accepted JSON: {exc}")

    if criterion_id == "valid_json":
        return _result(True, "The complete response is accepted JSON.")
    if criterion_id == "json_object":
        return _result(isinstance(data, dict), "The response must be a JSON object.")
    if criterion_id == "json_array":
        return _result(isinstance(data, list), "The response must be a JSON array.")

    if criterion_id in ("json_required_keys", "json_forbidden_keys"):
        if not isinstance(data, dict):
            return _result(False, "A JSON object is required for a key check.")
        keys = parameters["keys"]
        if criterion_id == "json_required_keys":
            missing = [key for key in keys if key not in data]
            return _result(not missing, f"Missing required top-level keys: {missing}.")
        present = [key for key in keys if key in data]
        return _result(not present, f"Forbidden top-level keys present: {present}.")

    if criterion_id in ("json_field_type", "json_field_value"):
        if not isinstance(data, dict):
            return _result(False, "A JSON object is required for a field check.")
        name = parameters["field"]
        if name not in data:
            return _result(False, f"Top-level field {name!r} is missing.")
        if criterion_id == "json_field_type":
            expected = parameters["type"]
            matches = Draft202012Validator.TYPE_CHECKER.is_type(data[name], expected)
            return _result(matches, f"Field {name!r} must have JSON type {expected}.")
        # JSON Schema const compares objects/arrays structurally and distinguishes
        # booleans from numbers, unlike Python's True == 1 shortcut.
        matches = Draft202012Validator({"const": parameters["value"]}).is_valid(data[name])
        return _result(matches, f"Field {name!r} must equal the configured JSON value.")

    if criterion_id in ("json_array_min_length", "json_array_max_length"):
        if not isinstance(data, list):
            return _result(False, "A root JSON array is required for an array-length check.")
        if criterion_id == "json_array_min_length":
            bound = parameters["min_length"]
            return _result(len(data) >= bound, f"Array length is {len(data)}; minimum is {bound}.")
        bound = parameters["max_length"]
        return _result(len(data) <= bound, f"Array length is {len(data)}; maximum is {bound}.")

    validator = _schema_validator(parameters["schema"])
    try:
        error = next(validator.iter_errors(data), None)
    except Unresolvable as exc:
        raise StructuredConfigurationError(
            "A local schema reference could not be resolved."
        ) from exc
    except RecursionError as exc:
        raise StructuredEvaluationError("Schema evaluation exceeded the nesting limit.") from exc
    if error is not None:
        return _result(False, f"Schema mismatch at {list(error.absolute_path)}: {error.message}")
    return _result(True, "The response matches the configured JSON Schema.")


# Register these callables in Lina's eventual shared registry. Each already has
# the proposed (response, parameters, context) callable interface.
STRUCTURED_EVALUATORS = {
    criterion_id: partial(evaluate_structured, criterion_id) for criterion_id in PARAMETER_SCHEMAS
}
