"""Score concise answers using an explicit word limit."""


def evaluate(criterion_id: str, response: str, parameters: dict):
    if criterion_id != "conciseness":
        raise ValueError("Unknown criterion")
    if not isinstance(response, str) or len(response) > 100_000:
        raise ValueError("Response must be bounded text")
    count = len(response.split())
    limit = parameters["maximum_words"]
    score = 1.0 if count <= limit else limit / count
    return count <= limit, score, f"Words: {count}; limit: {limit}"
