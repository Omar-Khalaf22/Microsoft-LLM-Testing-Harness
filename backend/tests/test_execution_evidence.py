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


@pytest.mark.parametrize(
    ("exit_code", "expected_pass"),
    [(0, True), (1, False), (127, False)],
)
def test_code_execution_exit_codes(exit_code, expected_pass):
    source = "print(1)"
    result = evidence(source)
    result["exit_code"] = exit_code
    passed, score, _ = evaluate_criterion(
        "code_execution", source, parameters(), {"execution_result": result}
    )
    assert passed is expected_pass
    assert score == float(expected_pass)


@pytest.mark.parametrize(
    ("outcomes", "expected_pass", "expected_score"),
    [
        ([True, True], True, 1.0),
        ([True, False], False, 0.5),
        ([False, False], False, 0.0),
    ],
)
def test_unit_test_score_boundaries(outcomes, expected_pass, expected_score):
    source = "print(1)"
    result = evidence(source)
    for item, outcome in zip(result["test_results"], outcomes, strict=True):
        item["passed"] = outcome
    passed, score, _ = evaluate_criterion(
        "unit_test_pass", source, parameters(), {"execution_result": result}
    )
    assert passed is expected_pass
    assert score == pytest.approx(expected_score)


@pytest.mark.parametrize("criterion_id", ["code_execution", "unit_test_pass"])
def test_execution_timeout_fails_closed(criterion_id):
    source = "print(1)"
    result = evidence(source)
    result["timed_out"] = True
    passed, score, _ = evaluate_criterion(
        criterion_id, source, parameters(), {"execution_result": result}
    )
    assert not passed
    assert score == 0.0


@pytest.mark.parametrize("criterion_id", ["code_execution", "unit_test_pass"])
def test_untrusted_execution_evidence_rejected(criterion_id):
    source = "print(1)"
    result = evidence(source)
    result["trusted"] = False
    with pytest.raises(ValueError):
        evaluate_criterion(criterion_id, source, parameters(), {"execution_result": result})


def test_duplicate_test_results_rejected():
    source = "print(1)"
    result = evidence(source)
    result["test_results"][1]["id"] = "one"
    with pytest.raises(ValueError):
        evaluate_criterion("unit_test_pass", source, parameters(), {"execution_result": result})


def test_missing_test_result_rejected():
    source = "print(1)"
    result = evidence(source)
    result["test_results"].pop()
    with pytest.raises(ValueError):
        evaluate_criterion("unit_test_pass", source, parameters(), {"execution_result": result})
