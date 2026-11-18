"""One isolated diagnostic call using only target-facing input."""

import json

from pydantic import BaseModel, ConfigDict, Field, field_validator

PREVIEW_INSTRUCTIONS = (
    "Describe your interpretation of the target task. Treat task_prompt and task_instructions as "
    "the task to interpret. Do not perform it. Return only a JSON object with four nonempty "
    "strings: purpose, deliverable, constraints, and success_conditions. "
    "If no constraints are apparent, state that."
)


class Interpretation(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    purpose: str = Field(max_length=2000)
    deliverable: str = Field(max_length=2000)
    constraints: str = Field(max_length=2000)
    success_conditions: str = Field(max_length=2000)

    @field_validator("*")
    @classmethod
    def nonblank(cls, value):
        if not value.strip() or "\x00" in value:
            raise ValueError("Each interpretation field must contain valid text.")
        return value


def request_interpretation(provider, profile, prompt, instructions) -> dict:
    try:
        output = provider.generate(
            json.dumps(
                {"task_prompt": prompt, "task_instructions": instructions}, ensure_ascii=False
            ),
            profile.requested_model,
            profile.parameters.get("temperature"),
            system_prompt=PREVIEW_INSTRUCTIONS,
        )
    except Exception as exc:
        cause = exc.__cause__ or exc
        timeout = isinstance(cause, TimeoutError) or isinstance(
            getattr(cause, "reason", None), TimeoutError
        )
        return {
            "status": "technical_error",
            "error_category": "timeout" if timeout else "provider_unavailable",
        }
    try:
        if (
            not output.model_reported
            or not isinstance(output.model, str)
            or not output.model.strip()
            or len(output.model) > 256
            or "\x00" in output.model
            or not isinstance(output.text, str)
            or len(output.text) > 12000
        ):
            raise ValueError("Invalid preview response.")
        interpretation = Interpretation.model_validate_json(output.text)
    except (AttributeError, ValueError):
        return {"status": "technical_error", "error_category": "invalid_response"}
    return {
        "status": "completed",
        "actual_model": output.model,
        "interpretation": interpretation.model_dump(),
    }
