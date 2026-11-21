"""Check configured contradictory assertions in a response.

This is an explicit contradiction rule evaluator, not semantic reasoning analysis.
"""


def evaluate(criterion_id: str, response: str, parameters: dict):
    if criterion_id != "reasoning_consistency":
        raise ValueError("Unknown reasoning consistency criterion")
    if not isinstance(response, str) or len(response) > 100_000:
        raise ValueError("Response must be bounded text")
    text = response.casefold() if parameters["ignore_case"] else response
    pairs = parameters["contradiction_pairs"]
    contradictions = 0
    for pair in pairs:
        first, second = pair
        if parameters["ignore_case"]:
            first, second = first.casefold(), second.casefold()
        contradictions += first in text and second in text
    score = 1.0 - contradictions / len(pairs)
    passed = contradictions <= parameters["maximum_contradictions"]
    return (
        passed,
        score,
        f"Configured contradictory assertion pairs detected: {contradictions}/{len(pairs)}",
    )
