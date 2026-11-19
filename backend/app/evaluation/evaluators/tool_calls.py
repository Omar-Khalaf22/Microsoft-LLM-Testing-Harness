"""Evaluate recorded tool calls against approved expected calls and JSON schemas."""

import json
from collections import Counter

from jsonschema import Draft202012Validator


def _calls(context, name):
    calls = context.get(name)
    if not isinstance(calls, list) or len(calls) > 100:
        raise ValueError(f"{name} must be a list of at most 100 calls")
    for call in calls:
        if not isinstance(call, dict) or set(call) != {"name", "arguments"}:
            raise ValueError("Each call requires only name and arguments")
        if not isinstance(call["name"], str) or not call["name"].strip():
            raise ValueError("Tool name must be a nonempty string")
        if not isinstance(call["arguments"], dict):
            raise ValueError("Tool arguments must be an object")
        try:
            serialized = json.dumps(call, allow_nan=False, sort_keys=True)
        except (TypeError, ValueError, RecursionError) as exc:
            raise ValueError("Tool calls must contain finite JSON values") from exc
        if len(serialized) > 32000:
            raise ValueError("Tool call exceeds size limit")
    return calls


def _schemas(context):
    schemas = context.get("tool_schemas")
    if not isinstance(schemas, dict) or len(schemas) > 100:
        raise ValueError("Approved tool schemas must be a mapping")
    for name, schema in schemas.items():
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Schema names must be nonempty strings")
        Draft202012Validator.check_schema(schema)
    return schemas


def evaluate(criterion_id: str, response: str, parameters: dict, context: dict):
    if not isinstance(context, dict):
        raise ValueError("Recorded tool call context is required")
    actual = _calls(context, "actual_tool_calls")
    schemas = _schemas(context)
    if criterion_id == "function_argument_validation":
        if not actual:
            raise ValueError("At least one recorded tool call is required")
        valid = 0
        for call in actual:
            schema = schemas.get(call["name"])
            if schema is not None and Draft202012Validator(schema).is_valid(call["arguments"]):
                valid += 1
        score = valid / len(actual)
        return (
            score >= parameters["minimum_score"],
            score,
            f"Valid arguments: {valid} of {len(actual)} recorded calls",
        )
    if criterion_id == "tool_call_accuracy":
        expected = _calls(context, "expected_tool_calls")
        if any(call["name"] not in schemas for call in expected + actual):
            raise ValueError("Every expected and actual tool needs an approved schema")
        if any(
            not Draft202012Validator(schemas[call["name"]]).is_valid(call["arguments"])
            for call in expected + actual
        ):
            raise ValueError("Tool calls must conform to approved argument schemas")
        wanted = Counter(json.dumps(call, sort_keys=True) for call in expected)
        observed = Counter(json.dumps(call, sort_keys=True) for call in actual)
        matched = sum((wanted & observed).values())
        precision = matched / len(actual) if actual else float(not expected)
        recall = matched / len(expected) if expected else float(not actual)
        score = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        return (
            score >= parameters["minimum_score"],
            score,
            f"Exact matching calls: {matched}; F1: {score:.4f}",
        )
    raise ValueError("Unknown tool call criterion")
