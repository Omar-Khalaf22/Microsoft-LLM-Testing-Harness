"""Pattern/numeric checks. No model-generated code or network requests are executed."""

import re
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit

import regex

MAX_RESPONSE = 100_000
REGEX_TIMEOUT = 0.05


def validate_pattern_parameters(criterion_id: str, parameters: dict) -> None:
    if criterion_id in {"regex_match", "regex_not_match"}:
        try:
            regex.compile(parameters["pattern"], regex.VERSION1)
        except regex.error as exc:
            raise ValueError("Invalid regular expression.") from exc
    if criterion_id == "numeric_range" and parameters["minimum"] > parameters["maximum"]:
        raise ValueError("The numeric minimum cannot exceed the maximum.")


def evaluate(criterion_id: str, response: str, parameters: dict) -> tuple[bool, float, str]:
    if not isinstance(response, str):
        raise TypeError("The model response must be text.")
    if len(response) > MAX_RESPONSE:
        raise RuntimeError("Response exceeds the pattern evaluator input limit.")
    text = response.strip()
    if criterion_id in {"regex_match", "regex_not_match"}:
        # A timeout propagates to the dispatcher as an evaluator error, never zero points.
        matched = (
            regex.search(parameters["pattern"], response, regex.VERSION1, timeout=REGEX_TIMEOUT)
            is not None
        )
        met = matched if criterion_id == "regex_match" else not matched
        return met, float(met), "Pattern found" if matched else "Pattern not found"
    if criterion_id == "email_format":
        met = bool(re.fullmatch(r"[^\s@]+@[^\s@.]+(?:\.[^\s@.]+)+", text))
        return met, float(met), "Whole response checked for basic email syntax; no delivery lookup"
    if criterion_id == "url_format":
        try:
            url = urlsplit(text)
            met = (
                url.scheme in {"http", "https"}
                and bool(url.hostname)
                and not any(c.isspace() for c in text)
                and url.port != 0
            )
        except ValueError:
            met = False
        return met, float(met), "Whole response checked for an absolute HTTP(S) URL; no fetch"
    if criterion_id.startswith("numeric_"):
        # Require exactly one scalar. Never extract an arbitrary number from prose.
        if not re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", text):
            return False, 0.0, "Expected one numeric scalar as the complete response"
        try:
            value = Decimal(text)
        except InvalidOperation:
            return False, 0.0, "Response is not a supported numeric scalar"
        if not value.is_finite() or abs(value.adjusted()) > 1000:
            return False, 0.0, "Numeric scalar exceeds the supported range"
        if criterion_id == "numeric_exact":
            met = value == Decimal(str(parameters["expected"]))
        elif criterion_id == "numeric_range":
            met = (
                Decimal(str(parameters["minimum"])) <= value <= Decimal(str(parameters["maximum"]))
            )
        else:
            met = abs(value - Decimal(str(parameters["expected"]))) <= Decimal(
                str(parameters["tolerance"])
            )
        return met, float(met), "Compared the complete numeric scalar using decimal arithmetic"
    if criterion_id in {"word_count_min", "word_count_max"}:
        count = len(re.findall(r"\b[\w]+(?:['’-][\w]+)*\b", text))
        met = (
            count >= parameters["count"]
            if criterion_id.endswith("min")
            else count <= parameters["count"]
        )
        return met, float(met), f"{count} words; configured bound {parameters['count']}"
    if criterion_id == "required_sections":
        headings = {
            re.sub(r"^\s*#{1,6}\s+", "", line).strip().rstrip(":").casefold()
            for line in response.splitlines()
            if line.strip()
        }
        present = [s for s in parameters["sections"] if s.strip().casefold() in headings]
        ratio = len(present) / len(parameters["sections"])
        return (
            ratio == 1,
            ratio,
            f"Found {len(present)} of {len(parameters['sections'])} section headings",
        )
    raise ValueError("Unknown pattern/numeric criterion.")
