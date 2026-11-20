"""SQLite syntax validation without executing generated SQL."""

import sqlite3


def evaluate(criterion_id: str, response: str, parameters: dict) -> tuple[bool, float, str]:
    if criterion_id != "sql_syntax":
        raise ValueError(f"Unsupported criterion: {criterion_id}")
    if not isinstance(response, str):
        raise TypeError("The model response must be text.")
    sql = response.strip()
    if not sql:
        return False, 0.0, "Empty SQL statement"
    if len(sql) > 100_000:
        return False, 0.0, "SQL exceeds the validation limit"
    # Only prepare a query. Never execute user generated statements.
    if not sql.lstrip().upper().startswith(("SELECT ", "WITH ", "VALUES ")):
        return False, 0.0, "Only read only SQLite queries are supported"
    connection = sqlite3.connect(":memory:")
    try:
        try:
            connection.execute("EXPLAIN " + sql)
        except sqlite3.Error as exc:
            return False, 0.0, f"SQLite preparation failed: {exc}"
        return True, 1.0, "SQLite query prepared successfully without execution"
    finally:
        connection.close()
