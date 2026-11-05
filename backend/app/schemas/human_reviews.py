"""Human review request and response contracts."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator


class HumanReviewCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    # Accepted for P2 clients, ignored for identity by the authenticated route.
    reviewer_id: str | None = Field(default=None, min_length=1, max_length=128)
    rating: int = Field(ge=0, le=100)
    rationale: str = Field(min_length=1, max_length=4000)

    @field_validator("reviewer_id", "rationale")
    @classmethod
    def not_blank(cls, value):
        if value is None:
            return value
        if not value.strip():
            raise ValueError("Must not be blank")
        return value.strip()


class HumanReviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    run_id: str
    reviewer_id: str
    rating: int
    rationale: str
    revision: int
    created_at: datetime
    attribution: dict[str, JsonValue] | None = None
