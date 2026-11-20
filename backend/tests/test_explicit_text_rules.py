"""Tests for caller configured language and protected excerpt rules."""

import pytest

from app.evaluation.registry import evaluate_criterion, validate_criterion


def test_spelling_vocabulary():
    params = {"allowed_words": ["hello", "world"], "minimum_score": 0.75}
    passed, score, _ = evaluate_criterion("spelling", "Hello world", params, {})
    assert passed and score == 1.0
    passed, score, _ = evaluate_criterion("spelling", "Hello stranger", params, {})
    assert not passed and score == 0.5


def test_grammar_phrase_rules():
    params = {
        "forbidden_phrases": ["could of"],
        "ignore_case": True,
        "maximum_violations": 0,
    }
    passed, score, _ = evaluate_criterion("grammar", "Could of done it", params, {})
    assert not passed and score == 0.5
    passed, score, _ = evaluate_criterion("grammar", "Could have done it", params, {})
    assert passed and score == 1.0


def test_protected_excerpt_rules():
    params = {"protected_excerpts": ["private passage"], "ignore_case": True}
    passed, score, detail = evaluate_criterion(
        "copyright_compliance", "PRIVATE PASSAGE", params, {}
    )
    assert not passed and score == 0.0
    assert "private passage" not in detail.lower()
    passed, score, _ = evaluate_criterion(
        "copyright_compliance", "Independent wording", params, {}
    )
    assert passed and score == 1.0


@pytest.mark.parametrize(
    ("criterion_id", "parameters"),
    [
        ("spelling", {"allowed_words": [], "minimum_score": 1}),
        (
            "grammar",
            {"forbidden_phrases": [], "ignore_case": True, "maximum_violations": 0},
        ),
        ("copyright_compliance", {"protected_excerpts": [], "ignore_case": True}),
    ],
)
def test_invalid_rules(criterion_id, parameters):
    with pytest.raises(ValueError):
        validate_criterion(criterion_id, parameters)
