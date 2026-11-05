"""Internal contracts, not an agreed storage or frontend schema."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Criterion(Contract):
    criterion_id: str = Field(min_length=1)
    parameters: dict[str, Any] = Field(default_factory=dict)
    weight: float = Field(gt=0, le=100)

    @model_validator(mode="before")
    @classmethod
    def valid_allocation(cls, data):
        from .lina_points import allocation

        if isinstance(data, dict):
            allocation(data.get("weight"))
        return data


class CriticalPolicy(Contract):
    """Proposed extension, deliberately separate from Lina's criterion contract."""

    criterion_id: str
    threshold: float = Field(ge=0, le=1)


class Snapshot(Contract):
    test_id: str = Field(min_length=1)
    test_version: int = Field(gt=0)
    prompt: str = Field(min_length=1, max_length=100000)
    instructions: str = ""
    model: str = Field(min_length=1)
    temperature: float = Field(default=0, ge=0, le=2)
    configuration_state: Literal["approved"]
    criteria: list[Criterion] = Field(min_length=1, max_length=100)
    judge_model: str = Field(min_length=1)
    critical_policy: list[CriticalPolicy] = Field(default_factory=list)

    @model_validator(mode="after")
    def allocations(self):
        from decimal import Decimal

        ids = [x.criterion_id for x in self.criteria]
        if len(set(ids)) != len(ids):
            raise ValueError("Duplicate criterion")
        if sum(Decimal(str(x.weight)) for x in self.criteria) != 100:
            raise ValueError("Allocations must total 100")
        policies = [x.criterion_id for x in self.critical_policy]
        if len(set(policies)) != len(policies) or not set(policies) <= set(ids):
            raise ValueError("Critical policy must identify unique configured criteria")
        return self


class Error(Contract):
    code: str
    message: str


class Outcome(Contract):
    criterion_id: str
    maximum_points: float
    status: Literal["completed", "error"]
    normalized_score: float | None = None
    score: float | None = None
    rationale: str | None = None
    evaluator_model: str | None = None
    resolved_evaluator_model: str | None = None
    evidence: list[str] = Field(default_factory=list)
    error: Error | None = None


class Run(Contract):
    id: str
    execution_id: str
    rerun_of: str | None = None
    snapshot: Snapshot
    status: Literal["pending", "running", "completed", "failed"] = "pending"
    evaluation_status: Literal["pending", "completed", "incomplete"] = "pending"
    overall_status: Literal["pending", "passed", "failed", "incomplete"] = "pending"
    response: str | None = None
    resolved_model: str | None = None
    usage: dict[str, int | None] = Field(default_factory=dict)
    criteria: list[Outcome] = Field(default_factory=list)
    score: float | None = None
    failed_critical_criteria: list[str] = Field(default_factory=list)
    error: Error | None = None
    started_at: str | None = None
    completed_at: str | None = None
    latency_ms: int | None = None


class ExecuteVersion(Contract):
    test_id: str = Field(min_length=1)
    test_version: int = Field(gt=0)
    rerun_of: str | None = None


class ExecuteSuite(Contract):
    suite_id: str = Field(min_length=1)


class Execution(Contract):
    id: str
    run_ids: list[str] = Field(min_length=1)
