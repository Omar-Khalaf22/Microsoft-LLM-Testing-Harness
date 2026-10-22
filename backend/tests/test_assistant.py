"""Assistant transport, registry validation, and API contracts; no paid requests."""

import asyncio
import io
import json
from copy import deepcopy
from unittest.mock import AsyncMock, Mock
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from app.assistant.provider import AssistantError, OpenAIRecommendationProvider
from app.assistant.schemas import SuggestionRequest
from app.assistant.service import recommendation_schema, suggest
from app.config import Settings
from app.evaluation.providers import DemoProvider
from app.evaluation.registry import list_supported_criteria
from app.routes import assistant

REQUEST = SuggestionRequest(objective="Return JSON", test_prompt="Return an object")


def row(cid="valid_json", parameters=None, points=100):
    return {
        "criterion_id": cid,
        "parameters": {} if parameters is None else parameters,
        "maximum_points": points,
        "reason": "Checks a stated output requirement.",
    }


def live(monkeypatch, payload=None, *, status=200, choice=None):
    payload = {"suggestions": [row()]} if payload is None else payload
    content = payload if isinstance(payload, str) else json.dumps(payload)
    choice = (
        choice if choice is not None else {"finish_reason": "stop", "message": {"content": content}}
    )
    response = httpx.Response(
        status,
        json={"choices": [choice]},
        request=httpx.Request("POST", "https://example.invalid/v1/chat/completions"),
    )
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.post.return_value = response
    monkeypatch.setattr("app.assistant.provider.httpx.AsyncClient", Mock(return_value=client))
    return OpenAIRecommendationProvider("test-only", "https://example.invalid/v1/"), client.post


def call(provider, request=REQUEST):
    return asyncio.run(suggest(request, provider, "fixed-model"))


def post(provider, repo, body=None):
    app = FastAPI()
    app.include_router(assistant.router)
    app.dependency_overrides[assistant.get_assistant_provider] = lambda: provider
    app.dependency_overrides[assistant.get_recommendation_repository] = lambda: repo
    with TestClient(app) as client:
        return client.post("/assistant/suggest-criteria", json=body or REQUEST.model_dump())


def test_live_request_schema_and_saved_draft_preserve_original_inputs(monkeypatch):
    provider, http = live(monkeypatch)
    request = {"objective": " Return JSON\n", "test_prompt": "  Return an object\n"}
    repo = Mock()
    response = post(provider, repo, request)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["suggestions"] == [row()]
    assert result["status"] == "generated" and result["requires_approval"] is True
    assert result["objective"] == request["objective"]
    assert result["test_prompt"] == request["test_prompt"]
    assert result["assistant_model"] == assistant.get_settings().assistant_model
    assert result["provider"] == "openai_compatible" and result["catalog_revision"] == "p2.1"
    assert UUID(result["recommendation_id"]) and result["created_at"].endswith("+00:00")
    assert "score" not in result
    repo.save.assert_called_once_with(result)
    outbound = http.call_args.kwargs["json"]
    assert outbound["model"] == result["assistant_model"]
    assert http.call_args.args[0] == "https://example.invalid/v1/chat/completions"
    assert "ONLY supported IDs" in outbound["messages"][0]["content"]
    task = json.loads(outbound["messages"][1]["content"])
    assert task["test_prompt"] == request["test_prompt"]
    assert {item["criterion_id"] for item in task["supported_criteria"]} == {
        item["id"] for item in list_supported_criteria()
    }
    schema = outbound["response_format"]["json_schema"]["schema"]
    assert outbound["response_format"]["type"] == "json_schema"
    assert len(schema["properties"]["suggestions"]["items"]["anyOf"]) == 36
    Draft202012Validator(schema).validate({"suggestions": [row()]})


@pytest.mark.parametrize("definition", list_supported_criteria(), ids=lambda d: d["id"])
def test_all_36_runtime_criteria_are_usable(monkeypatch, definition):
    payload = {"suggestions": [row(definition["id"], definition["example_parameters"])]}
    schema = recommendation_schema(list_supported_criteria())
    Draft202012Validator(schema).validate(payload)
    provider, _ = live(monkeypatch, payload)
    assert call(provider)["suggestions"] == payload["suggestions"]


def test_decimal_points_and_literal_schema_property_names_are_preserved(monkeypatch):
    schema = {"type": "object", "properties": {"$ref": {"type": "string"}, "$id": {}}}
    payload = {"suggestions": [row("json_schema", {"schema": schema}, 33.33), row(points=66.67)]}
    provider, _ = live(monkeypatch, payload)
    assert call(provider)["suggestions"] == payload["suggestions"]


