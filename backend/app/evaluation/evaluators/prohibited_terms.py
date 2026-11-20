"""User supplied prohibited term detection, not a general toxicity classifier."""

import re


def evaluate(criterion_id: str, response: str, parameters: dict):
    if criterion_id != "profanity_detection":
        raise ValueError("Unknown prohibited term criterion")
    if not isinstance(response, str) or len(response) > 100_000:
        raise ValueError("Response must be bounded text")
    terms = parameters["prohibited_terms"]
    if len(terms) > 100 or any(len(term) > 100 for term in terms):
        raise ValueError("Prohibited term list exceeds limits")
    matched = [
        term
        for term in terms
        if re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", response, re.IGNORECASE)
    ]
    passed = not matched
    return passed, float(passed), f"Prohibited terms matched: {len(matched)}"
