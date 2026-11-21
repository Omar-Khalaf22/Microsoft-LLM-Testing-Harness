"""Evaluate compliance with explicit higher priority response constraints.

This evaluator checks configured response rules, not semantic instruction hierarchy.
"""


def evaluate(criterion_id: str, response: str, parameters: dict):
    if criterion_id != "instruction_priority":
        raise ValueError("Unknown instruction priority criterion")
    if not isinstance(response, str) or len(response) > 100_000:
        raise ValueError("Response must be bounded text")
    text = response.casefold() if parameters["ignore_case"] else response
    required = parameters["required_phrases"]
    forbidden = parameters["forbidden_phrases"]
    met = 0
    for phrase in required:
        candidate = phrase.casefold() if parameters["ignore_case"] else phrase
        met += candidate in text
    violations = 0
    for phrase in forbidden:
        candidate = phrase.casefold() if parameters["ignore_case"] else phrase
        violations += candidate in text
    total = len(required) + len(forbidden)
    score = (met + len(forbidden) - violations) / total
    passed = met == len(required) and violations == 0
    return (
        passed,
        score,
        f"Required constraints met: {met}/{len(required)}; forbidden matches: {violations}",
    )
