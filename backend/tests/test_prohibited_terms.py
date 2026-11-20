"""Regression tests for explicit prohibited term rules."""

import pytest

from app.evaluation.registry import evaluate_criterion, validate_criterion


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        ("No prohibited content here.", True),
        ("A BADWORD appears.", False),
        ("badwords are not exact matches.", True),
        ("The term badword! is present.", False),
        ("badwording should not match.", True),
    ],
)
def test_prohibited_term_detection(response, expected):
    passed, score, detail = evaluate_criterion(
        "profanity_detection",
        response,
        {"prohibited_terms": ["badword"]},
        {},
    )
    assert passed is expected
    assert score == float(expected)
    assert "matched" in detail


@pytest.mark.parametrize("terms", [[], [""], ["x" * 101]])
def test_invalid_terms_rejected(terms):
    with pytest.raises(ValueError):
        validate_criterion("profanity_detection", {"prohibited_terms": terms})
