"""Regression tests for recorded execution metric criteria."""

import pytest

from app.evaluation.registry import evaluate_criterion


@pytest.mark.parametrize(
    "criterion,metric,value,budget,expected",
    [
        ("latency_budget", "latency_ms", 300, 500, True),
        ("latency_budget", "latency_ms", 600, 500, False),
        ("response_time", "latency_ms", 500, 500, True),
        ("response_time", "latency_ms", 501, 500, False),
        ("token_budget", "total_tokens", 80, 100, True),
        ("token_budget", "total_tokens", 120, 100, False),
    ],
)
def test_recorded_metric(criterion, metric, value, budget, expected):
    passed, score, detail = evaluate_criterion(
        criterion,
        "Model response",
        {"maximum": budget},
        {"recorded_execution_metrics": {metric: value}},
    )
    assert passed is expected
    assert 0 <= score <= 1
    assert metric in detail


@pytest.mark.parametrize("value", [None, -1, True, "500", float("inf")])
def test_invalid_latency_metric(value):
    with pytest.raises(ValueError):
        evaluate_criterion(
            "latency_budget",
            "Model response",
            {"maximum": 500},
            {"recorded_execution_metrics": {"latency_ms": value}},
        )


def test_missing_telemetry_is_not_assumed():
    with pytest.raises(ValueError, match="Recorded execution metrics"):
        evaluate_criterion("token_budget", "response", {"maximum": 100}, {})
