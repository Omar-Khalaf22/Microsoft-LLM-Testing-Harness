"""Behavioral scoring checks for refusal protocols and conversation facts."""

import pytest

from app.evaluation.registry import evaluate_criterion


@pytest.mark.parametrize(
    ("expected_refusal", "response", "expected_pass"),
    [
        (True, "REFUSED: Cannot comply.", True),
        (True, "Cannot comply.", False),
        (False, "Here is the answer.", True),
        (False, "REFUSED: Cannot comply.", False),
    ],
)
def test_refusal_protocol(expected_refusal, response, expected_pass):
    parameters = {
        "expected_refusal": expected_refusal,
        "refusal_marker": "REFUSED:",
    }
    passed, score, detail = evaluate_criterion("refusal_accuracy", response, parameters, {})
    assert passed is expected_pass
    assert score == float(expected_pass)
    assert detail


@pytest.mark.parametrize("criterion_id", ["multi_turn_consistency", "memory_consistency"])
@pytest.mark.parametrize(
    ("response", "expected_pass", "expected_score"),
    [
        ("My name is Lina. I live in Tampa.", True, 1.0),
        ("My name is Lina.", False, 0.5),
        ("My name is Bob. I live in Tampa.", False, 0.0),
    ],
)
def test_history_fact_retention(criterion_id, response, expected_pass, expected_score):
    parameters = {
        "expected_facts": ["My name is Lina", "I live in Tampa"],
        "conflicting_facts": ["My name is Bob"],
        "ignore_case": True,
        "minimum_retention": 1,
    }
    context = {
        "conversation_history": ["My name is Lina.", "I live in Tampa."],
    }
    passed, score, detail = evaluate_criterion(criterion_id, response, parameters, context)
    assert passed is expected_pass
    assert score == pytest.approx(expected_score)
    assert detail


@pytest.mark.parametrize("criterion_id", ["multi_turn_consistency", "memory_consistency"])
def test_history_missing_expected_fact_rejected(criterion_id):
    parameters = {
        "expected_facts": ["My name is Lina"],
        "conflicting_facts": ["My name is Bob"],
        "ignore_case": True,
        "minimum_retention": 1,
    }
    context = {"conversation_history": ["Unrelated history."]}
    with pytest.raises(ValueError):
        evaluate_criterion(criterion_id, "My name is Lina.", parameters, context)
