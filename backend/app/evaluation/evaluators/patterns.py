"""Deterministic pattern, format, numeric, and structure evaluators.

Every evaluator follows the Prototype 2 interface ``evaluate(response, parameters, context)`` and
returns an :class:`EvaluatorResult` holding a pass/fail flag, a normalized 0-1 score, and a short
explanation. Weights belong to the scoring layer, so these checks are binary (1.0 or 0.0).

Two kinds of problem are kept strictly apart:

* a *response* that does not satisfy a criterion produces a failed result;
* invalid *parameters* (unknown key, wrong type, unsafe regex) raise :class:`ParameterError`,
  because that is a configuration error and not a model failure.

Numeric extraction policy (shared by ``numeric_exact``, ``numeric_range`` and
``numeric_tolerance``): the response must contain exactly one plain number. Zero numbers or
several numbers is a failure, never a guess. An optional ``marker`` restricts the search to the
rest of the line after the last occurrence of that text (for example ``"Answer:"``).

Regular expressions come from users and LLM suggestions, so they are untrusted. Python's ``re``
engine cannot be interrupted and is cubic or exponential on some patterns, so patterns are
statically screened and then executed in a short-lived subprocess with a hard time limit.
"""

from __future__ import annotations

import ipaddress
import json
import math
import re
import subprocess
import sys
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
from typing import Any
from urllib.parse import urlsplit

try:  # Private module, but the project pins Python 3.12; screening degrades gracefully.
    from re import _constants as _sre_constants
    from re import _parser as _sre_parser
except ImportError:  # pragma: no cover
    _sre_constants = None
    _sre_parser = None

MAX_RESPONSE_CHARS = 100_000
MAX_PATTERN_CHARS = 300
MAX_REPEAT_BOUND = 1_000
REGEX_TIMEOUT_SECONDS = 2.0
MAX_NUMBER_TOKEN_CHARS = 64
MAX_MARKER_CHARS = 100
MAX_SECTIONS = 20
MAX_SECTION_CHARS = 100
MAX_URL_CHARS = 2_048
MAX_URL_CANDIDATES = 200
MAX_EMAIL_CHARS = 254
MAX_SCHEMES = 5
SNIPPET_CHARS = 80


class ParameterError(ValueError):
    """Criterion parameters are invalid; this is a configuration error, not a failed response."""


@dataclass(frozen=True)
class EvaluatorResult:
    passed: bool
    score: float
    detail: str


EvaluatorFn = Callable[[str, Mapping[str, Any], "Mapping[str, Any] | None"], EvaluatorResult]


def _pass(detail: str) -> EvaluatorResult:
    return EvaluatorResult(True, 1.0, detail)


def _fail(detail: str) -> EvaluatorResult:
    return EvaluatorResult(False, 0.0, detail)


def _snippet(value: str) -> str:
    flat = " ".join(value.split())
    return flat if len(flat) <= SNIPPET_CHARS else flat[: SNIPPET_CHARS - 3] + "..."


# --------------------------------------------------------------------------------------------
# Parameter schemas and validation
# --------------------------------------------------------------------------------------------


def _string(description: str, *, max_length: int, min_length: int = 1, **extra: Any) -> dict:
    spec = {"type": "string", "description": description, "maxLength": max_length}
    if min_length:
        spec["minLength"] = min_length
    return {**spec, **extra}


def _boolean(description: str, *, default: bool) -> dict:
    return {"type": "boolean", "description": description, "default": default}


def _number(description: str, **extra: Any) -> dict:
    return {"type": "number", "description": description, **extra}


def _integer(description: str, *, minimum: int, maximum: int) -> dict:
    return {"type": "integer", "description": description, "minimum": minimum, "maximum": maximum}


