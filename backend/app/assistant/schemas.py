from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.evaluation.configuration import validate_selection
from app.evaluation.points import allocation


class SuggestionRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    objective: str = Field(min_length=1, max_length=2000)
    test_prompt: str = Field(min_length=1, max_length=10000)

    @field_validator("objective", "test_prompt")
    @classmethod
    def not_blank(cls, value):
        if not value.strip():
            raise ValueError("The objective and test prompt cannot be blank.")
        return value


class Suggestion(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    criterion_id: str = Field(min_length=1, max_length=100)
    parameters: dict
    maximum_points: float = Field(gt=0, le=100)
    reason: str = Field(min_length=1, max_length=2000)

    @field_validator("maximum_points", mode="before")
    @classmethod
    def points(cls, value):
        return float(allocation(value))

    @field_validator("reason")
    @classmethod
    def meaningful_reason(cls, value):
        if not value.strip():
            raise ValueError("Each suggestion needs a nonblank reason.")
        return value


class SuggestionOutput(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    suggestions: list[Suggestion] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def valid_selection(self):
        validate_selection(
            [
                {
                    "criterion_id": x.criterion_id,
                    "parameters": x.parameters,
                    "weight": x.maximum_points,
                }
                for x in self.suggestions
            ]
        )
        return self
