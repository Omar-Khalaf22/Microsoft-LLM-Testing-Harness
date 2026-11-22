"""Regression tests for structured entity matching and context relevance."""

import pytest

from app.evaluation.registry import evaluate_criterion


@pytest.mark.parametrize(
    ("response", "expected_pass", "expected_score"),
    [
        ('["Microsoft", "Tampa"]', True, 1.0),
        ('["Microsoft"]', False, 2 / 3),
        ('["Unrelated"]', False, 0.0),
    ],
)
def test_entity_extraction_f1(response, expected_pass, expected_score):
    parameters = {
        "reference_entities": ["Microsoft", "Tampa"],
        "ignore_case": True,
        "minimum_f1": 0.8,
    }
    passed, score, detail = evaluate_criterion("entity_extraction", response, parameters, {})
    assert passed is expected_pass
    assert score == pytest.approx(expected_score)
    assert detail


@pytest.mark.parametrize(
    ("response", "expected_pass", "expected_score"),
    [
        ('[{"text": "Microsoft", "label": "ORG"}]', True, 1.0),
        ('[{"text": "Microsoft", "label": "PERSON"}]', False, 0.0),
        ("[]", False, 0.0),
    ],
)
def test_named_entity_accuracy_f1(response, expected_pass, expected_score):
    parameters = {
        "reference_entities": [{"text": "Microsoft", "label": "ORG"}],
        "ignore_case": True,
        "minimum_f1": 0.8,
    }
    passed, score, detail = evaluate_criterion(
        "named_entity_accuracy", response, parameters, {}
    )
    assert passed is expected_pass
    assert score == pytest.approx(expected_score)
    assert detail


@pytest.mark.parametrize(
    ("passages", "expected_pass", "expected_score"),
    [
        (["Microsoft in Tampa"], True, 1.0),
        (["Microsoft only"], True, 0.5),
        (["Unrelated information"], False, 0.0),
    ],
)
def test_context_relevance_overlap(passages, expected_pass, expected_score):
    parameters = {"stop_words": [], "minimum_overlap": 0.5}
    context = {"query": "Microsoft Tampa", "retrieved_contexts": passages}
    passed, score, detail = evaluate_criterion(
        "context_relevance", "response", parameters, context
    )
    assert passed is expected_pass
    assert score == pytest.approx(expected_score)
    assert detail


@pytest.mark.parametrize(
    ("criterion_id", "response", "parameters"),
    [
        (
            "entity_extraction",
            '["Microsoft", "microsoft"]',
            {"reference_entities": ["Microsoft"], "ignore_case": True, "minimum_f1": 1},
        ),
        (
            "named_entity_accuracy",
            '[{"text": "Microsoft", "label": "ORG"}, {"text": "Microsoft", "label": "ORG"}]',
            {
                "reference_entities": [{"text": "Microsoft", "label": "ORG"}],
                "ignore_case": True,
                "minimum_f1": 1,
            },
        ),
    ],
)
def test_duplicate_entity_predictions_rejected(criterion_id, response, parameters):
    with pytest.raises(ValueError):
        evaluate_criterion(criterion_id, response, parameters, {})