def _check_value(criterion_id: str, name: str, value: Any, spec: Mapping[str, Any]) -> Any:
    kind = spec["type"]
    label = f"{criterion_id}: parameter '{name}'"
    if kind == "string":
        if not isinstance(value, str):
            raise ParameterError(f"{label} must be a string")
        if spec.get("minLength", 0) and not value.strip():
            raise ParameterError(f"{label} must not be blank")
        if len(value) > spec["maxLength"]:
            raise ParameterError(f"{label} must be at most {spec['maxLength']} characters")
        if "enum" in spec and value not in spec["enum"]:
            raise ParameterError(f"{label} must be one of: {', '.join(spec['enum'])}")
    elif kind == "boolean":
        if not isinstance(value, bool):
            raise ParameterError(f"{label} must be true or false")
    elif kind in ("integer", "number"):
        is_number = isinstance(value, int | float) and not isinstance(value, bool)
        if not is_number or (kind == "integer" and not isinstance(value, int)):
            raise ParameterError(
                f"{label} must be {'an integer' if kind == 'integer' else 'a number'}"
            )
        if isinstance(value, float) and not math.isfinite(value):
            raise ParameterError(f"{label} must be finite")
        if "minimum" in spec and value < spec["minimum"]:
            raise ParameterError(f"{label} must be at least {spec['minimum']}")
        if "maximum" in spec and value > spec["maximum"]:
            raise ParameterError(f"{label} must be at most {spec['maximum']}")
    elif kind == "array":
        if not isinstance(value, list | tuple):
            raise ParameterError(f"{label} must be a list")
        if not spec.get("minItems", 0) <= len(value) <= spec["maxItems"]:
            raise ParameterError(
                f"{label} must contain {spec.get('minItems', 0)} to {spec['maxItems']} items"
            )
        return [_check_value(criterion_id, f"{name}[]", item, spec["items"]) for item in value]
    return value


def _resolve(criterion_id: str, schema: Mapping[str, Any], parameters: Any) -> dict[str, Any]:
    if not isinstance(parameters, Mapping):
        raise ParameterError(f"{criterion_id}: parameters must be an object")
    properties = schema["properties"]
    unknown = sorted(str(key) for key in parameters if key not in properties)
    if unknown:
        raise ParameterError(f"{criterion_id}: unknown parameter(s): {', '.join(unknown)}")
    missing = [key for key in schema["required"] if key not in parameters]
    if missing:
        raise ParameterError(f"{criterion_id}: missing required parameter(s): {', '.join(missing)}")
    resolved: dict[str, Any] = {}
    for name, spec in properties.items():
        if name in parameters:
            resolved[name] = _check_value(criterion_id, name, parameters[name], spec)
        else:
            resolved[name] = spec.get("default")
    return resolved


EVALUATORS: dict[str, EvaluatorFn] = {}
PARAMETER_SCHEMAS: dict[str, dict[str, Any]] = {}
_CHECKS: dict[str, Callable[[dict[str, Any]], None] | None] = {}


def validate_parameters(criterion_id: str, parameters: Mapping[str, Any]) -> dict[str, Any]:
    """Return parameters with defaults applied, or raise :class:`ParameterError`.

    Safe to call before a run (for example to vet an assistant suggestion): it performs the same
    checks, including regex screening, that execution performs.
    """
    if criterion_id not in PARAMETER_SCHEMAS:
        raise ParameterError(f"Unknown pattern criterion: {criterion_id}")
    resolved = _resolve(criterion_id, PARAMETER_SCHEMAS[criterion_id], parameters)
    check = _CHECKS[criterion_id]
    if check is not None:
        check(resolved)
    return resolved


