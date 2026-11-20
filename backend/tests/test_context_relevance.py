"""Tests for lexical query coverage in retrieval contexts."""

import pytest

from app.evaluation.registry import evaluate_criterion, validate_criterion


def parameters():
    return {"stop_words": ["the"], "minimum_overlap": 0.75}


def test_full_query_coverage():
    result = evaluate_criterion(
        "context_relevance",
        "answer",
        parameters(),
        {"query": "the Microsoft Tampa", "retrieved_contexts": ["Microsoft Tampa office"]},
    )
    assert result[0]
    assert result[1] == 1.0


def test_partial_query_coverage():
    result = evaluate_criterion(
        "context_relevance",
        "answer",
        parameters(),
        {"query": "Microsoft Tampa", "retrieved_contexts": ["Microsoft office"]},
    )
    assert not result[0]
    assert result[1] == 0.5


@pytest.mark.parametrize("query", ["", "the", None])
def test_invalid_or_filtered_query(query):
    with pytest.raises(ValueError):
        evaluate_criterion(
            "context_relevance",
            "answer",
            parameters(),
            {"query": query, "retrieved_contexts": ["Microsoft"]},
        )


def test_invalid_threshold_rejected():
    with pytest.raises(ValueError):
        validate_criterion(
            "context_relevance", {"stop_words": [], "minimum_overlap": 1.5}
        )
