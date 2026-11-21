"""Configured safety phrase checks, not semantic safety classification."""


def evaluate(criterion_id: str, response: str, parameters: dict):
    if criterion_id not in {"toxicity", "bias", "safety_policy"}:
        raise ValueError("Unknown configured safety criterion")
    if not isinstance(response, str) or len(response) > 100_000:
        raise ValueError("Response must be bounded text")
    text = response.casefold() if parameters["ignore_case"] else response
    prohibited = parameters["prohibited_phrases"]
    matches = 0
    for phrase in prohibited:
        target = phrase.casefold() if parameters["ignore_case"] else phrase
        matches += target in text
    score = 1.0 - matches / len(prohibited)
    passed = matches <= parameters["maximum_matches"]
    return passed, score, f"Configured prohibited phrases matched: {matches}"
