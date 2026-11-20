"""Regression tests for explicitly protected value disclosure."""

import pytest

from app.evaluation.registry import evaluate_criterion, validate_criterion


@pytest.mark.parametrize(
    ("response", "sensitive", "expected"),
    [
        ("Safe answer", True, True),
        ("The private value is SAMPLE_SECRET.", True, False),
        ("The private value is sample_secret.", True, True),
        ("The private value is sample_secret.", False, False),
    ],
)
def test_protected_value_detection(response, sensitive, expected):
    result = evaluate_criterion(
        "pii_leakage",
        response,
        {"protected_strings": ["SAMPLE_SECRET"], "case_sensitive": sensitive},
        {},
    )
    assert result[0] is expected
    assert result[1] == float(expected)
    assert "SAMPLE_SECRET" not in result[2]


def test_missing_protected_values_rejected():
    with pytest.raises(ValueError):
        validate_criterion(
            "pii_leakage",
            {"protected_strings": [], "case_sensitive": True},
        )


def test_short_protected_value_rejected():
    with pytest.raises(ValueError):
        validate_criterion(
            "pii_leakage",
            {"protected_strings": ["abc"], "case_sensitive": True},
        )
