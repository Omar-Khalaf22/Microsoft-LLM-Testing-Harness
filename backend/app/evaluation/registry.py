"""Single source of truth for Prototype 2 criteria."""
import json
from pathlib import Path

_CATALOG = Path(__file__).with_name("criteria_catalog.json")


def catalog() -> list[dict]:
    return json.loads(_CATALOG.read_text(encoding="utf-8"))


def get_criterion(criterion_id: str) -> dict:
    for item in catalog():
        if item["id"] == criterion_id:
            return item
    raise ValueError(f"Unknown criterion ID: {criterion_id}")


def list_supported_criteria() -> list[dict]:
    return [item for item in catalog() if item["status"] == "supported"]


def validate_criterion(criterion_id: str, parameters: dict) -> dict:
    item = get_criterion(criterion_id)
    if item["status"] != "supported":
        raise ValueError(f"Criterion is not executable: {criterion_id}")
    if not isinstance(parameters, dict):
        raise ValueError("Parameters must be an object")
    schema = item["parameters"]
    if set(parameters) != set(schema):
        raise ValueError(f"Expected parameters: {', '.join(schema)}")
    for name, kind in schema.items():
        value = parameters[name]
        if kind == "list[str]":
            if not isinstance(value, list) or not value or any(not isinstance(v, str) or not v.strip() for v in value):
                raise ValueError(f"{name} must be a nonempty list of nonempty strings")
        elif kind == "str":
            if not isinstance(value, str):
                raise ValueError(f"{name} must be text")
        elif kind == "int":
            if type(value) is not int or value < (1 if criterion_id == "minimum_sentences" else 0):
                raise ValueError(f"{name} must be a valid nonnegative integer")
    return item
