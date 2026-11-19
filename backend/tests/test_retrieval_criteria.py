"""Regression tests for ranking based retrieval evaluation."""

import pytest

from app.evaluation.registry import evaluate_criterion, validate_criterion


@pytest.mark.parametrize(
    "criterion,ranked,relevant,threshold,passed,score",
    [
        ("retrieval_hit_rate", ["a", "b"], ["b"], 1.0, True, 1.0),
        ("retrieval_hit_rate", ["a", "b"], ["c"], 1.0, False, 0.0),
        ("retrieval_hit_rate", [], ["a"], 1.0, False, 0.0),
        ("retrieval_mrr", ["a", "b", "c"], ["b"], 0.5, True, 0.5),
        ("retrieval_mrr", ["a", "b", "c"], ["c"], 0.5, False, 1.0 / 3),
        ("retrieval_mrr", ["a", "b"], ["z"], 0.1, False, 0.0),
        ("retrieval_mrr", ["a", "b"], ["a", "b"], 1.0, True, 1.0),
    ],
)
def test_ranked_retrieval(criterion, ranked, relevant, threshold, passed, score):
    result = evaluate_criterion(
        criterion,
        "",
        {"minimum_score": threshold},
        {"retrieved_document_ids": ranked, "relevant_document_ids": relevant},
    )
    assert result[0] is passed
    assert result[1] == pytest.approx(score)
    assert "rank" in result[2]


@pytest.mark.parametrize(
    "context",
    [
        {},
        {"retrieved_document_ids": [], "relevant_document_ids": []},
        {"retrieved_document_ids": ["a", "a"], "relevant_document_ids": ["a"]},
        {"retrieved_document_ids": [None], "relevant_document_ids": ["a"]},
        {"retrieved_document_ids": ["a"], "relevant_document_ids": ["", "b"]},
        {"retrieved_document_ids": "a", "relevant_document_ids": ["a"]},
    ],
)
def test_invalid_retrieval_evidence_fails_explicitly(context):
    with pytest.raises(ValueError):
        evaluate_criterion("retrieval_mrr", "", {"minimum_score": 0.5}, context)


def test_retrieval_threshold_validation():
    with pytest.raises(ValueError, match="minimum_score"):
        validate_criterion("retrieval_hit_rate", {"minimum_score": 1.5})
