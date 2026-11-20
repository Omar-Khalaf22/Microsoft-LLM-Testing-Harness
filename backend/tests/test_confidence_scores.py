"""Regression tests for structured confidence scoring."""

import pytest

from app.evaluation.registry import evaluate_criterion, validate_criterion


def test_confidence_alignment():
    params = {"maximum_brier_score": 0.05}
    passed, score, _ = evaluate_criterion(
        "confidence_alignment", '{"confidence":0.9,"correct":true}', params, {}
    )
    assert passed
    assert score == pytest.approx(0.99)
    passed, score, _ = evaluate_criterion(
        "confidence_alignment", '{"confidence":0.9,"correct":false}', params, {}
    )
    assert not passed
    assert score == pytest.approx(0.19)


def test_batch_uncertainty():
    response = '[{"confidence":0.8,"correct":true},{"confidence":0.2,"correct":false}]'
    passed, score, detail = evaluate_criterion(
        "uncertainty_calibration", response, {"maximum_brier_score": 0.05}, {}
    )
    assert passed
    assert score == pytest.approx(0.96)
    assert "samples: 2" in detail


@pytest.mark.parametrize(
    "response",
    [
        "[]",
        '[{"confidence":0.5,"correct":true}]',
        '[{"confidence":1.5,"correct":true},{"confidence":0,"correct":false}]',
        '[{"confidence":true,"correct":true},{"confidence":0,"correct":false}]',
        '[{"confidence":0.5,"correct":1},{"confidence":0,"correct":false}]',
    ],
)
def test_invalid_batch_rejected(response):
    with pytest.raises(ValueError):
        evaluate_criterion(
            "uncertainty_calibration", response, {"maximum_brier_score": 1}, {}
        )


def test_invalid_threshold():
    with pytest.raises(ValueError):
        validate_criterion("confidence_alignment", {"maximum_brier_score": 2})
