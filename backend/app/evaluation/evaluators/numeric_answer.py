"""Check a response containing a single numeric answer against a reference.

This does not verify proofs, derivations, or mathematical reasoning.
"""

import re
from decimal import Decimal, InvalidOperation

NUMBER = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?")


def evaluate(criterion_id: str, response: str, parameters: dict):
    if criterion_id != "mathematical_correctness":
        raise ValueError("Unknown mathematical criterion")
    if not isinstance(response, str) or len(response) > 100_000:
        raise ValueError("Response must be bounded text")
    candidate = response.strip()
    if NUMBER.fullmatch(candidate) is None:
        return False, 0.0, "Response is not a single numeric answer"
    try:
        actual = Decimal(candidate)
        expected = Decimal(parameters["expected_value"])
        tolerance = Decimal(parameters["absolute_tolerance"])
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("Invalid reference numeric value") from exc
    if not actual.is_finite() or not expected.is_finite():
        raise ValueError("Numeric values must be finite")
    difference = abs(actual - expected)
    passed = difference <= tolerance
    return (
        passed,
        float(passed),
        f"Absolute numeric error: {difference}; allowed: {tolerance}",
    )
