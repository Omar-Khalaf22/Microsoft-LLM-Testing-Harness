import pytest

from app.evaluation.configuration import validate_selection
from app.evaluation.registry import list_supported_criteria, validate_criterion
from app.evaluation.scoring import score_response
from app.evaluation.validators import evaluate_selected


def chosen(cid="exact_match", parameters=None, weight=100):
    return {
        "criterion_id": cid,
        "parameters": parameters if parameters is not None else {"expected": "yes"},
        "weight": weight,
    }


@pytest.mark.parametrize("weight", [0, -1, 100.001, 0.001, True, "100", float("nan"), float("inf")])
def test_invalid_selected_points(weight):
    with pytest.raises(ValueError):
        validate_selection([chosen(weight=weight)])


def test_decimal_full_credit_and_small_maximum():
    score, rows = evaluate_selected(
        "yes",
        [
            chosen(weight=33.33),
            chosen("minimum_characters", {"count": 3}, 33.33),
            chosen("nonempty_response", {}, 33.34),
        ],
    )
    assert score == 100 and [r["score"] for r in rows] == [33.33, 33.33, 33.34]
    score, rows = evaluate_selected(
        "yes", [chosen(weight=0.06), chosen("nonempty_response", {}, 99.94)]
    )
    assert score == 100 and rows[0]["score"] == rows[0]["maximum_points"] == 0.06


def test_legacy_precision_is_correct_too():
    score, rows = score_response(
        "yes",
        "yes",
        [],
        0,
        1,
        [],
        {
            "keyword": 33.33,
            "relevance": 33.33,
            "length": 33.34,
            "sentences": 0,
            "forbidden": 0,
            "valid": 0,
        },
    )
    assert score == 100
    assert all(r.score <= r.maximum_points for r in rows)


def test_content_fractional_result_and_round_half_up():
    score, rows = evaluate_selected(
        "alpha",
        [
            chosen("required_keywords", {"keywords": ["alpha", "beta"]}, 33.33),
            chosen("nonempty_response", {}, 66.67),
        ],
    )
    assert rows[0]["normalized_score"] == 0.5 and rows[0]["score"] == 16.67
    assert score == 83.34


def test_structured_and_content_execute_together():
    score, rows = evaluate_selected(
        '{"count":3}',
        [
            chosen("json_field_type", {"field": "count", "type": "integer"}, 50),
            chosen("contains_text", {"text": "count"}, 50),
        ],
    )
    assert score == 100 and len(rows) == 2
    score, _ = evaluate_selected(
        '{"count":"three"}', [chosen("json_field_type", {"field": "count", "type": "integer"})]
    )
    assert score == 0


def test_missing_response_is_not_full_credit_for_forbidden_terms():
    score, rows = evaluate_selected(None, [chosen("forbidden_keywords", {"keywords": ["secret"]})])
    assert score is None and rows[0]["score"] is None


def test_catalog_examples_all_validate():
    for definition in list_supported_criteria():
        assert definition["status"] == "supported"
        validate_criterion(definition["id"], definition["example_parameters"])


def test_forbidden_terms_award_zero_if_any_forbidden_term_appears():
    score, rows = evaluate_selected(
        "secret", [chosen("forbidden_keywords", {"keywords": ["secret", "hidden"]})]
    )
    assert score == 0 and rows[0]["normalized_score"] == 0


def test_legacy_fractional_half_cent_uses_decimal_arithmetic():
    score, rows = score_response(
        "irrelevant",
        "a b c d e f g",
        list("abcdefghij"),
        0,
        1,
        [],
        {
            "keyword": 0.05,
            "relevance": 0,
            "length": 0,
            "sentences": 0,
            "forbidden": 0,
            "valid": 99.95,
        },
    )
    assert rows[0].score == 0.04 and score == 99.99
