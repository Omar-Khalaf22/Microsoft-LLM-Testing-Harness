"""Additional bounded deterministic criteria for Prototype 4."""
import ast
import re
from datetime import datetime
from xml.etree import ElementTree


MAX_LENGTH = 100_000


def evaluate(criterion_id: str, response: str, parameters: dict):
    if not isinstance(response, str):
        raise TypeError("Response must be text")
    if len(response) > MAX_LENGTH:
        raise RuntimeError("Response exceeds the evaluator input limit")
    text = response.strip()
    if criterion_id == "xml_validity":
        try:
            ElementTree.fromstring(text)
            ok = True
        except ElementTree.ParseError:
            ok = False
        return ok, float(ok), "Complete response parsed as XML" if ok else "Invalid XML document"
    if criterion_id == "date_format":
        try:
            parsed = datetime.strptime(text, parameters["format"])
            ok = parsed.strftime(parameters["format"]) == text
        except (ValueError, OverflowError):
            ok = False
        return ok, float(ok), "Exact date format comparison"
    if criterion_id == "code_syntax":
        try:
            ast.parse(text, mode="exec")
            ok = True
        except (SyntaxError, ValueError, MemoryError, RecursionError):
            ok = False
        return ok, float(ok), "Python syntax parsed without executing code"
    if criterion_id == "citation_presence":
        count = len(re.findall(r"\[[1-9][0-9]*\]|\[[^]\n]+\]\(https?://[^)\s]+\)", response))
        target = parameters["minimum"]
        ok = count >= target
        return (
            ok,
            min(1.0, count / target),
            f"Found {count} citation markers; minimum {target}. Presence does not verify sources.",
        )
    if criterion_id == "markdown_links":
        count = len(re.findall(r"\[[^]\n]+\]\(https?://[^)\s]+\)", response))
        target = parameters["minimum"]
        ok = count >= target
        return (
            ok,
            min(1.0, count / target),
            f"Found {count} Markdown HTTP links; minimum {target}. Links were not fetched.",
        )
    if criterion_id == "required_links":
        required = parameters["urls"]
        found = [url for url in required if url in response]
        ratio = len(found) / len(required)
        return (
            ratio == 1,
            ratio,
            f"Found {len(found)} of {len(required)} required URL strings; no availability check",
        )
    if criterion_id == "list_length":
        count = sum(
            bool(re.match(r"^\s*(?:[-*+]\s+|[0-9]+[.)]\s+)", line))
            for line in response.splitlines()
        )
        lo, hi = parameters["minimum"], parameters["maximum"]
        ok = lo <= count <= hi
        return ok, float(ok), f"Found {count} Markdown list items; expected {lo} through {hi}"
    if criterion_id == "numeric_units":
        number = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
        match = re.fullmatch(rf"\s*({number})\s*([A-Za-z%°/]+)\s*", response)
        ok = bool(match and match.group(2) == parameters["unit"])
        return (
            ok,
            float(ok),
            f"Expected one numeric value followed by exact unit {parameters['unit']!r}",
        )
    raise ValueError(f"Unsupported criterion: {criterion_id}")
