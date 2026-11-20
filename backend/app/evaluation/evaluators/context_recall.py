"""Reference fact coverage in retrieved contexts, not semantic RAG recall."""


def evaluate(criterion_id: str, response: str, parameters: dict, context: dict):
    if criterion_id != "context_recall":
        raise ValueError("Unknown context recall criterion")
    if not isinstance(context, dict):
        raise ValueError("Evaluation context must be an object")
    passages = context.get("retrieved_contexts")
    if not isinstance(passages, list) or not passages or len(passages) > 100:
        raise ValueError("Provide 1 to 100 retrieved contexts")
    if any(not isinstance(item, str) or len(item) > 10000 for item in passages):
        raise ValueError("Retrieved contexts must be bounded strings")
    reference = parameters["reference_facts"]
    text = "\n".join(passages)
    if parameters["ignore_case"]:
        text = text.casefold()
    found = sum(
        (fact.casefold() if parameters["ignore_case"] else fact) in text
        for fact in reference
    )
    score = found / len(reference)
    return (
        score >= parameters["minimum_recall"],
        score,
        f"Reference facts found in retrieved contexts: {found}/{len(reference)}",
    )
