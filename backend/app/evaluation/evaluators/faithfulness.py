"""Verify explicit answer claims against supplied reference evidence.

This is deterministic evidence matching, not semantic entailment.
"""


def evaluate(criterion_id: str, response: str, parameters: dict, context: dict):
    if criterion_id != "faithfulness":
        raise ValueError("Unknown faithfulness criterion")
    if not isinstance(response, str) or len(response) > 100_000:
        raise ValueError("Response must be bounded text")
    if not isinstance(context, dict):
        raise ValueError("Context must be an object")
    sources = context.get("retrieved_contexts")
    if (
        not isinstance(sources, list)
        or not 1 <= len(sources) <= 100
        or any(not isinstance(item, str) or len(item) > 10000 for item in sources)
    ):
        raise ValueError("retrieved_contexts must contain 1 to 100 bounded strings")
    evidence = "\n".join(sources)
    if parameters["ignore_case"]:
        evidence = evidence.casefold()
        response = response.casefold()
    claims = parameters["claims"]
    supported = 0
    for claim in claims:
        candidate = claim.casefold() if parameters["ignore_case"] else claim
        if candidate in response and candidate in evidence:
            supported += 1
    score = supported / len(claims)
    return (
        score >= parameters["minimum_support"],
        score,
        f"Claims present in both response and evidence: {supported}/{len(claims)}",
    )