@pytest.mark.parametrize(
    "payload",
    [
        {"suggestions": [row("invented")]},
        {"suggestions": [row("semantic_similarity")]},
        {"suggestions": [row("json_field_type")]},
        {"suggestions": [row("valid_json", {"extra": 1})]},
        {"suggestions": [row("numeric_range", {"minimum": 5, "maximum": 1})]},
        {"suggestions": [row("regex_match", {"pattern": "["})]},
        {"suggestions": [row("json_schema", {"schema": {"$ref": "https://example.invalid"}})]},
        {"suggestions": [row(points=50), row(points=50)]},
        {"suggestions": [{**row(), "reason": " \n"}]},
        {"suggestions": [row()], "approved": True},
        {"suggestions": []},
        '{"suggestions": [], "suggestions": []}',
        '{"suggestions": [], "unexpected": NaN}',
        "not json",
        "```json\n{}\n```",
        pytest.param(" " * 100_001, id="oversized-response"),
    ],
)
def test_invalid_output_is_not_saved_or_replaced_by_demo(monkeypatch, payload):
    provider, http = live(monkeypatch, payload)
    repo = Mock()
    response = post(provider, repo)
    assert response.status_code == 502, response.text
    repo.save.assert_not_called()
    http.assert_awaited_once()


@pytest.mark.parametrize("points", [True, "100", 0, -1, 100.001, 99.99, float("nan"), float("inf")])
def test_invalid_allocations_rejected_in_full(monkeypatch, points):
    provider, _ = live(monkeypatch, {"suggestions": [row(points=points)]})
    with pytest.raises(AssistantError):
        call(provider)


@pytest.mark.parametrize(
    "choice",
    [
        {"finish_reason": "length", "message": {"content": "{}"}},
        {"finish_reason": "stop", "message": {"content": "{}", "refusal": "private"}},
        {"finish_reason": "stop", "message": {"content": None}},
        {"finish_reason": "stop", "message": []},
        {"message": {"content": "{}"}},
        {},
    ],
)
def test_refused_truncated_or_malformed_responses_are_not_saved(monkeypatch, choice):
    provider, _ = live(monkeypatch, choice=choice)
    repo = Mock()
    assert post(provider, repo).status_code == 502
    repo.save.assert_not_called()


@pytest.mark.parametrize("status", [401, 429, 500])
def test_provider_http_errors_are_sanitized_without_retries(monkeypatch, status):
    provider, http = live(monkeypatch, status=status)
    repo = Mock()
    response = post(provider, repo)
    assert response.status_code == 502 and "test-only" not in response.text
    assert response.json()["detail"]["code"] == "assistant_provider_error"
    http.assert_awaited_once()
    repo.save.assert_not_called()


def test_timeout_is_504_and_does_not_save_or_retry(monkeypatch):
    provider, http = live(monkeypatch)
    http.side_effect = httpx.ReadTimeout("private credential")
    repo = Mock()
    response = post(provider, repo)
    assert response.status_code == 504 and "private credential" not in response.text
    http.assert_awaited_once()
    repo.save.assert_not_called()


def test_total_deadline_covers_a_stalled_request(monkeypatch):
    provider, http = live(monkeypatch)
    provider.timeout_seconds = 0.01

    async def stalled(*args, **kwargs):
        await asyncio.Event().wait()

    http.side_effect = stalled
    with pytest.raises(AssistantError) as error:
        call(provider)
    assert error.value.status_code == 504


def test_unexpected_provider_and_storage_errors_are_sanitized(monkeypatch):
    provider, _ = live(monkeypatch)
    provider.complete = AsyncMock(side_effect=RuntimeError("private credential"))
    repo = Mock()
    response = post(provider, repo)
    assert response.status_code == 502 and "private credential" not in response.text
    repo.save.assert_not_called()
    provider, _ = live(monkeypatch)
    repo.save.side_effect = RuntimeError("private database URL")
    response = post(provider, repo)
    assert response.status_code == 500 and "private database URL" not in response.text


