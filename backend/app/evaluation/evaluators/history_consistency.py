"""Check response consistency against explicit facts in conversation history.

This is a literal consistency protocol, not semantic contradiction detection.
"""


def evaluate(criterion_id: str, response: str, parameters: dict, context: dict):
    if criterion_id not in {"multi_turn_consistency", "memory_consistency"}:
        raise ValueError("Unknown history consistency criterion")
    if not isinstance(response, str) or len(response) > 100_000:
        raise ValueError("Response must be bounded text")
    if not isinstance(context, dict):
        raise ValueError("Evaluation context must be an object")
    history = context.get("conversation_history")
    if not isinstance(history, list) or not history or len(history) > 100:
        raise ValueError("Conversation history must contain 1 to 100 messages")
    if any(not isinstance(message, str) or len(message) > 10000 for message in history):
        raise ValueError("History messages must be bounded strings")
    history_text = "\n".join(history)
    response_text = response
    if parameters["ignore_case"]:
        history_text = history_text.casefold()
        response_text = response_text.casefold()
    expected = parameters["expected_facts"]
    conflicts = parameters["conflicting_facts"]
    for fact in expected:
        normalized = fact.casefold() if parameters["ignore_case"] else fact
        if normalized not in history_text:
            raise ValueError("Expected fact is not present in conversation history")
    retained = 0
    for fact in expected:
        normalized = fact.casefold() if parameters["ignore_case"] else fact
        retained += normalized in response_text
    contradicted = 0
    for phrase in conflicts:
        normalized = phrase.casefold() if parameters["ignore_case"] else phrase
        contradicted += normalized in response_text
    score = retained / len(expected) if not contradicted else 0.0
    passed = score >= parameters["minimum_retention"] and contradicted == 0
    return (
        passed,
        score,
        f"History facts retained: {retained}/{len(expected)}; conflicts: {contradicted}",
    )
