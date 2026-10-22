import pytest

from app.evaluation.evaluators import patterns
from app.evaluation.registry import validate_criterion
from app.evaluation.validators import evaluate_selected


@pytest.mark.parametrize(
    "cid,params,yes,no",
    [
        ("regex_match", {"pattern": "^OK$"}, "OK", "not OK"),
        ("regex_not_match", {"pattern": "secret"}, "public", "secret"),
        ("email_format", {}, "name@example.com", "name at example.com"),
        ("url_format", {}, "https://example.com/path", "javascript:alert(1)"),
        ("numeric_exact", {"expected": 3}, "3.0", "4"),
        ("numeric_range", {"minimum": 1, "maximum": 3}, "3", "4"),
        ("numeric_tolerance", {"expected": 5, "tolerance": 0.1}, "5.1", "5.10001"),
        ("word_count_min", {"count": 3}, "One two three", "One two"),
        ("word_count_max", {"count": 2}, "One two", "One two three"),
        (
            "required_sections",
            {"sections": ["Summary", "Risks"]},
            "# SUMMARY\nText\nRisks:\nOther",
            "This prose mentions summary and risks.",
        ),
    ],
)
def test_pattern_and_numeric_results(cid, params, yes, no):
    validate_criterion(cid, params)
    assert patterns.evaluate(cid, yes, params)[1] == 1
    assert patterns.evaluate(cid, no, params)[1] == 0


@pytest.mark.parametrize(
    "text", ["There are 2 and 3", "true", "NaN", "Infinity", "3 kg", '{"count":3}', "1e10000"]
)
def test_numeric_extraction_never_guesses(text):
    assert patterns.evaluate("numeric_exact", text, {"expected": 3})[1] == 0


@pytest.mark.parametrize(
    "cid,params",
    [
        ("regex_match", {"pattern": "["}),
        ("regex_match", {"pattern": "x" * 257}),
        ("numeric_range", {"minimum": 5, "maximum": 1}),
        ("numeric_tolerance", {"expected": 1, "tolerance": -1}),
        ("word_count_min", {"count": True}),
        ("required_sections", {"sections": []}),
    ],
)
def test_invalid_parameters_rejected(cid, params):
    with pytest.raises(ValueError):
        validate_criterion(cid, params)


def test_regex_timeout_is_unavailable_instead_of_zero(monkeypatch):
    def timed_out(*a, **k):
        raise TimeoutError("private pattern data")

    monkeypatch.setattr(patterns.regex, "search", timed_out)
    score, rows = evaluate_selected(
        "x", [{"criterion_id": "regex_match", "parameters": {"pattern": "x"}, "weight": 100}]
    )
    assert score is None
    assert rows[0]["status"] == "error" and rows[0]["score"] is None
    assert "private" not in rows[0]["detail"]


def test_large_input_is_an_evaluator_error():
    with pytest.raises(RuntimeError):
        patterns.evaluate("regex_match", "x" * 100001, {"pattern": "x"})
