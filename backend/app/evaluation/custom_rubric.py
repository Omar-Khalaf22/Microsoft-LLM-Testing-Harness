"""The versioned custom evaluator contract and its evidence bounds."""

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CUSTOM_RUBRIC_METHOD = "custom_rubric_v1"
CUSTOM_ROW_ID = re.compile(r"custom_[0-9a-f]{32}")


class CustomRules(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    title: str = Field(min_length=1, max_length=100)
    instructions: str = Field(min_length=1, max_length=6000)
    reference_evidence: str = Field(default="", max_length=10000)
    requires_reference: bool = False

    @field_validator("title", "instructions", "reference_evidence")
    @classmethod
    def safe_text(cls, value):
        if "\x00" in value:
            raise ValueError("Scoring text cannot contain null characters.")
        return value

    @model_validator(mode="after")
    def required_text(self):
        if not self.title.strip() or not self.instructions.strip():
            raise ValueError("Enter a title and scoring instructions.")
        if self.requires_reference and not self.reference_evidence.strip():
            raise ValueError("Supply reference evidence for factual verification.")
        return self


class EvidenceExcerpt(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    source: Literal["reference", "answer"]
    excerpt: str = Field(min_length=1, max_length=1000)


def validated_excerpts(value, *, reference: str, answer: str) -> list[dict]:
    if not isinstance(value, list) or len(value) > 10:
        raise ValueError("Expected up to ten evidence excerpts.")
    sources = {"reference": reference, "answer": answer}
    excerpts = []
    for item in value:
        excerpt = EvidenceExcerpt.model_validate(item)
        if not excerpt.excerpt.strip() or excerpt.excerpt not in sources[excerpt.source]:
            raise ValueError("Evidence excerpt was not found in its claimed source.")
        excerpts.append(excerpt.model_dump())
    return excerpts
