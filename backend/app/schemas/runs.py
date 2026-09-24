"""HTTP contracts for the temporary inline-input Run workflow."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StringConstraints

NonemptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class RunCreateRequest(BaseModel):
    """Inline inputs; an optional test ID revises a previously saved test."""

    model_config = ConfigDict(strict=True, extra="forbid")

    test_name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
    ]
    prompt: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=10_000)
    ]
    model: NonemptyText = "gpt-4.1-mini"
    temperature: float = Field(default=0.2, ge=0, le=2, allow_inf_nan=False)
    expected_keywords: list[NonemptyText] = Field(default_factory=list, max_length=20)
    minimum_length: int = Field(default=40, ge=0, le=10_000)
    minimum_sentences: int = Field(default=2, ge=1, le=20)
    forbidden_terms: list[NonemptyText] = Field(default_factory=list, max_length=20)
    test_id: NonemptyText | None = None
    test_version: int | None = Field(default=None, ge=1)


class CriterionResultResponse(BaseModel):
    """One existing automatic scoring result, independent of execution status."""

    name: str
    passed: bool
    score: float
    detail: str


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
    score: float
    passed: bool
    criteria: list[CriterionResultResponse]
    latency_ms: int
    created_at: str
    metadata: dict[str, JsonValue]
