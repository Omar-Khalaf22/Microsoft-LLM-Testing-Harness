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
        found = sum(
            (fact.casefold() if parameters["ignore_case"] else fact) in text
            for fact in required
        )
        score = found / len(required)
        return (
            score >= parameters["minimum_coverage"],
            score,
            f"Required facts present: {found}/{len(required)}",
        )
    if criterion_id == "contradiction_detection":
        forbidden = parameters["contradicting_phrases"]
        found = sum(
            (phrase.casefold() if parameters["ignore_case"] else phrase) in text
            for phrase in forbidden
        )
        passed = found == 0
        return passed, float(passed), f"Configured contradictory phrases found: {found}"
    markers = parameters["answer_markers"]
    found = sum(
        (marker.casefold() if parameters["ignore_case"] else marker) in text
        for marker in markers
    )
    passed = found > 0
    return passed, float(passed), f"Answer markers present: {found}/{len(markers)}"
