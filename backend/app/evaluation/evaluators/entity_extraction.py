"""Compare structured entity extraction output with an explicit reference list."""

import json


def evaluate(criterion_id: str, response: str, parameters: dict):
    if criterion_id != "entity_extraction":
        raise ValueError("Unknown entity extraction criterion")
    if not isinstance(response, str) or len(response) > 100_000:
        raise ValueError("Response must be bounded text")
    try:
        extracted = json.loads(response)
    except (TypeError, ValueError) as exc:
        raise ValueError("Response must be a JSON array of entity strings") from exc
    if not isinstance(extracted, list) or len(extracted) > 200:
        raise ValueError("Response must be a JSON array of at most 200 entities")
    if any(not isinstance(item, str) or not item.strip() or len(item) > 256 for item in extracted):
        raise ValueError("Every extracted entity must be a nonempty bounded string")
    expected = parameters["reference_entities"]
    normalize = (lambda value: value.casefold().strip()) if parameters["ignore_case"] else (
        lambda value: value.strip()
    )
    actual_set = {normalize(item) for item in extracted}
    expected_set = {normalize(item) for item in expected}
    if len(actual_set) != len(extracted) or len(expected_set) != len(expected):
        raise ValueError("Duplicate entities after normalization are not allowed")
    matched = len(actual_set & expected_set)
    precision = matched / len(actual_set) if actual_set else float(not expected_set)
    recall = matched / len(expected_set) if expected_set else float(not actual_set)
    score = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return score >= parameters["minimum_f1"], score, (
        f"Entity precision: {precision:.4f}; recall: {recall:.4f}; F1: {score:.4f}"
    )
