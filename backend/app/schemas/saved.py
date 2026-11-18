"""HTTP inputs for saved tests, previews, suites, and executions."""

from typing import Annotated, Literal

from pydantic import Field, JsonValue, StringConstraints, model_validator

from app.storage.records import Record, SavedDefinition, TestReference

Identifier = Annotated[str, StringConstraints(min_length=1, max_length=128)]
ProfileId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")]
AttemptPosition = Annotated[str, StringConstraints(pattern=r"^[1-9][0-9]*:[1-9][0-9]*$")]


class DraftInput(SavedDefinition):
    state: Literal["draft"] = "draft"


class VersionInput(Record):
    expected_version: int = Field(gt=0, strict=True)
    definition: DraftInput


class VersionView(TestReference):
    name: str
    state: Literal["draft", "approved", "historical"]
    definition: dict[str, JsonValue]
    approval: dict[str, JsonValue] | None
    definition_hash: str | None


class ProfileView(Record):
    profile_id: str
    profile_revision: int
    provider: str
    requested_model: str
    parameters: dict[str, JsonValue]


class PreviewInput(Record):
    test: TestReference
    profile_id: ProfileId


class PreviewView(PreviewInput):
    preview_id: str
    status: Literal["completed", "technical_error"]
    interpretation: dict[str, str]
    error_category: str | None
    actual_model: str | None


class PreviewChoice(Record):
    preview_id: Identifier
    confirmed: bool = Field(default=False, strict=True)
    acknowledge_error: bool = Field(default=False, strict=True)

    @model_validator(mode="after")
    def one_action(self):
        if self.confirmed == self.acknowledge_error:
            raise ValueError("Confirm the interpretation or acknowledge the preview error.")
        return self


class SuiteReference(Record):
    suite_id: Identifier
    suite_revision: int = Field(gt=0, strict=True)


class SuiteInput(Record):
    name: str = Field(min_length=1, max_length=100)
    items: list[TestReference] = Field(min_length=1, max_length=100)


class SuiteRevisionInput(SuiteInput):
    expected_revision: int = Field(gt=0, strict=True)


class SuiteView(SuiteReference, SuiteInput):
    pass


class ExecutionInput(Record):
    test: TestReference | None = None
    suite: SuiteReference | None = None
    profile_ids: list[ProfileId] = Field(min_length=1, max_length=10)
    idempotency_key: Identifier
    previews: dict[AttemptPosition, PreviewChoice] = Field(default_factory=dict, max_length=1000)

    @model_validator(mode="after")
    def selection(self):
        if (self.test is None) == (self.suite is None):
            raise ValueError("Choose one saved test version or suite revision.")
        if len(set(self.profile_ids)) != len(self.profile_ids):
            raise ValueError("Choose each target profile at most once.")
        return self


class RerunInput(Record):
    idempotency_key: Identifier
    test: TestReference | None = None
    profile_id: ProfileId | None = None


AttemptStatus = Literal["pending", "running", "completed", "failed"]


class AttemptView(TestReference):
    run_id: str
    status: AttemptStatus
    suite_position: int
    model_position: int


class ExecutionView(Record):
    execution_id: str
    status: AttemptStatus
    progress: dict[AttemptStatus, int]
    attempts: list[AttemptView]
