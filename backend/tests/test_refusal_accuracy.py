"""Tests for explicit protocol refusal scoring."""

import pytest

from app.evaluation.registry import evaluate_criterion, validate_criterion


@pytest.mark.parametrize(
    ("response", "expected", "passed"),
    [
        ("REFUSED: unsafe", True, True),
        ("  REFUSED: unsafe", True, True),
        ("Allowed answer", False, True),
        ("Allowed answer", True, False),
        ("REFUSED: unsafe", False, False),
        ("This is REFUSED: in the middle", True, False),
    ],
)
def test_refusal_marker(response, expected, passed):
    result = evaluate_criterion(
        "refusal_accuracy",
        response,
        {"expected_refusal": expected, "refusal_marker": "REFUSED:"},
        {},
    )
    assert result[0] is passed
    assert result[1] == float(passed)


@pytest.mark.parametrize("marker", ["", "x" * 129])
def test_invalid_marker(marker):
    with pytest.raises(ValueError):
        validate_criterion(
            "refusal_accuracy",
            {"expected_refusal": True, "refusal_marker": marker},
        )
