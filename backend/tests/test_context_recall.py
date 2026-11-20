"""Tests for explicit reference fact coverage in retrieval context."""

import pytest

from app.evaluation.registry import evaluate_criterion, validate_criterion


def parameters():
    return {
        "reference_facts": ["Microsoft", "Tampa"],
        "ignore_case": True,
        "minimum_recall": 0.75,
    }


def test_complete_reference_coverage():
    result = evaluate_criterion(
        "context_recall",
        "answer",
        parameters(),
        {"retrieved_contexts": ["microsoft has an office", "TAMPA is in Florida"]},
    )
    assert result[0]
    assert result[1] == 1.0


def test_partial_reference_coverage():
    result = evaluate_criterion(
        "context_recall",
        "answer",
        parameters(),
        {"retrieved_contexts": ["Microsoft is mentioned"]},
    )
    assert not result[0]
    assert result[1] == 0.5


@pytest.mark.parametrize("contexts", [[], ["ok", 42], "not a list"])
def test_invalid_contexts(contexts):
    with pytest.raises(ValueError):
        evaluate_criterion(
            "context_recall", "answer", parameters(), {"retrieved_contexts": contexts}
        )


def test_missing_reference_facts_rejected():
    with pytest.raises(ValueError):
        validate_criterion(
            "context_recall",
            {"reference_facts": [], "ignore_case": True, "minimum_recall": 0.8},
        )