def _evaluator(
    criterion_id: str,
    properties: dict[str, dict],
    *,
    required: tuple[str, ...] = (),
    check: Callable[[dict[str, Any]], None] | None = None,
) -> Callable[[Callable[[str, dict[str, Any]], EvaluatorResult]], EvaluatorFn]:
    schema = {
        "type": "object",
        "properties": properties,
        "required": list(required),
        "additionalProperties": False,
    }

    def decorate(function: Callable[[str, dict[str, Any]], EvaluatorResult]) -> EvaluatorFn:
        def evaluate(
            response: str,
            parameters: Mapping[str, Any],
            context: Mapping[str, Any] | None = None,
        ) -> EvaluatorResult:
            if not isinstance(response, str):
                raise ParameterError(f"{criterion_id}: response must be text")
            resolved = validate_parameters(criterion_id, parameters)
            if len(response) > MAX_RESPONSE_CHARS:
                return _fail(
                    f"Response has {len(response):,} characters; "
                    f"at most {MAX_RESPONSE_CHARS:,} can be evaluated"
                )
            return function(response, resolved)

        evaluate.__name__ = criterion_id
        evaluate.__qualname__ = criterion_id
        evaluate.__doc__ = function.__doc__
        EVALUATORS[criterion_id] = evaluate
        PARAMETER_SCHEMAS[criterion_id] = schema
        _CHECKS[criterion_id] = check
        return evaluate

    return decorate


# --------------------------------------------------------------------------------------------
# Regular expressions
# --------------------------------------------------------------------------------------------

_REGEX_PROPERTIES: dict[str, dict] = {
    "pattern": _string(
        "Python regular expression searched for anywhere in the response",
        max_length=MAX_PATTERN_CHARS,
    ),
    "ignore_case": _boolean("Match upper and lower case alike", default=False),
    "multiline": _boolean("Let ^ and $ match at the start and end of every line", default=False),
    "dotall": _boolean("Let . also match newline characters", default=False),
}

_WORKER_SOURCE = (
    "import json, re, sys\n"
    "data = json.loads(sys.stdin.read())\n"
    "match = re.compile(data['p'], data['f']).search(data['t'])\n"
    "print(json.dumps(None if match is None else [match.start(), match.end()]))\n"
)


class _RegexTimeout(Exception):
    pass


class _RegexWorkerError(Exception):
    pass


def _regex_flags(parameters: Mapping[str, Any]) -> int:
    flags = 0
    if parameters["ignore_case"]:
        flags |= re.IGNORECASE
    if parameters["multiline"]:
        flags |= re.MULTILINE
    if parameters["dotall"]:
        flags |= re.DOTALL
    return flags


_REPEAT_NAMES = ("MAX_REPEAT", "MIN_REPEAT", "POSSESSIVE_REPEAT")
_REPEAT_OPS = frozenset(
    getattr(_sre_constants, name)
    for name in _REPEAT_NAMES
    if _sre_constants is not None and hasattr(_sre_constants, name)
)


def _child_patterns(op: Any, value: Any) -> list[Any]:
    """Sub-patterns nested directly inside one parsed regex node."""
    constants = _sre_constants
    if op in _REPEAT_OPS:
        return [value[2]]
    if op == constants.SUBPATTERN:
        return [value[3]]
    if op == constants.BRANCH:
        return list(value[1])
    if op in (constants.ASSERT, constants.ASSERT_NOT):
        return [value[1]]
    if op == getattr(constants, "ATOMIC_GROUP", None):
        return [value]
    return []


def _variable_repeat_inside(items: Any) -> bool:
    for op, value in items:
        if op in _REPEAT_OPS and value[0] != value[1]:
            return True
        if any(_variable_repeat_inside(child) for child in _child_patterns(op, value)):
            return True
    return False


