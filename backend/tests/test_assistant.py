import json
import os

import httpx
import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://test:test@localhost/test")

from app.assistant.provider import AssistantError, OpenAIRecommendationProvider  # noqa: E402
from app.assistant.registry import CriterionDefinition  # noqa: E402
from app.assistant.service import ASSISTANT_INSTRUCTIONS, RecommendationService  # noqa: E402
from app.config import Settings  # noqa: E402
from app.main import app  # noqa: E402
from app.routes.assistant import get_service  # noqa: E402


def definition(name, properties=None, required=None, executable=True):
    return CriterionDefinition(
        name,
        f"Check {name}",
        {
            "type": "object",
            "properties": properties or {},
            "required": required or [],
            "additionalProperties": False,
        },
        executable,
    )


class Registry:
    def __init__(self):
        self.definitions = [
            definition("valid_json"),
            definition("json_object"),
            definition(
                "required_keywords",
                {
                    "keywords": {
                        "type": "array",
                        "items": {"type": "string", "minLength": 1},
                        "minItems": 1,
                    }
                },
                ["keywords"],
            ),
            definition(
                "json_field_type",
                {
                    "field": {"type": "string", "minLength": 1},
                    "type": {
                        "enum": [
                            "object",
                            "array",
                            "string",
                            "number",
                            "integer",
                            "boolean",
                            "null",
                        ]
                    },
                },
                ["field", "type"],
            ),
            definition("json_schema", {"schema": {"type": ["object", "boolean"]}}, ["schema"]),
            definition("planned_only", executable=False),
        ]
        self.validated = []

    def list_supported_criteria(self):
        return self.definitions

    def validate_criterion(self, criterion_id, parameters):
        item = next(item for item in self.definitions if item.criterion_id == criterion_id)
        Draft202012Validator(item.parameter_schema).validate(parameters)
        self.validated.append(criterion_id)


def suggestion(name="valid_json", parameters=None, points=100):
    return {
        "criterion_id": name,
        "parameters": parameters or {},
        "maximum_points": points,
        "reason": "The requested response must parse as JSON.",
    }


class Provider:
    def __init__(self, output):
        self.output = output
        self.messages = None

    async def complete(self, messages, schema):
        self.messages = messages
        self.schema = schema
        if isinstance(self.output, Exception):
            raise self.output
        return self.output if isinstance(self.output, str) else json.dumps(self.output)


@pytest.fixture
def endpoint():
    registry = Registry()
    provider = Provider({"suggestions": [suggestion()]})
    app.dependency_overrides[get_service] = lambda: RecommendationService(registry, provider)
    with TestClient(app) as client:
        yield client, registry, provider
    app.dependency_overrides.clear()


REQUEST = {"objective": "Return JSON", "test_prompt": "Return an object."}


def test_valid_contract_and_prompt_separation(endpoint):
    client, registry, provider = endpoint
    response = client.post("/assistant/suggest-criteria", json=REQUEST)
    assert response.status_code == 200
    assert response.json() == provider.output
    assert registry.validated == ["valid_json"]
    assert provider.messages[0] == {"role": "system", "content": ASSISTANT_INSTRUCTIONS}
    data = json.loads(provider.messages[1]["content"])
    assert data["test_prompt"] == REQUEST["test_prompt"]
    assert "planned_only" not in json.dumps(data)
    assert "weight" not in response.text


@pytest.mark.parametrize(
    "field,value",
    [
        ("objective", ""),
        ("objective", "  "),
        ("test_prompt", ""),
        ("test_prompt", "\n"),
        ("objective", None),
        ("test_prompt", 123),
    ],
)
def test_invalid_requests(endpoint, field, value):
    client, _, provider = endpoint
    assert (
        client.post("/assistant/suggest-criteria", json={**REQUEST, field: value}).status_code
        == 422
    )
    assert provider.messages is None


@pytest.mark.parametrize("field", ["objective", "test_prompt"])
def test_missing_request_fields(endpoint, field):
    client, _, _ = endpoint
    assert (
        client.post(
            "/assistant/suggest-criteria",
            json={key: value for key, value in REQUEST.items() if key != field},
        ).status_code
        == 422
    )


@pytest.mark.parametrize(
    "items",
    [
        [],
        [suggestion("unknown")],
        [suggestion("planned_only")],
        [suggestion("required_keywords")],
        [suggestion("required_keywords", {"terms": ["hello"]})],
        [suggestion("required_keywords", {"keywords": "hello"})],
        [suggestion("required_keywords", {"keywords": []})],
        [suggestion(points=50), suggestion(points=50)],
        *[[suggestion(points=value)] for value in [0, -1, True, 1.5, "100", 101, 99]],
        [{**suggestion(), "reason": " "}],
        [{**suggestion(), "weight": 100}],
        [suggestion("json_field_type", {"field": "count", "type": "int"})],
        [suggestion("json_schema", {"schema": {"type": "invalid"}})],
        [suggestion("json_schema", {"schema": {"$ref": "https://example.com/schema"}})],
        [suggestion("json_schema", {"schema": {"$defs": {"x": {"$dynamicRef": "file:///x"}}}})],
    ],
)
def test_reject_invalid_model_recommendations(endpoint, items):
    client, _, provider = endpoint
    provider.output = {"suggestions": items}
    response = client.post("/assistant/suggest-criteria", json=REQUEST)
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "assistant_invalid_output"


