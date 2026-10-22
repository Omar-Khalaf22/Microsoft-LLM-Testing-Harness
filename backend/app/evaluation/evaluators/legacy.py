"""Unweighted equivalents of the six original checks; retained for old test workflows."""

import re

STOP_WORDS = set(
    (
        "the and for with what why how from into this that explain describe "
        "write provide tell are is to of in on a an"
    ).split()
)


def evaluate(criterion_id: str, response: str, parameters: dict, context: dict | None = None):
    if not isinstance(response, str):
        raise TypeError("The model response must be text.")
    folded = response.lower()
    if criterion_id == "keyword_coverage":
        terms = parameters["keywords"]
        hits = sum(term.lower() in folded for term in terms)
        ratio = hits / len(terms) if terms else 1.0
        return ratio == 1, ratio, f"Matched {hits} of {len(terms)} keywords"
    if criterion_id == "prompt_relevance":
        prompt = (context or {}).get("prompt", "")
        terms = {
            x
            for x in re.findall(r"[a-z0-9']+", prompt.lower())
            if len(x) > 2 and x not in STOP_WORDS
        }
        hits = len(terms & set(re.findall(r"[a-z0-9']+", folded)))
        ratio = hits / len(terms) if terms else 1.0
        return ratio >= 0.5, ratio, f"Matched {hits} of {len(terms)} meaningful prompt terms"
    if criterion_id in {"response_length", "sentence_structure"}:
        count = (
            len(response)
            if criterion_id == "response_length"
            else len([s for s in re.split(r"[.!?]+", response) if s.strip()])
        )
        target = parameters["count"]
        ratio = min(1.0, count / target) if target else 1.0
        return count >= target, ratio, f"Measured {count}; target {target}"
    if criterion_id == "forbidden_terms":
        hits = [t for t in parameters["terms"] if t.lower() in folded]
        return (
            not hits,
            float(not hits),
            "No forbidden terms detected" if not hits else f"Detected: {', '.join(hits)}",
        )
    if criterion_id == "nonempty_response":
        met = bool(response.strip())
        return met, float(met), "Model returned usable text" if met else "Response is empty"
    raise ValueError("Unknown legacy criterion.")


WEIGHT_IDS = {
    "keyword": "keyword_coverage",
    "relevance": "prompt_relevance",
    "length": "response_length",
    "sentences": "sentence_structure",
    "forbidden": "forbidden_terms",
    "valid": "nonempty_response",
}
