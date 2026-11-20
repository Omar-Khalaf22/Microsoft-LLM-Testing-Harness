"""Evaluate declared numeric confidence against known binary outcomes.

Confidence alignment uses a single prediction. Calibration uses a batch.
"""

import json
import math


def _validate_entry(entry):
    if not isinstance(entry, dict) or set(entry) != {"confidence", "correct"}:
        raise ValueError("Each prediction requires confidence and correct")
    confidence = entry["confidence"]
    correct = entry["correct"]
    if (
        isinstance(confidence, bool)
        or not isinstance(confidence, (int, float))
        or not math.isfinite(confidence)
        or not 0 <= confidence <= 1
        or not isinstance(correct, bool)
    ):
        raise ValueError("Confidence must be finite in [0, 1] and correct must be boolean")
    return confidence, float(correct)


def evaluate(criterion_id: str, response: str, parameters: dict):
    if criterion_id not in {"confidence_alignment", "uncertainty_calibration"}:
        raise ValueError("Unknown confidence criterion")
    if not isinstance(response, str) or len(response) > 100_000:
        raise ValueError("Response must be bounded text")
    try:
        data = json.loads(response)
    except (TypeError, ValueError) as exc:
        raise ValueError("Response must be valid JSON") from exc
    if criterion_id == "confidence_alignment":
        entries = [data]
    else:
        if not isinstance(data, list) or not 2 <= len(data) <= 1000:
            raise ValueError("Calibration requires 2 to 1000 predictions")
        entries = data
    predictions = [_validate_entry(entry) for entry in entries]
    brier = sum((confidence - correct) ** 2 for confidence, correct in predictions)
    brier /= len(predictions)
    score = 1.0 - brier
    return (
        brier <= parameters["maximum_brier_score"],
        score,
        f"Brier score: {brier:.4f}; samples: {len(predictions)}",
    )
