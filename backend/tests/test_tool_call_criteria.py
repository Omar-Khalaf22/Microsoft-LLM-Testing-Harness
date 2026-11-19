"""Regression tests for tool call scoring with explicit recorded evidence."""

import pytest
from app.evaluation.registry import evaluate_criterion, validate_criterion


SCHEMAS = {
    "search": {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
        "additionalProperties": False,
    }
}


def call(query):
    return {"name": "search", "arguments": {"query": query}}


def context(expected, actual):
    return {
        "tool_schemas": SCHEMAS,
        "expected_tool_calls": expected,
        "actual_tool_calls": actual,
    }


def test_exact_tool_calls_pass():
    result = evaluate_criterion(
        "tool_call_accuracy",
        "",
        {"minimum_score": 1},
        context([call("one"), call("two")], [call("two"), call("one")]),
    )
    assert result[0] is True
    assert result[1] == 1


def test_tool_calls_count_repetitions():
    result = evaluate_criterion(
        "tool_call_accuracy",
        "",
        {"minimum_score": 1},
        context([call("one"), call("one")], [call("one")]),
    )
    assert result[0] is False
    assert result[1] == pytest.approx(2 / 3)


def test_tool_calls_different_arguments_fail():
    result = evaluate_criterion(
        "tool_call_accuracy",
        "",
        {"minimum_score": 1},
        context([call("one")], [call("two")]),
    )
    assert result[1] == 0


def test_argument_schema_scoring():
    actual = [call("one"), {"name": "search", "arguments": {"query": 12}}]
    result = evaluate_criterion(
        "function_argument_validation",
        "",
        {"minimum_score": 1},
        context([], actual),
    )
    assert result[0] is False
    assert result[1] == 0.5


def test_missing_tool_evidence_rejected():
    with pytest.raises(ValueError):
        evaluate_criterion(
            "tool_call_accuracy",
            "",
            {"minimum_score": 1},
            {},
        )


def test_unapproved_tool_rejected():
    with pytest.raises(ValueError):
        evaluate_criterion(
            "tool_call_accuracy",
            "",
            {"minimum_score": 1},
            context([], [{"name": "unknown", "arguments": {}}]),
        )


def test_invalid_score_threshold_rejected():
    with pytest.raises(ValueError):
        validate_criterion("tool_call_accuracy", {"minimum_score": 2})
