from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StringConstraints, model_validator

NonemptyText = Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1)]


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class SuggestCriteriaRequest(ContractModel):
    objective: NonemptyText
    test_prompt: NonemptyText


class Suggestion(ContractModel):
    criterion_id: NonemptyText
    parameters: dict[str, JsonValue]
    maximum_points: int = Field(gt=0, le=100)
    reason: NonemptyText


class SuggestCriteriaResponse(ContractModel):
    suggestions: list[Suggestion] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_allocation(self) -> "SuggestCriteriaResponse":
        ids = [item.criterion_id for item in self.suggestions]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate criterion IDs")
        if sum(item.maximum_points for item in self.suggestions) != 100:
            raise ValueError("Maximum points must total 100")
        return self
