"""Behavioral scoring regression cases for recorded execution metrics."""

import pytest

from app.evaluation.registry import evaluate_criterion


@pytest.mark.parametrize(
    ("criterion_id", "metric", "maximum"),
    [
        ("latency_budget", "latency_ms", 100),
        ("response_time", "latency_ms", 100),
        ("token_budget", "total_tokens", 100),
    ],
)
@pytest.mark.parametrize(
    ("measured", "expected_pass", "expected_score"),
    [(0, True, 1.0), (100, True, 1.0), (200, False, 0.5)],
)
def test_recorded_metric_boundaries(
    criterion_id, metric, maximum, measured, expected_pass, expected_score
):
    context = {"recorded_execution_metrics": {metric: measured}}
    passed, score, detail = evaluate_criterion(
        criterion_id, "response", {"maximum": maximum}, context
    )
    assert passed is expected_pass
    assert score == pytest.approx(expected_score)
    assert detail


@pytest.mark.parametrize("criterion_id", ["latency_budget", "response_time", "token_budget"])
def test_missing_recorded_metric_is_rejected(criterion_id):
    with pytest.raises(ValueError):
        evaluate_criterion(criterion_id, "response", {"maximum": 100}, {})


@pytest.mark.parametrize(
    ("expected", "actual", "expected_pass", "expected_score"),
    [
        (["search"], ["search"], True, 1.0),
        (["search"], ["other"], False, 0.0),
        (["search", "read"], ["search"], False, 2 / 3),
        ([], [], True, 1.0),
    ],
)
def test_tool_selection_scores(expected, actual, expected_pass, expected_score):
    context = {"expected_tool_names": expected, "actual_tool_names": actual}
    passed, score, detail = evaluate_criterion(
        "tool_selection", "response", {"minimum_score": 1}, context
    )
    assert passed is expected_pass
    assert score == pytest.approx(expected_score)
    assert detail


@pytest.mark.parametrize(
    ("budget", "expected_pass", "expected_score"),
    [(0.002, True, 1.0), (0.001, False, 0.5)],
)
def test_cost_budget_scores(budget, expected_pass, expected_score):
    context = {
        "recorded_execution_metrics": {
            "model": "test-model",
            "input_tokens": 1000,
            "output_tokens": 1000,
        },
        "versioned_price_map": {
            "test-model": {
                "version": "v1",
                "input_per_million": 1.0,
                "output_per_million": 1.0,
            }
        },
    }
    passed, score, detail = evaluate_criterion(
        "cost_budget", "response", {"maximum_usd": budget}, context
    )
    assert passed is expected_pass
    assert score == pytest.approx(expected_score)
    assert detail


def test_cost_budget_requires_pricing_evidence():
    with pytest.raises(ValueError):
        evaluate_criterion("cost_budget", "response", {"maximum_usd": 1}, {})
