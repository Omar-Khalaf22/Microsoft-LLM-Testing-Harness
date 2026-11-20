"""Score explicit tone and sentiment signals against configured vocabularies.

Lexical scoring is not a semantic sentiment classifier.
"""

import re


def evaluate(criterion_id: str, response: str, parameters: dict):
    if criterion_id not in {"sentiment_alignment", "tone_consistency"}:
        raise ValueError("Unknown lexical style criterion")
    if not isinstance(response, str) or len(response) > 100_000:
        raise ValueError("Response must be bounded text")
    tokens = re.findall(r"\b\w+\b", response.casefold())
    positive = {term.casefold() for term in parameters["positive_terms"]}
    negative = {term.casefold() for term in parameters["negative_terms"]}
    positive_count = sum(token in positive for token in tokens)
    negative_count = sum(token in negative for token in tokens)
    total = positive_count + negative_count
    observed = (positive_count - negative_count) / total if total else 0.0
    target = parameters["target_score"]
    tolerance = parameters["tolerance"]
    distance = abs(observed - target)
    passed = distance <= tolerance
    score = max(0.0, 1.0 - distance / 2.0)
    return (
        passed,
        score,
        f"Lexical style score: {observed:.4f}; target: {target:.4f}; "
        f"matched terms: {total}",
    )
