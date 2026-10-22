"""Adapt the executable runtime catalog without duplicating its criterion definitions."""

from dataclasses import dataclass
from typing import Any, Protocol

from app.evaluation import registry


@dataclass(frozen=True)
class CriterionDefinition:
    criterion_id: str
    description: str
    parameter_schema: dict[str, Any]
    executable: bool


class CriteriaRegistry(Protocol):
    def list_supported_criteria(self) -> list[CriterionDefinition]: ...

    def validate_criterion(self, criterion_id: str, parameters: dict[str, Any]) -> None:
        """Raise ValueError for invalid parameters; never execute an evaluator."""
        ...


class RegistryUnavailable(RuntimeError):
    pass


class RuntimeCriteriaRegistry:
    def list_supported_criteria(self) -> list[CriterionDefinition]:
        definitions = []
        for entry in registry.list_supported_criteria():
            # Supported status is authoritative; entries without an evaluator cannot run.
            if entry["status"] != "supported" or not entry.get("evaluator"):
                continue
            properties = {}
            for name, kind in entry["parameters"].items():
                if kind == "str":
                    properties[name] = {"type": "string"}
                elif kind == "int":
                    properties[name] = {"type": "integer"}
                elif kind == "list[str]":
                    properties[name] = {
                        "type": "array",
                        "minItems": 1,
                        "items": {"type": "string", "minLength": 1},
                    }
                else:
                    # Fail closed when future catalog types require adapter reconciliation.
                    raise ValueError("Unrecognized runtime parameter type")
            definitions.append(
                CriterionDefinition(
                    criterion_id=entry["id"],
                    description=entry["description"],
                    parameter_schema={
                        "type": "object",
                        "properties": properties,
                        "required": list(properties),
                        "additionalProperties": False,
                    },
                    executable=True,
                )
            )
        return definitions

    def validate_criterion(self, criterion_id: str, parameters: dict[str, Any]) -> None:
        # Includes registry-specific value constraints (e.g. minimum_sentences >= 1).
        registry.validate_criterion(criterion_id, parameters)


def get_runtime_registry() -> CriteriaRegistry:
    return RuntimeCriteriaRegistry()