@pytest.mark.parametrize(
    "raw", ["not JSON", "```json\n{}\n```", "null", "[]", "{}", '{"suggestions": NaN}']
)
def test_malformed_output(endpoint, raw):
    client, _, provider = endpoint
    provider.output = raw
    assert client.post("/assistant/suggest-criteria", json=REQUEST).status_code == 502


def test_runtime_registry_changes_are_used(endpoint):
    client, registry, provider = endpoint
    registry.definitions = [definition("nonempty_response")]
    provider.output = {"suggestions": [suggestion("nonempty_response")]}
    assert client.post("/assistant/suggest-criteria", json=REQUEST).status_code == 200
    assert "valid_json" not in json.dumps(provider.messages)
    assert registry.validated == ["nonempty_response"]


@pytest.mark.parametrize(
    "kind", ["object", "array", "string", "number", "integer", "boolean", "null"]
)
def test_json_field_types(endpoint, kind):
    client, _, provider = endpoint
    provider.output = {"suggestions": [suggestion("json_field_type", {"field": "x", "type": kind})]}
    assert client.post("/assistant/suggest-criteria", json=REQUEST).status_code == 200


def test_local_schema_reference(endpoint):
    client, _, provider = endpoint
    provider.output = {
        "suggestions": [
            suggestion(
                "json_schema",
                {
                    "schema": {
                        "$defs": {"x": {"type": "integer"}},
                        "$ref": "#/$defs/x",
                    }
                },
            )
        ]
    }
    assert client.post("/assistant/suggest-criteria", json=REQUEST).status_code == 200


def test_missing_runtime_registry(monkeypatch):
    from app.assistant.registry import RegistryUnavailable
    from app.routes import assistant

    def unavailable():
        raise RegistryUnavailable()

    monkeypatch.setattr(assistant, "get_registry", unavailable)
    with TestClient(app) as client:
        response = client.post("/assistant/suggest-criteria", json=REQUEST)
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "registry_unavailable"


@pytest.mark.parametrize(
    "status,code", [(504, "assistant_timeout"), (502, "assistant_provider_error")]
)
def test_service_errors(endpoint, status, code):
    client, _, provider = endpoint
    provider.output = AssistantError(status, code, "Safe message")
    response = client.post("/assistant/suggest-criteria", json=REQUEST)
    assert response.status_code == status
    assert response.json()["detail"]["message"] == "Safe message"


@pytest.mark.parametrize(
    "failure,status",
    [
        ("timeout", 504),
        ("http", 502),
        ("malformed", 502),
        ("refusal", 502),
        ("truncated", 502),
        ("invalid_choice", 502),
        ("invalid_message", 502),
        ("success", 200),
    ],
)
def test_real_provider_transport_mapping(endpoint, monkeypatch, failure, status):
    client, registry, _ = endpoint

    async def post(self, url, **kwargs):
        assert kwargs["headers"]["Authorization"] == "Bearer test-secret"
        assert kwargs["json"]["response_format"]["type"] == "json_schema"
        assert kwargs["json"]["model"] == "configured-model"
        if failure == "timeout":
            raise httpx.ReadTimeout("test-secret")
        request = httpx.Request("POST", url)
        if failure == "http":
            return httpx.Response(401, request=request, text="test-secret")
        if failure == "malformed":
            return httpx.Response(200, request=request, json={})
        if failure == "invalid_choice":
            return httpx.Response(200, request=request, json={"choices": ["invalid"]})
        if failure == "invalid_message":
            return httpx.Response(200, request=request, json={"choices": [{"message": []}]})
        return httpx.Response(
            200,
            request=request,
            json={
                "choices": [
                    {
                        "finish_reason": "length" if failure == "truncated" else "stop",
                        "message": {
                            "refusal": "No" if failure == "refusal" else None,
                            "content": json.dumps({"suggestions": [suggestion()]}),
                        },
                    }
                ]
            },
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    settings = Settings(
        database_url="unused", openai_api_key="test-secret", assistant_model="configured-model"
    )
    app.dependency_overrides[get_service] = lambda: RecommendationService(
        registry, OpenAIRecommendationProvider(settings)
    )
    response = client.post("/assistant/suggest-criteria", json=REQUEST)
    assert response.status_code == status
    assert "test-secret" not in response.text


@pytest.mark.parametrize(
    "catalog",
    [
        [],
        [definition("planned", executable=False)],
        [CriterionDefinition("bad", "Invalid schema", {"type": "unknown"}, True)],
    ],
)
def test_unavailable_or_invalid_catalog(endpoint, catalog):
    client, registry, provider = endpoint
    registry.definitions = catalog
    assert client.post("/assistant/suggest-criteria", json=REQUEST).status_code == 503
    assert provider.messages is None


def test_registry_authoritative_rejection(endpoint, monkeypatch):
    client, registry, _ = endpoint

    def reject(*args):
        raise ValueError("Internal validator details")

    monkeypatch.setattr(registry, "validate_criterion", reject)
    response = client.post("/assistant/suggest-criteria", json=REQUEST)
    assert response.status_code == 502
    assert "Internal validator" not in response.text


def test_multiple_suggestions(endpoint):
    client, _, provider = endpoint
    provider.output = {"suggestions": [suggestion(points=60), suggestion("json_object", points=40)]}
    assert client.post("/assistant/suggest-criteria", json=REQUEST).json() == provider.output


def test_missing_credentials(endpoint):
    client, registry, _ = endpoint
    app.dependency_overrides[get_service] = lambda: RecommendationService(
        registry, OpenAIRecommendationProvider(Settings(database_url="unused", openai_api_key=""))
    )
    assert client.post("/assistant/suggest-criteria", json=REQUEST).status_code == 503