def _screen_structure(items: Any, repeating: bool) -> None:
    constants = _sre_constants
    for op, value in items:
        if op in (constants.GROUPREF, constants.GROUPREF_EXISTS):
            raise ParameterError("Regex backreferences and conditionals are not allowed")
        multiplies = False
        if op in _REPEAT_OPS:
            low, high, body = value
            if low > MAX_REPEAT_BOUND or (high != constants.MAXREPEAT and high > MAX_REPEAT_BOUND):
                raise ParameterError(f"Repeat counts above {MAX_REPEAT_BOUND} are not allowed")
            multiplies = high == constants.MAXREPEAT or high > 1
            if multiplies and _variable_repeat_inside(body):
                raise ParameterError(
                    "Nested quantifiers such as (a+)+ are not allowed; they can take "
                    "exponential time"
                )
        if op == constants.BRANCH and repeating:
            raise ParameterError(
                "Alternation inside a repeated group such as (a|b)+ is not allowed"
            )
        for child in _child_patterns(op, value):
            _screen_structure(child, repeating or multiplies)


@lru_cache(maxsize=256)
def _screen_pattern(pattern: str, flags: int) -> None:
    if not pattern.strip():
        raise ParameterError("Regular expression pattern must not be blank")
    if len(pattern) > MAX_PATTERN_CHARS:
        raise ParameterError(f"Pattern must be at most {MAX_PATTERN_CHARS} characters")
    try:
        re.compile(pattern, flags)
    except (re.error, OverflowError, RecursionError) as exc:
        raise ParameterError(f"Invalid regular expression: {exc}") from None
    if _sre_parser is not None:
        _screen_structure(_sre_parser.parse(pattern, flags), repeating=False)


def _check_regex(parameters: dict[str, Any]) -> None:
    _screen_pattern(parameters["pattern"], _regex_flags(parameters))


