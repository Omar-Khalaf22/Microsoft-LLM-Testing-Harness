"""Authoritative catalog, parameter validation, and evaluator resolution."""

import json
from copy import deepcopy
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator

from .evaluators import content, legacy, patterns, structured

CATALOG_REVISION = "p2.1"
_CATALOG = Path(__file__).with_name("criteria_catalog.json")
_EVALUATORS = {
    "content": content.evaluate,
    "patterns": patterns.evaluate,
    "structured": structured.evaluate_structured,
    "legacy": legacy.evaluate,
}


@lru_cache(maxsize=1)
def _catalog():
    return json.loads(_CATALOG.read_text(encoding="utf-8"))


def _definition(item: dict) -> dict:
    definition = deepcopy(item)
    if definition.get("evaluator_type") == "structured":
        definition["parameter_schema"] = deepcopy(structured.PARAMETER_SCHEMAS[item["id"]])
    return definition


def catalog() -> list[dict]:
    return [_definition(item) for item in _catalog()]


def get_criterion(criterion_id: str) -> dict:
    for item in _catalog():
        if item["id"] == criterion_id:
            return _definition(item)
    raise ValueError(f"Unknown criterion ID: {criterion_id}")


def list_supported_criteria() -> list[dict]:
    return [_definition(item) for item in _catalog() if item["status"] == "supported"]


def validate_criterion(criterion_id: str, parameters: dict) -> dict:
    item = get_criterion(criterion_id)
    if item["status"] != "supported" or item.get("evaluator_type") not in _EVALUATORS:
        raise ValueError(f"Criterion is not executable: {criterion_id}")
    if not isinstance(parameters, dict):
        raise ValueError("Parameters must be an object.")
    try:
        if len(json.dumps(parameters, allow_nan=False)) > 32_000:
            raise ValueError("Criterion parameters exceed the 32,000 character limit.")
        error = next(Draft202012Validator(item["parameter_schema"]).iter_errors(parameters), None)
    except (TypeError, RecursionError) as exc:
        raise ValueError("Parameters must be finite, bounded JSON values.") from exc
    if error:
        raise ValueError(f"Invalid {criterion_id} parameters: {error.message}")
    if item["evaluator_type"] == "structured":
        structured.validate_structured_parameters(criterion_id, parameters)
    if item["evaluator_type"] == "patterns":
        patterns.validate_pattern_parameters(criterion_id, parameters)
    return item


def evaluate_criterion(criterion_id: str, response: str, parameters: dict, context: dict):
    item = validate_criterion(criterion_id, parameters)
    evaluator = _EVALUATORS[item["evaluator_type"]]
    if item["evaluator_type"] == "structured":
        result = evaluator(criterion_id, response, parameters, context)
        return result.passed, result.normalized_score, result.detail
    if item["evaluator_type"] == "legacy":
        return evaluator(criterion_id, response, parameters, context)
    return evaluator(criterion_id, response, parameters)
