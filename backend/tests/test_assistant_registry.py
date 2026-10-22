"""Use the real catalog and validator; replace only the external assistant call."""

import json

import pytest
from fastapi.testclient import TestClient

from app.assistant.prompts import DEFAULT_SYSTEM_PROMPT
from app.assistant.provider import OpenAIRecommendationProvider
from app.assistant.registry import get_runtime_registry
from app.assistant.service import ASSISTANT_INSTRUCTIONS
from app.evaluation import registry
from app.main import app


@pytest.fixture(autouse=True)
def no_live_assistant_calls(monkeypatch):
    async def blocked(*args, **kwargs):
        pytest.fail("Live assistant requests are forbidden in integration tests")

    monkeypatch.setattr(OpenAIRecommendationProvider, "complete", blocked)


def parameters_for(entry):
    values = {"list[str]": ["alpha"], "str": "alpha", "int": 2}
    return {name: values[kind] for name, kind in entry["parameters"].items()}


@pytest.mark.parametrize("entry", registry.list_supported_criteria(), ids=lambda item: item["id"])
def test_default_route_with_actual_registry(monkeypatch, entry):
    parameters = parameters_for(entry)
    expected = {
        "suggestions": [
            {
                "criterion_id": entry["id"],
                "parameters": parameters,
                "maximum_points": 100,
                "reason": "This criterion checks the explicitly requested content constraint.",
            }
        ]
    }
    calls = []
    original = registry.validate_criterion

    def validate(criterion_id, params):
        calls.append((criterion_id, params))
        return original(criterion_id, params)

    async def complete(self, messages, schema):
        assert messages[0]["content"] == ASSISTANT_INSTRUCTIONS
        assert messages[0]["content"] != DEFAULT_SYSTEM_PROMPT
        data = json.loads(messages[1]["content"])
        assert data["objective"] == "Check the requested content"
        expected_ids = {item["id"] for item in registry.list_supported_criteria()}
        assert {item["criterion_id"] for item in data["supported_criteria"]} == expected_ids
        assert "valid_json" not in json.dumps(schema)
        assert {item["criterion_id"] for item in data["supported_criteria"]} == {
            item["properties"]["criterion_id"]["enum"][0]
            for item in schema["properties"]["suggestions"]["items"]["anyOf"]
        }
        return json.dumps(expected)

    monkeypatch.setattr(registry, "validate_criterion", validate)
    monkeypatch.setattr(OpenAIRecommendationProvider, "complete", complete)
    with TestClient(app) as client:
        response = client.post(
            "/assistant/suggest-criteria",
            json={
                "objective": "Check the requested content",
                "test_prompt": "Include alpha twice.",
            },
        )
    assert response.status_code == 200, response.text
    assert response.json() == expected
    assert calls == [(entry["id"], parameters)]


@pytest.mark.parametrize(
    "criterion_id,parameters",
    [
        ("valid_json", {}),
        ("json_schema", {"schema": {"type": "object"}}),
        ("semantic_similarity", {}),
        ("json_object", {}),
        ("required_keywords", {"terms": ["alpha"]}),
        ("required_keywords", {"keywords": [" "]}),
        ("minimum_characters", {"count": -1}),
        ("minimum_sentences", {"count": 0}),
        ("minimum_sentences", {"count": True}),
    ],
)
def test_actual_registry_rejects_invalid_recommendation(monkeypatch, criterion_id, parameters):
    async def complete(*args):
        return json.dumps(
            {
                "suggestions": [
                    {
                        "criterion_id": criterion_id,
                        "parameters": parameters,
                        "maximum_points": 100,
                        "reason": "Check the specified objective.",
                    }
                ]
            }
        )

    monkeypatch.setattr(OpenAIRecommendationProvider, "complete", complete)
    with TestClient(app) as client:
        response = client.post(
            "/assistant/suggest-criteria",
            json={
                "objective": "Check content",
                "test_prompt": "Include alpha.",
            },
        )
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "assistant_invalid_output"


