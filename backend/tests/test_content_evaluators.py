"""Prototype 2 registry and content evaluator tests."""
import pytest

from app.evaluation.registry import catalog, get_criterion, list_supported_criteria, validate_criterion
from app.evaluation.validators import evaluate_selected
from app.evaluation.evaluators.content import evaluate


@pytest.mark.parametrize("criterion_id,params,response,passed", [
    ("required_keywords", {"keywords": ["alpha", "beta"]}, "alpha beta", True),
    ("forbidden_keywords", {"keywords": ["secret"]}, "public", True),
    ("required_phrases", {"phrases": ["hello world"]}, "hello world!", True),
    ("forbidden_phrases", {"phrases": ["do not"]}, "please proceed", True),
    ("exact_match", {"expected": "Yes"}, "Yes", True),
    ("contains_text", {"text": "Yes"}, "Yes please", True),
    ("case_insensitive_match", {"expected": "YES"}, "yes", True),
    ("minimum_characters", {"count": 3}, "abcd", True),
    ("maximum_characters", {"count": 4}, "abcd", True),
    ("minimum_sentences", {"count": 2}, "First. Second.", True),
])
def test_content_criteria(criterion_id, params, response, passed):
    validate_criterion(criterion_id, params)
    actual, normalized, detail = evaluate(criterion_id, response, params)
    assert actual is passed
    assert normalized == 1
    assert detail


def test_catalog_marks_only_implemented_entries_supported():
    assert len(catalog()) == 100
    assert len(list_supported_criteria()) == 10


def test_planned_criterion_cannot_execute():
    with pytest.raises(ValueError):
        validate_criterion("semantic_similarity", {})


def test_reject_missing_parameters():
    with pytest.raises(ValueError):
        validate_criterion("required_keywords", {})


def test_reject_invalid_weight_total():
    with pytest.raises(ValueError):
        evaluate_selected("hello", [{"id": "exact_match", "parameters": {"expected": "hello"}, "weight": 50}])


def test_dispatcher_scores_selected_criteria():
    score, results = evaluate_selected("hello", [
        {"id": "exact_match", "parameters": {"expected": "hello"}, "weight": 60},
        {"id": "minimum_characters", "parameters": {"count": 3}, "weight": 40},
    ])
    assert score == 100
    assert len(results) == 2


def test_dispatcher_rejects_duplicate_ids():
    with pytest.raises(ValueError):
        evaluate_selected("hello", [
            {"id": "exact_match", "parameters": {"expected": "hello"}, "weight": 50},
            {"id": "exact_match", "parameters": {"expected": "hello"}, "weight": 50},
        ])
