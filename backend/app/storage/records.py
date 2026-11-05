"""Validated internal inputs. Pranjal owns mapping HTTP DTOs to these records."""

import hashlib
import json
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from app.assistant.prompts import resolve_system_prompt
from app.evaluation.configuration import validate_selection
from app.evaluation.registry import CATALOG_REVISION, get_criterion
from app.evaluation.weights import ScoringWeights


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode("utf-8")
    ).hexdigest()


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class TestReference(Record):
    test_id: str = Field(min_length=1, max_length=128)
    test_version: int = Field(gt=0)


class SavedDefinition(Record):
    name: str = Field(min_length=1, max_length=100)
    objective: str = Field(default="", max_length=2000)
    prompt: str = Field(min_length=1, max_length=10000)
    base_system_prompt: str | None = Field(default=None, max_length=10000)
    custom_system_prompt: str | None = Field(default=None, max_length=10000)
    state: Literal["draft", "approved"] = "draft"
    criteria: list[dict[str, JsonValue]] | None = None
    legacy: dict[str, JsonValue] | None = None

    @model_validator(mode="after")
    def valid(self):
        if not self.name.strip() or not self.prompt.strip():
            raise ValueError("Name and prompt must not be blank.")
        if (self.criteria is None) == (self.legacy is None):
            raise ValueError("Supply exactly one of criteria or legacy settings.")
        if self.criteria is not None:
            self.criteria = validate_selection(self.criteria)
        else:
            from app.evaluation.models import TestRequest

            allowed = {
                "weights",
                "expected_keywords",
                "minimum_length",
                "minimum_sentences",
                "forbidden_terms",
            }
            if set(self.legacy) - allowed:
                raise ValueError("Unsupported legacy setting.")
            request = TestRequest.from_dict({"prompt": self.prompt, **self.legacy})
            self.legacy = {key: getattr(request, key) for key in allowed}
            ScoringWeights.model_validate(self.legacy["weights"])
        return self

    def frozen(self) -> dict:
        body = self.model_dump(mode="json")
        body["resolved_system_prompt"] = resolve_system_prompt(
            self.base_system_prompt, self.custom_system_prompt
        )
        body["catalog_revision"] = CATALOG_REVISION
        body["criterion_definitions"] = [
            get_criterion(c["criterion_id"]) for c in self.criteria or []
        ]
        return body


class ProfileSelection(Record):
    """Construct only from Pranjal's trusted server-side profile resolver.

    endpoint_id is an opaque identity, never an URL or credential. The resolver
    supplies the allowed parameter schema; this type must not be bound to a route.
    """

    profile_id: str = Field(min_length=1, max_length=128)
    profile_revision: int = Field(gt=0)
    provider: str = Field(min_length=1, max_length=100)
    endpoint_id: str = Field(min_length=1, max_length=128)
    requested_model: str = Field(min_length=1, max_length=256)
    parameters: dict[str, JsonValue] = Field(default_factory=dict)
    parameter_schema: dict[str, JsonValue] = Field(
        default_factory=lambda: {
            "type": "object",
            "additionalProperties": False,
        }
    )

    @model_validator(mode="after")
    def safe(self):
        from jsonschema import Draft202012Validator
        from jsonschema.exceptions import SchemaError, ValidationError

        for value in (self.profile_id, self.endpoint_id):
            if urlsplit(value).scheme or "@" in value or "?" in value:
                raise ValueError("Use an opaque server profile/endpoint identity.")
        try:
            Draft202012Validator.check_schema(self.parameter_schema)
            Draft202012Validator(self.parameter_schema).validate(self.parameters)
        except (SchemaError, ValidationError):
            raise ValueError(
                "Profile parameters do not match their allowed server schema."
            ) from None
        reject_secrets(self.model_dump())
        return self


def reject_secrets(value: Any) -> None:
    """Inspect configuration keys only. Prompts/responses are never scrubbed."""
    forbidden = {
        "api_key",
        "apikey",
        "authorization",
        "password",
        "access_token",
        "refresh_token",
        "client_secret",
        "connection_string",
        "database_url",
    }
    if isinstance(value, dict):
        for key, item in value.items():
            if key.lower().replace("-", "_") in forbidden:
                raise ValueError("Credentials cannot be persisted in configuration.")
            reject_secrets(item)
    elif isinstance(value, list):
        for item in value:
            reject_secrets(item)


def configuration_hash(definition: dict, profile: ProfileSelection) -> str:
    return canonical_hash({"definition": definition, "profile": profile.model_dump(mode="json")})
