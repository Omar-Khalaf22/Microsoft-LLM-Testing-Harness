"""Additional bounded deterministic criteria for Prototype 4."""

import ast
import json
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
    if criterion_id == "duplicate_detection":
        lines = [line.strip().casefold() for line in response.splitlines() if line.strip()]
        duplicates = len(lines) - len(set(lines))
        maximum = parameters["maximum_duplicate_lines"]
        ok = duplicates <= maximum
        return ok, float(ok), f"Found {duplicates} repeated nonempty lines; maximum {maximum}"
    if criterion_id == "table_structure":
        lines = [line.strip() for line in response.splitlines() if line.strip()]
        tables = []
        for index in range(len(lines) - 1):
            header = [cell.strip() for cell in lines[index].strip("|").split("|")]
            separator = [cell.strip() for cell in lines[index + 1].strip("|").split("|")]
            if len(header) < 2 or len(header) != len(separator):
                continue
            if not all(re.fullmatch(r":?-{3,}:?", cell) for cell in separator):
                continue
            rows = 0
            for line in lines[index + 2 :]:
                if "|" not in line:
                    break
                cells = [cell.strip() for cell in line.strip("|").split("|")]
                if len(cells) != len(header):
                    break
                rows += 1
            tables.append((len(header), rows))
        ok = any(
            columns >= parameters["minimum_columns"] and rows >= parameters["minimum_data_rows"]
            for columns, rows in tables
        )
        return ok, float(ok), f"Checked {len(tables)} Markdown tables for column and row minimums"
    if criterion_id in {"schema_required_keys", "schema_forbidden_keys"}:
        try:
            obj = json.loads(text)
        except (ValueError, RecursionError):
            return False, 0.0, "Response is not valid JSON"
        if not isinstance(obj, dict):
            return False, 0.0, "Response must be a JSON object"
        keys = parameters["keys"]
        if criterion_id == "schema_required_keys":
            matched = sum(key in obj for key in keys)
            score = matched / len(keys)
            return score == 1.0, score, f"Found {matched} of {len(keys)} required top level keys"
        absent = sum(key not in obj for key in keys)
        score = absent / len(keys)
        return score == 1.0, score, f"Absent {absent} of {len(keys)} forbidden top level keys"
    if criterion_id == "keyword_density":
        words = re.findall(r"\b\w+\b", response.casefold())
        keyword = parameters["keyword"].casefold()
        count = sum(word == keyword for word in words)
        density = count / len(words) if words else 0.0
        ok = parameters["minimum_ratio"] <= density <= parameters["maximum_ratio"]
        return ok, float(ok), f"Exact token density {density:.4f} ({count}/{len(words)})"
    if criterion_id == "repetition_penalty":
        words = re.findall(r"\b\w+\b", response.casefold())
        if not words:
            return False, 0.0, "No words to evaluate"
        repeated = len(words) - len(set(words))
        ratio = repeated / len(words)
        ok = ratio <= parameters["maximum_repeat_ratio"]
        return ok, float(ok), f"Repeated word occurrence ratio {ratio:.4f}"
    if criterion_id == "markdown_format":
        marker = parameters["required_element"]
        checks = {
            "heading": r"(?m)^#{1,6} +\S",
            "list": r"(?m)^\s*(?:[-*+] |\d+[.)] )\S",
            "link": r"\[[^]\n]+\]\(https?://[^)\s]+\)",
            "code_block": r"(?m)^\x60{3}[^\n]*\n[\s\S]*?^\x60{3}\s*$",
        }
        ok = bool(re.search(checks[marker], response))
        return ok, float(ok), f"Required Markdown element {marker}: {'found' if ok else 'missing'}"
    raise ValueError(f"Unsupported criterion: {criterion_id}")
