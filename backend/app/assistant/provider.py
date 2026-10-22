"""Assistant-only async transport; the model-under-test provider remains independent."""

import asyncio
from typing import Protocol

import httpx


class AssistantError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        self.status_code = status_code
        self.code = code
        self.message = message
        super().__init__(message)


class RecommendationProvider(Protocol):
    name: str

    async def complete(self, messages: list[dict[str, str]], schema: dict, model: str) -> str: ...


class OpenAIRecommendationProvider:
    name = "openai_compatible"

    def __init__(self, api_key: str, base_url: str, timeout_seconds: float = 30.0):
        self._api_key = api_key.strip()
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    async def complete(self, messages: list[dict[str, str]], schema: dict, model: str) -> str:
        if not self._api_key or self._api_key == "your-openai-api-key-here":
            raise AssistantError(
                503, "assistant_unconfigured", "Configure the assistant API key before continuing."
            )
        try:
            async with asyncio.timeout(self.timeout_seconds):
                async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                    response = await client.post(
                        f"{self.base_url}/chat/completions",
                        headers={"Authorization": f"Bearer {self._api_key}"},
                        json={
                            "model": model,
                            "messages": messages,
                            "response_format": {
                                "type": "json_schema",
                                "json_schema": {
                                    "name": "criteria_recommendations",
                                    "strict": False,
                                    "schema": schema,
                                },
                            },
                        },
                    )
                    response.raise_for_status()
                    choice = response.json()["choices"][0]
                    message = choice["message"]
                    if choice.get("finish_reason") != "stop" or message.get("refusal"):
                        raise ValueError("Incomplete or refused response")
                    content = message["content"]
                    if (
                        not isinstance(content, str)
                        or not content.strip()
                        or len(content) > 100_000
                    ):
                        raise ValueError("Missing or oversized content")
                    return content
        except (TimeoutError, httpx.TimeoutException):
            raise AssistantError(
                504, "assistant_timeout", "The assistant request timed out. Retry when ready."
            ) from None
        except httpx.HTTPError:
            raise AssistantError(
                502, "assistant_provider_error", "The assistant provider request failed."
            ) from None
        except (KeyError, IndexError, TypeError, ValueError, AttributeError, RecursionError):
            raise AssistantError(
                502, "assistant_invalid_output", "The assistant returned an incomplete response."
            ) from None
