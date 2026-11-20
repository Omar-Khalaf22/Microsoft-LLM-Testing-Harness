"""Deterministic reference coverage and contradiction rules.

These evaluators use caller supplied exact phrases, not semantic inference.
"""


def evaluate(criterion_id: str, response: str, parameters: dict):
    if criterion_id not in {"completeness", "contradiction_detection", "answerability"}:
        raise ValueError("Unknown reference rule criterion")
    if not isinstance(response, str) or len(response) > 100_000:
        raise ValueError("Response must be bounded text")
    text = response.casefold() if parameters["ignore_case"] else response
    if criterion_id == "completeness":
        required = parameters["required_facts"]
        found = 0
        for fact in required:
            candidate = fact.casefold() if parameters["ignore_case"] else fact
            found += candidate in text
        score = found / len(required)
        return (
            score >= parameters["minimum_coverage"],
            score,
            f"Required facts present: {found}/{len(required)}",
        )
    if criterion_id == "contradiction_detection":
        forbidden = parameters["contradicting_phrases"]
        found = 0
        for phrase in forbidden:
            candidate = phrase.casefold() if parameters["ignore_case"] else phrase
            found += candidate in text
        passed = found == 0
        return passed, float(passed), f"Configured contradictory phrases found: {found}"
    markers = parameters["answer_markers"]
    found = 0
    for marker in markers:
        candidate = marker.casefold() if parameters["ignore_case"] else marker
        found += candidate in text
    passed = found > 0
    return passed, float(passed), f"Answer markers present: {found}/{len(markers)}"
