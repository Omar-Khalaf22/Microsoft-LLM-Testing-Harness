"""Bounded response format compliance checks."""

import json
import re


def evaluate(criterion_id: str, response: str, parameters: dict):
    if criterion_id != "format_compliance":
        raise ValueError("Unknown format criterion")
    if not isinstance(response, str) or len(response) > 100_000:
        raise ValueError("Response must be bounded text")
    mode = parameters["format"]
    if mode == "json":
        try:
            value = json.loads(response)
            passed = isinstance(value, (dict, list))
        except (ValueError, TypeError):
            passed = False
    elif mode == "json_object":
        try:
            passed = isinstance(json.loads(response), dict)
        except (ValueError, TypeError):
            passed = False
    elif mode == "markdown_heading":
        passed = any(re.match(r"^#{1,6} +\S", line) for line in response.splitlines())
    elif mode == "fenced_code":
        passed = bool(re.search(r"(?m)^\x60{3}[^\n]*\n[\s\S]*?\n\x60{3}\s*$", response))
    elif mode == "plain_text":
        passed = not bool(re.search(r"(?m)^\s*(?:#{1,6} |\x60{3}|[-*] )", response))
    else:
        raise ValueError("Unknown format mode")
    return passed, float(passed), f"Format {mode}: {'matched' if passed else 'not matched'}"
