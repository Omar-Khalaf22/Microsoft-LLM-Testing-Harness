"""Registry dispatcher. Failed evaluations retain unavailable scores and a null total."""

from .configuration import criterion_definition, validate_selection
from .points import earned_points, total_points
from .registry import evaluate_criterion
from .rubric_integration import evaluate_rubric


def evaluate_selected(response: str, selected: list[dict], context: dict | None = None):
    # Adapt Lina's original standalone helper interface for existing callers.
    selected = [
        dict(criterion_id=x["id"], parameters=x["parameters"], weight=x["weight"])
        if isinstance(x, dict) and set(x) == {"id", "parameters", "weight"}
        else x
        for x in selected
    ]
    selected = validate_selection(selected)
    context = context if context is not None else {}
    results = []
    for item in selected:
        cid = item["criterion_id"]
        result = dict(
            id=cid,
            criterion_id=cid,
            name=criterion_definition(item)["name"],
            maximum_points=item["weight"],
            status="completed",
        )
        try:
            if item.get("method"):
                met, normalized, detail = evaluate_rubric(
                    cid, response, item["parameters"], context, custom=True
                )
            else:
                met, normalized, detail = evaluate_criterion(
                    cid, response, item["parameters"], context
                )
            score = earned_points(normalized, item["weight"])
            result.update(passed=met, normalized_score=normalized, score=score, detail=detail)
            if cid in context.get("rubric_evidence", {}):
                result.update(context["rubric_evidence"][cid])
        except Exception:
            result.update(
                status="error",
                passed=None,
                normalized_score=None,
                score=None,
                detail="Evaluator could not complete. Review the criterion or retry.",
            )
        results.append(result)
    total = (
        total_points([x["score"] for x in results])
        if all(x["status"] == "completed" for x in results)
        else None
    )
    return total, results
