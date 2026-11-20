"""Regression tests for evidence based source freshness."""

import pytest

from app.evaluation.registry import evaluate_criterion, validate_criterion

PARAMS = {
    "reference_date": "2026-11-20",
    "maximum_age_days": 30,
    "minimum_fresh_fraction": 0.5,
}


def test_freshness_all_recent():
    context = {"source_evidence": [{"published_at": "2026-11-01"}]}
    assert evaluate_criterion("source_freshness", "", PARAMS, context)[:2] == (True, 1.0)


def test_freshness_mixed():
    context = {
        "source_evidence": [
            {"published_at": "2026-11-01"},
            {"published_at": "2025-11-01"},
        ]
    }
    assert evaluate_criterion("source_freshness", "", PARAMS, context)[:2] == (True, 0.5)


def test_freshness_rejects_missing_evidence():
    with pytest.raises(ValueError):
        evaluate_criterion("source_freshness", "", PARAMS, {})


@pytest.mark.parametrize("published", ["invalid", "2026-11-21", "2026-02-30"])
def test_freshness_rejects_invalid_dates(published):
    with pytest.raises(ValueError):
        evaluate_criterion(
            "source_freshness", "", PARAMS, {"source_evidence": [{"published_at": published}]}
        )


def test_freshness_rejects_invalid_threshold():
    with pytest.raises(ValueError):
        validate_criterion("source_freshness", {**PARAMS, "minimum_fresh_fraction": 2})
