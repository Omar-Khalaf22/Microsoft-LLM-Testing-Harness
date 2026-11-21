"""Tests for explicitly configured safety phrase rules."""

import pytest

from app.evaluation.registry import evaluate_criterion, validate_criterion


@pytest.mark.parametrize("criterion_id", ["toxicity", "bias", "safety_policy"])
def test_configured_safety_rules(criterion_id):
    parameters = {
        "prohibited_phrases": ["blocked phrase", "another blocked phrase"],
        "ignore_case": True,
        "maximum_matches": 0,
    }
    passed, score, detail = evaluate_criterion(criterion_id, "BLOCKED PHRASE", parameters, {})
    assert not passed
    assert score == 0.5
    assert "matched: 1" in detail
    passed, score, _ = evaluate_criterion(criterion_id, "Unrelated text", parameters, {})
    assert passed
    assert score == 1.0


def test_configured_match_threshold():
    parameters = {
        "prohibited_phrases": ["blocked phrase", "another blocked phrase"],
        "ignore_case": True,
        "maximum_matches": 1,
    }
    passed, score, _ = evaluate_criterion("safety_policy", "blocked phrase", parameters, {})
    assert passed
    assert score == 0.5


@pytest.mark.parametrize("criterion_id", ["toxicity", "bias", "safety_policy"])
def test_empty_rules_rejected(criterion_id):
    with pytest.raises(ValueError):
        validate_criterion(
            criterion_id,
            {
                "prohibited_phrases": [],
                "ignore_case": True,
                "maximum_matches": 0,
            },
        )
