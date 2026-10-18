"""P1 coverage with all external model calls mocked."""

import io
import json
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.assistant.prompts import DEFAULT_SYSTEM_PROMPT, resolve_system_prompt
from app.config import Settings
from app.database import SessionLocal
from app.evaluation import providers
from app.evaluation.executor import TestExecutor as Executor
from app.evaluation.models import TestRequest as EvaluationRequest
from app.evaluation.models import ValidationError
from app.evaluation.repository import JsonResultRepository
from app.models import Model
from app.models import Test as SavedTest
from app.models import TestRun as SavedRun
from app.models import TestVersion as SavedVersion
from app.routes import runs
from app.schemas.runs import RunCreateRequest


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*args, **kwargs):
        pytest.fail("Unexpected model network request")

    monkeypatch.setattr(providers, "urlopen", blocked)


@pytest.mark.parametrize(
    "base, custom, expected",
    [
        (None, None, DEFAULT_SYSTEM_PROMPT),
        ("  Be precise.  ", None, "Be precise."),
        ("Base", "  Custom  ", "Base\n\nAdditional instructions:\nCustom"),
        ("Base", "", "Base"),
        ("Base", " \n\t", "Base"),
        (" ", None, DEFAULT_SYSTEM_PROMPT),
        (None, "Custom", DEFAULT_SYSTEM_PROMPT + "\n\nAdditional instructions:\nCustom"),
    ],
)
def test_prompt_composition(base, custom, expected):
    assert resolve_system_prompt(base, custom) == expected


def test_missing_optional_fields():
    api_request = RunCreateRequest(test_name="JSON check", prompt="Explain JSON")
    legacy_request = EvaluationRequest.from_dict({"prompt": "Explain JSON"})
    assert api_request.base_system_prompt is None
    assert api_request.custom_system_prompt is None
    assert legacy_request.base_system_prompt is None
    assert legacy_request.custom_system_prompt is None
    assert resolve_system_prompt() == DEFAULT_SYSTEM_PROMPT


@pytest.mark.parametrize("field", ["base_system_prompt", "custom_system_prompt"])
@pytest.mark.parametrize("value", [123, [], {}])
def test_legacy_rejects_nontext_instructions(field, value):
    with pytest.raises(ValidationError, match="must be text or null"):
        EvaluationRequest.from_dict({"prompt": "Explain JSON", field: value})


@pytest.mark.parametrize(
    "fields, expected",
    [
        ({}, DEFAULT_SYSTEM_PROMPT),
        ({"base_system_prompt": "Base"}, "Base"),
        (
            {"base_system_prompt": " Base ", "custom_system_prompt": " Custom "},
            "Base\n\nAdditional instructions:\nCustom",
        ),
        ({"custom_system_prompt": "  "}, DEFAULT_SYSTEM_PROMPT),
        ({"base_system_prompt": None, "custom_system_prompt": None}, DEFAULT_SYSTEM_PROMPT),
    ],
)
def test_api_to_provider_and_persistence(monkeypatch, tmp_path, fields, expected):
    prompt = "Explain JSON.\nKeep this user text intact: café."
    repository = JsonResultRepository(tmp_path / "results.jsonl")
    executor = Executor(
        providers.OpenAICompatibleProvider("fake-key", "https://example.invalid/v1"),
        repository,
    )
    opener = Mock(
        return_value=io.BytesIO(
            json.dumps(
                {
                    "choices": [{"message": {"content": "JSON is structured data. It is useful."}}],
                    "model": "returned-model",
                }
            ).encode()
        )
    )
    monkeypatch.setattr(providers, "urlopen", opener)
    app = FastAPI()
    app.include_router(runs.router)
    app.dependency_overrides[runs.get_executor] = lambda: executor
    with TestClient(app) as client:
        response = client.post(
            "/runs", json={"test_name": "P1 JSON check", "prompt": prompt, **fields}
        )
    assert response.status_code == 200
    opener.assert_called_once()
    payload = json.loads(opener.call_args.args[0].data)
    assert payload["messages"] == [
        {"role": "system", "content": expected},
        {"role": "user", "content": prompt},
    ]
    result = response.json()
    assert result["prompt"] == prompt
    assert result["metadata"]["base_system_prompt"] == fields.get("base_system_prompt")
    assert result["metadata"]["custom_system_prompt"] == fields.get("custom_system_prompt")
    assert result["metadata"]["resolved_system_prompt"] == expected
    assert repository.recent() == [result]


def test_legacy_path_and_demo_behavior(tmp_path):
    provider = providers.DemoProvider()
    prompt = "Explain secure JSON testing"
    original = provider.generate(prompt, "demo-strong-v1", 0.2)
    request = EvaluationRequest.from_dict(
        {
            "prompt": prompt,
            "model": "demo-strong-v1",
            "base_system_prompt": "Base",
            "custom_system_prompt": "Custom",
        }
    )
    executor = Executor(provider, JsonResultRepository(tmp_path / "legacy.jsonl"))
    result = executor.execute(request)
    assert result.response == original.text
    assert result.metadata["usage"] == original.usage
    assert result.prompt == prompt
    assert result.metadata["resolved_system_prompt"] == ("Base\n\nAdditional instructions:\nCustom")


