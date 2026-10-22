"""Validated selected-criterion configuration shared by API, assistant and dispatcher."""

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .points import allocation
from .registry import validate_criterion


class CriterionConfiguration(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    criterion_id: str = Field(min_length=1, max_length=100)
    parameters: dict = Field(default_factory=dict)
    weight: float

    @field_validator("weight", mode="before")
    @classmethod
    def points(cls, value):
        return float(allocation(value))

    @model_validator(mode="after")
    def supported_parameters(self):
        validate_criterion(self.criterion_id, self.parameters)
        return self


def validate_selection(selected: list[dict]) -> list[dict]:
    if not selected or len(selected) > 100:
        raise ValueError("Select between 1 and 100 criteria.")
    parsed = [CriterionConfiguration.model_validate(item).model_dump() for item in selected]
    if len({item["criterion_id"] for item in parsed}) != len(parsed):
        raise ValueError("Each criterion ID may be selected only once.")
    if sum(allocation(item["weight"]) for item in parsed) != 100:
        raise ValueError("Selected maximum points must total exactly 100.00.")
    return parsed
