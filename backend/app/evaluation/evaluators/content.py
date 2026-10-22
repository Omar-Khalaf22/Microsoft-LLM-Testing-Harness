"""Deterministic content evaluators for approved criteria IDs."""

import re


def evaluate(criterion_id: str, response: str, parameters: dict) -> tuple[bool, float, str]:
    """Return passed, normalized score and explanation."""
    if not isinstance(response, str):
        raise TypeError("The model response must be text.")
    text = response
    folded = text.casefold()
    if criterion_id in {
        "required_keywords",
        "forbidden_keywords",
        "required_phrases",
        "forbidden_phrases",
    }:
        key = "keywords" if criterion_id.endswith("keywords") else "phrases"
        terms = parameters[key]
        matches = [term for term in terms if term.casefold() in folded]
        required = criterion_id.startswith("required")
        ratio = len(matches) / len(terms) if required else float(not matches)
        return ratio == 1, ratio, f"Matched {len(matches)} of {len(terms)} configured {key}"
    if criterion_id == "exact_match":
        passed = text == parameters["expected"]
        return passed, float(passed), "Exact response comparison"
    if criterion_id == "contains_text":
        passed = parameters["text"] in text
        return passed, float(passed), "Case sensitive substring comparison"
    if criterion_id == "case_insensitive_match":
        passed = folded == parameters["expected"].casefold()
        return passed, float(passed), "Case insensitive full response comparison"
    if criterion_id in {"minimum_characters", "maximum_characters"}:
        target = parameters["count"]
        if criterion_id == "minimum_characters":
            passed = len(text) >= target
        else:
            passed = len(text) <= target
        ratio = float(passed)
        if criterion_id == "minimum_characters" and target and not passed:
            ratio = min(1.0, len(text) / target)
        return passed, ratio, f"{len(text)} characters; threshold {target}"
    if criterion_id == "minimum_sentences":
        count = len([part for part in re.split(r"[.!?]+", text) if part.strip()])
        target = parameters["count"]
        return count >= target, min(1.0, count / target), f"{count} sentences; minimum {target}"
    raise ValueError(f"Unsupported criterion: {criterion_id}")