def test_executor_preserves_user_whitespace(tmp_path):
    prompt = "  Test prompt\nwith spacing.  "
    provider = Mock(spec=providers.OpenAICompatibleProvider)
    provider.name = "openai_compatible"
    provider.generate.return_value = providers.ProviderResponse("Answer.", "model", {})
    executor = Executor(provider, JsonResultRepository(tmp_path / "spacing.jsonl"))
    result = executor.execute(EvaluationRequest(prompt=prompt, custom_system_prompt="Custom"))
    provider.generate.assert_called_once_with(
        prompt,
        "gpt-4.1-mini",
        0.2,
        system_prompt=DEFAULT_SYSTEM_PROMPT + "\n\nAdditional instructions:\nCustom",
    )
    assert result.prompt == prompt


@pytest.mark.parametrize("field", ["base_system_prompt", "custom_system_prompt"])
def test_api_rejects_nontext_before_execution(field):
    executor = Mock()
    app = FastAPI()
    app.include_router(runs.router)
    app.dependency_overrides[runs.get_executor] = lambda: executor
    with TestClient(app) as client:
        response = client.post(
            "/runs", json={"test_name": "Invalid system prompt", "prompt": "Hello", field: 42}
        )
    assert response.status_code == 422
    executor.execute.assert_not_called()


@pytest.mark.parametrize(
    "fields, expected",
    [
        ({}, DEFAULT_SYSTEM_PROMPT),
        (
            {"base_system_prompt": " Base ", "custom_system_prompt": " Custom "},
            "Base\n\nAdditional instructions:\nCustom",
        ),
    ],
)
def test_postgres_preserves_prompt_metadata_across_api_reload(monkeypatch, fields, expected):
    """Exercise real HTTP/executor/SQL storage; replace only settings and model transport."""
    identity = uuid4().hex
    name = f"P1 metadata {identity}"
    model = f"p1-model-{identity}"
    prompt = "Explain JSON.\nPreserve this user prompt: café."
    monkeypatch.setattr(
        runs,
        "get_settings",
        lambda: Settings(
            _env_file=None,
            database_url="postgresql+psycopg://unused/unused",
            llm_provider="openai",
            openai_api_key="fake-p1-test-only",
            openai_base_url="https://example.invalid/v1",
        ),
    )
    opener = Mock(
        return_value=io.BytesIO(
            json.dumps(
                {
                    "choices": [{"message": {"content": "JSON is structured. It is useful."}}],
                    "model": model,
                    "usage": {"prompt_tokens": 12, "completion_tokens": 9},
                }
            ).encode()
        )
    )
    monkeypatch.setattr(providers, "urlopen", opener)
    app = FastAPI()
    app.include_router(runs.router)
    try:
        with TestClient(app) as client:
            response = client.post(
                "/runs", json={"test_name": name, "model": model, "prompt": prompt, **fields}
            )
        assert response.status_code == 200, response.text
        result = response.json()
        opener.assert_called_once()
        assert json.loads(opener.call_args.args[0].data)["messages"] == [
            {"role": "system", "content": expected},
            {"role": "user", "content": prompt},
        ]
        metadata = result["metadata"]
        assert metadata["base_system_prompt"] == fields.get("base_system_prompt")
        assert metadata["custom_system_prompt"] == fields.get("custom_system_prompt")
        assert metadata["resolved_system_prompt"] == expected
        assert metadata["test_name"] == name
        assert metadata["test_version"] == 1
        assert result["prompt"] == prompt
        with SessionLocal() as session:
            saved = session.get(SavedRun, result["id"])
            assert saved.configuration["metadata"] == metadata
            assert saved.input_prompt == prompt
        # A separate client/repository/session must read the committed JSONB metadata.
        reloaded_app = FastAPI()
        reloaded_app.include_router(runs.router)
        with TestClient(reloaded_app) as client:
            history = client.get("/runs?limit=100")
        assert history.status_code == 200
        assert next(row for row in history.json() if row["id"] == result["id"]) == result
    finally:
        # Remove only rows owned by this test; run dependents cascade on deletion.
        with SessionLocal.begin() as session:
            test_ids = select(SavedTest.id).where(SavedTest.name == name)
            version_ids = select(SavedVersion.id).where(SavedVersion.test_id.in_(test_ids))
            session.execute(delete(SavedRun).where(SavedRun.test_version_id.in_(version_ids)))
            session.execute(delete(SavedVersion).where(SavedVersion.test_id.in_(test_ids)))
            session.execute(delete(SavedTest).where(SavedTest.name == name))
            session.execute(delete(Model).where(Model.id == model))
