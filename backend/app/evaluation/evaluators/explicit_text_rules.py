"""Explicit user supplied spelling, grammar, and protected excerpt rules.

These are bounded deterministic checks, not comprehensive language or legal analysis.
"""

import re


def evaluate(criterion_id: str, response: str, parameters: dict):
    if criterion_id not in {"spelling", "grammar", "copyright_compliance"}:
        raise ValueError("Unsupported rule criterion")
    if not isinstance(response, str) or len(response) > 100_000:
        raise ValueError("Response must be bounded text")
    if criterion_id == "spelling":
        tokens = re.findall(r"\b\w+\b", response.casefold())
        allowed = {word.casefold() for word in parameters["allowed_words"]}
        unknown = sum(token not in allowed for token in tokens)
        score = 1.0 if not tokens else 1.0 - unknown / len(tokens)
        return (
            score >= parameters["minimum_score"],
            score,
            f"Unrecognized words: {unknown}/{len(tokens)}",
        )
    if criterion_id == "grammar":
        violations = 0
        for rule in parameters["forbidden_phrases"]:
            flags = re.IGNORECASE if parameters["ignore_case"] else 0
            violations += len(re.findall(re.escape(rule), response, flags=flags))
        score = 1.0 / (1.0 + violations)
        return (
            violations <= parameters["maximum_violations"],
            score,
            f"Configured grammar rule violations: {violations}",
        )
    flags = re.IGNORECASE if parameters["ignore_case"] else 0
    matched = sum(
        bool(re.search(re.escape(excerpt), response, flags=flags))
        for excerpt in parameters["protected_excerpts"]
    )
    passed = matched == 0
    return passed, float(passed), f"Protected excerpts matched: {matched}"