def test_adapter_reads_runtime_changes(monkeypatch):
    runtime = get_runtime_registry()
    original = registry.list_supported_criteria()
    monkeypatch.setattr(registry, "list_supported_criteria", lambda: original[:1])
    assert [item.criterion_id for item in runtime.list_supported_criteria()] == [original[0]["id"]]


def test_adapter_fails_closed_on_new_parameter_type(monkeypatch):
    entry = {**registry.list_supported_criteria()[0], "parameters": {"new": "unrecognized"}}
    monkeypatch.setattr(registry, "list_supported_criteria", lambda: [entry])
    with pytest.raises(ValueError, match="parameter type"):
        get_runtime_registry().list_supported_criteria()


@pytest.mark.parametrize(
    "objective,test_prompt,keywords",
    [
        (
            "Ensure the response contains specific keywords",
            "Explain machine learning and mention neural networks.",
            ["machine learning", "neural networks"],
        ),
        (
            "Include the required keywords",
            "Describe solar energy and mention battery storage.",
            ["solar energy", "battery storage"],
        ),
        (
            "Check only the required keyword",
            "Mention the word sentence.",
            ["sentence"],
        ),
    ],
)
def test_keyword_only_precision_policy_and_single_criterion(
    monkeypatch, objective, test_prompt, keywords
):
    """Protect the model instructions and API path; no claim of live model evaluation."""
    expected = {
        "suggestions": [
            {
                "criterion_id": "required_keywords",
                "parameters": {"keywords": keywords},
                "maximum_points": 100,
                "reason": "Checks that the response includes the explicitly requested keywords.",
            }
        ]
    }

    async def complete(self, messages, schema):
        instructions = messages[0]["content"]
        # These assertions fail with the original prompt that allowed the live over-selection.
        assert (
            "Keyword-only requirements need only the appropriate keyword criterion" in instructions
        )
        assert "Do not invent sentence counts, character limits" in instructions
        assert "Never add criteria\nmerely to distribute the 100 available points" in instructions
        assert "must receive maximum_points of 100" in instructions
        assert "Every parameter must be grounded in the user's actual input" in instructions
        assert "remove any candidate or parameter unsupported by the input" in instructions
        data = json.loads(messages[1]["content"])
        assert data["objective"] == objective
        assert data["test_prompt"] == test_prompt
        # Keep the full executable catalog; precision comes from policy, not keyword blacklists.
        assert {item["criterion_id"] for item in data["supported_criteria"]} == {
            item["id"] for item in registry.list_supported_criteria()
        }
        return json.dumps(expected)

    monkeypatch.setattr(OpenAIRecommendationProvider, "complete", complete)
    with TestClient(app) as client:
        response = client.post(
            "/assistant/suggest-criteria",
            json={
                "objective": objective,
                "test_prompt": test_prompt,
            },
        )
    assert response.status_code == 200, response.text
    assert response.json() == expected
    assert len(response.json()["suggestions"]) == 1
    assert response.json()["suggestions"][0]["maximum_points"] == 100


def test_explicit_multiple_requirements_remain_supported(monkeypatch):
    expected = {
        "suggestions": [
            {
                "criterion_id": "required_keywords",
                "parameters": {"keywords": ["alpha"]},
                "maximum_points": 75,
                "reason": "Checks the explicitly required keyword alpha.",
            },
            {
                "criterion_id": "maximum_characters",
                "parameters": {"count": 200},
                "maximum_points": 25,
                "reason": "Checks the explicitly requested 200-character limit.",
            },
        ]
    }

    async def complete(self, messages, schema):
        instructions = messages[0]["content"]
        assert "proportionally to their stated importance" in instructions
        assert "If no relative importance is stated, use an approximately equal allocation" in (
            instructions
        )
        data = json.loads(messages[1]["content"])
        assert "three times" in data["objective"]
        assert "200" in data["test_prompt"]
        return json.dumps(expected)

    monkeypatch.setattr(OpenAIRecommendationProvider, "complete", complete)
    with TestClient(app) as client:
        response = client.post(
            "/assistant/suggest-criteria",
            json={
                "objective": "Including alpha is three times as important as the character limit.",
                "test_prompt": "Include alpha and use at most 200 characters.",
            },
        )
    assert response.status_code == 200, response.text
    assert response.json() == expected