def _isolated_search(pattern: str, flags: int, text: str) -> tuple[int, int] | None:
    """Run ``re.search`` in a fresh interpreter so a runaway match can be killed."""
    payload = json.dumps({"p": pattern, "f": flags, "t": text})
    try:
        completed = subprocess.run(
            [sys.executable, "-I", "-S", "-c", _WORKER_SOURCE],
            input=payload,
            capture_output=True,
            text=True,
            timeout=REGEX_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise _RegexTimeout from None
    except OSError as exc:
        raise _RegexWorkerError(str(exc)) from None
    if completed.returncode != 0:
        raise _RegexWorkerError(completed.stderr.strip()[-200:] or "worker failed")
    span = json.loads(completed.stdout)
    return None if span is None else (span[0], span[1])


def _search(text: str, parameters: dict[str, Any]) -> tuple[str, tuple[int, int] | None]:
    """Return ("match" | "no_match" | "timeout" | "error", span)."""
    try:
        span = _isolated_search(parameters["pattern"], _regex_flags(parameters), text)
    except _RegexTimeout:
        return "timeout", None
    except _RegexWorkerError:
        return "error", None
    return ("no_match", None) if span is None else ("match", span)


_UNVERIFIED = {
    "timeout": "The pattern did not finish within {limit:g}s and could not be evaluated; "
    "simplify the pattern",
    "error": "The pattern could not be evaluated",
}


@_evaluator("regex_match", _REGEX_PROPERTIES, required=("pattern",), check=_check_regex)
def regex_match(text: str, parameters: dict[str, Any]) -> EvaluatorResult:
    """Pass when the pattern is found anywhere in the response."""
    outcome, span = _search(text, parameters)
    if outcome == "match" and span is not None:
        return _pass(f"Pattern matched {_snippet(text[span[0] : span[1]])!r} at position {span[0]}")
    if outcome == "no_match":
        return _fail("Pattern was not found in the response")
    return _fail(_UNVERIFIED[outcome].format(limit=REGEX_TIMEOUT_SECONDS))


@_evaluator("regex_not_match", _REGEX_PROPERTIES, required=("pattern",), check=_check_regex)
def regex_not_match(text: str, parameters: dict[str, Any]) -> EvaluatorResult:
    """Pass when the pattern is absent. An unevaluable pattern fails rather than passes."""
    outcome, span = _search(text, parameters)
    if outcome == "no_match":
        return _pass("Pattern was not found in the response")
    if outcome == "match" and span is not None:
        return _fail(f"Forbidden pattern found: {_snippet(text[span[0] : span[1]])!r}")
    return _fail(_UNVERIFIED[outcome].format(limit=REGEX_TIMEOUT_SECONDS))


# --------------------------------------------------------------------------------------------
# Email and URL formats
# --------------------------------------------------------------------------------------------

_MODE = _string("'contains' finds one anywhere; 'exact' requires the whole response", max_length=8)
_MODE["enum"] = ["contains", "exact"]
_MODE["default"] = "contains"

_ALNUM = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")
_EMAIL_LOCAL_CHARS = _ALNUM | frozenset("._%+-'")
_LABEL_CHARS = _ALNUM | {"-"}
_EMAIL_SPLIT = re.compile(r"[\s,;<>()\[\]\"]+")


def _valid_domain(host: str) -> bool:
    if len(host) > 253 or "." not in host:
        return False
    labels = host.split(".")
    for label in labels:
        if not 1 <= len(label) <= 63 or label[0] == "-" or label[-1] == "-":
            return False
        if not all(char in _LABEL_CHARS for char in label):
            return False
    tld = labels[-1].lower()
    return (tld.isalpha() and 2 <= len(tld) <= 24) or tld.startswith("xn--")


def _valid_email(value: str) -> bool:
    if len(value) > MAX_EMAIL_CHARS or value.count("@") != 1:
        return False
    local, domain = value.split("@")
    if not 1 <= len(local) <= 64 or local[0] == "." or local[-1] == "." or ".." in local:
        return False
    if not all(char in _EMAIL_LOCAL_CHARS for char in local):
        return False
    return _valid_domain(domain)


def _email_candidates(text: str) -> Iterator[str]:
    for token in _EMAIL_SPLIT.split(text):
        token = token.strip(".:!?")
        if token.lower().startswith("mailto:"):
            token = token[7:]
        if "@" in token:
            yield token


@_evaluator("email_format", {"mode": _MODE})
def email_format(text: str, parameters: dict[str, Any]) -> EvaluatorResult:
    """Pass when the response is, or contains, a syntactically valid ASCII email address."""
    if parameters["mode"] == "exact":
        candidate = text.strip()
        if _valid_email(candidate):
            return _pass(f"Response is a valid email address: {_snippet(candidate)}")
        return _fail("Response is not a single valid email address")
    for candidate in _email_candidates(text):
        if _valid_email(candidate):
            return _pass(f"Found a valid email address: {_snippet(candidate)}")
    return _fail("No valid email address found in the response")


_SCHEME_CHARS = _ALNUM | frozenset("+-.")
_URL_STOP = frozenset("<>\"'`")
_SCHEME_RE = re.compile(r"[a-z][a-z0-9+.-]*")


def _trim_url(url: str) -> str:
    pairs = {")": "(", "]": "[", "}": "{"}
    while url:
        last = url[-1]
        if last in ".,;:!?\"'" or (last in pairs and url.count(last) > url.count(pairs[last])):
            url = url[:-1]
        else:
            break
    return url


def _url_candidates(text: str) -> Iterator[str]:
    position = 0
    for _ in range(MAX_URL_CANDIDATES):
        index = text.find("://", position)
        if index < 0:
            return
        start = index
        while start > 0 and text[start - 1] in _SCHEME_CHARS:
            start -= 1
        end = index + 3
        while end < len(text) and not text[end].isspace() and text[end] not in _URL_STOP:
            end += 1
        position = end
        raw = text[start:end]
        if len(raw) <= MAX_URL_CHARS:
            yield _trim_url(raw)


def _valid_url(url: str, schemes: frozenset[str]) -> bool:
    if not url or len(url) > MAX_URL_CHARS:
        return False
    if any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in url):
        return False
    try:
        parts = urlsplit(url)
        host = parts.hostname
        port = parts.port
    except ValueError:
        return False
    if not _SCHEME_RE.fullmatch(parts.scheme) or parts.scheme not in schemes:
        return False
    if not parts.netloc or not host or (port is not None and port == 0):
        return False
    if host == "localhost":
        return True
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return _valid_domain(host)
    return True


