"""Evaluate typed named entity predictions against a labeled reference.

Input is a JSON list of objects with text and label fields.
"""

import json


def _pairs(items, ignore_case):
    if not isinstance(items, list) or len(items) > 200:
        raise ValueError("Named entities must be a list of at most 200 objects")
    result = []
    for item in items:
        if not isinstance(item, dict) or set(item) != {"text", "label"}:
            raise ValueError("Each named entity requires exactly text and label")
        value, label = item["text"], item["label"]
        if (
            not isinstance(value, str)
            or not value.strip()
            or len(value) > 256
            or not isinstance(label, str)
            or not label.strip()
            or len(label) > 64
        ):
            raise ValueError("Named entity text and label must be bounded strings")
        result.append((value.strip().casefold() if ignore_case else value.strip(), label.strip()))
    if len(set(result)) != len(result):
        raise ValueError("Duplicate named entities are not allowed")
    return set(result)


def evaluate(criterion_id: str, response: str, parameters: dict):
    if criterion_id != "named_entity_accuracy":
        raise ValueError("Unknown named entity criterion")
    if not isinstance(response, str) or len(response) > 100_000:
        raise ValueError("Response must be bounded text")
    try:
        predicted = json.loads(response)
    except (TypeError, ValueError) as exc:
        raise ValueError("Response must be a JSON array of typed named entities") from exc
    actual = _pairs(predicted, parameters["ignore_case"])
    expected = _pairs(parameters["reference_entities"], parameters["ignore_case"])
    matched = len(actual & expected)
    precision = matched / len(actual) if actual else float(not expected)
    recall = matched / len(expected) if expected else float(not actual)
    score = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return (
        score >= parameters["minimum_f1"],
        score,
        (
            f"Typed named entity matches: {matched}; precision: {precision:.4f}; "
            f"recall: {recall:.4f}; F1: {score:.4f}"
        ),
    )
