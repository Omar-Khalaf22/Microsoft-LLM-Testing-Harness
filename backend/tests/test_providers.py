"""Characterize current providers; parsing quirks are intentional regression coverage."""

import io
import json
from dataclasses import FrozenInstanceError
from unittest.mock import Mock
from urllib.error import HTTPError, URLError

import pytest

from app.evaluation import providers
from app.evaluation.providers import DemoProvider, OpenAICompatibleProvider, ProviderResponse


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*args, **kwargs):
        pytest.fail("Unexpected provider network call")

    monkeypatch.setattr(providers, "urlopen", blocked)


@pytest.fixture
def http_response(monkeypatch):
    """Supply the context-managed byte stream consumed by json.load."""

    def install(body):
        raw = body if isinstance(body, bytes) else json.dumps(body).encode()
        opener = Mock(return_value=io.BytesIO(raw))
        monkeypatch.setattr(providers, "urlopen", opener)
        return opener

    return install


def generate():
    return OpenAICompatibleProvider("test-key", "https://example.invalid/v1").generate(
        "Explain JSON — briefly", "requested-model", 0.7
    )


def test_provider_response_fields_are_frozen():
    result = ProviderResponse("answer", "model", {"input_tokens": 2, "output_tokens": 3})
    assert result.text == "answer"
    assert result.model == "model"
    assert result.usage == {"input_tokens": 2, "output_tokens": 3}
    with pytest.raises(FrozenInstanceError):
        result.text = "changed"


@pytest.mark.parametrize("suffix", ["", "/", "///"])
def test_request_and_response_contract(http_response, suffix):
    opener = http_response(
        {
            "choices": [
                {"message": {"content": "First answer"}},
                {"message": {"content": "Ignored answer"}},
            ],
            "model": "returned-model",
            "usage": {"prompt_tokens": "12", "completion_tokens": 7},
        }
    )
    provider = OpenAICompatibleProvider("test-key", f"https://example.invalid/v1{suffix}")
    result = provider.generate("Explain JSON — briefly", "requested-model", 0.7)

    opener.assert_called_once()
    args, kwargs = opener.call_args
    assert len(args) == 1
    request = args[0]
    assert request.full_url == "https://example.invalid/v1/chat/completions"
    assert request.get_method() == "POST"
    headers = {key.lower(): value for key, value in request.header_items()}
    assert headers["authorization"] == "Bearer test-key"
    assert headers["content-type"] == "application/json"
    assert json.loads(request.data) == {
        "model": "requested-model",
        "messages": [{"role": "user", "content": "Explain JSON — briefly"}],
        "temperature": 0.7,
    }
    assert kwargs == {"timeout": 30}
    assert provider.name == "openai_compatible"
    assert result == ProviderResponse(
        "First answer", "returned-model", {"input_tokens": 12, "output_tokens": 7}
    )


@pytest.mark.parametrize(
    "extra, expected",
    [
        ({}, {"input_tokens": 0, "output_tokens": 0}),
        ({"usage": {}}, {"input_tokens": 0, "output_tokens": 0}),
        ({"usage": {"prompt_tokens": 4}}, {"input_tokens": 4, "output_tokens": 0}),
        ({"usage": {"completion_tokens": "5"}}, {"input_tokens": 0, "output_tokens": 5}),
    ],
)
def test_missing_usage_defaults_to_zero_and_missing_model_falls_back(
    http_response, extra, expected
):
    http_response({"choices": [{"message": {"content": "answer"}}], **extra})
    result = generate()
    assert result.model == "requested-model"
    assert result.usage == expected


def test_null_model_and_content_are_returned_without_validation(http_response):
    http_response({"choices": [{"message": {"content": None}}], "model": None})
    result = generate()
    assert isinstance(result, ProviderResponse)
    assert result.text is None
    assert result.model is None


def test_empty_api_key_is_rejected():
    with pytest.raises(RuntimeError, match="API key is required"):
        OpenAICompatibleProvider("", "https://example.invalid/v1")


@pytest.mark.parametrize(
    "error",
    [
        HTTPError(
            "https://example.invalid/v1/chat/completions", 429, "Too many requests", {}, None
        ),
        URLError("unreachable"),
        TimeoutError("timed out"),
    ],
    ids=["http-error", "url-error", "timeout"],
)
def test_transport_errors_are_wrapped(monkeypatch, error):
    monkeypatch.setattr(providers, "urlopen", Mock(side_effect=error))
    with pytest.raises(RuntimeError, match="Model request failed") as caught:
        generate()
    assert caught.value.__cause__ is error


@pytest.mark.parametrize(
    "body, error",
    [
        (b"not JSON", json.JSONDecodeError),
        ({}, KeyError),
        ({"choices": []}, IndexError),
        ({"choices": [{"message": {}}]}, KeyError),
        ({"choices": [{"message": None}]}, TypeError),
    ],
    ids=["malformed-json", "missing-choices", "empty-choices", "missing-content", "null-message"],
)
def test_response_parsing_errors_escape_unwrapped(http_response, body, error):
    http_response(body)
    with pytest.raises(error):
        generate()


@pytest.mark.parametrize(
    "usage, error",
    [
        (None, AttributeError),
        ([], AttributeError),
        ({"prompt_tokens": "unknown"}, ValueError),
        ({"completion_tokens": None}, TypeError),
    ],
    ids=["null-usage", "list-usage", "nonnumeric-token-count", "null-token-count"],
)
def test_malformed_usage_errors_escape_unwrapped(http_response, usage, error):
    http_response({"choices": [{"message": {"content": "answer"}}], "usage": usage})
    with pytest.raises(error):
        generate()


@pytest.mark.parametrize(
    "model, prefix",
    [
        ("demo-strong-v1", "Complete analysis for:"),
        ("demo-partial-v1", "Partial response for:"),
        ("demo-failing-v1", "Error: the requested information is unavailable."),
    ],
)
def test_demo_variants_are_successful_deterministic_responses(model, prefix):
    provider = DemoProvider()
    result = provider.generate("Explain secure JSON testing", model, 0.2)
    assert isinstance(result, ProviderResponse)
    assert result.text.startswith(prefix)
    assert result.model == model
    assert provider.name == "local_demo"
    assert result.usage == {"input_tokens": 4, "output_tokens": len(result.text.split())}
    assert provider.generate("Explain secure JSON testing", model, 0.2) == result
    # Temperature currently has no effect on demo output.
    assert provider.generate("Explain secure JSON testing", model, 1.8) == result


@pytest.mark.parametrize(
    "requested, returned",
    [
        ("gpt-4.1-mini", "demo-strong-v1"),
        ("", "demo-strong-v1"),
        ("demo-unknown", "demo-unknown"),
    ],
)
def test_demo_unrecognized_models_use_strong_text(requested, returned):
    provider = DemoProvider()
    strong = provider.generate("Explain testing", "demo-strong-v1", 0.2)
    result = provider.generate("Explain testing", requested, 0.2)
    assert result.text == strong.text
    assert result.model == returned
    assert result.usage == strong.usage


def test_demo_empty_prompt_uses_fallback_topic():
    result = DemoProvider().generate("", "demo-strong-v1", 0.2)
    assert "Complete analysis for: the requested topic." in result.text
    assert result.usage["input_tokens"] == 0