def _check_url(parameters: dict[str, Any]) -> None:
    for scheme in parameters["schemes"]:
        if not _SCHEME_RE.fullmatch(scheme):
            raise ParameterError(
                f"url_format: scheme {scheme!r} must be lowercase letters, digits, '+', '-' or '.'"
            )


@_evaluator(
    "url_format",
    {
        "mode": _MODE,
        "schemes": {
            "type": "array",
            "description": "Accepted URL schemes (hierarchical URLs only, such as http://)",
            "items": _string("A lowercase URL scheme", max_length=10),
            "minItems": 1,
            "maxItems": MAX_SCHEMES,
            "default": ["http", "https"],
        },
    },
    check=_check_url,
)
def url_format(text: str, parameters: dict[str, Any]) -> EvaluatorResult:
    """Pass when the response is, or contains, a well-formed URL with an accepted scheme."""
    schemes = frozenset(parameters["schemes"])
    if parameters["mode"] == "exact":
        candidate = text.strip()
        if _valid_url(candidate, schemes):
            return _pass(f"Response is a valid URL: {_snippet(candidate)}")
        return _fail("Response is not a single valid URL")
    for candidate in _url_candidates(text):
        if _valid_url(candidate, schemes):
            return _pass(f"Found a valid URL: {_snippet(candidate)}")
    return _fail("No valid URL found in the response")


# --------------------------------------------------------------------------------------------
# Numbers
# --------------------------------------------------------------------------------------------

_NUMBER = re.compile(
    r"[+-]?(?:(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|\.\d+)(?:[eE][+-]?\d{1,3})?", re.ASCII
)
_NUMBER_LEADING = "\"'([{<*_$€£¥"
_NUMBER_TRAILING = "\"')]}>*_.,;:!?%"

_MARKER = _string(
    "Only read the number found on the rest of the line after the last occurrence of this text",
    max_length=MAX_MARKER_CHARS,
    min_length=1,
)
_MARKER["default"] = None


def _extract_numbers(text: str) -> tuple[list[Decimal], int]:
    """Return plain numbers and a count of other tokens that contain digits."""
    values: list[Decimal] = []
    skipped = 0
    for raw in text.split():
        token = raw.replace("−", "-").lstrip(_NUMBER_LEADING).rstrip(_NUMBER_TRAILING)
        if not token or not any(char.isdigit() for char in token):
            continue
        if len(token) <= MAX_NUMBER_TOKEN_CHARS and _NUMBER.fullmatch(token):
            values.append(Decimal(token.replace(",", "")))
        else:
            skipped += 1
    return values, skipped


def _fmt(value: Decimal) -> str:
    text = format(value.normalize(), "f") if value else "0"
    return text if len(text) <= 40 else text[:37] + "..."


def _to_decimal(value: int | float) -> Decimal:
    return Decimal(value) if isinstance(value, int) else Decimal(repr(value))


def _target_number(text: str, marker: str | None) -> tuple[Decimal | None, str]:
    """Find the single target number, or explain exactly why there is none."""
    region = text
    where = "in the response"
    if marker is not None:
        matches = list(re.finditer(re.escape(marker), text, re.IGNORECASE))
        if not matches:
            return None, f"Marker {_snippet(marker)!r} was not found in the response"
        start = matches[-1].end()
        line_end = text.find("\n", start)
        region = text[start:] if line_end < 0 else text[start:line_end]
        where = f"after marker {_snippet(marker)!r}"
    values, skipped = _extract_numbers(region)
    if len(values) == 1:
        return values[0], f"Found {_fmt(values[0])} {where}"
    note = f" ({skipped} other token(s) containing digits ignored)" if skipped else ""
    if not values:
        return None, f"No numeric value found {where}{note}"
    listed = ", ".join(_fmt(value) for value in values[:5])
    more = ", ..." if len(values) > 5 else ""
    return None, (
        f"Ambiguous: found {len(values)} numbers {where} ({listed}{more}); "
        "set 'marker' to identify the answer"
    )


