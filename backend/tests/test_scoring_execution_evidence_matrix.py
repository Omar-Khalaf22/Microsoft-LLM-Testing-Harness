"""Additional validation regressions for external execution evidence.

These tests validate evidence shape, not runtime isolation or authenticity.
"""

import pytest

from app.evaluation.registry import evaluate_criterion


def parameters():
    return {
        "language": "python",
        "isolated_runtime": "sandbox-v1",
        "test_cases": [{"id": "first"}, {"id": "second"}],
    }


def evidence():
    return {
        "trusted": True,
        "runtime": "sandbox-v1",
        "language": "python",
        "source": "print(1)",
        "timed_out": False,
        "exit_code": 0,
        "test_results": [
            {"id": "first", "passed": True},
            {"id": "second", "passed": True},
        ],
    }


@pytest.mark.parametrize("criterion_id", ["code_execution", "unit_test_pass"])
@pytest.mark.parametrize(
    ("field", "invalid"),
    [
        ("trusted", False),
        ("runtime", "another-runtime"),
        ("language", "javascript"),
        ("source", "print(2)"),
    ],
)
def test_execution_evidence_mismatch_rejected(criterion_id, field, invalid):
    result = evidence()
    result[field] = invalid
    with pytest.raises(ValueError):
        evaluate_criterion(
            criterion_id, "print(1)", parameters(), {"execution_result": result}
        )


@pytest.mark.parametrize("criterion_id", ["code_execution", "unit_test_pass"])
def test_missing_timeout_status_fails_closed(criterion_id):
    result = evidence()
    result.pop("timed_out")
    passed, score, detail = evaluate_criterion(
        criterion_id, "print(1)", parameters(), {"execution_result": result}
    )
    assert passed is False
    assert score == 0.0
    assert detail


@pytest.mark.parametrize("invalid", [None, True, "0", 0.0])
def test_execution_exit_code_type_rejected(invalid):
    result = evidence()
    result["exit_code"] = invalid
    with pytest.raises(ValueError):
        evaluate_criterion(
            "code_execution", "print(1)", parameters(), {"execution_result": result}
        )


@pytest.mark.parametrize("invalid", [None, 1, "true"])
def test_unit_test_result_requires_boolean(invalid):
    result = evidence()
    result["test_results"][0]["passed"] = invalid
    with pytest.raises(ValueError):
        evaluate_criterion(
            "unit_test_pass", "print(1)", parameters(), {"execution_result": result}
        )


def test_unit_test_results_can_arrive_out_of_order():
    result = evidence()
    result["test_results"].reverse()
    passed, score, detail = evaluate_criterion(
        "unit_test_pass", "print(1)", parameters(), {"execution_result": result}
    )
    assert passed is True
    assert score == 1.0
    assert detail
