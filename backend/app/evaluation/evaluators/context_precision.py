"""Literal relevance precision of retrieved passages against reference facts."""


def evaluate(criterion_id: str, response: str, parameters: dict, context: dict):
    if criterion_id != "context_precision":
        raise ValueError("Unknown context precision criterion")
    if not isinstance(context, dict):
        raise ValueError("Evaluation context must be an object")
    passages = context.get("retrieved_contexts")
    if not isinstance(passages, list) or not passages or len(passages) > 100:
        raise ValueError("Provide 1 to 100 retrieved contexts")
    if any(not isinstance(item, str) or len(item) > 10000 for item in passages):
        raise ValueError("Retrieved contexts must be bounded strings")
    facts = parameters["reference_facts"]
    if parameters["ignore_case"]:
        passages = [passage.casefold() for passage in passages]
        facts = [fact.casefold() for fact in facts]
    relevant = sum(any(fact in passage for fact in facts) for passage in passages)
    score = relevant / len(passages)
    return (
        score >= parameters["minimum_precision"],
        score,
        f"Passages containing reference facts: {relevant}/{len(passages)}",
    )