def _numeric_check(
    text: str, marker: str | None, test: Callable[[Decimal], tuple[bool, str]]
) -> EvaluatorResult:
    value, found = _target_number(text, marker)
    if value is None:
        return _fail(found)
    passed, comparison = test(value)
    return (_pass if passed else _fail)(f"{found}; {comparison}")


@_evaluator(
    "numeric_exact",
    {"expected": _number("The exact number the response must contain"), "marker": _MARKER},
    required=("expected",),
)
def numeric_exact(text: str, parameters: dict[str, Any]) -> EvaluatorResult:
    """Pass when the single number in the response equals ``expected``."""
    expected = _to_decimal(parameters["expected"])

    def test(value: Decimal) -> tuple[bool, str]:
        return value == expected, f"expected exactly {_fmt(expected)}"

    return _numeric_check(text, parameters["marker"], test)


def _check_range(parameters: dict[str, Any]) -> None:
    low, high = parameters["minimum"], parameters["maximum"]
    if low is None and high is None:
        raise ParameterError("numeric_range: provide 'minimum', 'maximum', or both")
    if low is not None and high is not None and low > high:
        raise ParameterError("numeric_range: 'minimum' must not exceed 'maximum'")


@_evaluator(
    "numeric_range",
    {
        "minimum": _number("Smallest accepted value"),
        "maximum": _number("Largest accepted value"),
        "inclusive": _boolean("Whether the bounds themselves are accepted", default=True),
        "marker": _MARKER,
    },
    check=_check_range,
)
def numeric_range(text: str, parameters: dict[str, Any]) -> EvaluatorResult:
    """Pass when the single number in the response lies within the configured bounds."""
    low = None if parameters["minimum"] is None else _to_decimal(parameters["minimum"])
    high = None if parameters["maximum"] is None else _to_decimal(parameters["maximum"])
    inclusive = parameters["inclusive"]

    def test(value: Decimal) -> tuple[bool, str]:
        above = low is None or (value >= low if inclusive else value > low)
        below = high is None or (value <= high if inclusive else value < high)
        bounds = f"{'[' if inclusive else '('}{_fmt(low) if low is not None else '-inf'}, "
        bounds += f"{_fmt(high) if high is not None else 'inf'}{']' if inclusive else ')'}"
        return above and below, f"accepted range {bounds}"

    return _numeric_check(text, parameters["marker"], test)


@_evaluator(
    "numeric_tolerance",
    {
        "expected": _number("The target number"),
        "tolerance": _number("Largest accepted difference from the target", minimum=0),
        "relative": _boolean(
            "Treat tolerance as a fraction of the target (0.05 means 5%)", default=False
        ),
        "marker": _MARKER,
    },
    required=("expected", "tolerance"),
)
def numeric_tolerance(text: str, parameters: dict[str, Any]) -> EvaluatorResult:
    """Pass when the single number is within ``tolerance`` of ``expected``."""
    expected = _to_decimal(parameters["expected"])
    tolerance = _to_decimal(parameters["tolerance"])
    if parameters["relative"]:
        tolerance = abs(expected) * tolerance

    def test(value: Decimal) -> tuple[bool, str]:
        difference = abs(value - expected)
        return difference <= tolerance, (
            f"difference {_fmt(difference)} vs allowed {_fmt(tolerance)} from {_fmt(expected)}"
        )

    return _numeric_check(text, parameters["marker"], test)


# --------------------------------------------------------------------------------------------
# Words and sections
# --------------------------------------------------------------------------------------------


