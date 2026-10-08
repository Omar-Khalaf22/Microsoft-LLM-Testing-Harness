"""Validated 100-point scoring configuration shared by API and executor."""

from math import isclose
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ScoringWeights(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    keyword: float = Field(default=30, ge=0, le=100, allow_inf_nan=False)
    relevance: float = Field(default=20, ge=0, le=100, allow_inf_nan=False)
    length: float = Field(default=15, ge=0, le=100, allow_inf_nan=False)
    sentences: float = Field(default=15, ge=0, le=100, allow_inf_nan=False)
    forbidden: float = Field(default=10, ge=0, le=100, allow_inf_nan=False)
    valid: float = Field(default=10, ge=0, le=100, allow_inf_nan=False)

    @model_validator(mode="after")
    def total_is_100(self) -> Self:
        if not isclose(sum(self.model_dump().values()), 100, rel_tol=0, abs_tol=1e-8):
            raise ValueError("Scoring points must total 100.")
        return self


def default_weights() -> dict[str, float]:
    return ScoringWeights().model_dump()
