"""Measure explicit readability and repetition proxies.

These metrics do not establish semantic clarity or logical coherence.
"""

import re


def evaluate(criterion_id: str, response: str, parameters: dict):
    if criterion_id not in {"clarity", "coherence"}:
        raise ValueError("Unknown readability criterion")
    if not isinstance(response, str) or len(response) > 100_000:
        raise ValueError("Response must be bounded text")
    sentences = [sentence.strip() for sentence in re.split(r"[.!?]+", response) if sentence.strip()]
    if not sentences:
        return False, 0.0, "No nonempty sentences found"
    words = [re.findall(r"\b\w+\b", sentence) for sentence in sentences]
    if criterion_id == "clarity":
        eligible = sum(
            parameters["minimum_words"] <= len(tokens) <= parameters["maximum_words"]
            for tokens in words
        )
        score = eligible / len(sentences)
        return (
            score >= parameters["minimum_ratio"],
            score,
            f"Sentences within configured word limits: {eligible}/{len(sentences)}",
        )
    normalized = [" ".join(token.casefold() for token in tokens) for tokens in words]
    unique = len(set(normalized))
    score = unique / len(normalized)
    return (
        score >= parameters["minimum_ratio"],
        score,
        f"Distinct normalized sentences: {unique}/{len(normalized)}",
    )