def _count_words(text: str) -> int:
    """A word is a whitespace-delimited token containing at least one letter or digit."""
    return sum(1 for token in text.split() if any(char.isalnum() for char in token))


@_evaluator(
    "word_count_min",
    {"minimum": _integer("Fewest words accepted", minimum=0, maximum=MAX_RESPONSE_CHARS)},
    required=("minimum",),
)
def word_count_min(text: str, parameters: dict[str, Any]) -> EvaluatorResult:
    """Pass when the response has at least ``minimum`` words."""
    count = _count_words(text)
    minimum = parameters["minimum"]
    detail = f"Response has {count} words; at least {minimum} required"
    return (_pass if count >= minimum else _fail)(detail)


@_evaluator(
    "word_count_max",
    {"maximum": _integer("Most words accepted", minimum=0, maximum=MAX_RESPONSE_CHARS)},
    required=("maximum",),
)
def word_count_max(text: str, parameters: dict[str, Any]) -> EvaluatorResult:
    """Pass when the response has at most ``maximum`` words."""
    count = _count_words(text)
    maximum = parameters["maximum"]
    detail = f"Response has {count} words; at most {maximum} allowed"
    return (_pass if count <= maximum else _fail)(detail)


_BULLETS = ("- ", "* ", "+ ", "• ")
_MAX_HEADING_LINE_CHARS = 200


def _heading_text(line: str) -> str:
    """Reduce a heading, label or list item line to its plain text."""
    stripped = line.strip()
    if not stripped or len(stripped) > _MAX_HEADING_LINE_CHARS:
        return ""
    stripped = stripped.lstrip("#").lstrip()
    for bullet in _BULLETS:
        if stripped.startswith(bullet):
            stripped = stripped[len(bullet) :].lstrip()
            break
    head, _, rest = stripped.partition(" ")
    if rest and head[:-1].isdigit() and head[-1] in ".)":
        stripped = rest.lstrip()
    stripped = stripped.replace("**", "").replace("__", "").strip("*_ \t")
    return " ".join(stripped.split())


def _normalize_section(name: str, case_sensitive: bool) -> str:
    collapsed = " ".join(name.split())
    return collapsed if case_sensitive else collapsed.casefold()


@_evaluator(
    "required_sections",
    {
        "sections": {
            "type": "array",
            "description": "Section names that must each appear as a heading or 'Name:' label",
            "items": _string("A section name", max_length=MAX_SECTION_CHARS),
            "minItems": 1,
            "maxItems": MAX_SECTIONS,
        },
        "case_sensitive": _boolean("Require the exact capitalization", default=False),
    },
    required=("sections",),
)
def required_sections(text: str, parameters: dict[str, Any]) -> EvaluatorResult:
    """Pass when every named section appears as a heading, list item, or ``Name:`` label."""
    case_sensitive = parameters["case_sensitive"]
    wanted = {
        section: _normalize_section(section, case_sensitive) for section in parameters["sections"]
    }
    present: set[str] = set()
    for line in text.splitlines():
        candidate = _normalize_section(_heading_text(line), case_sensitive)
        if not candidate:
            continue
        for section, normalized in wanted.items():
            if candidate == normalized or candidate.startswith(normalized + ":"):
                present.add(section)
    missing = [section for section in wanted if section not in present]
    if not missing:
        return _pass(f"All {len(wanted)} required sections found")
    return _fail(
        f"Missing {len(missing)} of {len(wanted)} required sections: "
        + ", ".join(_snippet(section) for section in missing[:10])
    )


__all__ = [
    "EVALUATORS",
    "PARAMETER_SCHEMAS",
    "EvaluatorResult",
    "ParameterError",
    "email_format",
    "numeric_exact",
    "numeric_range",
    "numeric_tolerance",
    "regex_match",
    "regex_not_match",
    "required_sections",
    "url_format",
    "validate_parameters",
    "word_count_max",
    "word_count_min",
]
