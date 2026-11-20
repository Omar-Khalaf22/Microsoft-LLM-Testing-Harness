"""Tests for configured privacy disclosure scoring."""

import pytest

from app.evaluation.registry import evaluate_criterion, validate_criterion


def test_private_value_detected():
    params = {"protected_strings": ["PRIVATE_TOKEN"], "case_sensitive": False}
    passed, score, detail = evaluate_criterion(
        "privacy_compliance", "Leaked private_token", params, {}
    )
    assert not passed
    assert score == 0.0
    assert "PRIVATE_TOKEN" not in detail


def test_private_value_absent():
    params = {"protected_strings": ["PRIVATE_TOKEN"], "case_sensitive": True}
    passed, score, _ = evaluate_criterion(
        "privacy_compliance", "Only public information", params, {}
    )
    assert passed
    assert score == 1.0


def test_case_sensitive_comparison():
    params = {"protected_strings": ["PRIVATE_TOKEN"], "case_sensitive": True}
    passed, score, _ = evaluate_criterion("privacy_compliance", "private_token", params, {})
    assert passed
    assert score == 1.0


def test_empty_protected_values_rejected():
    with pytest.raises(ValueError):
        validate_criterion(
            "privacy_compliance",
            {"protected_strings": [], "case_sensitive": True},
        )
