"""HTTP contracts for the temporary inline-input Run workflow."""

from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StringConstraints,
    field_validator,
    model_validator,
)

from app.evaluation.configuration import CriterionConfiguration, validate_selection
from app.evaluation.weights import ScoringWeights

NonemptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class RunCreateRequest(BaseModel):
    """Inline inputs; an optional test ID revises a previously saved test."""

    model_config = ConfigDict(strict=True, extra="forbid")

    criteria: list[CriterionConfiguration] | None = None
    objective: str = Field(default="", max_length=2000)
    configuration_state: Literal["draft", "approved"] | None = None
    recommendation_id: str | None = Field(default=None, max_length=100)

    test_name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
    ]
    prompt: Annotated[str, StringConstraints(min_length=1, max_length=10_000)]
    base_system_prompt: str | None = Field(default=None, max_length=10000)
    custom_system_prompt: str | None = Field(default=None, max_length=10000)
    model: NonemptyText = "gpt-4.1-mini"
    temperature: float = Field(default=0.2, ge=0, le=2, allow_inf_nan=False)
    expected_keywords: list[NonemptyText] = Field(default_factory=list, max_length=20)
    minimum_length: int = Field(default=40, ge=0, le=10_000)
    minimum_sentences: int = Field(default=2, ge=1, le=20)
    forbidden_terms: list[NonemptyText] = Field(default_factory=list, max_length=20)
    weights: ScoringWeights = Field(default_factory=ScoringWeights)
    test_id: NonemptyText | None = None
    test_version: int | None = Field(default=None, ge=1)

    @field_validator("prompt")
    @classmethod
    def nonblank_prompt(cls, value):
        if not value.strip():
            raise ValueError("A nonblank prompt is required.")
        return value

    @model_validator(mode="after")
    def version_requires_test(self):
        if self.test_version is not None and self.test_id is None:
            raise ValueError("test_version requires test_id.")
        if self.criteria is not None:
            validate_selection([x.model_dump() for x in self.criteria])
            if self.configuration_state != "approved":
                raise ValueError("Review and approve the selected criteria before execution.")
            if {
                "weights",
                "expected_keywords",
                "minimum_length",
                "minimum_sentences",
                "forbidden_terms",
            } & self.model_fields_set:
                raise ValueError(
                    "Submit selected criteria or the original six-check settings, not both."
                )
        elif self.recommendation_id is not None:
            raise ValueError(
                "An approved selected-criteria configuration is required with a recommendation."
            )
        if self.configuration_state == "draft":
            raise ValueError("Draft configurations cannot execute.")
        return self


class CriterionResultResponse(BaseModel):
    """One existing automatic scoring result, independent of execution status."""

    name: str
    passed: bool | None
    score: float | None
    detail: str
    criterion_id: str | None = None
    maximum_points: float | None = None
    normalized_score: float | None = None
    status: str = "completed"


class RunResponse(BaseModel):
    """A completed executor result; completed does not imply evaluation passed.

    Metadata carries the executor's JSON values, not provider configuration or secrets.
    Identifiers and timestamps retain the string representation in TestResult.to_dict().
    """

    id: str
    status: Literal["pending", "running", "completed", "failed"]
    prompt: str
    model: str
    provider: str
    response: str
    score: float | None
    criteria: list[CriterionResultResponse]
    latency_ms: int
    created_at: str
    metadata: dict[str, JsonValue]
    error: dict[str, str] | None = None
