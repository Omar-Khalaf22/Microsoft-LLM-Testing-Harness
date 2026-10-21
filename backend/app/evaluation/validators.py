"""Validated criterion execution, independent of the legacy six score fields."""
from .evaluators.content import evaluate
from .registry import validate_criterion


def evaluate_selected(response: str, selected: list[dict]) -> tuple[float, list[dict]]:
    if not selected:
        raise ValueError("At least one criterion is required")
    if len(selected) > 100:
        raise ValueError("Too many criteria")
    total = 0.0
    results = []
    ids = set()
    for item in selected:
        if not isinstance(item, dict) or set(item) != {"id", "parameters", "weight"}:
            raise ValueError("Each criterion requires id, parameters and weight")
        criterion_id = item["id"]
        if not isinstance(criterion_id, str) or criterion_id in ids:
            raise ValueError("Criterion IDs must be unique strings")
        ids.add(criterion_id)
        validate_criterion(criterion_id, item["parameters"])
        weight = item["weight"]
        if type(weight) not in (int, float) or not 0 <= weight <= 100 or weight != weight:
            raise ValueError("Weights must be finite numbers between 0 and 100")
        passed, normalized, detail = evaluate(criterion_id, response, item["parameters"])
        score = round(normalized * weight, 1)
        results.append(
            {
                "id": criterion_id,
                "passed": passed,
                "normalized_score": normalized,
                "score": score,
                "detail": detail,
            }
        )
        total += weight
    if abs(total - 100) > 1e-8:
        raise ValueError("Weights must total 100")
    return min(100.0, round(sum(r["score"] for r in results), 1)), results
