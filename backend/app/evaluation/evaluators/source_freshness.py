"""Source freshness scoring using explicitly recorded publication dates."""

from datetime import date


def evaluate(criterion_id: str, response: str, parameters: dict, context: dict):
    if criterion_id != "source_freshness":
        raise ValueError(f"Unsupported criterion: {criterion_id}")
    if not isinstance(context, dict):
        raise ValueError("Evaluation context must be an object")
    sources = context.get("source_evidence")
    if not isinstance(sources, list) or not sources or len(sources) > 100:
        raise ValueError("Nonempty source_evidence list of at most 100 entries is required")
    try:
        reference = date.fromisoformat(parameters["reference_date"])
    except (TypeError, ValueError) as exc:
        raise ValueError("reference_date must be a valid ISO date") from exc
    ages = []
    for source in sources:
        if not isinstance(source, dict) or not isinstance(source.get("published_at"), str):
            raise ValueError("Each source requires a published_at ISO date")
        try:
            published = date.fromisoformat(source["published_at"])
        except ValueError as exc:
            raise ValueError("Source published_at must be a valid ISO date") from exc
        age = (reference - published).days
        if age < 0:
            raise ValueError("Source publication cannot be later than reference_date")
        ages.append(age)
    fresh = sum(age <= parameters["maximum_age_days"] for age in ages)
    score = fresh / len(ages)
    passed = score >= parameters["minimum_fresh_fraction"]
    return passed, score, f"Fresh dated sources: {fresh}/{len(ages)}"
