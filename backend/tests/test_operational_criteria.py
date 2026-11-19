"""Evidence based regression tests for operational scoring."""

import pytest

from app.evaluation.registry import evaluate_criterion, validate_criterion


@pytest.mark.parametrize(
    "expected,actual,score",
    [
        (["search"], ["search"], 1.0),
        (["search", "search"], ["search"], 2 / 3),
        (["search"], ["email"], 0.0),
        ([], [], 1.0),
        ([], ["search"], 0.0),
    ],
)
def test_tool_selection(expected, actual, score):
    result = evaluate_criterion(
        "tool_selection",
        "",
        {"minimum_score": 1},
        {"expected_tool_names": expected, "actual_tool_names": actual},
    )
    assert result[1] == pytest.approx(score)
    assert result[0] is (score == 1)


def test_cost_budget():
    context = {
        "recorded_execution_metrics": {
            "model": "test-model",
            "input_tokens": 100000,
            "output_tokens": 50000,
        },
        "versioned_price_map": {
            "test-model": {
                "version": "2026-11",
                "input_per_million": 1.0,
                "output_per_million": 2.0,
            }
        },
    }
    result = evaluate_criterion("cost_budget", "", {"maximum_usd": 0.25}, context)
    assert result[0] is True
    assert result[1] == 1.0
    result = evaluate_criterion("cost_budget", "", {"maximum_usd": 0.1}, context)
    assert result[0] is False
    assert result[1] == pytest.approx(0.5)


def test_cost_requires_recorded_evidence():
    with pytest.raises(ValueError):
        evaluate_criterion("cost_budget", "", {"maximum_usd": 1}, {})


def test_tool_selection_requires_recorded_evidence():
    with pytest.raises(ValueError):
        evaluate_criterion("tool_selection", "", {"minimum_score": 1}, {})


def test_cost_rejects_invalid_prices():
    context = {
        "recorded_execution_metrics": {
            "model": "m",
            "input_tokens": 1,
            "output_tokens": 1,
        },
        "versioned_price_map": {
            "m": {
                "version": "v1",
                "input_per_million": -1,
                "output_per_million": 1,
            }
        },
    }
    with pytest.raises(ValueError):
        evaluate_criterion("cost_budget", "", {"maximum_usd": 1}, context)


def test_invalid_threshold():
    with pytest.raises(ValueError):
        validate_criterion("tool_selection", {"minimum_score": 2})
