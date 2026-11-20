"""Regression coverage for SQLite query syntax scoring."""

import pytest

from app.evaluation.registry import evaluate_criterion, validate_criterion


@pytest.mark.parametrize(
    "query,expected",
    [
        ("SELECT 1 + 2", True),
        ("SELECT 'hello' AS greeting", True),
        ("WITH x AS (SELECT 2 AS value) SELECT value FROM x", True),
        ("SELECT FROM", False),
        ("SELECT (", False),
        ("DELETE FROM users", False),
        ("SELECT 1; DROP TABLE users", False),
        ("", False),
    ],
)
def test_sql_syntax_scoring(query, expected):
    passed, score, detail = evaluate_criterion("sql_syntax", query, {}, {})
    assert passed is expected
    assert score == float(expected)
    assert detail


def test_sql_syntax_rejects_unexpected_parameters():
    with pytest.raises(ValueError):
        validate_criterion("sql_syntax", {"unsafe": True})


def test_sql_syntax_rejects_unknown_tables_without_schema():
    passed, score, detail = evaluate_criterion("sql_syntax", "SELECT * FROM missing_table", {}, {})
    assert not passed
    assert score == 0.0
    assert "preparation failed" in detail.lower()
