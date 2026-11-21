"""Tests for scoring externally supplied isolated execution evidence."""

import pytest

from app.evaluation.registry import evaluate_criterion, validate_criterion


def parameters():
    return {
        "language": "python",
        "isolated_runtime": "sandbox-v1",
        "test_cases": [{"id": "one"}, {"id": "two"}],
    }


def evidence(source):
    return {
        "trusted": True,
        "runtime": "sandbox-v1",
        "language": "python",
        "source": source,
        "timed_out": False,
        "exit_code": 0,
        "test_results": [
            {"id": "one", "passed": True},
            {"id": "two", "passed": False},
        ],
    }


def test_code_execution_success():
    source = "print(1)"
    passed, score, _ = evaluate_criterion(
        "code_execution", source, parameters(), {"execution_result": evidence(source)}
    )
    assert passed
    assert score == 1.0


def test_unit_test_partial_result():
    source = "print(1)"
    passed, score, _ = evaluate_criterion(
        "unit_test_pass", source, parameters(), {"execution_result": evidence(source)}
    )
    assert not passed
    assert score == 0.5


def test_missing_execution_evidence_rejected():
    with pytest.raises(ValueError):
        evaluate_criterion("code_execution", "print(1)", parameters(), {})


def test_wrong_source_rejected():
    with pytest.raises(ValueError):
        evaluate_criterion(
            "code_execution",
            "print(2)",
            parameters(),
            {"execution_result": evidence("print(1)")},
        )


def test_invalid_configuration_rejected():
    invalid = parameters()
    invalid["test_cases"] = []
    with pytest.raises(ValueError):
        validate_criterion("unit_test_pass", invalid)
