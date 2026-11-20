"""Tests for literal reference fact precision in retrieved contexts."""

import pytest

from app.evaluation.registry import evaluate_criterion, validate_criterion


def parameters():
    return {
        "reference_facts": ["Microsoft", "Tampa"],
        "ignore_case": True,
        "minimum_precision": 0.75,
    }


def test_all_passages_relevant():
    result = evaluate_criterion(
        "context_precision",
        "answer",
        parameters(),
        {"retrieved_contexts": ["microsoft details", "TAMPA details"]},
    )
    assert result[0]
    assert result[1] == 1.0


def test_half_passages_relevant():
    result = evaluate_criterion(
        "context_precision",
        "answer",
        parameters(),
        {"retrieved_contexts": ["Microsoft details", "Unrelated details"]},
    )
    assert not result[0]
    assert result[1] == 0.5


@pytest.mark.parametrize("contexts", [[], ["valid", 123], "wrong type"])
def test_invalid_passages(contexts):
    with pytest.raises(ValueError):
        evaluate_criterion(
            "context_precision", "answer", parameters(), {"retrieved_contexts": contexts}
        )


def test_missing_reference_facts_rejected():
    with pytest.raises(ValueError):
        validate_criterion(
            "context_precision",
            {"reference_facts": [], "ignore_case": True, "minimum_precision": 0.8},
        )
