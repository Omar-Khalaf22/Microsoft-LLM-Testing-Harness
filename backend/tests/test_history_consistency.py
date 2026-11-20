"""Tests for history based fact consistency scoring."""

import pytest

from app.evaluation.registry import evaluate_criterion, validate_criterion


def parameters():
    return {
        "expected_facts": ["My name is Lina"],
        "conflicting_facts": ["My name is Bob"],
        "ignore_case": True,
        "minimum_retention": 1.0,
    }


@pytest.mark.parametrize("criterion_id", ["multi_turn_consistency", "memory_consistency"])
def test_retained_fact(criterion_id):
    result = evaluate_criterion(
        criterion_id,
        "MY NAME IS LINA",
        parameters(),
        {"conversation_history": ["Hello", "My name is Lina"]},
    )
    assert result[0]
    assert result[1] == 1.0


def test_conflict_fails():
    result = evaluate_criterion(
        "memory_consistency",
        "My name is Lina, but My name is Bob",
        parameters(),
        {"conversation_history": ["My name is Lina"]},
    )
    assert not result[0]
    assert result[1] == 0.0


def test_missing_fact_fails():
    result = evaluate_criterion(
        "multi_turn_consistency",
        "I am here",
        parameters(),
        {"conversation_history": ["My name is Lina"]},
    )
    assert not result[0]
    assert result[1] == 0.0


@pytest.mark.parametrize("history", [[], ["ok", 2], "wrong"])
def test_invalid_history(history):
    with pytest.raises(ValueError):
        evaluate_criterion(
            "memory_consistency",
            "My name is Lina",
            parameters(),
            {"conversation_history": history},
        )


def test_reference_not_in_history():
    with pytest.raises(ValueError):
        evaluate_criterion(
            "memory_consistency",
            "My name is Lina",
            parameters(),
            {"conversation_history": ["Different information"]},
        )


def test_invalid_parameters():
    with pytest.raises(ValueError):
        validate_criterion(
            "memory_consistency",
            {
                "expected_facts": [],
                "conflicting_facts": [],
                "ignore_case": True,
                "minimum_retention": 1,
            },
        )
