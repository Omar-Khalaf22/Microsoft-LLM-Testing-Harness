"""Regression tests for literal retrieval coverage and claim faithfulness."""

import pytest

from app.evaluation.registry import evaluate_criterion


@pytest.mark.parametrize(
    ("passages", "expected_pass", "expected_score"),
    [
        (["Microsoft", "Tampa"], True, 1.0),
        (["Microsoft", "Unrelated"], False, 0.5),
        (["Unrelated"], False, 0.0),
    ],
)
def test_context_precision(passages, expected_pass, expected_score):
    parameters = {
        "reference_facts": ["Microsoft", "Tampa"],
        "ignore_case": True,
        "minimum_precision": 1,
    }
    context = {"retrieved_contexts": passages}
    passed, score, detail = evaluate_criterion(
        "context_precision", "response", parameters, context
    )
    assert passed is expected_pass
    assert score == pytest.approx(expected_score)
    assert detail


@pytest.mark.parametrize(
    ("passages", "expected_pass", "expected_score"),
    [
        (["Microsoft", "Tampa"], True, 1.0),
        (["Microsoft"], False, 0.5),
        (["Unrelated"], False, 0.0),
    ],
)
def test_context_recall(passages, expected_pass, expected_score):
    parameters = {
        "reference_facts": ["Microsoft", "Tampa"],
        "ignore_case": True,
        "minimum_recall": 1,
    }
    context = {"retrieved_contexts": passages}
    passed, score, detail = evaluate_criterion(
        "context_recall", "response", parameters, context
    )
    assert passed is expected_pass
    assert score == pytest.approx(expected_score)
    assert detail


@pytest.mark.parametrize(
    ("response", "evidence", "expected_pass", "expected_score"),
    [
        ("Microsoft operates in Tampa.", "Microsoft operates in Tampa.", True, 1.0),
        ("Microsoft operates in Tampa.", "Microsoft operates elsewhere.", False, 0.5),
        ("No matching claims.", "No relevant facts.", False, 0.0),
    ],
)
def test_faithfulness_claim_coverage(response, evidence, expected_pass, expected_score):
    parameters = {
        "claims": ["Microsoft", "Tampa"],
        "ignore_case": True,
        "minimum_support": 1,
    }
    context = {"retrieved_contexts": [evidence]}
    passed, score, detail = evaluate_criterion("faithfulness", response, parameters, context)
    assert passed is expected_pass
    assert score == pytest.approx(expected_score)
    assert detail


@pytest.mark.parametrize(
    "criterion_id", ["context_precision", "context_recall", "faithfulness"]
)
def test_retrieval_evidence_required(criterion_id):
    parameters = {
        "reference_facts": ["Microsoft"],
        "ignore_case": True,
        "minimum_precision": 1,
        "minimum_recall": 1,
    }
    if criterion_id == "faithfulness":
        parameters = {"claims": ["Microsoft"], "ignore_case": True, "minimum_support": 1}
    else:
        parameters.pop("minimum_recall" if criterion_id == "context_precision" else "minimum_precision")
    with pytest.raises(ValueError):
        evaluate_criterion(criterion_id, "Microsoft", parameters, {})
