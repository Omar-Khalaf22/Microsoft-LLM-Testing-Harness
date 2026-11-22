"""Behavioral regression cases for evidence, confidence, and reference rules."""

import pytest

from app.evaluation.registry import evaluate_criterion

CASES = [
    (
        "completeness",
        "Alpha beta",
        {"required_facts": ["alpha", "beta"], "ignore_case": True, "minimum_coverage": 1},
        {},
        True,
        1.0,
    ),
    (
        "completeness",
        "Alpha",
        {"required_facts": ["alpha", "beta"], "ignore_case": True, "minimum_coverage": 1},
        {},
        False,
        0.5,
    ),
    (
        "contradiction_detection",
        "Safe answer",
        {"contradicting_phrases": ["wrong"], "ignore_case": True},
        {},
        True,
        1.0,
    ),
    (
        "contradiction_detection",
        "WRONG answer",
        {"contradicting_phrases": ["wrong"], "ignore_case": True},
        {},
        False,
        0.0,
    ),
    (
        "answerability",
        "The answer is 42",
        {"answer_markers": ["42"], "ignore_case": True},
        {},
        True,
        1.0,
    ),
    (
        "answerability",
        "Unknown",
        {"answer_markers": ["42"], "ignore_case": True},
        {},
        False,
        0.0,
    ),
    (
        "confidence_alignment",
        '{"confidence": 1, "correct": true}',
        {"maximum_brier_score": 0.25},
        {},
        True,
        1.0,
    ),
    (
        "confidence_alignment",
        '{"confidence": 1, "correct": false}',
        {"maximum_brier_score": 0.25},
        {},
        False,
        0.0,
    ),
    (
        "uncertainty_calibration",
        '[{"confidence": 1, "correct": true}, {"confidence": 0, "correct": false}]',
        {"maximum_brier_score": 0.25},
        {},
        True,
        1.0,
    ),
    (
        "uncertainty_calibration",
        '[{"confidence": 1, "correct": false}, {"confidence": 0, "correct": true}]',
        {"maximum_brier_score": 0.25},
        {},
        False,
        0.0,
    ),
    (
        "source_freshness",
        "response",
        {"reference_date": "2026-11-20", "maximum_age_days": 10, "minimum_fresh_fraction": 1},
        {"source_evidence": [{"published_at": "2026-11-10"}]},
        True,
        1.0,
    ),
    (
        "source_freshness",
        "response",
        {"reference_date": "2026-11-20", "maximum_age_days": 10, "minimum_fresh_fraction": 1},
        {"source_evidence": [{"published_at": "2026-11-09"}]},
        False,
        0.0,
    ),
]


@pytest.mark.parametrize(
    ("criterion_id", "response", "parameters", "context", "expected_pass", "expected_score"),
    CASES,
    ids=[f"{case[0]}_{index}" for index, case in enumerate(CASES)],
)
def test_evidence_and_confidence_scores(
    criterion_id, response, parameters, context, expected_pass, expected_score
):
    passed, score, detail = evaluate_criterion(criterion_id, response, parameters, context)
    assert passed is expected_pass
    assert score == pytest.approx(expected_score)
    assert detail


@pytest.mark.parametrize(
    ("criterion_id", "response", "parameters", "context"),
    [
        ("confidence_alignment", "not json", {"maximum_brier_score": 0.25}, {}),
        ("uncertainty_calibration", "[]", {"maximum_brier_score": 0.25}, {}),
        (
            "source_freshness",
            "response",
            {"reference_date": "2026-11-20", "maximum_age_days": 10, "minimum_fresh_fraction": 1},
            {"source_evidence": [{"published_at": "2026-11-21"}]},
        ),
    ],
)
def test_invalid_evidence_is_rejected(criterion_id, response, parameters, context):
    with pytest.raises(ValueError):
        evaluate_criterion(criterion_id, response, parameters, context)
