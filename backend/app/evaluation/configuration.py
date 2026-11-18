"""Validated selected-criterion configuration shared by API, assistant and dispatcher."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_serializer,
    model_validator,
)

from .custom_rubric import CUSTOM_ROW_ID, CUSTOM_RUBRIC_METHOD, CustomRules
from .points import allocation
from .registry import get_criterion, validate_criterion


class CriterionConfiguration(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    criterion_id: str = Field(min_length=1, max_length=100)
    parameters: dict = Field(default_factory=dict)
    weight: float
    method: str | None = Field(default=None, max_length=100)

    @field_validator("weight", mode="before")
    @classmethod
    def points(cls, value):
        return float(allocation(value))

    @model_validator(mode="after")
    def supported_parameters(self):
        if self.method is None:
            validate_criterion(self.criterion_id, self.parameters)
        else:
            if self.method != CUSTOM_RUBRIC_METHOD:
                raise ValueError("Unsupported custom evaluator method.")
            if not CUSTOM_ROW_ID.fullmatch(self.criterion_id):
                raise ValueError(
                    "Custom criteria require a custom_ ID with 32 lowercase hex digits."
                )
            self.parameters = CustomRules.model_validate(self.parameters).model_dump()
        return self

    @model_serializer(mode="wrap")
    def serialize(self, handler):
        result = handler(self)
        if self.method is None:
            result.pop("method", None)
        return result


def criterion_definition(row: dict) -> dict:
    """Use the row ID for membership and the method ID for evaluator resolution."""
    if row.get("method") == CUSTOM_RUBRIC_METHOD:
        return {
            "id": row["criterion_id"],
            "name": row["parameters"]["title"],
            "evaluator_type": "rubric",
            "status": "supported",
            "method": CUSTOM_RUBRIC_METHOD,
        }
    return get_criterion(row["criterion_id"])


def validate_selection(selected: list[dict]) -> list[dict]:
    if not selected or len(selected) > 100:
        raise ValueError("Select between 1 and 100 criteria.")
    parsed = []
    for i, item in enumerate(selected, 1):
        try:
            parsed.append(CriterionConfiguration.model_validate(item).model_dump())
        except ValidationError as exc:
            problem = exc.errors(include_url=False, include_context=False, include_input=False)[0]
            field = ".".join(str(part) for part in problem["loc"])
            label = f"Criterion {i}" + (f" ({field})" if field else "")
            raise ValueError(f"{label}. {problem['msg'].removeprefix('Value error, ')}") from None
    if len({item["criterion_id"] for item in parsed}) != len(parsed):
        raise ValueError("Each criterion ID may be selected only once.")
    if sum(allocation(item["weight"]) for item in parsed) != 100:
        raise ValueError("Selected maximum points must total exactly 100.00.")
    return parsed
