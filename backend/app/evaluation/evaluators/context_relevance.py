"""Deterministic query term overlap in retrieved passages."""

import re


def evaluate(criterion_id: str, response: str, parameters: dict, context: dict):
    if criterion_id != "context_relevance":
        raise ValueError("Unknown context relevance criterion")
    if not isinstance(context, dict):
        raise ValueError("Evaluation context must be an object")
    query = context.get("query")
    passages = context.get("retrieved_contexts")
    if not isinstance(query, str) or not query.strip() or len(query) > 10000:
        raise ValueError("A nonempty bounded query is required")
    if not isinstance(passages, list) or not passages or len(passages) > 100:
        raise ValueError("Provide 1 to 100 retrieved contexts")
    if any(not isinstance(item, str) or len(item) > 10000 for item in passages):
        raise ValueError("Retrieved contexts must be bounded strings")
    terms = set(re.findall(r"\w+", query.casefold()))
    terms.difference_update(word.casefold() for word in parameters["stop_words"])
    if not terms:
        raise ValueError("Query has no terms after stop word filtering")
    overlaps = []
    for passage in passages:
        tokens = set(re.findall(r"\w+", passage.casefold()))
        overlaps.append(len(terms & tokens) / len(terms))
    score = sum(overlaps) / len(overlaps)
    return (
        score >= parameters["minimum_overlap"],
        score,
        f"Mean query term coverage across {len(passages)} passages: {score:.4f}",
    )