@pytest.mark.parametrize(
    "provider_name,key",
    [("openai", ""), ("openai", "your-openai-api-key-here"), ("other", "test-only")],
)
def test_invalid_configuration_is_503_without_a_network_request(monkeypatch, provider_name, key):
    settings = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://unused/unused",
        llm_provider=provider_name,
        openai_api_key=key,
    )
    monkeypatch.setattr(assistant, "get_settings", lambda: settings)
    http = Mock(side_effect=AssertionError("No request should be made"))
    monkeypatch.setattr("app.assistant.provider.httpx.AsyncClient", http)
    app = FastAPI()
    app.include_router(assistant.router)
    with TestClient(app) as client:
        assert (
            client.post("/assistant/suggest-criteria", json=REQUEST.model_dump()).status_code == 503
        )
    http.assert_not_called()


@pytest.mark.parametrize(
    "patch",
    [
        {"objective": " "},
        {"test_prompt": "\n"},
        {"objective": "x" * 2001},
        {"test_prompt": "x" * 10001},
        {"extra": 1},
    ],
)
def test_invalid_request_is_422_before_calling_or_saving(monkeypatch, patch):
    provider, http = live(monkeypatch)
    repo = Mock()
    assert post(provider, repo, {**REQUEST.model_dump(), **patch}).status_code == 422
    http.assert_not_awaited()
    repo.save.assert_not_called()


@pytest.mark.parametrize("timeout", [0, -1, 121, float("inf"), float("nan")])
def test_invalid_timeout_configuration_rejected(timeout):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, database_url="unused", assistant_timeout_seconds=timeout)


def test_bad_registry_is_unavailable_instead_of_becoming_an_empty_catalog():
    definitions = list_supported_criteria()
    for invalid in ([], definitions + definitions[:1]):
        with pytest.raises(AssistantError) as error:
            recommendation_schema(invalid)
        assert error.value.status_code == 503
    invalid = deepcopy(definitions)
    invalid[0]["parameter_schema"] = {"type": "not-a-type"}
    with pytest.raises(AssistantError):
        recommendation_schema(invalid)


def test_demo_remains_explicit_and_offline(monkeypatch):
    http = Mock(side_effect=AssertionError("Demo mode must not make paid requests"))
    monkeypatch.setattr("app.assistant.provider.httpx.AsyncClient", http)
    assert call(DemoProvider())["provider"] == "local_demo"
    http.assert_not_called()


def test_openai_recommendation_approval_execution_and_sql_reload(monkeypatch):
    from app.database import SessionLocal
    from app.evaluation import providers
    from app.evaluation.executor import TestExecutor as Executor
    from app.evaluation.providers import OpenAICompatibleProvider
    from app.repositories.prototype_runs import PostgresResultRepository
    from app.repositories.recommendations import RecommendationRepository
    from app.routes import runs

    provider, assistant_http = live(monkeypatch)
    run_http = Mock(
        return_value=io.BytesIO(
            json.dumps({"choices": [{"message": {"content": '{"count": 3}'}}]}).encode()
        )
    )
    monkeypatch.setattr(providers, "urlopen", run_http)
    app = FastAPI()
    app.include_router(assistant.router)
    app.include_router(runs.router)
    app.dependency_overrides[assistant.get_assistant_provider] = lambda: provider
    executor = Executor(
        OpenAICompatibleProvider("test-only", "https://example.invalid/v1"),
        PostgresResultRepository(SessionLocal),
    )
    app.dependency_overrides[runs.get_executor] = lambda: executor
    with TestClient(app) as client:
        recommendation = client.post(
            "/assistant/suggest-criteria", json=REQUEST.model_dump()
        ).json()
        body = {
            "test_name": "Assistant integration " + recommendation["recommendation_id"],
            "prompt": REQUEST.test_prompt,
            "objective": REQUEST.objective,
            "model": "gpt-4o-mini",
            "recommendation_id": recommendation["recommendation_id"],
            "criteria": [{"criterion_id": "valid_json", "parameters": {}, "weight": 100}],
            "configuration_state": "draft",
        }
        assert client.post("/runs", json=body).status_code == 422
        run_http.assert_not_called()
        response = client.post("/runs", json={**body, "configuration_state": "approved"})
        assert response.status_code == 200, response.text
        saved = response.json()
        assert saved["score"] == 100 and "passed" not in saved
        assert saved["metadata"]["generated_configuration"] == recommendation
    with TestClient(app) as fresh_client:
        assert fresh_client.get("/runs/" + saved["id"]).json() == saved
    assert (
        RecommendationRepository(SessionLocal).get(recommendation["recommendation_id"])
        == recommendation
    )
    assistant_http.assert_awaited_once()
    run_http.assert_called_once()
