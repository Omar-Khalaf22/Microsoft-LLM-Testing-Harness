"""Deterministic retrieval quality metrics using approved relevance labels."""


def evaluate(criterion_id: str, response: str, parameters: dict, context: dict):
    """Score one query using ranked document identifiers and relevance judgments."""
    if not isinstance(context, dict):
        raise ValueError("Retrieval context must be an object")
    ranked = context.get("retrieved_document_ids")
    relevant = context.get("relevant_document_ids")
    if not isinstance(ranked, list) or not isinstance(relevant, list):
        raise ValueError("Ranked and relevant document ID lists are required")
    if not relevant:
        raise ValueError("At least one relevant document ID is required")
    if any(not isinstance(x, str) or not x.strip() for x in ranked + relevant):
        raise ValueError("Document IDs must be nonempty strings")
    if len(ranked) != len(set(ranked)) or len(relevant) != len(set(relevant)):
        raise ValueError("Document IDs must be unique within each list")
    if len(ranked) > 10000 or len(relevant) > 10000:
        raise ValueError("Document ID lists exceed the limit")
    relevant_set = set(relevant)
    first_rank = next((i for i, item in enumerate(ranked, start=1) if item in relevant_set), None)
    if criterion_id == "retrieval_hit_rate":
        score = 1.0 if first_rank is not None else 0.0
    elif criterion_id == "retrieval_mrr":
        score = 1.0 / first_rank if first_rank is not None else 0.0
    else:
        raise ValueError("Unknown retrieval criterion")
    minimum = parameters["minimum_score"]
    return score >= minimum, score, f"First relevant document rank: {first_rank}; score: {score:.4f}"
