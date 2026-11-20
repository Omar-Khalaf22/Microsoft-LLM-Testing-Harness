"""Tests for explicit claim faithfulness against retrieved evidence."""

import pytest

from app.evaluation.registry import evaluate_criterion, validate_criterion


def params():
    return {
        "claims": ["Tampa", "Microsoft"],
        "ignore_case": True,
        "minimum_support": 1.0,
    }


def test_supported_claims():
    result = evaluate_criterion(
        "faithfulness",
        "Tampa Microsoft",
        params(),
        {"retrieved_contexts": ["Microsoft is in Tampa"]},
    )
    assert result[0]
    assert result[1] == 1.0


def test_unsupported_claim_fails():
    result = evaluate_criterion(
        "faithfulness",
        "Tampa Microsoft",
        params(),
        {"retrieved_contexts": ["Tampa only"]},
    )
    assert not result[0]
    assert result[1] == 0.5


def test_claim_missing_from_response():
    result = evaluate_criterion(
        "faithfulness",
        "Tampa",
        params(),
        {"retrieved_contexts": ["Tampa Microsoft"]},
    )
    assert not result[0]
    assert result[1] == 0.5


@pytest.mark.parametrize("sources", [[], "not a list", [123]])
def test_invalid_evidence(sources):
    with pytest.raises(ValueError):
        evaluate_criterion(
            "faithfulness",
            "Tampa Microsoft",
            params(),
            {"retrieved_contexts": sources},
        )


def test_invalid_claims():
    parameters = params()
    parameters["claims"] = []
    with pytest.raises(ValueError):
        validate_criterion("faithfulness", parameters)
