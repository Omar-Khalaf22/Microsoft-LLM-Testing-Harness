"""Supported Prototype 2 criteria and precise point allocation."""

import json
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from pydantic import BaseModel, Field, model_validator

CATALOG = {
    "nonempty": ("Nonempty response", "Checks the model returned text"),
    "valid_json": ("Valid JSON", "Checks JSON syntax"),
    "json_object": ("JSON object", "Checks the response is a JSON object"),
    "required_keys": ("Required JSON fields", "Checks requested top-level keys"),
    "field_types": ("JSON field types", "Checks top-level field types"),
    "minimum_length": ("Minimum length", "Checks response character count"),
    "keywords": ("Keyword coverage", "Checks required words or phrases"),
    "forbidden_terms": ("Forbidden terms", "Checks disallowed words or phrases"),
}
TWO = Decimal("0.01")


class CriterionSelection(BaseModel):
    id: str
    points: str
    parameters: dict = Field(default_factory=dict)


class ScoringConfiguration(BaseModel):
    criteria: list[CriterionSelection] = Field(min_length=1, max_length=12)

    @model_validator(mode="after")
    def validate_configuration(self):
        ids = set()
        total = Decimal("0")
        for criterion in self.criteria:
            if criterion.id not in CATALOG or criterion.id in ids:
                raise ValueError(f"Unknown or duplicate criterion: {criterion.id}")
            ids.add(criterion.id)
            try:
                weight = Decimal(criterion.points)
            except (InvalidOperation, ValueError):
                raise ValueError("Criterion points must be decimal numbers") from None
            if not weight.is_finite() or weight <= 0 or weight.as_tuple().exponent < -2:
                raise ValueError("Points must be positive and have at most two decimals")
            total += weight
            parameters = criterion.parameters
            if criterion.id in ("required_keys", "keywords", "forbidden_terms"):
                key = "keys" if criterion.id == "required_keys" else "terms"
                values = parameters.get(key)
                if (
                    not isinstance(values, list)
                    or not values
                    or not all(isinstance(x, str) and x.strip() for x in values)
                ):
                    raise ValueError(f"{criterion.id} needs a nonempty {key} list")
            if criterion.id == "minimum_length":
                minimum = parameters.get("min_chars")
                if type(minimum) is not int or minimum <= 0:
                    raise ValueError("minimum_length needs positive min_chars")
            if criterion.id == "field_types":
                types = parameters.get("types")
                allowed = ("string", "number", "boolean", "object", "array", "null")
                valid_types = isinstance(types, dict) and bool(types)
                if valid_types:
                    valid_types = all(
                        isinstance(key, str) and key and value in allowed
                        for key, value in types.items()
                    )
                if not valid_types:
                    raise ValueError("field_types needs types mapping to JSON type names")
        if total != Decimal("100.00"):
            raise ValueError(f"Points must total exactly 100.00, not {total}")
        return self


def _json_type(value):
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, str):
        return "string"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, list):
        return "array"
    return "object"


def evaluate_one(criterion, response):
    """Return a normalized fraction and supporting evidence."""
    criterion_id = criterion.id
    parameters = criterion.parameters
    text = response.strip()
    if criterion_id == "nonempty":
        fraction = Decimal(1) if text else Decimal(0)
        return fraction, "Response has text" if text else "Response is empty"
    if criterion_id == "minimum_length":
        count = len(response)
        fraction = min(Decimal(1), Decimal(count) / Decimal(parameters["min_chars"]))
        return fraction, f'{count} of {parameters["min_chars"]} characters'
    if criterion_id in ("keywords", "forbidden_terms"):
        terms = parameters["terms"]
        matches = [term for term in terms if term.casefold() in response.casefold()]
        if criterion_id == "keywords":
            fraction = Decimal(len(matches)) / Decimal(len(terms))
            return fraction, f"Matched {len(matches)} of {len(terms)} terms"
        if matches:
            return Decimal(0), "Found forbidden terms: " + ", ".join(matches)
        return Decimal(1), "No forbidden terms found"
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return Decimal(0), "Response is not valid JSON"
    if criterion_id == "valid_json":
        return Decimal(1), "Response parses as JSON"
    if criterion_id == "json_object":
        fraction = Decimal(1) if isinstance(data, dict) else Decimal(0)
        detail = "Response is a JSON object" if fraction else "JSON value is not an object"
        return fraction, detail
    if not isinstance(data, dict):
        return Decimal(0), "Expected a top-level JSON object"
    if criterion_id == "required_keys":
        keys = parameters["keys"]
        matched = [key for key in keys if key in data]
        fraction = Decimal(len(matched)) / Decimal(len(keys))
        return fraction, f"Found {len(matched)} of {len(keys)} required fields"
    if criterion_id == "field_types":
        types = parameters["types"]
        matched = []
        for key, expected in types.items():
            if key in data and _json_type(data[key]) == expected:
                matched.append(key)
        fraction = Decimal(len(matched)) / Decimal(len(types))
        return fraction, f"{len(matched)} of {len(types)} fields have correct types"
    raise ValueError("Unsupported evaluator")


def evaluate(configuration, response):
    rows = []
    total = Decimal("0")
    for criterion in configuration.criteria:
        fraction, evidence = evaluate_one(criterion, response)
        earned = (Decimal(criterion.points) * fraction).quantize(
            TWO, rounding=ROUND_HALF_UP
        )
        total += earned
        row = {
            "id": criterion.id,
            "name": CATALOG[criterion.id][0],
            "maximum": criterion.points,
            "earned": str(earned),
            "normalized": str(fraction),
            "evidence": evidence,
        }
        rows.append(row)
    return {"total": str(total.quantize(TWO)), "criteria": rows}
